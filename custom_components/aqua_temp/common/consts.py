from datetime import timedelta

from ..cloud.consts import HTTP_HEADER_X_TOKEN

DOMAIN = "aqua_temp"
DEFAULT_NAME = "Aqua Temp"
SIGNAL_AQUA_TEMP_DEVICE_NEW = f"signal_{DOMAIN}_device_new"
CONFIGURATION_FILE = f"{DOMAIN}.config.json"
LEGACY_KEY_FILE = f"{DOMAIN}.key"

UPDATE_API_INTERVAL = timedelta(minutes=5)

ADD_COMPONENT_SIGNALS = [SIGNAL_AQUA_TEMP_DEVICE_NEW]

STORAGE_DATA_KEY = "key"

INVALID_TOKEN_SECTION = "https://github.com/MatiasFernandez/aquatemp#invalid-token"

DEFAULT_ENTRY_ID = "config"

CONF_TITLE = "title"
CONF_API_TYPE = "api_type"
CONF_LOG_SESSION_TOKEN = "log_session_token"

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
    HTTP_HEADER_X_TOKEN,
]
