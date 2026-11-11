"""Documented on/off settings for Econergy radiators."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import EconergyCoordinator


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    coordinator: EconergyCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    entities = []
    for device in coordinator.data.get("devices", []):
        device_id = str(device.get("id") or "")
        if device_id:
            entities.extend([
                EconergyDocumentedSettingSwitch(coordinator, device, "keypadLocked"),
                EconergyDocumentedSettingSwitch(coordinator, device, "childProtection"),
            ])
    async_add_entities(entities)


class EconergyDocumentedSettingSwitch(CoordinatorEntity, SwitchEntity):
    """A boolean setting from GET/PATCH /devices/{id}/settings."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: EconergyCoordinator, device: dict[str, Any], key: str) -> None:
        super().__init__(coordinator)
        self._device_id = str(device["id"])
        self._key = key
        if key == "keypadLocked":
            self._attr_name = "Verrouillage du clavier"
            self._attr_icon = "mdi:lock"
        else:
            self._attr_name = "Protection enfant"
            self._attr_icon = "mdi:account-child"
        self._attr_unique_id = f"{DOMAIN}_{self._device_id}_{key}"

    @property
    def _settings(self) -> dict[str, Any]:
        return self.coordinator.settings.get(self._device_id, {})

    @property
    def is_on(self) -> bool | None:
        value = self._settings.get(self._key)
        return value if isinstance(value, bool) else None

    @property
    def available(self) -> bool:
        return super().available and isinstance(self._settings.get(self._key), bool)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        description = (
            "Empêche les modifications involontaires depuis le clavier du radiateur."
            if self._key == "keypadLocked"
            else "Limite la chauffe des parois du radiateur."
        )
        return {
            "econergy_device_id": self._device_id,
            "api_setting": self._key,
            "description": description,
            "api_error": self.coordinator.settings_errors.get(self._device_id),
        }

    @property
    def device_info(self) -> DeviceInfo:
        device = self.coordinator.find_device(self._device_id) or {}
        info = device.get("info") or {}
        firmware = info.get("firmware") or {}
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=f"Econergy {device.get('name') or 'Radiateur'}",
            manufacturer="Econergy / Carrera",
            model=str(info.get("reference") or "Radiateur connecté"),
            sw_version=str(firmware.get("version")) if firmware.get("version") else None,
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set_value(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set_value(False)

    async def _set_value(self, value: bool) -> None:
        try:
            await self.coordinator.async_update_device_setting(self._device_id, self._key, value)
        except Exception as err:
            raise HomeAssistantError(f"Modification de {self._attr_name.lower()} impossible : {err}") from err
        self.async_write_ha_state()
