"""Econergy radiators: ambient temperature and cloud control."""
from __future__ import annotations

from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature, HVACMode
from homeassistant.const import UnitOfTemperature, ATTR_TEMPERATURE
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.event import async_track_time_change
from homeassistant.util import dt as dt_util
from .schedule import effective_target_temperature
from .api import EconergyApiError, EconergyAuthError
from .const import DOMAIN

PRESET_MANUAL = "Manuel"
PRESET_FROST = "Hors gel"
PRESET_SCHEDULE = "Programmation"
MODES = {0: "Arrêt", 1: PRESET_FROST, 3: PRESET_MANUAL, 4: PRESET_SCHEDULE}
PRESET_CODES = {PRESET_FROST: 1, PRESET_MANUAL: 3, PRESET_SCHEDULE: 4}


async def async_setup_entry(hass, entry, async_add_entities):
    api, coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        EconergyRadiator(api, coordinator, device)
        for device in coordinator.data.get("devices", [])
        if isinstance(device, dict) and device.get("_id")
    ])


class EconergyRadiator(CoordinatorEntity, ClimateEntity):
    _attr_has_entity_name = True
    _attr_name = None
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.PRESET_MODE
    )
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
    _attr_preset_modes = [PRESET_MANUAL, PRESET_FROST, PRESET_SCHEDULE]
    _attr_target_temperature_step = 0.5
    _attr_min_temp = 7
    _attr_max_temp = 30
    _attr_icon = "mdi:radiator"

    def __init__(self, api, coordinator, device):
        super().__init__(coordinator)
        self._api = api
        self._device_id = str(device["_id"])
        self._attr_unique_id = f"econergy_cloud_{self._device_id}_climate"

    @property
    def _device(self):
        return next((d for d in self.coordinator.data.get("devices", [])
                     if str(d.get("_id")) == self._device_id), None)

    @property
    def _room_label(self):
        device = self._device or {}
        room_id = (device.get("data") or {}).get("room")
        for room in self.coordinator.data.get("rooms") or []:
            if room.get("uuid") == room_id:
                return str(room.get("label") or "Radiateur")
        return "Radiateur"

    @property
    def device_info(self):
        return DeviceInfo(identifiers={(DOMAIN, self._device_id)},
                          name=f"Radiateur {self._room_label}",
                          manufacturer="Econergy / Carrera", model="Wi-Fi radiator")

    @property
    def _raw_mode(self):
        return ((self._device or {}).get("config") or {}).get("mode")

    @property
    def hvac_mode(self):
        if self._raw_mode is None:
            return None
        return HVACMode.OFF if self._raw_mode == 0 else HVACMode.HEAT

    @property
    def preset_mode(self):
        return MODES.get(self._raw_mode) if self._raw_mode in (1, 3, 4) else None

    @property
    def current_temperature(self):
        value = ((self._device or {}).get("status") or {}).get("temperature")
        try:
            return round(float(value), 1) if value is not None else None
        except (ValueError, TypeError):
            return None

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        # Refresh displayed schedule target at each minute boundary, even
        # between two 120-second API polls. Does not send device commands.
        self.async_on_remove(
            async_track_time_change(
                self.hass, self._on_clock_minute, second=0
            )
        )

    async def _on_clock_minute(self, now):
        # Run on Home Assistant's event loop, never in the executor thread.
        self.async_write_ha_state()

    @property
    def target_temperature(self):
        config = ((self._device or {}).get("config") or {})
        return effective_target_temperature(config, dt_util.now())

    @property
    def extra_state_attributes(self):
        dev = self._device or {}
        config = dev.get("config") or {}
        return {"econergy_mode_raw": self._raw_mode,
                "econergy_state_raw": (dev.get("status") or {}).get("state"),
                "econergy_manual_setpoint": config.get("setPoint"),
                "econergy_eco_setpoint": config.get("eco"),
                "econergy_comfort_setpoint": config.get("comfort"),
                "econergy_setpoint_applies_in_manual": True}

    async def _write(self, *, mode=None, temperature=None):
        try:
            await self._api.set_radiator(self._device_id, mode=mode, temperature=temperature)
        except (EconergyAuthError, EconergyApiError) as exc:
            raise HomeAssistantError(f"Commande Econergy refusée : {exc}") from exc
        # Force a fresh read after a user command; do not let the coordinator's
        # request-refresh debounce delay the state confirmation shown in HA.
        await self.coordinator.async_refresh()

    async def async_set_temperature(self, **kwargs):
        value = kwargs.get(ATTR_TEMPERATURE)
        if value is None:
            return
        temperature = float(value)
        if not self.min_temp <= temperature <= self.max_temp:
            raise HomeAssistantError("Consigne hors limites (7–30 °C)")
        if abs(temperature * 2 - round(temperature * 2)) > 0.0001:
            raise HomeAssistantError("La consigne doit être un multiple de 0,5 °C")
        await self._write(mode=3, temperature=temperature)

    async def async_set_hvac_mode(self, hvac_mode):
        if hvac_mode == HVACMode.OFF:
            await self._write(mode=0)
        elif hvac_mode == HVACMode.HEAT:
            await self._write(mode=3)
        else:
            raise HomeAssistantError("Mode HVAC non pris en charge")

    async def async_set_preset_mode(self, preset_mode):
        if preset_mode not in PRESET_CODES:
            raise HomeAssistantError("Préréglage Econergy inconnu")
        await self._write(mode=PRESET_CODES[preset_mode])
