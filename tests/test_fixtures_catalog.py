"""Every fixture is described in fixtures/README.md, and every entry there exists."""

import re

from .conftest import FIXTURES

CATALOG = FIXTURES / "README.md"


def catalogued_files() -> set[str]:
    """Catalogued paths, as <## heading>/<file in a table row's first cell>."""
    files = set()
    folder = None

    for line in CATALOG.read_text().splitlines():
        if line.startswith("## "):
            folder = line.removeprefix("## ").strip()

        match = re.match(r"\|\s*`([^`]+\.json)`", line)

        if match and folder is not None:
            files.add(f"{folder}/{match.group(1)}")

    return files


def test_catalog_matches_fixtures():
    fixtures = {
        path.relative_to(FIXTURES).as_posix() for path in FIXTURES.rglob("*.json")
    }

    assert catalogued_files() == fixtures
