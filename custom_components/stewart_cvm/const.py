"""Constants for the Stewart CVM integration."""

DOMAIN = "stewart_cvm"
MANUFACTURER = "Stewart"
MODEL = "CVM"
EVENT = "CVM_event"

# Domain used by the pre-HACS package; its config entries are imported by the config flow.
LEGACY_DOMAIN = "CVM"
CONF_LEGACY_ENTRY = "legacy_entry_id"

CVM_PRESETS_ASPECT = "cvmpresetar"
CVM_PRESETS_POSITION = "cvmpresetpos"

CVM_CONNECT_TIMEOUT = 20
CVM_LOGIN_TIMEOUT = 5
CVM_PORT = 23
CVM_MIN_COMMAND_INTERVAL = 1
CVM_CALIBRATE_TIMEOUT = 20
