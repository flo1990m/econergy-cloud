"""Constants for Econergy Cloud."""

DOMAIN = "econergy"
NAME = "Econergy Cloud 2.1.4 (Bêta)"
BASE_URL = "https://econergy-app.fr/api/smarthome/v1"

# Econergy Lab public OAuth application. Public clients do not use a secret.
OAUTH_CLIENT_ID = "6af46d41611559f97958913b"
OAUTH_AUTHORIZE_URL = "https://econergy-app.fr/api/oauth/authorize"
OAUTH_TOKEN_URL = "https://econergy-app.fr/api/oauth/token"
OAUTH_SCOPES = "readonly write multihome"

PROGRAM_PANEL_PATH = "econergy-program"
PROGRAM_PANEL_URL = "/econergy-program"

# Read the already-published home inventory every five minutes. This is a GET
# only; it does not wake radiator radios. A forced radio refresh is user-driven.
INVENTORY_POLL_INTERVAL_SECONDS = 300
STATUS_REQUEST_COMMAND_TIMEOUT_SECONDS = 20
STATUS_REQUEST_STATE_TIMEOUT_SECONDS = 30
STATUS_REQUEST_POLL_INTERVAL_SECONDS = 2
STATUS_REQUEST_DEFAULT_RETRY_AFTER_SECONDS = 60

DEFAULT_MANUAL_SETPOINT_C = 18.0
FROST_SETPOINT_C = 7.5
REQUEST_TIMEOUT_SECONDS = 20
COMMAND_ACK_TIMEOUT_SECONDS = 15
STATE_CONFIRM_TIMEOUT_SECONDS = 18
PROGRAM_COMMAND_TIMEOUT_SECONDS = 60
PROGRAM_CONFIRM_TIMEOUT_SECONDS = 30
PROGRAM_POLL_INTERVAL_SECONDS = 2

MODE_OFF = "OFF"
MODE_FROST = "FROST"
MODE_MANUAL = "MANUAL"
MODE_PROG = "PROG"
SUPPORTED_MODES = {MODE_OFF, MODE_FROST, MODE_MANUAL, MODE_PROG}

PRESET_MANUAL = "Manuel"
PRESET_FROST = "Hors gel"
PRESET_PROGRAM = "Programmation"
PRESET_TO_MODE = {
    PRESET_MANUAL: MODE_MANUAL,
    PRESET_FROST: MODE_FROST,
    PRESET_PROGRAM: MODE_PROG,
}
MODE_TO_PRESET = {v: k for k, v in PRESET_TO_MODE.items()}

WEEKDAYS = {
    "monday": "Lundi",
    "tuesday": "Mardi",
    "wednesday": "Mercredi",
    "thursday": "Jeudi",
    "friday": "Vendredi",
    "saturday": "Samedi",
    "sunday": "Dimanche",
}
