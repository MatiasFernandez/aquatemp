"""Installing a test build on Home Assistant with install.sh, against a local server."""

from collections.abc import Iterator
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import threading

import pytest

from utils.serve import build_package, make_server

INSTALL = Path(__file__).parents[2] / "utils" / "install.sh"
RELEASE = {"domain": "aqua_temp", "name": "Aqua Temp", "version": "3.4.2"}

pytestmark = pytest.mark.skipif(
    shutil.which("sh") is None, reason="install.sh needs a POSIX shell"
)


def serve_as_github(staging: Path, repo: str, ref: str) -> None:
    """The checkout's package where GitHub serves ref's legacy tarball, in a top folder
    named after the repository and the commit, as GitHub names it."""
    path = staging / repo / "legacy.tar.gz" / ref
    path.parent.mkdir(parents=True)
    top = f"{repo.replace('/', '-')}-1a2b3c4"
    with (
        tarfile.open(staging / "aqua_temp.tar.gz") as source,
        tarfile.open(path, "w:gz") as archive,
    ):
        for member in source.getmembers():
            data = source.extractfile(member)
            member.name = member.name.replace("aquatemp/", f"{top}/", 1)
            archive.addfile(member, data)


@pytest.fixture
def staging(repo: Path, tmp_path: Path) -> Path:
    """What the server serves: the checkout's package, and the same package where
    GitHub serves a pull request and a branch from."""
    staging = tmp_path / "staging"
    staging.mkdir()
    build_package(repo, staging / "aqua_temp.tar.gz")
    (staging / "not-a-tarball.txt").write_text("hello")
    with tarfile.open(staging / "empty.tar.gz", "w:gz") as archive:
        archive.add(repo / "README.md", "aquatemp/README.md")
    for ref in ["refs/pull/51/head", "fix/auto-mode"]:
        serve_as_github(staging, "MatiasFernandez/aquatemp", ref)
    return staging


@pytest.fixture
def server(staging: Path, socket_enabled: None) -> Iterator[str]:
    """A server on 127.0.0.1, the only host the Home Assistant test plugin lets tests
    reach."""
    with make_server(staging, "127.0.0.1", 0) as server:
        thread = threading.Thread(
            target=server.serve_forever, kwargs={"poll_interval": 0.01}
        )
        thread.start()
        yield f"http://127.0.0.1:{server.server_port}"
        server.shutdown()
        thread.join()


@pytest.fixture
def config(tmp_path: Path) -> Path:
    """A Home Assistant configuration folder with a release installed."""
    config = tmp_path / "config"
    installed = config / "custom_components" / "aqua_temp"
    installed.mkdir(parents=True)
    (config / "configuration.yaml").write_text("")
    (installed / "manifest.json").write_text(json.dumps(RELEASE))
    (installed / "removed_in_the_build.py").write_text("")
    return config


def install(config: Path, server: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["sh", str(INSTALL), *args, "--config", str(config), "--no-restart"],
        capture_output=True,
        text=True,
        env={**os.environ, "AQUATEMP_CODELOAD": server},
        check=False,
    )


def files(folder: Path) -> list[str]:
    return sorted(path.name for path in folder.iterdir())


def version(folder: Path) -> str:
    return json.loads((folder / "manifest.json").read_text())["version"]


def test_installs_the_served_build(config: Path, server: str, repo: Path):
    installed = config / "custom_components" / "aqua_temp"

    result = install(config, server, "url", f"{server}/aqua_temp.tar.gz")

    assert result.returncode == 0, result.stderr
    assert files(installed) == ["__init__.py", "manifest.json"]
    assert (installed / "manifest.json").read_text() == (
        (repo / "custom_components" / "aqua_temp" / "manifest.json")
        .read_text()
        .replace("3.5.0", version(installed))
    )


def test_installs_where_nothing_is_installed_yet(tmp_path: Path, server: str):
    config = tmp_path / "fresh-config"
    config.mkdir()
    (config / "configuration.yaml").write_text("")

    result = install(config, server, "url", f"{server}/aqua_temp.tar.gz")

    assert result.returncode == 0, result.stderr
    assert files(config / "custom_components" / "aqua_temp") == [
        "__init__.py",
        "manifest.json",
    ]
    assert "aqua_temp.bak" not in files(config)


def test_saves_the_copy_it_replaces(config: Path, server: str):
    install(config, server, "url", f"{server}/aqua_temp.tar.gz")

    assert version(config / "aqua_temp.bak") == "3.4.2"
    assert files(config / "aqua_temp.bak") == [
        "manifest.json",
        "removed_in_the_build.py",
    ]


