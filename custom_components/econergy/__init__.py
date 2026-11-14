"""Econergy Cloud: official Econergy Lab API only."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import voluptuous as vol

from .api import EconergyApi, EconergyApiError, EconergyAuthError
from .const import DOMAIN, WEEKDAYS
from .coordinator import EconergyCoordinator
from .program_helpers import validate_periods
from .frontend import async_register_frontend
from .oauth import async_register_oauth_implementation

_LOGGER = logging.getLogger(__name__)
PLATFORMS = ["climate", "sensor", "number", "button", "text", "switch", "binary_sensor"]
SERVICE_SET_PROGRAM_DAY = "set_program_day"
_PROGRAM_PERIOD_SCHEMA = vol.Schema({
    vol.Required("start"): cv.string,
    vol.Required("end"): cv.string,
})
_PROGRAM_SERVICE_SCHEMA = vol.Schema({
    vol.Required("device_id"): cv.string,
    vol.Optional("day"): vol.In(tuple(WEEKDAYS)),
    vol.Optional("periods"): vol.All([_PROGRAM_PERIOD_SCHEMA], vol.Length(max=3)),
    vol.Optional("eco_c"): vol.Coerce(float),
    vol.Optional("comfort_c"): vol.Coerce(float),
})


def _validate_target(value: float, label: str, minimum: float, maximum: float) -> float:
    if not minimum <= value <= maximum:
        raise HomeAssistantError(
            f"La consigne {label} doit être comprise entre {minimum:g} et {maximum:g} °C."
        )
    if abs(value * 2 - round(value * 2)) > 0.0001:
        raise HomeAssistantError(f"La consigne {label} doit être réglée par pas de 0,5 °C.")
    return round(value, 1)


async def _async_set_program_day(hass: HomeAssistant, call: ServiceCall) -> dict[str, Any]:
    """Update a schedule day and/or Eco/Comfort targets and return real results.

    Each write is awaited and confirmed by the coordinator before the service
    returns. Target writes are deliberately sent as independent PATCH requests,
    matching the existing number entities' known-good write path.
    """
    data = call.data
    device_id = str(data["device_id"])
    changes: dict[str, Any] = {}

    has_day = "day" in data
    has_periods = "periods" in data
    if has_day != has_periods:
        raise HomeAssistantError("Le jour et ses créneaux doivent être fournis ensemble.")
    if has_day:
        try:
            changes["days"] = {str(data["day"]): validate_periods(data["periods"])}
        except ValueError as err:
            raise HomeAssistantError(str(err)) from err

    if "eco_c" in data:
        changes["ecoC"] = _validate_target(float(data["eco_c"]), "Éco", 13.0, 19.0)
    if "comfort_c" in data:
        changes["comfortC"] = _validate_target(float(data["comfort_c"]), "Confort", 13.5, 30.0)
    if not changes:
        raise HomeAssistantError("Aucun changement de programme n'a été fourni.")

    coordinator = None
    for entry_data in hass.data.get(DOMAIN, {}).values():
        candidate = entry_data.get("coordinator") if isinstance(entry_data, dict) else None
        if candidate and candidate.find_device(device_id):
            coordinator = candidate
            break

    if coordinator is None:
        raise HomeAssistantError("Radiateur Econergy introuvable ou intégration non chargée.")

    current = coordinator.find_program(device_id) or {}
    eco = changes.get("ecoC", current.get("ecoC"))
    comfort = changes.get("comfortC", current.get("comfortC"))
    try:
        eco_value = float(eco)
        comfort_value = float(comfort)
    except (TypeError, ValueError) as err:
        raise HomeAssistantError("Les consignes Éco et Confort actuelles sont introuvables.") from err
    if comfort_value < eco_value + 0.5:
        raise HomeAssistantError("La consigne Confort doit être au moins 0,5 °C au-dessus de la consigne Éco.")

    settings = coordinator.settings.get(device_id) or {}
    maximum = settings.get("maxSetpointC", 30)
    try:
        maximum = float(maximum)
    except (TypeError, ValueError):
        maximum = 30.0
    if comfort_value > maximum:
        raise HomeAssistantError(
            f"La consigne Confort ({comfort_value:g} °C) dépasse la butée maximale du radiateur ({maximum:g} °C). "
            "Augmente d'abord la butée maximale dans les réglages du radiateur."
        )

    # Keep schedule and setpoint writes independent. The number entities write
    # one setpoint key per PATCH; the card now follows the same proven path.
    updates: list[dict[str, Any]] = []

    async def _write_one(label: str, payload: dict[str, Any]) -> None:
        result = await coordinator.async_update_program(device_id, payload)
        updates.append({
            "field": label,
            "command_id": result.get("command_id"),
            "command_status": result.get("command_status"),
            "confirmed": True,
        })

    try:
        if "days" in changes:
            await _write_one("programme", {"days": changes["days"]})

        eco_changed = "ecoC" in changes
        comfort_changed = "comfortC" in changes
        if eco_changed and comfort_changed:
            old_eco = float(current.get("ecoC"))
            old_comfort = float(current.get("comfortC"))
            # Avoid an invalid intermediate pair while applying two new targets.
            if eco_value > old_comfort - 0.5:
                await _write_one("consigne_confort", {"comfortC": comfort_value})
                await _write_one("consigne_eco", {"ecoC": eco_value})
            else:
                await _write_one("consigne_eco", {"ecoC": eco_value})
                await _write_one("consigne_confort", {"comfortC": comfort_value})
        elif eco_changed:
            await _write_one("consigne_eco", {"ecoC": eco_value})
        elif comfort_changed:
            await _write_one("consigne_confort", {"comfortC": comfort_value})

    except Exception as err:
        _LOGGER.error(
            "Échec de l'enregistrement du programme (%s, champs=%s, étapes_confirmées=%s)",
            device_id,
            ",".join(changes),
            len(updates),
            exc_info=True,
        )
        if updates:
            completed = ", ".join(item["field"] for item in updates)
            raise HomeAssistantError(
                f"Mise à jour partielle : {completed} confirmé(s), mais la suite a échoué : {err}"
            ) from err
        raise HomeAssistantError(f"Impossible de confirmer la mise à jour Econergy : {err}") from err

    return {
        "success": True,
        "device_id": device_id,
        "updates": updates,
    }


async def _async_register_program_service(hass: HomeAssistant) -> None:
    """Register a blocking, response-returning async service for the card."""
    if not hass.services.has_service(DOMAIN, SERVICE_SET_PROGRAM_DAY):
        async def _handle_program_service(call: ServiceCall) -> dict[str, Any]:
            return await _async_set_program_day(hass, call)

        # The callback must itself be async. A normal lambda returning a
        # coroutine is treated as a synchronous callback by Home Assistant,
        # which would leave the coroutine un-awaited.
        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_PROGRAM_DAY,
            _handle_program_service,
            schema=_PROGRAM_SERVICE_SCHEMA,
            supports_response=SupportsResponse.OPTIONAL,
        )


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up OAuth support and the bundled Lovelace card."""
    async_register_oauth_implementation(hass)
    await async_register_frontend(hass)
    await _async_register_program_service(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    # Ensure the bundled card is registered even on setups where async_setup
    # was not called before the config entry was loaded.
    async_register_oauth_implementation(hass)
    await async_register_frontend(hass)
    await _async_register_program_service(hass)

    # Remove retired helpers and the speculative dynamic settings entities
    # from 2.0.0b2. Keep the Eco/Comfort numbers and existing refresh button.
    registry = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        if entity.platform != DOMAIN:
            continue
        unique_id = str(entity.unique_id).lower()
        legacy_entity = (
            entity.domain in {"select", "time"}
            or (entity.domain == "text" and "program" in unique_id)
            or (entity.domain == "button" and "program" in unique_id and not unique_id.endswith("_open_program"))
            or (entity.domain == "binary_sensor" and unique_id.endswith("_window_open_state"))
            or (entity.domain == "switch" and not unique_id.endswith(("_keypadlocked", "_childprotection")))
            or (entity.domain == "number" and not unique_id.endswith(("_ecoc", "_comfortc", "_max_setpoint_c")))
        )
        if legacy_entity:
            registry.async_remove(entity.entity_id)

    session = async_get_clientsession(hass)
    implementation = await config_entry_oauth2_flow.async_get_config_entry_implementation(
        hass, entry
    )
    oauth_session = config_entry_oauth2_flow.OAuth2Session(
        hass, entry, implementation
    )
    api = EconergyApi(session, oauth_session=oauth_session)
    home_id = str(entry.data["home_id"])
    home_name = str(entry.data.get("home_name") or "Econergy")

    try:
        me, _ = await api.validate_home_access(home_id)
        coordinator = EconergyCoordinator(hass, entry, api, home_id, home_name)
        coordinator.token_expires_at = oauth_session.token.get("expires_at")
        await coordinator.async_initialize()
    except EconergyAuthError as err:
        raise ConfigEntryAuthFailed(
            "Autorisation Econergy invalide ou expirée. Reconnectez votre compte Econergy."
        ) from err
    except EconergyApiError as err:
        raise ConfigEntryNotReady(f"Accès à l'API Econergy impossible : {err}") from err
    except Exception as err:
        if isinstance(err, (ConfigEntryAuthFailed, ConfigEntryNotReady)):
            raise
        _LOGGER.debug("Échec de l'initialisation Econergy", exc_info=True)
        raise ConfigEntryNotReady("Initialisation de l'API Econergy impossible") from err

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "api": api,
        "coordinator": coordinator,
    }
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    coordinator.async_start_deferred_initialization(entry)
    return True


