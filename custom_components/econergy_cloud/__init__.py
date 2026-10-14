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
from .const import DOMAIN, UPDATE_INTERVAL_SECONDS

_LOGGER = logging.getLogger(__name__)
PLATFORMS = ["sensor", "climate"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    api = EconergyApi(
        async_get_clientsession(hass), entry.data["email"], entry.data["password"]
    )

    async def _update():
        try:
            return await api.get_home()
        except EconergyAuthError as exc:
            raise ConfigEntryAuthFailed("Econergy authentication failed") from exc
        except EconergyApiError as exc:
            raise UpdateFailed(str(exc)) from exc

    coordinator = DataUpdateCoordinator(
        hass, _LOGGER, name="Econergy Cloud", update_method=_update,
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
