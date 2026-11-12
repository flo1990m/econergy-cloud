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
            EconergyRefreshStatusButton(coordinator, device),
            EconergyRefreshConsumptionButton(coordinator, device),
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


class EconergyRefreshStatusButton(_EconergyButton):
    """Ask the radiator for a fresh complete state (one request/minute max)."""

    _attr_name = "Actualiser l'état"
    _attr_icon = "mdi:refresh"

    def __init__(self, coordinator: EconergyCoordinator, device: dict[str, Any]) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{DOMAIN}_{self._device_id}_request_status"
        self._last_result: dict[str, Any] | None = None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return dict(self._last_result or {})

    async def async_press(self) -> None:
        try:
            self._last_result = await self.coordinator.async_request_device_status(self._device_id)
        except Exception as err:
            raise HomeAssistantError(f"Actualisation Econergy impossible : {err}") from err
        self.async_write_ha_state()


class EconergyRefreshConsumptionButton(_EconergyButton):
    """Refresh the official 15-day daily consumption report."""

    _attr_name = "Actualiser la consommation"
    _attr_icon = "mdi:refresh"

    def __init__(self, coordinator: EconergyCoordinator, device: dict[str, Any]) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{DOMAIN}_{self._device_id}_refresh_consumption"
        self._last_refresh: str | None = None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        days = (self.coordinator.consumption.get(self._device_id) or {}).get("days") or []
        api_days = days[-15:]
        return {
            "dernier_rechargement": self._last_refresh,
            "nombre_de_jours": len(api_days),
            "nombre_de_jours_archive": len(days),
            "date_debut_archive": days[0].get("date") if days else None,
            "date_fin_archive": days[-1].get("date") if days else None,
            "erreur_api": self.coordinator.consumption_errors.get(self._device_id),
        }

    async def async_press(self) -> None:
        try:
            await self.coordinator.async_refresh_consumption(self._device_id)
            self._last_refresh = datetime.now().astimezone().isoformat()
        except Exception as err:
            raise HomeAssistantError(f"Lecture de la consommation Econergy impossible : {err}") from err
        self.async_write_ha_state()


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
            if "MANUAL_NOT_FOUND" in str(err):
                device = self._device
                info = device.get("info") or {}
                reference = str(info.get("reference") or "référence inconnue")
                name = str(device.get("name") or "Radiateur")
                persistent_notification.async_create(
                    self.hass,
                    f"Aucune notice PDF n'est actuellement disponible sur les serveurs Econergy pour le modèle **{reference}**.",
                    title=f"Notice Econergy indisponible – {name}",
                    notification_id=f"econergy_manual_unavailable_{self._device_id}",
                )
                return
            raise HomeAssistantError(
                f"Notice Econergy indisponible pour ce radiateur : {err}"
            ) from err
        except Exception as err:
            raise HomeAssistantError(
                f"Notice Econergy indisponible pour ce radiateur : {err}"
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
