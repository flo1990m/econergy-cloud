DOMAIN = "econergy_cloud"
BASE_URL = "https://raegy28bl9.execute-api.eu-west-3.amazonaws.com/Prod"
APP_VERSION = "1.2.0"

# Request a fresh diagnostic from all radiators before each grouped home read.
# The diagnostic needs around 9–12 seconds to reach radiator state reports.
# Wait for it inside the refresh, then poll again after 4m45s (about 5m
# between diagnostic requests, including the 15-second settle period).
DIAGNOSTIC_SETTLE_SECONDS = 15
UPDATE_INTERVAL_SECONDS = 285
