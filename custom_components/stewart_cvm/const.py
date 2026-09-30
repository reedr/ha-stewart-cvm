"""Constants for the Stewart CVM integration."""

DOMAIN = "stewart_cvm"
MANUFACTURER = "Stewart"
MODEL = "CVM"

# Domain used by the pre-HACS package; its config entries are imported by the config flow.
LEGACY_DOMAIN = "CVM"
CONF_LEGACY_ENTRY = "legacy_entry_id"

CVM_PRESETS_ASPECT = "cvmpresetar"
CVM_PRESETS_POSITION = "cvmpresetpos"
CONF_RECALIBRATE = "recalibrate"

CVM_CONNECT_TIMEOUT = 20
CVM_LOGIN_TIMEOUT = 5
CVM_PORT = 23
CVM_MIN_COMMAND_INTERVAL = 1
CVM_CALIBRATE_TIMEOUT = 20
# During calibration, how long to wait for a recalled preset to start moving the motor
# before assuming it is already there, and how long to let it settle after it stops.
CVM_MOTION_TIMEOUT = 5
CVM_SETTLE_TIME = 5
