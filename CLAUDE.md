# Aquatemp Home Assistant Integration

Home Assistant custom integration (domain `aqua_temp`, installed via HACS) for PHINX Aqua Temp / HiTemp heat pumps, polling the vendor's cloud API.

Development setup, quality checks, developer scripts and release conventions are in [CONTRIBUTING.md](CONTRIBUTING.md); follow it.

## Commands

There is no build step.

```bash
uv sync                                            # set up or refresh .venv from uv.lock
uv run pre-commit run --all-files                  # full lint/format pass
uv run pre-commit run ruff-check --files <path>    # single hook on specific files
uv run pytest                                      # offline test suite
```

## Layout

- `custom_components/aqua_temp/cloud/` is the cloud API library: HTTP, login and token, retries, device discovery and polling, writes, reading state (mode, targets, power, fan), and the device profiles. It knows nothing of Home Assistant or the integration: [cloud/ruff.toml](custom_components/aqua_temp/cloud/ruff.toml) bans `homeassistant`, the integration's own modules and relative imports from parent packages. Inside it, use relative imports. The ban lists the integration's modules one by one, because relative imports resolve to `custom_components.aqua_temp.cloud.*`. Add new top-level modules of the integration to that list.
- The integration keeps everything HA-specific: entity descriptions and platforms (`build_entity_descriptions` in `common/entity_descriptions.py`, from `DeviceProfile.parameters`), translations, the `Store`, config entries, the `HVACMode` conversion and the new-device dispatcher signal (both in the coordinator, which passes `on_new_device` to the client).
- Profiles live in `cloud/profiles/`. `api.<type>.json` holds the field names per API type (`ApiProfile`). `mapping.<product id>.json` gives the protocol code behind each role and the mode and fan values. `entity_description.<product id>.json` is the parameter catalog; it also carries HA presentation fields (`platform`, `device_class`, ...), which the library passes through untouched. `DeviceProfiles.for_product` falls back to `default` for the mapping and the catalog independently.
- Each client gets its own aiohttp session and headers, so config entries don't share a token.