async def async_remove_config_entry_device(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    device_entry: dr.DeviceEntry,
) -> bool:
    """Allow removal only when Econergy no longer reports this radiator.

    This keeps active devices protected while allowing orphaned device records
    left behind after a radiator was re-paired or replaced to be removed.
    """
    entry_data = hass.data.get(DOMAIN, {}).get(config_entry.entry_id)
    coordinator = (
        entry_data.get("coordinator")
        if isinstance(entry_data, dict)
        else None
    )
    if coordinator is None or coordinator.data is None:
        return False

    device_ids = {
        str(identifier[1])
        for identifier in device_entry.identifiers
        if len(identifier) == 2 and identifier[0] == DOMAIN
    }
    if not device_ids:
        return False

    current_device_ids = {
        str(device.get("id"))
        for device in coordinator.data.get("devices", [])
        if device.get("id")
    }
    can_remove = device_ids.isdisjoint(current_device_ids)
    if can_remove:
        _LOGGER.info(
            "Suppression de l'ancien appareil Econergy du registre Home Assistant : %s",
            ", ".join(sorted(device_ids)),
        )
    return can_remove


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
        if not hass.data.get(DOMAIN):
            hass.services.async_remove(DOMAIN, SERVICE_SET_PROGRAM_DAY)
    return unloaded
