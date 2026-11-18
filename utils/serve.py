"""Serve this checkout's integration on the local network, so Home Assistant can install it.

Packages custom_components/aqua_temp from the working tree, committed or not, stamps its version
with the commit, and serves the package and install.sh until Ctrl-C. It prints the lines to paste
in Home Assistant. See docs/testing-in-home-assistant.md.

    uv run utils/serve.py [--host <ip>] [--port <port>]
"""

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import io
from pathlib import Path
import re
import shutil
import socket
import subprocess
import tarfile
import tempfile

PACKAGE = "custom_components/aqua_temp"
ARCHIVE = "aqua_temp.tar.gz"
INSTALLER = Path(__file__).with_name("install.sh")
RELEASED_INSTALLER = (
    "https://raw.githubusercontent.com/MatiasFernandez/aquatemp/main/utils/install.sh"
)


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout


def package_files(repo: Path) -> list[str]:
    """The integration's files in the working tree: tracked and untracked ones, without those
    git ignores, such as __pycache__."""
    listed = git(
        repo, "ls-files", "-z", "--cached", "--others", "--exclude-standard", PACKAGE
    )
    return sorted(
        {path for path in listed.split("\0") if path and (repo / path).is_file()}
    )


def version_stamp(repo: Path) -> str:
    """The commit, marked dirty when the integration differs from it."""
    commit = git(repo, "rev-parse", "--short", "HEAD").strip()
    dirty = git(repo, "status", "--porcelain", "--", PACKAGE).strip()
    return f"{commit}.dirty" if dirty else commit


def stamp_manifest(manifest: str, stamp: str) -> str:
    """The manifest with stamp as its version's build metadata, replacing any it had."""
    return re.sub(r'("version":\s*"[^"+]*)[^"]*"', rf'\1+{stamp}"', manifest, count=1)


def build_package(repo: Path, destination: Path) -> str:
    """Writes the integration to destination as a .tar.gz with a top folder, as GitHub's
    tarballs have, and returns the stamped version."""
    stamp = version_stamp(repo)
    version = ""
    with tarfile.open(destination, "w:gz") as archive:
        for path in package_files(repo):
            name = f"aquatemp/{path}"
            if path == f"{PACKAGE}/manifest.json":
                manifest = stamp_manifest((repo / path).read_text(), stamp)
                version = re.search(r'"version":\s*"([^"]*)"', manifest)[1]
                data = manifest.encode()
                info = archive.gettarinfo(repo / path, name)
                info.size = len(data)
                archive.addfile(info, io.BytesIO(data))
            else:
                archive.add(repo / path, name)
    return version


def lan_ip() -> str:
    """The address other machines on the network reach this one at. Connecting a UDP socket
    sends nothing; it only picks the interface a packet would leave from."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.connect(("192.0.2.1", 9))
        return probe.getsockname()[0]


def make_server(directory: Path, host: str, port: int) -> ThreadingHTTPServer:
    handler = partial(SimpleHTTPRequestHandler, directory=str(directory))
    return ThreadingHTTPServer((host, port), handler)


def run_installer(installer_url: str, args: str) -> str:
    """A line that downloads install.sh and runs it only if the download succeeded, so a failed
    download stops there instead of looking like an install."""
    return f"wget -O /tmp/aquatemp-install.sh {installer_url} && sh /tmp/aquatemp-install.sh {args}"


def in_container(line: str) -> str:
    """line run from the Home Assistant OS console, in the container that sees the
    configuration, restarting Home Assistant only if it succeeded."""
    return (
        f"docker exec -i homeassistant sh -c '{line} --no-restart' && ha core restart"
    )


def instructions(base_url: str, version: str) -> str:
    install = run_installer(f"{base_url}/install.sh", f"url {base_url}/{ARCHIVE}")
    # From GitHub, so it still works once this stops
    rollback = run_installer(RELEASED_INSTALLER, "rollback")
    return f"""\
Serving version {version} at {base_url}

In the Terminal & SSH add-on, paste:

  {install}

In the Home Assistant OS console, after `login`, paste:

  {in_container(install)}

To put back the copy it replaces, also after this stops, paste in the add-on:

  {rollback}

or in the console:

  {in_container(rollback)}

Anyone on your network can download it while this runs. Ctrl-C to stop."""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", help="the address to serve on (default: the LAN IP)")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    repo = Path(git(INSTALLER.parent, "rev-parse", "--show-toplevel").strip())
    try:
        host = args.host or lan_ip()
    except OSError as error:
        parser.error(
            f"cannot tell this computer's address on the network ({error}); "
            "pass it with --host <this computer's IP>"
        )
    with tempfile.TemporaryDirectory() as staging:
        version = build_package(repo, Path(staging) / ARCHIVE)
        shutil.copy(INSTALLER, staging)
        with make_server(Path(staging), host, args.port) as server:
            print(
                instructions(f"http://{host}:{server.server_port}", version),
                flush=True,
            )
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass


if __name__ == "__main__":
    main()
