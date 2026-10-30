# Tests

Running the suite, the mocked cloud and fixtures: see [CONTRIBUTING.md](../CONTRIBUTING.md#tests).

## Names and structure

- Name the behavior in plain language, not the code's fields or parameters.
  - ✗ `test_set_hvac_mode_with_off_param`
  - ✓ `test_hvac_off_powers_off`
- Name what is always true, not this one example's values.
  - ✗ `test_climate_is_heat_when_mode_is_1`
  - ✓ `test_climate_reports_the_device_mode`
- The module docstring says what the file covers. Test docstrings only when the name isn't enough.
- Setup, exercise and assert, separated by blank lines. No section-label comments; comments explaining why a value is expected are fine.
- One behavior per test. Compare whole values (a payload, a list of endpoints) in one assert rather than field by field.

## pytest

- Plain `assert` and test functions; no `unittest.TestCase` or test classes.
- Setup goes in fixtures. Keep a fixture in its module until another module needs it. Avoid `autouse`.
- Change the scenario by overriding `cloud_responses` per module, or with `@cloud_with(...)` per test.
- `@pytest.mark.parametrize` for the same behavior over several inputs, with readable ids.
- `pytest.raises(..., match=...)` around the failing call only.
- No `@pytest.mark.asyncio`: `asyncio_mode` is `auto`.
- No `sleep`: patch it or move the clock.

## Mocking

- Mock only the boundary: the cloud's HTTP API (already done by the harness), the clock, randomness. Never patch the integration's or library's own modules; test one level up instead.
- `patch` where the name is looked up (`...cloud.client.sleep`), not where it's defined.
- No bare `MagicMock`: use `autospec=True` or `wraps=`.
- Assert on outcomes and on what crossed the boundary (`wire`, entity states), not on `assert_called_with` against internals.

## Expected values

- Literals, or read from the profile files or fixtures. Never computed by the code under test.
- Pinning behavior that looks wrong: keep the assertion and add `# Possible bug: ...`.

## Home Assistant

- Go through the public surface: `MockConfigEntry`, `hass.services.async_call(..., blocking=True)`, then `hass.states`, the registries or diagnostics. Don't call entity methods or read coordinator attributes.
- Use `pytest-homeassistant-custom-component` helpers (`async_fire_time_changed`, `freezer`) instead of rebuilding them.

## What to test

- Don't restate the implementation or check that a mock returns what it was given.
- Don't test Home Assistant or library behavior the integration doesn't add to.
- A bug fix needs a test that fails without the fix.
- Don't add tests asserting that removed code stays removed. Deleting code only needs the tests that covered it updated or removed.
