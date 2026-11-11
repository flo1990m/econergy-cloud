"""Read-only runtime states returned by the Econergy API."""
from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import EconergyCoordinator


_FIELDS = (
    ("windowOpen", "Fenêtre détectée ouverte", "window", "mdi:window-open-variant"),
    ("heating", "Chauffage en cours", "running", "mdi:radiator"),
    ("fanBoost", "Ventilateur boost", "running", "mdi:fan"),
)


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        token = value.strip().lower()
        if token in {"true", "on", "yes", "open", "opened", "active", "running", "1", "boost"}:
            return True
        if token in {"false", "off", "no", "closed", "inactive", "stopped", "0", "none", ""}:
            return False
    return None


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    coordinator: EconergyCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    entities = []
    for device in coordinator.data.get("devices", []):
        if not device.get("id"):
            continue
        state = device.get("state") or {}
        for key, name, device_class, icon in _FIELDS:
            if key in state and (key != "fanBoost" or state.get(key) is not None):
                entities.append(EconergyRuntimeBinarySensor(coordinator, device, key, name, device_class, icon))
    async_add_entities(entities)


class EconergyRuntimeBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """A runtime sensor such as heating, window open, or fan boost."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, device, key, name, device_class, icon) -> None:
        super().__init__(coordinator)
        self._device_id = str(device["id"])
        self._key = key
        self._attr_name = name
        self._attr_icon = icon
        self._attr_unique_id = f"{DOMAIN}_{self._device_id}_{key.lower()}"
        if device_class == "window":
            self._attr_device_class = BinarySensorDeviceClass.WINDOW
        elif device_class == "running":
            self._attr_device_class = BinarySensorDeviceClass.RUNNING

    @property
    def _device(self) -> dict[str, Any]:
        return self.coordinator.find_device(self._device_id) or {}

    @property
    def _state(self) -> dict[str, Any]:
        return self._device.get("state") or {}

    @property
    def is_on(self) -> bool | None:
        return _as_bool(self._state.get(self._key))

    @property
    def available(self) -> bool:
        return super().available and self._key in self._state and _as_bool(self._state.get(self._key)) is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "econergy_device_id": self._device_id,
            "valeur_api_brute": self._state.get(self._key),
            "state_updated_at": self._state.get("updatedAt"),
        }

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
