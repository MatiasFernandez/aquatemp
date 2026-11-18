"""The one place that knows which Home Assistant test harness is installed.

Home Assistant's `pytest-homeassistant` replaces `pytest-homeassistant-custom-component`
from 2026.11 on. The latest-release environment uses the former and the floor
environment (tests/floor/) the latter, and the two can't be installed together, so
the tests import the harness helpers from here.

Delete this module when the floor reaches 2026.11.0: import from
`pytest_homeassistant.common`, and drop the `enable_custom_integrations_if_needed`
fixture and its import in tests/integration/conftest.py.
"""

import pytest

try:
    from pytest_homeassistant.common import MockConfigEntry, async_fire_time_changed

    @pytest.fixture(autouse=True)
    def enable_custom_integrations_if_needed() -> None:
        """Nothing to do: the `hass` fixture of this harness loads custom integrations."""

except ImportError:  # the floor's older harness
    from pytest_homeassistant_custom_component.common import (
        MockConfigEntry,
        async_fire_time_changed,
    )

    @pytest.fixture(autouse=True)
    def enable_custom_integrations_if_needed(enable_custom_integrations) -> None:
        """Lets Home Assistant load `custom_components/`."""


__all__ = [
    "MockConfigEntry",
    "async_fire_time_changed",
    "enable_custom_integrations_if_needed",
]
