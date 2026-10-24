# Aquatemp Home Assistant Integration

Home Assistant custom integration (domain `aqua_temp`, installed via HACS) for PHINX Aqua Temp / HiTemp heat pumps, polling the vendor's cloud API.

Development setup, quality checks, developer scripts and release conventions are in [CONTRIBUTING.md](CONTRIBUTING.md); follow it.

## Commands

There is no build step.

```bash
pre-commit run --all-files                   # full lint/format pass
pre-commit run ruff-check --files <path>     # single hook on specific files
pytest                                       # offline test suite
```
