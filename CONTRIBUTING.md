# Contributing

## Development setup

Requires [uv](https://docs.astral.sh/uv/). It installs the Python in [.python-version](.python-version), the minimum of the oldest supported Home Assistant release (see `homeassistant` in [hacs.json](hacs.json)), and the exact dependency versions in [uv.lock](uv.lock).

```bash
uv sync                                                   # create .venv with the integration's and dev dependencies
uv run pre-commit install                                 # run the hooks on every commit
git config blame.ignoreRevsFile .git-blame-ignore-revs   # skip formatting-only commits in git blame
```

Prefix commands with `uv run` (as below), or activate `.venv` to run them directly.

Dependencies are declared in [pyproject.toml](pyproject.toml): `dependencies` for what the integration and developer scripts import, the `dev` group for test and lint tools. Change them with `uv add` / `uv remove` (`--dev` for the group), which also updates `uv.lock`; commit both. Dependabot opens weekly PRs bumping the lock.

`uv.lock` resolves `homeassistant` per Python version, so the 3.13 environment gets the newest Home Assistant release that still supports 3.13, not the latest one.

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

When raising the minimum Home Assistant version in `hacs.json`, update to match in [pyproject.toml](pyproject.toml): the `homeassistant` lower bound, `requires-python` and ruff's `target-version`, plus [.python-version](.python-version). Then run `uv lock`.

If a commit only reformats code, add its full SHA to [.git-blame-ignore-revs](.git-blame-ignore-revs).

## Tests

[pytest](https://docs.pytest.org/) runs offline against a mocked cloud ([aioresponses](https://github.com/pnuckowski/aioresponses)), driving the real config manager and API client through a full update cycle. Any request without a registered response fails the test, so nothing reaches the real cloud.

```bash
uv run pytest                                    # everything
uv run pytest tests/test_fetch_data.py -k shape  # one file, tests matching a name
```

Fixtures live in [tests/fixtures/](tests/fixtures/), one folder per API type, and are catalogued in its [README](tests/fixtures/README.md). List new fixtures there; a test fails otherwise.

- Top-level files are real responses recorded from a device, merged and sanitised (device code replaced, metadata dropped). The maintainer regenerates them from private probe recordings; don't edit them by hand.
- Files under `synthetic/` are written by hand for endpoints that were never recorded.

## Developer scripts

Both scripts import `custom_components` and `utils` as top-level packages, so run them from the repository root with `PYTHONPATH=.`.

### Call the cloud API from the CLI

[utils/api-testing.py](utils/api-testing.py) logs in with the AquaTemp API type, fetches every device on the account and logs its data. It keeps running until stopped with Ctrl+C.

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
- Writing `custom_components/aqua_temp/parameters/entity_description.<device>.json` is commented out. Uncomment it to regenerate the files, or copy the logged output.

## Changelog and releases

- [CHANGELOG.md](CHANGELOG.md) follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Add user-facing changes under `## [Unreleased]`.
- A release commit (`Release X.Y.Z`) moves the Unreleased entries to a dated version section and bumps `version` in [manifest.json](custom_components/aqua_temp/manifest.json).
- When a change is also proposed upstream, link the upstream PR from its changelog entry. When an upstream merge brings in a change this fork already had, note it in the changelog.
