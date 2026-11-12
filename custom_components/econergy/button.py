"""Action buttons available directly on each Econergy radiator device page."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from homeassistant.components import persistent_notification
from homeassistant.components.button import ButtonEntity
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import EconergyApiError
from .const import DOMAIN
from .coordinator import EconergyCoordinator


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    coordinator: EconergyCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities(
        entity
        for device in coordinator.data.get("devices", [])
        if device.get("id")
        for entity in (
            EconergyProgramOpenButton(coordinator, device),
            EconergyRefreshInfoButton(coordinator, device),
            EconergyManualButton(coordinator, device),
        )
    )


class _EconergyButton(CoordinatorEntity, ButtonEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: EconergyCoordinator, device: dict[str, Any]) -> None:
        super().__init__(coordinator)
        self._device_id = str(device["id"])

    @property
    def _device(self) -> dict[str, Any]:
        return self.coordinator.find_device(self._device_id) or {}

    @property
    def device_info(self) -> DeviceInfo:
        device = self._device
        info = device.get("info") or {}
        firmware = info.get("firmware") or {}
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=f"Econergy {device.get('name') or 'Radiateur'}",
            manufacturer="Econergy / Carrera",
            model=str(info.get("reference") or "Radiateur connecté"),
            sw_version=str(firmware.get("version")) if firmware.get("version") else None,
        )


class EconergyProgramOpenButton(_EconergyButton):
    """Open this radiator's friendly weekly-program editor in the HA frontend."""

    _attr_name = "Programmes du radiateur"
    _attr_icon = "mdi:calendar-edit"

    def __init__(self, coordinator: EconergyCoordinator, device: dict[str, Any]) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{DOMAIN}_{self._device_id}_open_program"

    async def async_press(self) -> None:
        # A small frontend module listens for this event and navigates the
        # currently active Home Assistant UI to the dedicated program editor.
        self.hass.bus.async_fire(
            "econergy_program_requested",
            {"device_id": self._device_id},
        )


class EconergyRefreshInfoButton(_EconergyButton):
    """Refresh radiator state and daily consumption in one user action."""

    _attr_name = "Actualiser les infos"
    _attr_icon = "mdi:refresh"

    def __init__(self, coordinator: EconergyCoordinator, device: dict[str, Any]) -> None:
        super().__init__(coordinator, device)
        # Preserve the former status button unique_id so existing entity references survive.
        self._attr_unique_id = f"{DOMAIN}_{self._device_id}_request_status"
        self._last_result: dict[str, Any] | None = None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return dict(self._last_result or {})

    async def async_press(self) -> None:
        status_result: dict[str, Any] | None = None
        consumption_result: dict[str, Any] | None = None
        status_exception: str | None = None
        consumption_exception: str | None = None

        # A status request can be rate-limited or fail; always attempt the independent
        # daily-consumption read afterwards.
        try:
            status_result = await self.coordinator.async_request_device_status(self._device_id)
        except Exception as err:
            status_exception = str(err)

        try:
            consumption_result = await self.coordinator.async_refresh_consumption(self._device_id)
        except Exception as err:
            consumption_exception = str(err)

        status_error = status_exception or (
            str(status_result.get("error"))
            if status_result and status_result.get("error")
            else None
        )
        days = (
            consumption_result.get("days")
            if isinstance(consumption_result, dict)
            else (self.coordinator.consumption.get(self._device_id) or {}).get("days")
        ) or []

        self._last_result = {
            "date_actualisation": datetime.now().astimezone().isoformat(),
            "etat_frais": bool(status_result and status_result.get("fresh")),
            "statut_actualisation_etat": status_result.get("status") if status_result else (
                "ERREUR" if status_exception else "INCONNU"
            ),
            "erreur_actualisation_etat": status_error,
            "consommation_actualisee": consumption_exception is None,
            "nombre_de_jours_archive": len(days),
            "date_premier_releve": days[0].get("date") if days else None,
            "date_dernier_releve": days[-1].get("date") if days else None,
            "erreur_actualisation_consommation": consumption_exception,
        }
        self.async_write_ha_state()

        if status_exception and consumption_exception:
            raise HomeAssistantError(
                "Les actualisations de l'état et de la consommation ont toutes les deux échoué. "
                + "État : "
                + status_exception
                + " ; consommation : "
                + consumption_exception
            )


class EconergyManualButton(_EconergyButton):
    """Fetch the temporary manual URL only when the user requests it."""

    _attr_name = "Télécharger la notice"
    _attr_icon = "mdi:file-pdf-box"

    def __init__(self, coordinator: EconergyCoordinator, device: dict[str, Any]) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{DOMAIN}_{self._device_id}_get_manual"

    async def async_press(self) -> None:
        try:
            manual = await self.coordinator.async_get_manual(self._device_id, "fr")
        except EconergyApiError as err:
            raise HomeAssistantError(
                f"L'API Econergy n'a pas fourni le lien PDF attendu via "
                f"GET /devices/{self._device_id}/manual?lang=fr : {err}"
            ) from err
        except Exception as err:
            raise HomeAssistantError(
                f"Échec de la récupération de la notice Econergy : {err}"
            ) from err

        url = str(manual.get("url") or "")
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise HomeAssistantError("Econergy a retourné une adresse de notice invalide.")

        name = str(self._device.get("name") or "Radiateur")
        reference = str(manual.get("reference") or "")
        message = (
            f"[Ouvrir la notice PDF]({url})\n\n"
            "Le lien est temporaire et a été récupéré à l'instant depuis Econergy."
        )
        persistent_notification.async_create(
            self.hass,
            message,
            title=f"Notice Econergy – {name}{f' ({reference})' if reference else ''}",
            notification_id=f"econergy_manual_{self._device_id}",
        )
