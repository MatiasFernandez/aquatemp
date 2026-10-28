"""pytest only honors pytest_plugins in the root conftest, so the cloud mock is
registered here for both the cloud and the integration tests."""

pytest_plugins = ["tests.cloud.mock_cloud"]
