"""Constants for the Pool IQ integration."""
from __future__ import annotations

DOMAIN = "pooliq"
VERSION = "0.4.1"

# JetLinks backend the Pool IQ app talks to.
DEFAULT_HOST = "http://47.236.42.212:8850"

# Login credentials are not shipped with the integration. The installer
# enters the username and password supplied by Pool IQ Hub.

DEFAULT_SCAN_INTERVAL = 300  # seconds

CONF_HOST = "host"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_DEVICE_ID = "device_id"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_SHOW_PANEL = "show_panel"

PLATFORMS = ["sensor", "binary_sensor", "switch", "select", "number", "button"]
