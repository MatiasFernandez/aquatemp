# Contributing

Bug reports are as valuable as code: the maintainer has a single heat pump, so they're how problems with other models come to light. Use the [issue forms](https://github.com/MatiasFernandez/aquatemp/issues/new/choose), and [discussions](https://github.com/MatiasFernandez/aquatemp/discussions) for ideas, questions and which heat pumps work.

## Pull requests

Pull requests are welcome. Before opening one:

- Add or update tests for the change wherever possible. The suite runs offline against a mocked cloud (see [Tests](#tests)), so a new profile or a fix for a model usually needs only a fixture and a test. If something can't be tested, say why in the PR.
- Run the [quality checks](#quality-checks) and both test runs; CI runs the same.
- Add user-facing changes to [CHANGELOG.md](CHANGELOG.md) (see [Changelog and releases](#changelog-and-releases)).
- Keep each PR to one change, and explain what it fixes and how you checked it, ideally on a real device.

## Development setup

Requires [uv](https://docs.astral.sh/uv/). It installs the Python in [.python-version](.python-version), the one the latest stable Home Assistant release needs, and the exact dependency versions in [uv.lock](uv.lock). The development environment runs that latest release; the oldest supported one (see `homeassistant` in [hacs.json](hacs.json)) is covered by the [floor tests](#tests).

```bash
uv sync                                                   # create .venv with the integration's and dev dependencies
uv run pre-commit install                                 # run the hooks on every commit
git config blame.ignoreRevsFile .git-blame-ignore-revs   # skip formatting-only commits in git blame
```

Prefix commands with `uv run` (as below), or activate `.venv` to run them directly.

Dependencies are declared in [pyproject.toml](pyproject.toml): `dependencies` for what the integration and developer scripts import, the `dev` group for test and lint tools. Change them with `uv add` / `uv remove` (`--dev` for the group), which also updates `uv.lock`; commit both. Dependabot opens weekly PRs bumping the lock.

The dev group's exact `pytest-homeassistant-custom-component` pin decides the Home Assistant version (and `pytest`, `pytest-asyncio`, `pytest-cov`): each release pins one `homeassistant` release exactly. It tracks the latest stable Home Assistant, and Dependabot bumps it. That only works while `requires-python` is that Home Assistant's minimum Python: Dependabot resolves at the lowest Python `requires-python` allows, and doesn't see plugin releases that need a newer one. When a bump needs a newer Python, raise `requires-python` and [.python-version](.python-version) with it. The oldest supported Home Assistant isn't in the lock (Dependabot couldn't bump the pin otherwise): it has a uv project of its own in [tests/floor/](tests/floor/pyproject.toml), with its own `uv.lock` and `.python-version`. Dependabot only watches the root project, so the floor moves by hand.

## Quality checks

There is no build step. Checks run as pre-commit hooks:

- [ruff](https://docs.astral.sh/ruff/) lint and format for Python, configured in [pyproject.toml](pyproject.toml)
- codespell, yamllint, prettier (Markdown, JSON, YAML) and basic file checks
- [actionlint](https://github.com/rhysd/actionlint) (workflow correctness) and [zizmor](https://docs.zizmor.sh/) (workflow security) for GitHub Actions. Pin third-party actions to a commit SHA with a `# vX.Y.Z` comment; Dependabot keeps both updated.

```bash
uv run pre-commit run --all-files                   # everything
uv run pre-commit run ruff-check --files <path>     # one hook on specific files
```

CI additionally runs the [tests](#tests), `hassfest` and the HACS validation action.

The oldest supported Home Assistant (the floor) and the latest one stay at most 12 months apart, Home Assistant's minimum deprecation window. Testing both covers the two ends of the supported range, not the releases between them. Raise the floor when the latest moves further ahead. To raise it:

- `homeassistant` in [hacs.json](hacs.json), and the `homeassistant` lower bound in [pyproject.toml](pyproject.toml) (then `uv lock`).
- [tests/floor/pyproject.toml](tests/floor/pyproject.toml): the `pytest-homeassistant-custom-component` release pinning the new floor exactly; check whether the `pycares` constraint is still needed. Then `uv lock` in `tests/floor/`.
- If the floor's minimum Python changed: ruff's `target-version` in [pyproject.toml](pyproject.toml), and `requires-python` and `.python-version` in `tests/floor/` (before `uv lock`).
- Fallbacks kept for older releases. Once the floor reaches 2026.8.0, `async_get_ha_device` in [common/device_lookup.py](custom_components/aqua_temp/common/device_lookup.py) can drop its `async_get_device` fallback.
- [CHANGELOG.md](CHANGELOG.md): users on older Home Assistant releases can no longer install it.

If a commit only reformats code, add its full SHA to [.git-blame-ignore-revs](.git-blame-ignore-revs).

## Tests

[pytest](https://docs.pytest.org/) runs offline against a mocked cloud ([aioresponses](https://github.com/pnuckowski/aioresponses)), driving the cloud library's real API client and profiles through a full update cycle. Any request without a registered response fails the test, so nothing reaches the real cloud.

The tests follow the cloud library boundary:

- [tests/cloud/](tests/cloud/) tests the cloud library alone. Like the library, it must not import Home Assistant or the integration; its [ruff.toml](tests/cloud/ruff.toml) bans Home Assistant and the integration's modules one by one, but not the integration package itself. Home Assistant still has to be installed: importing `custom_components.aqua_temp.cloud` runs the integration's `__init__.py` first. The mocked cloud lives there too, in [mock_cloud.py](tests/cloud/mock_cloud.py), which the root [conftest.py](tests/conftest.py) registers as a pytest plugin, so the integration tests get the same fixtures.
- [tests/integration/](tests/integration/) tests the integration side. [test_integration.py](tests/integration/test_integration.py) sets up a config entry on a real Home Assistant from [pytest-homeassistant-custom-component](https://github.com/MatthewFlamm/pytest-homeassistant-custom-component) (its `hass` fixture), against the mocked cloud: entities, the device registry, climate services and diagnostics.

```bash
uv run pytest                                             # everything
uv run pytest tests/cloud/test_fetch_data.py -k protocol  # one file, tests matching a name
uv run pytest --cov                                       # with a coverage report (add --cov-report=html for htmlcov/)
```

`uv run pytest` runs on the latest Home Assistant, from the lock. To run the suite on the oldest supported one, from the [tests/floor/](tests/floor/pyproject.toml) project (its own lock and `.venv`, and that release's Python), still from the repository root:

```bash
uv run --project tests/floor --locked pytest
```

CI runs both, and both must pass. Both upload coverage and test results to [Codecov](https://codecov.io/gh/MatiasFernandez/aquatemp), flagged `latest` and `floor`. It merges the two, so code only one of them runs (a fallback for older Home Assistant releases) still counts as covered, and comments on pull requests with the coverage of the changed lines and any failing tests.

Fixtures live in [tests/cloud/fixtures/](tests/cloud/fixtures/), one folder per API type, and are catalogued in its [README](tests/cloud/fixtures/README.md). List new fixtures there; a test fails otherwise.

- Top-level files are real responses recorded from a device, merged and sanitised (device code replaced, metadata dropped). The maintainer regenerates them from private probe recordings; don't edit them by hand.
- Files under `synthetic/` are written by hand for endpoints that were never recorded.

### Mutation testing

[mutmut](https://mutmut.readthedocs.io/) checks that the tests catch changes to the code: it applies small edits (mutants) to the modules in `source_paths` under `[tool.mutmut]` in [pyproject.toml](pyproject.toml), and runs the tests covering each one. Run it on demand, not in CI, when adding or reviewing tests.

```bash
uv run mutmut run                  # every mutant, results kept in mutants/ for the next commands
uv run mutmut results              # mutants that no test caught
uv run mutmut show <mutant>        # the diff of one
uv run mutmut browse               # the same, interactively
```

A surviving mutant is a change the tests don't notice. Some are harmless: log messages, or edits that don't change behaviour. The rest point at a missing assertion or test. Delete `mutants/` to start over after changing the configuration.

## Developer scripts

Both scripts import `custom_components` and `utils` as top-level packages, so run them from the repository root with `PYTHONPATH=.`.

### Call the cloud API from the CLI

[utils/api-testing.py](utils/api-testing.py) logs in with the AquaTemp API type, fetches every device on the account, logs its data and exits.

```bash
USERNAME=you@example.com PASSWORD=secret DEBUG=true PYTHONPATH=. uv run python utils/api-testing.py
```

| Environment variable | Default | Description                       |
| -------------------- | ------- | --------------------------------- |
| `USERNAME`           | -       | Aqua Temp account username        |
| `PASSWORD`           | -       | Aqua Temp account password        |
| `DEBUG`              | `False` | `True` enables DEBUG-level output |

The API allows one login per account at a time, so running the script logs out the mobile app or Home Assistant session using the same account.

### Generate entity descriptions from the app resources

[utils/parse-resources.py](utils/parse-resources.py) reads the parameter names from each device's `utils/devices/<device>/resources.xml`, which is extracted from the mobile app. It maps them with that device's `consts.py`, and logs the resulting entity descriptions and translation keys.

```bash
PYTHONPATH=. uv run python utils/parse-resources.py
```

Limitations of the script as it stands:

- File paths use Windows separators (`\\`), so it only finds the XML files on Windows.
- Writing `custom_components/aqua_temp/cloud/profiles/entity_description.<device>.json` is commented out. Uncomment it to regenerate the files, or copy the logged output.

## Changelog and releases

- [CHANGELOG.md](CHANGELOG.md) follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Add user-facing changes under `## [Unreleased]`.
- A release commit (`Release X.Y.Z`) moves the Unreleased entries to a dated version section and bumps `version` in [manifest.json](custom_components/aqua_temp/manifest.json).
- When a change is also proposed upstream, link the upstream PR from its changelog entry. When an upstream merge brings in a change this fork already had, note it in the changelog.
