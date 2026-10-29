"""Econergy cloud integration."""
from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import EconergyApi, EconergyAuthError, EconergyApiError
from .const import DOMAIN, OFF_UPDATE_INTERVAL_SECONDS, UPDATE_INTERVAL_SECONDS

_LOGGER = logging.getLogger(__name__)
PLATFORMS = ["sensor", "climate"]


def _all_radiators_off(home_data: dict) -> bool:
    """Return True only when every known radiator is explicitly in OFF mode."""
    devices = home_data.get("devices")
    if not isinstance(devices, list) or not devices:
        return False

    for device in devices:
        if not isinstance(device, dict):
            return False
        config = device.get("config")
        if not isinstance(config, dict):
            return False
        mode = config.get("mode")
        if isinstance(mode, bool) or str(mode) != "0":
            return False

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    api = EconergyApi(
        async_get_clientsession(hass), entry.data["email"], entry.data["password"]
    )

    async def _update():
        try:
            home_data = await api.get_home()
            # One API request returns the entire home, including all radiator
            # temperatures and configurations. Use the slower interval only
            # when every radiator is explicitly OFF.
            interval = (
                OFF_UPDATE_INTERVAL_SECONDS
                if _all_radiators_off(home_data)
                else UPDATE_INTERVAL_SECONDS
            )
            coordinator.update_interval = timedelta(seconds=interval)
            return home_data
        except EconergyAuthError as exc:
            raise ConfigEntryAuthFailed("Econergy authentication failed") from exc
        except EconergyApiError as exc:
            raise UpdateFailed(str(exc)) from exc

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="Econergy Cloud",
        update_method=_update,
        update_interval=timedelta(seconds=UPDATE_INTERVAL_SECONDS),
    )
    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryAuthFailed:
        raise
    except Exception as exc:
        raise ConfigEntryNotReady(str(exc)) from exc
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = (api, coordinator)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return ok
