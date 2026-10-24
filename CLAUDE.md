# Aquatemp Home Assistant Integration

Home Assistant custom integration (domain `aqua_temp`, installed via HACS) for PHINX Aqua Temp / HiTemp heat pumps, polling the vendor's cloud API.

## Commands

There is no unit test suite and no build step. Quality gates are pre-commit hooks (black, isort, flake8, pyupgrade `--py39-plus`, autoflake, bandit, codespell, yamllint, prettier, JSON/YAML checks) plus CI-only `hassfest` and HACS validation.

```bash
pre-commit run --all-files            # full lint/format pass
pre-commit run black --files <path>   # single hook on specific files
```

## Release conventions

- `CHANGELOG.md` follows Keep a Changelog; add user-facing changes under `## [Unreleased]`.
- A release commit ("Release X.Y.Z") moves the Unreleased entries to a dated version section and bumps `version` in `manifest.json`.
- When a change diverges from upstream, add a row to the "Differences from upstream" table in `README.md`.
