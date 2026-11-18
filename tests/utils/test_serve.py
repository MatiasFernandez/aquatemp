"""Packaging a checkout's integration and serving it to Home Assistant."""

import json
from pathlib import Path
import socket
import tarfile
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.loader import Integration
from tests.utils.conftest import git
from utils.serve import build_package, instructions, main


def packaged(archive: Path) -> dict[str, bytes]:
    with tarfile.open(archive) as tar:
        return {
            member.name: tar.extractfile(member).read()
            for member in tar.getmembers()
            if member.isfile()
        }


def packaged_version(archive: Path) -> str:
    manifest = packaged(archive)["aquatemp/custom_components/aqua_temp/manifest.json"]
    return json.loads(manifest)["version"]


def test_package_holds_the_integrations_files_committed_or_not(
    repo: Path, tmp_path: Path
):
    package = repo / "custom_components" / "aqua_temp"
    (package / "new.py").write_text("")
    (package / "__pycache__").mkdir()
    (package / "__pycache__" / "new.cpython-314.pyc").write_text("")

    build_package(repo, tmp_path / "package.tar.gz")

    assert sorted(packaged(tmp_path / "package.tar.gz")) == [
        "aquatemp/custom_components/aqua_temp/__init__.py",
        "aquatemp/custom_components/aqua_temp/manifest.json",
        "aquatemp/custom_components/aqua_temp/new.py",
    ]


def test_package_leaves_out_deleted_files(repo: Path, tmp_path: Path):
    (repo / "custom_components" / "aqua_temp" / "__init__.py").unlink()

    build_package(repo, tmp_path / "package.tar.gz")

    assert sorted(packaged(tmp_path / "package.tar.gz")) == [
        "aquatemp/custom_components/aqua_temp/manifest.json",
    ]


def test_package_version_names_the_commit(repo: Path, tmp_path: Path):
    commit = git(repo, "rev-parse", "--short", "HEAD").strip()

    version = build_package(repo, tmp_path / "package.tar.gz")

    assert (version, packaged_version(tmp_path / "package.tar.gz")) == (
        f"3.5.0+{commit}",
        f"3.5.0+{commit}",
    )


def test_package_version_marks_uncommitted_changes(repo: Path, tmp_path: Path):
    commit = git(repo, "rev-parse", "--short", "HEAD").strip()
    (repo / "custom_components" / "aqua_temp" / "__init__.py").write_text("# changed")

    version = build_package(repo, tmp_path / "package.tar.gz")

    assert version == f"3.5.0+{commit}.dirty"


def test_package_version_ignores_changes_outside_the_integration(
    repo: Path, tmp_path: Path
):
    commit = git(repo, "rev-parse", "--short", "HEAD").strip()
    (repo / "README.md").write_text("changed")

    version = build_package(repo, tmp_path / "package.tar.gz")

    assert version == f"3.5.0+{commit}"


# The shapes serve.py and install.sh stamp: a commit, a dirty one, a pull request's commit
@pytest.mark.parametrize(
    "version",
    [
        "3.5.0+1a2b3c4",
        "3.5.0+1a2b3c4.dirty",
        "3.5.0+pr51.1a2b3c4",
    ],
)
async def test_home_assistant_loads_a_stamped_version(
    hass: HomeAssistant, tmp_path: Path, version: str
):
    package = tmp_path / "aqua_temp"
    package.mkdir()
    (package / "manifest.json").write_text(
        json.dumps({"domain": "aqua_temp", "name": "Aqua Temp", "version": version})
    )
    root = SimpleNamespace(__name__="custom_components", __path__=[str(tmp_path)])

    integration = Integration.resolve_from_root(hass, root, "aqua_temp")

    assert integration is not None


def test_instructions_name_the_server():
    assert instructions("http://192.0.2.10:8000", "3.5.0+1a2b3c4") == (
        """\
Serving version 3.5.0+1a2b3c4 at http://192.0.2.10:8000

In the Terminal & SSH add-on, paste:

  wget -O /tmp/aquatemp-install.sh http://192.0.2.10:8000/install.sh && sh /tmp/aquatemp-install.sh url http://192.0.2.10:8000/aqua_temp.tar.gz

In the Home Assistant OS console, after `login`, paste:

  docker exec -i homeassistant sh -c 'wget -O /tmp/aquatemp-install.sh http://192.0.2.10:8000/install.sh && sh /tmp/aquatemp-install.sh url http://192.0.2.10:8000/aqua_temp.tar.gz --no-restart' && ha core restart

To put back the copy it replaces, also after this stops, paste in the add-on:

  wget -O /tmp/aquatemp-install.sh https://raw.githubusercontent.com/MatiasFernandez/aquatemp/main/utils/install.sh && sh /tmp/aquatemp-install.sh rollback

or in the console:

  docker exec -i homeassistant sh -c 'wget -O /tmp/aquatemp-install.sh https://raw.githubusercontent.com/MatiasFernandez/aquatemp/main/utils/install.sh && sh /tmp/aquatemp-install.sh rollback --no-restart' && ha core restart

Anyone on your network can download it while this runs. Ctrl-C to stop."""
    )


def test_without_a_network_it_asks_for_the_host(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    socket_enabled: None,
):
    monkeypatch.setattr("sys.argv", ["serve.py"])

    with (
        patch.object(
            socket.socket,
            "connect",
            autospec=True,
            side_effect=OSError("Network is unreachable"),
        ),
        pytest.raises(SystemExit) as exit_info,
    ):
        main()

    assert exit_info.value.code != 0
    assert "--host <this computer's IP>" in capsys.readouterr().err
