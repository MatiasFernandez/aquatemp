# Testing a change in Home Assistant

You can install a version of the integration that isn't released yet on your own Home Assistant: a pull request someone asked you to try, or a change you're working on. It replaces the installed copy until you go back to a release.

- [Try a pull request](#try-a-pull-request)
- [Test your own change](#test-your-own-change)
- [Go back to a release](#go-back-to-a-release)

Everything here runs [`utils/install.sh`](../utils/install.sh). It downloads the version and checks it holds the integration before it touches the installed copy, so a failed download changes nothing. It saves the copy it replaces as `aqua_temp.bak` in your configuration folder, and restarts Home Assistant when it can.

## Try a pull request

You need a shell on Home Assistant. The easiest one is the **Terminal & SSH** add-on: in Home Assistant OS, Settings → Add-ons → Add-on store, install it, start it, and open its web UI.

Paste this line, with the pull request's number in place of `51`:

```sh
wget -O /tmp/aquatemp-install.sh https://raw.githubusercontent.com/MatiasFernandez/aquatemp/main/utils/install.sh && sh /tmp/aquatemp-install.sh pr 51
```

Home Assistant restarts with the pull request installed. Settings → Devices & Services → Aqua Temp shows its version with `+pr51.<commit>` at the end, and so does a diagnostics download, which tells whoever reads it what you were running.

When you're done, [go back to a release](#go-back-to-a-release). Install it again to pick up new commits on the pull request; the commit in the version tells which one you have.

To install a branch, a tag or a commit instead, replace `pr 51` with `ref <name>`. For a branch on someone's fork, add `--repo <owner>/aquatemp`.

**From the Home Assistant OS console** instead of the add-on (the machine's screen, or your hypervisor's console): type `login` at the `ha >` prompt, then paste:

```sh
docker exec -i homeassistant sh -c 'wget -O /tmp/aquatemp-install.sh https://raw.githubusercontent.com/MatiasFernandez/aquatemp/main/utils/install.sh && sh /tmp/aquatemp-install.sh pr 51 --no-restart' && ha core restart
```

**On Home Assistant Container or Core**, run the first line in any shell that can see the configuration folder, adding `--config <path to it>`, and restart Home Assistant yourself.

## Test your own change

From your checkout of the repository, on a computer on the same network as Home Assistant:

```sh
uv run utils/serve.py
```

It packages your working copy of `custom_components/aqua_temp`, including changes you haven't committed, and serves it with `install.sh` until you press Ctrl-C. It prints the lines to paste, for the add-on and for the console, with your computer's address in them, and the lines to go back. The installed version ends with `+<commit>`, and `.dirty` when it holds uncommitted changes.

After each change, stop it, run it again and paste the install line again.

- If it picks the wrong address, pass `--host <your computer's IP>`; `--port` changes the port from 8000.
- Run it only on a network you trust: anyone on it can download the package while it runs. Your computer's firewall may ask you to let Python accept connections the first time.
- It serves your copy of `install.sh`, so a change to the script tests itself.

## Go back to a release

If you installed the integration with HACS, open Aqua Temp in HACS, choose ⋮ → Redownload, pick the version you had, and restart Home Assistant. HACS deletes the folder before downloading, so nothing from the test version is left.

Otherwise, put back the copy the last install replaced. In the Terminal & SSH add-on:

```sh
wget -O /tmp/aquatemp-install.sh https://raw.githubusercontent.com/MatiasFernandez/aquatemp/main/utils/install.sh && sh /tmp/aquatemp-install.sh rollback
```

From the Home Assistant OS console, after `login`:

```sh
docker exec -i homeassistant sh -c 'wget -O /tmp/aquatemp-install.sh https://raw.githubusercontent.com/MatiasFernandez/aquatemp/main/utils/install.sh && sh /tmp/aquatemp-install.sh rollback --no-restart' && ha core restart
```

Only one copy is kept: installing twice in a row saves the first test version, not the release.
