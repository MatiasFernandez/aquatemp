# Contributing

## Development setup

Requires Python 3.13 or newer, the minimum of the oldest supported Home Assistant release (see `homeassistant` in [hacs.json](hacs.json)).

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

pre-commit install                                        # run the hooks on every commit
git config blame.ignoreRevsFile .git-blame-ignore-revs   # skip formatting-only commits in git blame
```

`requirements.txt` does not pin `homeassistant`, so pip installs the latest release, which may need a newer Python than the minimum above.

Install pre-commit itself once per machine, for example with `uv tool install pre-commit`, `pipx install pre-commit` or `brew install pre-commit`.

## Quality checks

There is no unit test suite and no build step. Checks run as pre-commit hooks:

- [ruff](https://docs.astral.sh/ruff/) lint and format for Python, configured in [pyproject.toml](pyproject.toml)
- codespell, yamllint, prettier (Markdown, JSON, YAML) and basic file checks

```bash
pre-commit run --all-files                   # everything
pre-commit run ruff-check --files <path>     # one hook on specific files
```

CI additionally runs `hassfest` and the HACS validation action.

When raising the minimum Home Assistant version in `hacs.json`, update `target-version` in `pyproject.toml` to the Python version that release requires.

If a commit only reformats code, add its full SHA to [.git-blame-ignore-revs](.git-blame-ignore-revs).

## Developer scripts

Both scripts import `custom_components` and `utils` as top-level packages, so run them from the repository root with `PYTHONPATH=.`.

### Call the cloud API from the CLI

[tests/api-testing.py](tests/api-testing.py) logs in with the AquaTemp API type, fetches every device on the account and logs its data. It keeps running until stopped with Ctrl+C.

```bash
USERNAME=you@example.com PASSWORD=secret DEBUG=true PYTHONPATH=. python tests/api-testing.py
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
PYTHONPATH=. python utils/parse-resources.py
```

Limitations of the script as it stands:

- File paths use Windows separators (`\\`), so it only finds the XML files on Windows.
- Writing `custom_components/aqua_temp/parameters/entity_description.<device>.json` is commented out. Uncomment it to regenerate the files, or copy the logged output.

## Changelog and releases

- [CHANGELOG.md](CHANGELOG.md) follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Add user-facing changes under `## [Unreleased]`.
- A release commit (`Release X.Y.Z`) moves the Unreleased entries to a dated version section and bumps `version` in [manifest.json](custom_components/aqua_temp/manifest.json).
- When a change diverges from upstream, add a row to the "Differences from upstream" table in [README.md](README.md).