def test_rollback_puts_back_the_replaced_copy(config: Path, server: str):
    install(config, server, "url", f"{server}/aqua_temp.tar.gz")

    result = install(config, server, "rollback")

    assert result.returncode == 0, result.stderr
    assert files(config / "custom_components" / "aqua_temp") == [
        "manifest.json",
        "removed_in_the_build.py",
    ]


def test_rollback_without_a_saved_copy_fails(config: Path, server: str):
    result = install(config, server, "rollback")

    assert result.returncode != 0
    assert version(config / "custom_components" / "aqua_temp") == "3.4.2"


@pytest.mark.parametrize(
    ("args", "stamped"),
    [
        (["pr", "51"], "3.5.0+pr51.1a2b3c4"),
        (["ref", "fix/auto-mode"], "3.5.0+1a2b3c4"),
    ],
    ids=["pull request", "branch"],
)
def test_installs_from_github_stamping_what_it_installed(
    config: Path, server: str, args: list[str], stamped: str
):
    result = install(config, server, *args)

    assert result.returncode == 0, result.stderr
    assert version(config / "custom_components" / "aqua_temp") == stamped


def test_installs_a_fork_s_branch(config: Path, server: str, staging: Path):
    serve_as_github(staging, "someone/aquatemp", "main")

    result = install(config, server, "ref", "main", "--repo", "someone/aquatemp")

    assert result.returncode == 0, result.stderr
    assert version(config / "custom_components" / "aqua_temp") == "3.5.0+1a2b3c4"


@pytest.mark.parametrize(
    "args",
    [
        ["pr", "999"],
        ["url", "{server}/missing.tar.gz"],
        ["url", "{server}/not-a-tarball.txt"],
        ["url", "{server}/empty.tar.gz"],
    ],
    ids=["missing pull request", "missing file", "not a tarball", "no integration"],
)
def test_a_failed_download_changes_nothing(config: Path, server: str, args: list[str]):
    result = install(config, server, *(arg.format(server=server) for arg in args))

    assert result.returncode != 0
    assert "nothing was changed" in result.stderr
    assert files(config) == ["configuration.yaml", "custom_components"]
    assert files(config / "custom_components" / "aqua_temp") == [
        "manifest.json",
        "removed_in_the_build.py",
    ]


def lock(file: Path) -> None:
    """Makes file unreadable, so copying the folder holding it fails partway."""
    file.write_text("")
    file.chmod(0)


cannot_lock = pytest.mark.skipif(
    os.geteuid() == 0, reason="root reads files whatever their permissions"
)


@cannot_lock
def test_a_failed_save_keeps_the_saved_copy_and_the_installed_one(
    config: Path, server: str
):
    installed = config / "custom_components" / "aqua_temp"
    saved = config / "aqua_temp.bak"
    saved.mkdir()
    (saved / "manifest.json").write_text(json.dumps({**RELEASE, "version": "3.3.0"}))
    lock(installed / "unreadable.py")

    result = install(config, server, "url", f"{server}/aqua_temp.tar.gz")

    assert result.returncode != 0
    assert files(config) == ["aqua_temp.bak", "configuration.yaml", "custom_components"]
    assert (version(saved), version(installed)) == ("3.3.0", "3.4.2")


@cannot_lock
def test_a_failed_rollback_keeps_the_installed_copy(config: Path, server: str):
    install(config, server, "url", f"{server}/aqua_temp.tar.gz")
    lock(config / "aqua_temp.bak" / "unreadable.py")

    result = install(config, server, "rollback")

    assert result.returncode != 0
    assert files(config / "custom_components" / "aqua_temp") == [
        "__init__.py",
        "manifest.json",
    ]


@pytest.mark.parametrize(
    "args",
    [[], ["pr", "abc"], ["ref"], ["rollback", "now"], ["upgrade"], ["--force"]],
    ids=[
        "nothing",
        "pr not a number",
        "ref without a value",
        "rollback with a value",
        "unknown command",
        "unknown option",
    ],
)
def test_refuses_bad_arguments(config: Path, server: str, args: list[str]):
    result = install(config, server, *args)

    assert result.returncode != 0
    assert version(config / "custom_components" / "aqua_temp") == "3.4.2"


def test_refuses_a_folder_without_a_configuration(tmp_path: Path, server: str):
    folder = tmp_path / "not-a-config"
    folder.mkdir()

    result = install(folder, server, "url", f"{server}/aqua_temp.tar.gz")

    assert (result.returncode, files(folder)) == (1, [])
