"""Fail an integration test when Home Assistant reports deprecated usage by aqua_temp.

Home Assistant only logs deprecated usage by a custom integration, so tests would pass
silently until a release removes the API. These are the reports about this integration,
by where they come from:
- the frame helper, on its own logger: "Detected that custom integration 'aqua_temp' ..."
  (deprecated attribute writes, calls, ...), raised with the integration's frame;
- the entity deprecation helpers, on the integration module's logger: "Detected code
  that ..." when no integration frame is found, and "<module>::<Class> provides the
  deprecated <name>" at class-definition time.
Anything else logged (other integrations, libraries) is none of our business.

Home Assistant reports each call site once and the harness clears that between tests
(the latest one also clears the entity helpers' record), so every test that triggers a
report fails. The class-definition report is logged once per process, when the module is
first imported, so only the test that happens to import it sees that one.

A report during setup or the test body fails the test; one during teardown makes pytest
show an error in teardown. A deprecation that can't be fixed right away goes in
ACCEPTED_DEPRECATIONS: its reports become pytest warnings instead. A full run of the
integration tests fails if an entry no longer matches any report, so fixed ones get
removed.
"""

from dataclasses import dataclass
import logging
from pathlib import Path
import re
import warnings

import pytest


@dataclass(frozen=True)
class AcceptedDeprecation:
    """A deprecation report to tolerate until it's fixed."""

    match: str
    """Text the report contains, e.g. "AquaTempClimateEntity._attr_temperature_unit"."""
    reason: str
    """Why it isn't fixed yet, and what fixing it involves."""


# Keep this empty unless a deprecation needs more work than the change that found it.
ACCEPTED_DEPRECATIONS: list[AcceptedDeprecation] = []


class AcceptedDeprecationWarning(UserWarning):
    """A deprecation report matching an entry of ACCEPTED_DEPRECATIONS."""


_OWN_LOGGER = "custom_components.aqua_temp"
_FRAME_REPORT = re.compile(r"Detected that custom integration 'aqua_temp' ")
_ENTITY_REPORT = re.compile(r"Detected code that |provides the deprecated ")
_INTEGRATION_TESTS = Path(__file__).resolve().parent
_HOW_TO_FIX = (
    "Fix it in the integration. If it needs more work than this change (e.g. it "
    "appeared with a Home Assistant bump), add an AcceptedDeprecation with the reason "
    "to ACCEPTED_DEPRECATIONS in tests/integration/deprecation_reports.py and track "
    "the fix."
)

_reports = pytest.StashKey[list[str]]()
_matched = pytest.StashKey[set[AcceptedDeprecation]]()
_warned = pytest.StashKey[set[str]]()
_stale = pytest.StashKey[set[AcceptedDeprecation]]()
_ran = pytest.StashKey[set[str]]()
_partial = pytest.StashKey[bool]()


class _DeprecationReports(logging.Handler):
    def __init__(self, reports: list[str]) -> None:
        super().__init__(logging.WARNING)
        self.reports = reports

    def emit(self, record: logging.LogRecord) -> None:
        message = record.getMessage()
        own_module = record.name == _OWN_LOGGER or record.name.startswith(
            f"{_OWN_LOGGER}."
        )
        if (
            record.name == "homeassistant.helpers.frame"
            and _FRAME_REPORT.match(message)
        ) or (own_module and _ENTITY_REPORT.search(message)):
            self.reports.append(message)


def _accepted_by(message: str) -> AcceptedDeprecation | None:
    return next((a for a in ACCEPTED_DEPRECATIONS if a.match in message), None)


@pytest.fixture(autouse=True)
def home_assistant_deprecation_reports(request: pytest.FixtureRequest):
    """Collects the deprecation reports about this integration while the test runs,
    teardown included; `pytest_runtest_makereport` acts on them."""
    reports = request.node.stash.setdefault(_reports, [])
    handler = _DeprecationReports(reports)
    root = logging.getLogger()
    root.addHandler(handler)

    yield

    root.removeHandler(handler)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo):
    report = yield

    if call.when == "teardown":
        item.config.stash.setdefault(_ran, set()).add(item.nodeid)
    # Setup's reports wait for the test body, so a test fails rather than errors
    if call.when == "setup" and report.passed:
        return report

    reports = item.stash.get(_reports, [])
    distinct = list(dict.fromkeys(reports))
    reports.clear()
    unaccepted = []
    for message in distinct:
        if accepted := _accepted_by(message):
            item.config.stash.setdefault(_matched, set()).add(accepted)
            # Once per run, on the first test reporting it, not once per test
            warned = item.config.stash.setdefault(_warned, set())
            if message in warned:
                continue
            warned.add(message)
            warnings.warn_explicit(
                f"{message} (accepted: {accepted.reason})",
                AcceptedDeprecationWarning,
                filename=str(item.path),
                lineno=item.location[1] or 0,
            )
        else:
            unaccepted.append(message)

    if unaccepted and report.passed:
        listed = "\n".join(f"  - {message}" for message in unaccepted)
        report.outcome = "failed"
        report.longrepr = (
            "Home Assistant reported deprecated usage by the aqua_temp integration:\n"
            f"{listed}\n{_HOW_TO_FIX}"
        )

    return report


def pytest_deselected(items: list[pytest.Item]) -> None:
    if any(_INTEGRATION_TESTS in item.path.parents for item in items):
        items[0].config.stash[_partial] = True


@pytest.hookimpl(tryfirst=True)
def pytest_sessionfinish(session: pytest.Session) -> None:
    """Fail a full run of the integration tests on entries matching no report."""
    config = session.config
    collected = [
        item for item in session.items if _INTEGRATION_TESTS in item.path.parents
    ]
    # A partial run may skip the tests that would match. Every test file must have been
    # collected (not the case for a file argument, --ignore, --lf skipping files, or the
    # xdist controller, which collects nothing), no test deselected inside them (-k, -m,
    # --deselect), and every collected test run (not stopped early by -x)
    full_run = (
        set(_INTEGRATION_TESTS.rglob("test_*.py")) <= {item.path for item in collected}
        and not config.stash.get(_partial, False)
        and {item.nodeid for item in collected} <= config.stash.get(_ran, set())
    )
    stale = set(ACCEPTED_DEPRECATIONS) - config.stash.get(_matched, set())
    if not full_run or not stale:
        return

    config.stash[_stale] = stale
    session.exitstatus = pytest.ExitCode.TESTS_FAILED


def pytest_terminal_summary(terminalreporter, config: pytest.Config) -> None:
    if not (stale := config.stash.get(_stale, None)):
        return

    terminalreporter.section("stale accepted deprecations", red=True)
    terminalreporter.write_line(
        "No report matched these ACCEPTED_DEPRECATIONS entries in "
        "tests/integration/deprecation_reports.py, so the run fails. The deprecation "
        "was fixed or Home Assistant stopped reporting it: remove the entry."
    )
    for accepted in stale:
        terminalreporter.write_line(f"  - {accepted.match!r}: {accepted.reason}")
