"""Ambient temperature measurements from Econergy Cloud."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfTemperature
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    api, coordinator = hass.data[DOMAIN][entry.entry_id]
    devices = coordinator.data.get("devices") or []
    async_add_entities([
        EconergyTemperatureSensor(coordinator, entry.entry_id, device)
        for device in devices if isinstance(device, dict) and device.get("_id")
    ])


class EconergyTemperatureSensor(CoordinatorEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:thermometer"
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry_id, device):
        super().__init__(coordinator)
        self._device_id = str(device["_id"])
        self._attr_unique_id = f"econergy_cloud_{self._device_id}_temperature"
        self._attr_name = "Température ambiante"
        self._entry_id = entry_id

    @property
    def _device(self):
        return next((d for d in (self.coordinator.data.get("devices") or [])
                     if str(d.get("_id")) == self._device_id), None)

    @property
    def _room_label(self):
        d = self._device
        if not d:
            return "Radiateur"
        room_id = (d.get("data") or {}).get("room")
        for room in self.coordinator.data.get("rooms") or []:
            if room.get("uuid") == room_id:
                return str(room.get("label") or "Radiateur")
        return "Radiateur"

    @property
    def device_info(self):
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=f"Radiateur {self._room_label}",
            manufacturer="Econergy / Carrera",
            model="Wi-Fi radiator",
        )

    @property
    def native_value(self):
        device = self._device
        if not device:
            return None
        value = (device.get("status") or {}).get("temperature")
        try:
            return round(float(value), 1) if value is not None else None
        except (ValueError, TypeError):
            return None

    @property
    def available(self):
        return super().available and self._device is not None
