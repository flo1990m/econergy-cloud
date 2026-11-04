"""Econergy Cloud integration."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import EconergyApi, EconergyAuthError, EconergyApiError
from .const import DIAGNOSTIC_SETTLE_SECONDS, DOMAIN, UPDATE_INTERVAL_SECONDS

_LOGGER = logging.getLogger(__name__)
PLATFORMS = ["sensor", "climate"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    api = EconergyApi(
        async_get_clientsession(hass), entry.data["email"], entry.data["password"]
    )

    last_diagnostic = {"requested_at": None, "acknowledged": 0}

    async def _update():
        # The mobile diagnostic queues a state report; it does not return the
        # new temperatures immediately. The radiator usually reports 9–12 s
        # later, so wait before reading the home snapshot.
        diagnostic_requested_at = None
        diagnostic_acknowledged = 0
        try:
            acknowledgements = await api.diagnose_home()
            diagnostic_acknowledged = sum(
                1 for item in acknowledgements if item.get("acknowledge")
            )
            _LOGGER.debug(
                "Econergy diagnostic: %s/%s radiateurs ont accusé réception",
                diagnostic_acknowledged,
                len(acknowledgements),
            )
            if diagnostic_acknowledged:
                diagnostic_requested_at = datetime.now(timezone.utc).isoformat()
                last_diagnostic["requested_at"] = diagnostic_requested_at
                last_diagnostic["acknowledged"] = diagnostic_acknowledged
                await asyncio.sleep(DIAGNOSTIC_SETTLE_SECONDS)
        except EconergyAuthError as exc:
            _LOGGER.warning(
                "Econergy diagnostic authentication failed; reading cached cloud state: %s",
                exc,
            )
        except EconergyApiError as exc:
            _LOGGER.warning(
                "Econergy diagnostic unavailable; reading cached cloud state: %s",
                exc,
            )

        try:
            home = await api.get_home()
            if last_diagnostic["requested_at"]:
                # These attributes let Home Assistant record/confirm each
                # successful diagnostic even when the measured temperature
                # itself has not changed. Keep the last success visible if a
                # later diagnostic request fails.
                home["_diagnostic_requested_at"] = last_diagnostic["requested_at"]
                home["_diagnostic_acknowledged"] = last_diagnostic["acknowledged"]
            return home
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
