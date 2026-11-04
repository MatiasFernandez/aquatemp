"""Faults: getDeviceStatus decides whether to read the fault, which lands in device data."""

from .mock_cloud import DATA, DATA_IDLE, DEVICE_CODE, cloud_with

# Literal on purpose: the expected values must not come from the config under test
STATUS = "app/device/getDeviceStatus"
FAULT = "app/device/getFaultDataByDeviceCode"

RESPONSES = {DATA: DATA_IDLE}


@cloud_with(
    RESPONSES
    | {
        STATUS: "synthetic/device_status_fault",
        FAULT: "synthetic/device_fault",
    }
)
async def test_fault_description_becomes_device_data(api, wire):
    await api.update()

    assert wire[-2:] == [
        (STATUS, {"deviceCode": DEVICE_CODE}),
        (FAULT, {"deviceCode": DEVICE_CODE}),
    ]
    assert api.get_device_data(DEVICE_CODE)["fault"] == "Water flow failure"


@cloud_with(
    RESPONSES
    | {
        STATUS: ["synthetic/device_status_fault", "device_status.online"],
        FAULT: "synthetic/device_fault",
    }
)
async def test_cleared_fault_is_removed(api, wire):
    await api.update()

    assert "fault" in api.get_device_data(DEVICE_CODE)

    wire.clear()
    await api.update()

    assert FAULT not in [endpoint for endpoint, _ in wire]
    assert "fault" not in api.get_device_data(DEVICE_CODE)


@cloud_with(
    RESPONSES
    | {
        STATUS: "synthetic/device_status_fault",
        FAULT: "synthetic/device_fault_empty",
    }
)
async def test_fault_without_records_sets_no_fault(api):
    await api.update()

    assert "fault" not in api.get_device_data(DEVICE_CODE)


@cloud_with(
    RESPONSES
    | {
        STATUS: "synthetic/device_status_no_flag",
        FAULT: "synthetic/device_fault_empty",
    }
)
async def test_missing_fault_flag_still_reads_the_fault(api, wire):
    await api.update()

    # Possible bug: the flag defaults to the string "False", which is
    # truthy, so a status without isFault still reads the fault
    assert wire[-1] == (FAULT, {"deviceCode": DEVICE_CODE})
    assert "fault" not in api.get_device_data(DEVICE_CODE)
