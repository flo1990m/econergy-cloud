"""Editable radiator identity fields for Econergy."""
from __future__ import annotations

from typing import Any

from homeassistant.components.text import TextEntity, TextMode
from homeassistant.exceptions import HomeAssistantError
from homeassistant.const import EntityCategory
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import EconergyCoordinator


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    coordinator: EconergyCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities(
        EconergyDeviceNameText(coordinator, device)
        for device in coordinator.data.get("devices", [])
        if device.get("id")
    )


class EconergyDeviceNameText(CoordinatorEntity, TextEntity):
    """Rename a radiator with the documented PATCH /devices/{deviceId} endpoint."""

    _attr_has_entity_name = True
    _attr_name = "Nom du radiateur"
    _attr_icon = "mdi:form-textbox"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = TextMode.TEXT
    _attr_native_min = 0
    _attr_native_max = 50

    def __init__(self, coordinator: EconergyCoordinator, device: dict[str, Any]) -> None:
        super().__init__(coordinator)
        self._device_id = str(device["id"])
        self._attr_unique_id = f"{DOMAIN}_{self._device_id}_device_name"

    @property
    def _device(self) -> dict[str, Any]:
        return self.coordinator.find_device(self._device_id) or {}

    @property
    def native_value(self) -> str:
        return str(self._device.get("name") or "Radiateur")

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

    async def async_set_value(self, value: str) -> None:
        try:
            await self.coordinator.async_rename_device(self._device_id, value)
        except Exception as err:
            raise HomeAssistantError(f"Renommage du radiateur impossible : {err}") from err
        self.async_write_ha_state()
