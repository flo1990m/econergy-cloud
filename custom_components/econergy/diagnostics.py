"""Diagnostics for the official Econergy Lab API integration."""
from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    item = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    coordinator = item.get("coordinator")
    api = item.get("api")
    data = coordinator.data if coordinator is not None else None
    return {
        "entry": {
            "domain": entry.domain,
            "title": entry.title,
            "home_id": entry.data.get("home_id"),
            "home_name": entry.data.get("home_name"),
            "has_oauth_authorization": bool(
                (entry.data.get("token") or {}).get("access_token")
            ),
            "oauth_token_expires_at": (data or {}).get("expires_at"),
        },
        "api_version": getattr(api, "api_version", None),
        "program_errors": (data or {}).get("program_errors", {}),
        "programs": (data or {}).get("programs", {}),
        "settings": (data or {}).get("settings", {}),
        "settings_errors": (data or {}).get("settings_errors", {}),
        "consumption": (data or {}).get("consumption", {}),
        "consumption_errors": (data or {}).get("consumption_errors", {}),
        "last_commands": (data or {}).get("last_commands", {}),
        "devices": [
            {
                "id": device.get("id"),
                "name": device.get("name"),
                "info": device.get("info"),
                "state": device.get("state"),
                "lastSeenAt": device.get("lastSeenAt"),
                "available_api_fields": sorted(str(key) for key in device if not str(key).startswith("_")),
                "status_request": device.get("_ha_status_request"),
                "settings": (data or {}).get("settings", {}).get(str(device.get("id")), {}),
                "consumption": (data or {}).get("consumption", {}).get(str(device.get("id")), {}),
            }
            for device in (data or {}).get("devices", [])
        ],
    }
