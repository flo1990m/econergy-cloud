DOMAIN = "econergy_cloud"
BASE_URL = "https://raegy28bl9.execute-api.eu-west-3.amazonaws.com/Prod"
APP_VERSION = "1.2.0"

# Poll the whole home every 5 minutes while any radiator is not OFF.
UPDATE_INTERVAL_SECONDS = 300
# Reduce API traffic to one read every 15 minutes when every radiator is OFF.
OFF_UPDATE_INTERVAL_SECONDS = 900
