from enum import StrEnum


class Endpoints(StrEnum):
    Login = "app/user/login"
    UserInfo = "app/user/getUserInfo"
    ListRegisteredDevices = "app/device/deviceList"
    ListSharedAppectDevices = "app/device/getMyAppectDeviceShareDataList"
    ListSharedTobeDevices = "app/device/getMyTobeAppectDeviceShareDataList"
    DeviceStatus = "app/device/getDeviceStatus"
    DeviceControl = "app/device/control"
    DeviceFault = "app/device/getFaultDataByDeviceCode"
    DeviceData = "app/device/getDataByCode"
    DeviceDataV5 = "app/device/v5/getDataByCode"
    DevicePassthroughInstruction = "device/sendDevicePassthroughInstruction"
