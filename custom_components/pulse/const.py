DOMAIN = "pulse"

CONF_HOST = "host"
CONF_PORT = "port"
CONF_TOKEN = "token"
CONF_TARGET_ID = "target_id"
CONF_WEBHOOK_ID = "webhook_id"

DEFAULT_PORT = 80
PLATFORMS = ["button", "binary_sensor", "sensor"]
DATA_CLIENT = "client"
DATA_COORDINATOR = "coordinator"
DATA_WEBHOOK_ID = "webhook_id"
DATA_ABSENCE = "absence_count"

# Number of consecutive periodic pushes a MAC may be missing before HA
# removes the corresponding device + entities. At 2-min cadence this is ~6
# minutes of grace, enough to ride out a single firmware reboot.
STALE_CONTROLLER_GRACE_PUSHES = 3
