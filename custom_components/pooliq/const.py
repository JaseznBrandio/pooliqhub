"""Constants for the Pool IQ integration."""
from __future__ import annotations

DOMAIN = "pooliq"
VERSION = "0.4.9"

# JetLinks backend the Pool IQ app talks to.
DEFAULT_HOST = "http://47.236.42.212:8850"

# Login credentials are not shipped with the integration. The installer
# enters the username and password supplied by Pool IQ Hub.

DEFAULT_SCAN_INTERVAL = 30  # seconds
OLD_DEFAULT_SCAN_INTERVAL = 300  # default before 0.4.2

CONF_HOST = "host"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_DEVICE_ID = "device_id"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_SHOW_PANEL = "show_panel"

PLATFORMS = ["sensor", "binary_sensor", "switch", "select", "number", "button"]

# Chlorinator faults. The unit reports one number made of flags added together
# (one flag per fault), so several faults at once arrive as their sum,
# e.g. Low salt (0x0004) + Water temp low (0x0040) = 0x0044 = 68.
# From the Pool IQ Hub fault table; "TDS" is the unit's term for salt.
FAULT_FLAGS: tuple[tuple[int, str], ...] = (
    (0x0010, "Low flow"),  # water flow fault
    (0x0400, "Extremely high salt"),
    (0x0001, "High salt"),
    (0x0004, "Low salt"),
    (0x0008, "No output"),
    (0x0200, "Low output"),
    (0x0002, "Internal temp high"),
    (0x0100, "Transformer temp high"),
    (0x0020, "Water temp high"),
    (0x0080, "Water temp rising fast"),
    (0x0040, "Water temp low"),
    (0x0800, "Check ioniser rods"),
)


def fault_list(code) -> list[str] | None:
    """Every fault in the reported number, in plain words ([] when there are none)."""
    try:
        code = int(code)
    except (TypeError, ValueError):
        return None
    faults = [name for flag, name in FAULT_FLAGS if code & flag]
    unknown = code & ~sum(flag for flag, _ in FAULT_FLAGS)
    if unknown:
        faults.append(f"Code 0x{unknown:04X}")
    return faults


def fault_text(code) -> str | None:
    """"OK", or the active faults joined, e.g. "Low salt, Water temp low"."""
    faults = fault_list(code)
    if faults is None:
        return None
    return ", ".join(faults) if faults else "OK"
