# Aquatemp Home Assistant Integration

Home Assistant custom integration (domain `aqua_temp`, installed via HACS) for PHNIX Aqua Temp / HiTemp heat pumps, polling the vendor's cloud API.

Development setup, quality checks, developer scripts and release conventions are in [CONTRIBUTING.md](CONTRIBUTING.md); follow it.

## Commands

There is no build step.

```bash
uv sync                                            # set up or refresh .venv from uv.lock
uv run pre-commit run --all-files                  # full lint/format pass
uv run pre-commit run ruff-check --files <path>    # single hook on specific files
uv run pytest                                      # offline test suite, latest Home Assistant
uv run --project tests/floor --locked pytest       # oldest supported Home Assistant, from tests/floor/uv.lock
```

## Layout

- `custom_components/aqua_temp/cloud/` is the cloud API client: a library independent of Home Assistant and of the integration. Use relative imports inside it. [cloud/ruff.toml](custom_components/aqua_temp/cloud/ruff.toml) enforces the boundary by listing the integration's modules one by one, so add any new top-level integration module there and to [tests/cloud/ruff.toml](tests/cloud/ruff.toml).
- Everything Home Assistant-specific lives outside `cloud/`: entities, translations, config entries and storage. The coordinator translates between the library and Home Assistant.
- Device profiles in `cloud/profiles/` are JSON: field names per API type (`api.<type>.json`), and per product the protocol mapping (`mapping.<product id>.json`) and parameter catalog (`entity_description.<product id>.json`). Each falls back to `default` on its own.
- Each client has its own aiohttp session, so config entries don't share a token.
- Tests: `tests/cloud/` for the library, `tests/integration/` for the rest. Read [tests/AGENTS.md](tests/AGENTS.md) before writing tests if your tool hasn't loaded it.

## Pull requests

Open one only when the person you work with asks. Fill in [.github/pull_request_template.md](.github/pull_request_template.md) and keep it short:

- **Manual testing** is what someone actually checked by hand: in Home Assistant, the app, or against the cloud. Don't describe the automated tests or restate the diff. If nobody ran the change in Home Assistant, say so; never fill in "Tested on" with a setup that wasn't used.
- **Notes for reviewers** holds what the diff doesn't show: decisions and why, context from the app or the device. Describe what the change does; don't list what was left as it was or options that came up while working on it. Mention a ruled-out alternative only when a reviewer would likely suggest it. Leave it out if there is none.
- **AI use** says what the AI did and what the person did, in a sentence or two. Attribution trailers or a "Generated with" footer don't count as that.
