# Contributing

Bug reports are as valuable as code: the maintainer has a single heat pump, so they're how problems with other models come to light. Use the [issue forms](https://github.com/MatiasFernandez/aquatemp/issues/new/choose), and [discussions](https://github.com/MatiasFernandez/aquatemp/discussions) for ideas, questions and which heat pumps work.

## Pull requests

Pull requests are welcome, also from heat pump owners who don't usually write code: a change you have run on your own heat pump is worth a lot here, even if an AI tool helped you write it. Before opening one:

- Add or update tests for the change wherever possible. The suite runs offline against a mocked cloud (see [Tests](#tests)), so a new profile or a fix for a model usually needs only a fixture and a test. If something can't be tested, say why in the PR.
- Run the [quality checks](#quality-checks) and both test runs; CI runs the same.
- Add user-facing changes to [CHANGELOG.md](CHANGELOG.md) (see [Changelog and releases](#changelog-and-releases)).
- Keep each PR to one change.

Fill in the [pull request template](.github/pull_request_template.md): why the change is needed, what you tested by hand and on which setup (ideally in your own Home Assistant, on your heat pump), and anything a reviewer can't get from the diff, such as decisions you took and why.

AI tools are welcome. Say in the PR what they did and what you did yourself; a tool name or a `Co-Authored-By` line alone doesn't tell a reviewer much. Make sure you have run the change and understand it, and answer review questions in your own words.

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

## Device profiles

What the integration polls and controls on a heat pump comes from JSON files in [cloud/profiles/](custom_components/aqua_temp/cloud/profiles/). Each product gets a mapping (`mapping.<level>.json`: the code behind each role, such as mode, power and each mode's target temperature) and a catalog (`entity_description.<level>.json`: the parameters to poll, and the entity each one with a platform becomes). Both resolve through three levels, each one optional except the last:

1. the product, `<product id>`
2. its class, from [classes.json](custom_components/aqua_temp/cloud/profiles/classes.json). `pool_heat_pump` holds the 30 product ids the official app handles as one group, requesting the same 45 codes and 10 bit codes for all of them; they are inferred to be heat pumps from those codes, and pool ones from the app showing them with its swimming pool page and image. `pool_heat_pump` ships a catalog, a delta adding the bits the official app reads for the class; no class has a mapping file yet.
3. `default`, which must have both files, complete

A file is either complete, replacing everything below it, or a delta holding only its differences from the level below. A delta names the level it applies on in `inherits`: the nearest level below it with a file of its kind. For a product in a class without that file, that's `default`; once the class gets one, the product's delta fails to load until it names the class, so whoever adds the class file checks that each delta on it still holds. Prefer a delta for a product that differs from its class or `default` in a few entries, so fixes to the level below still reach it.

- A catalog is complete as an array of entries. As an object it's a delta: `remove` lists the keys of inherited entries to drop, and each of `entries` replaces the inherited entry with the same `key` whole, keeping its place, or is appended after the inherited ones.
- A mapping is complete as an object without `inherits`. With it, it's a delta, merged into the one below key by key, nested objects included. `null` removes the key at any depth: in `hvac_modes` or `fan_modes` it drops a mode, and for an optional role such as `current_temperature` it means the product has no code for it. The resolved mapping must still give a code for `power`, `mode`, `temperature` and `fan`, which the client uses on every device, and list at least one HVAC mode and one fan mode. Mode names must be known ones, each HVAC mode but `off` needs a `set` string (`off` has none), and no two modes of a table share a wire value.

```json
{
  "inherits": "default",
  "remove": ["T01"],
  "entries": [
    { "key": "T1", "name": "Suction Temp. [T1]", "platform": "sensor" }
  ]
}
```

```json
{ "inherits": "default", "hvac_modes": { "heat": { "target": "R04" } } }
```

A file breaking these rules, such as a delta naming the wrong level, removing a key the level below doesn't have or listing a key twice, fails when the integration loads, and so in the tests.

A catalog entry with `"request_field": "bitCodes"` is requested in the read's bit codes array rather than with the other codes: single bits such as `Sys1CompState` answer only there. Only an API type whose `api.<type>.json` names a `bit_codes` field has that array; on the others such an entry is neither requested nor set up as an entity.

Besides `key`, `name`, `platform` and `device_class`, an entry describes its entity with:

- `unit_of_measurement` and `state_class`, for a sensor.
- `on_value` and `off_value`, for a binary sensor: the value that reads as on, and the one that reads as off. With `off_value` set, any other value, a missing one included, makes the entity unavailable.
- `entity_category`: absent puts the entity under diagnostics, `null` with the device's main entities.
- `enabled_default`: `false` adds the entity disabled.
- `verified`: `false` when nothing confirms what the entity shows, such as a bit whose meaning and polarity were guessed rather than seen on a device or in the official app. It doesn't change the entity; it tells whoever reads the profile.

A catalog entity's English name is in [translations/en.json](custom_components/aqua_temp/translations/en.json) under `<level>_<key>` (lowercased, without `/`), where `<level>` is the file that defines the entry: an inherited entry uses the lower level's translation, and an entry a delta adds or replaces needs one under the delta's level.

Check what a product resolves to with [utils/show-profile.py](#show-a-products-profile). A change to a profile file shows up in the [resolved-profile references](#resolved-profile-references): regenerate them and check that only the products you meant to change moved. For a live device, the diagnostics name the class and the files its profile comes from; run the script on the product id in its device data, on the version that reported it, for the rest.

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

### Resolved-profile references

Two committed files pin what every known product's [profile](#device-profiles) resolves to, plus the default, a device reporting no product and an unknown product: [tests/cloud/resolved_profiles.json](tests/cloud/resolved_profiles.json) (the mapping and catalog) and [tests/integration/resolved_entity_names.json](tests/integration/resolved_entity_names.json) (each entity's platform, key and English name). Products with the same result share one entry. The tests rebuild both and compare.

A diff in either one is a change users will see: different codes polled or controlled, entities added, removed or renamed. When a change to a profile is meant to do that, regenerate them and review the diff as part of the change; never regenerate them only to make a test pass.

```bash
PYTHONPATH=. uv run python utils/show-profile.py --write-references
```

### Mutation testing

[mutmut](https://mutmut.readthedocs.io/) checks that the tests catch changes to the code: it applies small edits (mutants) to the modules in `source_paths` under `[tool.mutmut]` in [pyproject.toml](pyproject.toml), and runs the tests covering each one. Run it on demand, not in CI, when adding or reviewing tests.

```bash
uv run mutmut run                  # every mutant, results kept in mutants/ for the next commands
uv run mutmut results              # mutants that no test caught
uv run mutmut show <mutant>        # the diff of one
uv run mutmut browse               # the same, interactively
```

A surviving mutant is a change the tests don't notice. Some are harmless edits that don't change behaviour; the rest point at a missing assertion or test. Delete `mutants/` to start over after changing the configuration.

`_LOGGER` calls are not mutated, including calls split over several lines: `do_not_mutate_patterns` under `[tool.mutmut]` skips them. Their mutants only change the log output, which few tests read, so most survive and bury the useful ones. To skip other code, prefer adding a pattern there over a `# pragma: no mutate` on each line.

## Developer scripts

The scripts import `custom_components` and `utils` as top-level packages, so run them from the repository root with `PYTHONPATH=.`.

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

### Show a product's profile

[utils/show-profile.py](utils/show-profile.py) prints the mapping and catalog a product resolves to, its class, and the files each comes from (its chain, lowest level first).

```bash
PYTHONPATH=. uv run python utils/show-profile.py 1442284873216843776   # one product
PYTHONPATH=. uv run python utils/show-profile.py --all                 # every known product
```

`--write-references` rewrites the [resolved-profile references](#resolved-profile-references) instead.

### Generate entity descriptions from the app resources

[utils/parse-resources.py](utils/parse-resources.py) reads the parameter names from each device's `utils/devices/<device>/resources.xml`, which is extracted from the mobile app. It maps them with that device's `consts.py`, and logs the resulting entity descriptions and translation keys.

```bash
PYTHONPATH=. uv run python utils/parse-resources.py
```

Limitations of the script as it stands:

- File paths use Windows separators (`\\`), so it only finds the XML files on Windows.
- Writing `custom_components/aqua_temp/cloud/profiles/entity_description.<device>.json` is commented out. Uncomment it to regenerate the files, or copy the logged output.

### Call the cloud API by hand

[docs/api/](docs/api/README.md) is a [Bruno](https://www.usebruno.com/) collection documenting what we know about the cloud API, one request per endpoint. Its notes mark what was probed against the live API and what comes from the integration's client; add what you find when you probe.

## Changelog and releases

- [CHANGELOG.md](CHANGELOG.md) follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Add user-facing changes under `## [Unreleased]`.
- A release commit (`Release X.Y.Z`) moves the Unreleased entries to a dated version section and bumps `version` in [manifest.json](custom_components/aqua_temp/manifest.json).
- When a change is also proposed upstream, link the upstream PR from its changelog entry. When an upstream merge brings in a change this fork already had, note it in the changelog.
