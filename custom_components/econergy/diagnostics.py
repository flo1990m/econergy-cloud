"""Diagnostics for the official Econergy Lab API integration."""
from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN


def _consumption_summary(value: Any) -> dict[str, Any]:
    """Keep diagnostics compact while exposing the permanent archive extent."""
    if not isinstance(value, dict):
        return {}
    days = value.get("days") or []
    valid_days = [
        day for day in days
        if isinstance(day, dict) and isinstance(day.get("date"), str)
    ]
    return {
        "deviceId": value.get("deviceId"),
        "powerW": value.get("powerW"),
        "api_days": valid_days[-15:],
        "archived_days_count": len(valid_days),
        "archive_start": valid_days[0].get("date") if valid_days else None,
        "archive_end": valid_days[-1].get("date") if valid_days else None,
    }


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
        "consumption_loaded_date": getattr(coordinator, "consumption_loaded_date", None),
        "consumption": {
            device_id: _consumption_summary(value)
            for device_id, value in (data or {}).get("consumption", {}).items()
        },
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
                "consumption": _consumption_summary(
                    (data or {}).get("consumption", {}).get(str(device.get("id")), {})
                ),
            }
            for device in (data or {}).get("devices", [])
        ],
    }
