"""Temperature numbers for Econergy programs and documented max-setpoint limit."""
from __future__ import annotations

from typing import Any

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import EconergyCoordinator


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: EconergyCoordinator = data["coordinator"]
    entities = []
    for device in coordinator.data.get("devices", []):
        device_id = str(device.get("id") or "")
        if not device_id:
            continue
        entities.append(EconergyProgramNumber(coordinator, device, "ecoC"))
        entities.append(EconergyProgramNumber(coordinator, device, "comfortC"))
        entities.append(EconergyMaximumSetpointNumber(coordinator, device))
    async_add_entities(entities)


class _EconergyNumber(CoordinatorEntity, NumberEntity):
    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_step = 0.5
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: EconergyCoordinator, device: dict[str, Any]) -> None:
        super().__init__(coordinator)
        self._device_id = str(device["id"])

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


class EconergyProgramNumber(_EconergyNumber):
    """Editable Eco or Comfort target, PATCHed independently from HVAC mode."""

    def __init__(self, coordinator: EconergyCoordinator, device: dict[str, Any], key: str) -> None:
        super().__init__(coordinator, device)
        self._key = key
        self._attr_unique_id = f"{DOMAIN}_{self._device_id}_{key.lower()}"
        self._attr_name = "Consigne Éco" if key == "ecoC" else "Consigne Confort"

    @property
    def _program(self) -> dict[str, Any] | None:
        return self.coordinator.find_program(self._device_id)

    @property
    def native_value(self) -> float | None:
        value = (self._program or {}).get(self._key)
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @property
    def native_min_value(self) -> float:
        program = self._program or {}
        if self._key == "comfortC":
            try:
                return max(13.5, float(program.get("ecoC", 13)) + 0.5)
            except (TypeError, ValueError):
                return 13.5
        return 13.0

    @property
    def native_max_value(self) -> float:
        program = self._program or {}
        settings = self.coordinator.settings.get(self._device_id) or {}
        device_limit = settings.get("maxSetpointC", 30)
        try:
            device_limit = float(device_limit)
        except (TypeError, ValueError):
            device_limit = 30.0
        if self._key == "ecoC":
            try:
                return min(19.0, float(program.get("comfortC", 30)) - 0.5)
            except (TypeError, ValueError):
                return 19.0
        return min(30.0, device_limit)

    @property
    def available(self) -> bool:
        return super().available and self._program is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "econergy_device_id": self._device_id,
            "program_mode_unchanged": True,
            "last_command": self.coordinator.last_commands.get(self._device_id),
        }

    async def async_set_native_value(self, value: float) -> None:
        try:
            target = float(value)
        except (TypeError, ValueError) as err:
            raise HomeAssistantError("Consigne de programme invalide.") from err
        if abs(target * 2 - round(target * 2)) > 0.0001:
            raise HomeAssistantError("Les consignes doivent être réglées par pas de 0,5 °C.")
        if self._key == "ecoC":
            if not 13 <= target <= 19:
                raise HomeAssistantError("La consigne Éco doit être comprise entre 13 et 19 °C.")
            comfort = float((self._program or {}).get("comfortC", 0))
            if target >= comfort:
                raise HomeAssistantError("La consigne Éco doit rester au moins 0,5 °C sous la consigne Confort.")
        else:
            if not 13.5 <= target <= self.native_max_value:
                raise HomeAssistantError("La consigne Confort dépasse les limites autorisées du radiateur.")
            eco = float((self._program or {}).get("ecoC", 0))
            if target < eco + 0.5:
                raise HomeAssistantError("La consigne Confort doit être au moins 0,5 °C au-dessus de la consigne Éco.")

        try:
            result = await self.coordinator.async_update_program(self._device_id, {self._key: target})
        except Exception as err:
            raise HomeAssistantError(f"Mise à jour du programme Econergy impossible : {err}") from err
        self.async_write_ha_state()


class EconergyMaximumSetpointNumber(_EconergyNumber):
    """Maximum allowed heating temperature, enforced by the radiator itself."""

    _attr_name = "Butée de température max"
    _attr_icon = "mdi:thermometer-chevron-up"

    def __init__(self, coordinator: EconergyCoordinator, device: dict[str, Any]) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{DOMAIN}_{self._device_id}_max_setpoint_c"

    @property
    def native_value(self) -> float | None:
        value = (self.coordinator.settings.get(self._device_id) or {}).get("maxSetpointC")
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @property
    def native_min_value(self) -> float:
        return 13.5

    @property
    def native_max_value(self) -> float:
        return 30.0

    @property
    def available(self) -> bool:
        return super().available and self.native_value is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "econergy_device_id": self._device_id,
            "30_c_signifie": "Aucune butée maximale",
            "regle_api": "Ne peut pas être inférieure à la consigne manuelle ou Confort en place.",
            "last_command": self.coordinator.last_commands.get(self._device_id),
        }

    async def async_set_native_value(self, value: float) -> None:
        try:
            await self.coordinator.async_update_device_setting(
                self._device_id, "maxSetpointC", float(value)
            )
        except Exception as err:
            raise HomeAssistantError(f"Modification de la butée maximale impossible : {err}") from err
        self.async_write_ha_state()
