"""A git checkout holding the integration, for the test-install tools."""

from pathlib import Path
import subprocess

import pytest

MANIFEST = (
    '{\n  "domain": "aqua_temp",\n  "name": "Aqua Temp",\n  "version": "3.5.0"\n}\n'
)


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A checkout with the integration committed, a file outside it, and git ignoring
    __pycache__."""
    repo = tmp_path / "repo"
    package = repo / "custom_components" / "aqua_temp"
    package.mkdir(parents=True)
    (package / "manifest.json").write_text(MANIFEST)
    (package / "__init__.py").write_text("")
    (repo / "README.md").write_text("")
    (repo / ".gitignore").write_text("__pycache__/\n")
    git(repo, "init", "--quiet")
    git(repo, "add", ".")
    git(
        repo,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.com",
        "commit",
        "--quiet",
        "--no-gpg-sign",
        "-m",
        "Initial",
    )
    return repo
