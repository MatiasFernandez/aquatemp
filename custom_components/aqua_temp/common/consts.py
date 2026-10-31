from homeassistant.const import CONF_USERNAME

from ..cloud.consts import HTTP_HEADER_X_TOKEN

DOMAIN = "aqua_temp"
DEFAULT_NAME = "Aqua Temp"
SIGNAL_AQUA_TEMP_DEVICE_NEW = f"signal_{DOMAIN}_device_new"
CONFIGURATION_FILE = f"{DOMAIN}.config.json"
LEGACY_KEY_FILE = f"{DOMAIN}.key"

# Seconds between polls, by default and the range the options accept. Each
# poll makes a few requests per device
DEFAULT_UPDATE_INTERVAL = 300
MIN_UPDATE_INTERVAL = 30
MAX_UPDATE_INTERVAL = 3600

# Seconds a request to the cloud may take, the range the options accept. The
# cloud itself gives up on a device that doesn't acknowledge a control after
# about 50 s
MIN_REQUEST_TIMEOUT = 5
MAX_REQUEST_TIMEOUT = 60

ADD_COMPONENT_SIGNALS = [SIGNAL_AQUA_TEMP_DEVICE_NEW]

STORAGE_DATA_KEY = "key"

INVALID_TOKEN_SECTION = "https://github.com/MatiasFernandez/aquatemp#invalid-token"

DEFAULT_ENTRY_ID = "config"

CONF_TITLE = "title"
CONF_API_TYPE = "api_type"
CONF_LOG_SESSION_TOKEN = "log_session_token"
CONF_REQUEST_TIMEOUT = "request_timeout"
CONF_UPDATE_INTERVAL = "update_interval"

DATA_ITEM_DEVICES = "device"
DATA_ITEM_LOGIN_DETAILS = "login-details"
DATA_ITEM_CONFIG = "configuration"

API_STATUS = "api_status"

TO_REDACT = [
    "userId",
    "user_id",
    "userName",
    "user_name",
    "accessKey",
    CONF_USERNAME,
    HTTP_HEADER_X_TOKEN,
]
