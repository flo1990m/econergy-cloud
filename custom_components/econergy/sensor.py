"""Ambient-temperature and weekly-program sensors for Econergy radiators."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import UnitOfTemperature, UnitOfTime
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, WEEKDAYS
from .coordinator import EconergyCoordinator
from .program_helpers import format_schedule


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: EconergyCoordinator = data["coordinator"]
    entities = []
    for device in coordinator.data.get("devices", []):
        if not device.get("id"):
            continue
        entities.append(EconergyAmbientTemperatureSensor(coordinator, device))
        entities.append(EconergyDevicePowerSensor(coordinator, device))
        entities.append(EconergyFirmwareSensor(coordinator, device))
        entities.append(EconergyInstalledAtSensor(coordinator, device))
        entities.append(EconergyLastSeenSensor(coordinator, device))
        entities.append(EconergyStateUpdatedSensor(coordinator, device))
        entities.append(EconergySetpointKindSensor(coordinator, device))
        entities.append(EconergyLastCommandSensor(coordinator, device))
        entities.append(EconergyConsumptionSensor(coordinator, device, "estimatedKWh"))
        entities.append(EconergyConsumptionSensor(coordinator, device, "heatingSeconds"))
        # Create it immediately; its state fills when the deferred API read completes.
        entities.append(EconergyWeeklyProgramSensor(coordinator, device))
    async_add_entities(entities)


class _EconergyDeviceEntity(CoordinatorEntity):
    def __init__(self, coordinator: EconergyCoordinator, device: dict[str, Any]) -> None:
        super().__init__(coordinator)
        self._device_id = str(device["id"])

    @property
    def _device(self) -> dict[str, Any] | None:
        return self.coordinator.find_device(self._device_id)

    @property
    def device_info(self) -> DeviceInfo:
        device = self._device or {}
        info = device.get("info") or {}
        firmware = info.get("firmware") or {}
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=f"Econergy {device.get('name') or 'Radiateur'}",
            manufacturer="Econergy / Carrera",
            model=str(info.get("reference") or "Radiateur connecté"),
            sw_version=str(firmware.get("version")) if firmware.get("version") else None,
        )


class EconergyAmbientTemperatureSensor(_EconergyDeviceEntity, SensorEntity):
    """Expose the last temperature reported by the radiator."""

    _attr_has_entity_name = True
    _attr_name = "Température ambiante"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_suggested_display_precision = 1
    _attr_icon = "mdi:thermometer"

    def __init__(self, coordinator: EconergyCoordinator, device: dict[str, Any]) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{DOMAIN}_{self._device_id}_ambient_temperature"

    @property
    def native_value(self) -> float | None:
        value = ((self._device or {}).get("state") or {}).get("measuredC")
        try:
            return round(float(value), 1) if value is not None else None
        except (ValueError, TypeError):
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        device = self._device or {}
        state = device.get("state") or {}
        info = device.get("info") or {}
        firmware = info.get("firmware") or {}
        request = device.get("_ha_status_request") or {}
        return {
            "econergy_device_id": self._device_id,
            "mode": state.get("mode"),
            "consigne_c": state.get("setpointC"),
            "state_updated_at": state.get("updatedAt"),
            "last_seen_at": device.get("lastSeenAt"),
            "derniere_demande_statut": request.get("requested_at"),
            "commande_actualisation_id": request.get("command_id"),
            "commande_actualisation_statut": request.get("command_status"),
            "actualisation_confirmee": request.get("fresh"),
            "statut_actualisation": request.get("status"),
            "erreur_actualisation": request.get("error"),
            "state_updated_at_apres_demande": request.get("state_updated_at"),
            "reference": info.get("reference"),
            "puissance_nominale_w": info.get("powerW"),
            "firmware": firmware.get("version"),
            "api_version": self.coordinator.data.get("api_version") if self.coordinator.data else None,
            "api_settings": self.coordinator.settings.get(self._device_id),
            "api_device_state": state,
            "api_consumption_15_days": self.coordinator.consumption.get(self._device_id),
            "api_device_info": info,
            "api_device_field_names": sorted(str(key) for key in device if not str(key).startswith("_")),
        }


class EconergyWeeklyProgramSensor(_EconergyDeviceEntity, SensorEntity):
    """Expose Eco/Comfort targets and all seven day's Comfort periods."""

    _attr_has_entity_name = True
    _attr_name = "Programme hebdomadaire"
    _attr_icon = "mdi:calendar-week"

    def __init__(self, coordinator: EconergyCoordinator, device: dict[str, Any]) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{DOMAIN}_{self._device_id}_weekly_program"

    @property
    def _program(self) -> dict[str, Any] | None:
        return self.coordinator.find_program(self._device_id)

    @property
    def native_value(self) -> str | None:
        program = self._program
        if not program:
            return None
        return f"Éco {program.get('ecoC')} °C · Confort {program.get('comfortC')} °C"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        program = self._program or {}
        raw_days = program.get("days") or {}
        return {
            "econergy_device_id": self._device_id,
            "eco_c": program.get("ecoC"),
            "comfort_c": program.get("comfortC"),
            "max_setpoint_c": (self.coordinator.settings.get(self._device_id) or {}).get("maxSetpointC", 30),
            "jours": {
                day_name: format_schedule(raw_days.get(day_key, [])) or "Éco toute la journée"
                for day_key, day_name in WEEKDAYS.items()
            },
            "days_api": raw_days,
            "empty_day_means": "Éco toute la journée",
            "timezone": "Heure locale du domicile (Europe/Paris selon la documentation Econergy)",
        }


class EconergyDevicePowerSensor(_EconergyDeviceEntity, SensorEntity):
    """Nominal radiator power reported by the API."""

    _attr_has_entity_name = True
    _attr_name = "Puissance nominale"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = "W"
    _attr_icon = "mdi:flash"

    def __init__(self, coordinator: EconergyCoordinator, device: dict[str, Any]) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{DOMAIN}_{self._device_id}_nominal_power"

    @property
    def native_value(self) -> float | None:
        value = ((self._device or {}).get("info") or {}).get("powerW")
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None


class EconergyFirmwareSensor(_EconergyDeviceEntity, SensorEntity):
    """Firmware version reported by the API."""

    _attr_has_entity_name = True
    _attr_name = "Firmware"
    _attr_icon = "mdi:chip"

    def __init__(self, coordinator: EconergyCoordinator, device: dict[str, Any]) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{DOMAIN}_{self._device_id}_firmware"

    @property
    def native_value(self) -> str | None:
        firmware = (((self._device or {}).get("info") or {}).get("firmware") or {})
        value = firmware.get("version")
        return str(value) if value is not None else None


class EconergyInstalledAtSensor(_EconergyDeviceEntity, SensorEntity):
    """Radiator installation date reported in the device information."""

    _attr_has_entity_name = True
    _attr_name = "Date d'installation"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:calendar-check-outline"

    def __init__(self, coordinator: EconergyCoordinator, device: dict[str, Any]) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{DOMAIN}_{self._device_id}_installed_at"

    @property
    def native_value(self):
        value = ((self._device or {}).get("info") or {}).get("installedAt")
        if not isinstance(value, str) or not value:
            return None
        from datetime import datetime
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None


class EconergyLastSeenSensor(_EconergyDeviceEntity, SensorEntity):
    """Last communication timestamp reported by the API."""

    _attr_has_entity_name = True
    _attr_name = "Dernière communication"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:cloud-check-outline"

    def __init__(self, coordinator: EconergyCoordinator, device: dict[str, Any]) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{DOMAIN}_{self._device_id}_last_seen"

    @property
    def native_value(self):
        value = (self._device or {}).get("lastSeenAt")
        if not isinstance(value, str) or not value:
            return None
        from datetime import datetime
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None


class EconergyStateUpdatedSensor(_EconergyDeviceEntity, SensorEntity):
    """Actual timestamp of the last full state report, not the API request time."""

    _attr_has_entity_name = True
    _attr_name = "Dernière remontée d'état"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:clock-check-outline"

    def __init__(self, coordinator: EconergyCoordinator, device: dict[str, Any]) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{DOMAIN}_{self._device_id}_state_updated_at"

    @property
    def native_value(self):
        value = ((self._device or {}).get("state") or {}).get("updatedAt")
        if not isinstance(value, str) or not value:
            return None
        from datetime import datetime
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None


class EconergySetpointKindSensor(_EconergyDeviceEntity, SensorEntity):
    """Operating regime currently used by the program: Comfort, Eco, or Manual."""

    _attr_has_entity_name = True
    _attr_name = "Régime appliqué"
    _attr_icon = "mdi:thermostat-auto"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["Confort", "Éco", "Manuel"]

    def __init__(self, coordinator: EconergyCoordinator, device: dict[str, Any]) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{DOMAIN}_{self._device_id}_setpoint_kind"

    @property
    def native_value(self) -> str | None:
        value = ((self._device or {}).get("state") or {}).get("setpointKind")
        return {"COMFORT": "Confort", "ECO": "Éco", "MANUAL": "Manuel"}.get(
            str(value).upper() if value is not None else ""
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        state = (self._device or {}).get("state") or {}
        return {"mode": state.get("mode"), "consigne_c": state.get("setpointC")}


class EconergyConsumptionSensor(_EconergyDeviceEntity, SensorEntity):
    """Most recent daily consumption point, with all 15 days retained as attributes."""

    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: EconergyCoordinator, device: dict[str, Any], field: str) -> None:
        super().__init__(coordinator, device)
        self._field = field
        if field == "estimatedKWh":
            self._attr_name = "Consommation estimée (dernier jour)"
            self._attr_unique_id = f"{DOMAIN}_{self._device_id}_consumption_latest_day"
            self._attr_device_class = SensorDeviceClass.ENERGY
            self._attr_native_unit_of_measurement = "kWh"
            self._attr_suggested_display_precision = 2
            self._attr_icon = "mdi:lightning-bolt"
        else:
            self._attr_name = "Durée de chauffe (dernier jour)"
            self._attr_unique_id = f"{DOMAIN}_{self._device_id}_heating_duration_latest_day"
            self._attr_device_class = SensorDeviceClass.DURATION
            self._attr_native_unit_of_measurement = UnitOfTime.HOURS
            self._attr_suggested_display_precision = 1
            self._attr_icon = "mdi:timer-outline"

    @property
    def _consumption(self) -> dict[str, Any]:
        return self.coordinator.consumption.get(self._device_id, {})

    @property
    def _latest_day(self) -> dict[str, Any] | None:
        days = self._consumption.get("days") or []
        return days[-1] if days and isinstance(days[-1], dict) else None

    @property
    def native_value(self) -> float | None:
        day = self._latest_day
        if not day or day.get(self._field) is None:
            return None
        try:
            value = float(day[self._field])
            return value / 3600 if self._field == "heatingSeconds" else value
        except (TypeError, ValueError):
            return None

    @property
    def available(self) -> bool:
        return super().available and self._latest_day is not None and self._field in self._latest_day

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        days = self._consumption.get("days") or []
        return {
            "econergy_device_id": self._device_id,
            "date_du_releve": (self._latest_day or {}).get("date"),
            "puissance_nominale_w": self._consumption.get("powerW"),
            "jours_disponibles": days,
            "nombre_de_jours": len(days),
            "valeur_null_signifie": "Aucune remontée du radiateur pour cette journée, ce n'est pas une consommation nulle.",
            "nature_estimation": "Durée de chauffe × puissance nominale ; ce n'est pas un relevé de compteur.",
            "erreur_api": self.coordinator.consumption_errors.get(self._device_id),
            "date_du_cache": self.coordinator.consumption_loaded_date,
        }


class EconergyLastCommandSensor(_EconergyDeviceEntity, SensorEntity):
    """Most recent write acknowledgement returned by Econergy."""

    _attr_has_entity_name = True
    _attr_name = "Statut de la dernière commande"
    _attr_icon = "mdi:check-network-outline"

    def __init__(self, coordinator: EconergyCoordinator, device: dict[str, Any]) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{DOMAIN}_{self._device_id}_last_command_status"

    @property
    def native_value(self) -> str | None:
        command = self.coordinator.last_commands.get(self._device_id) or {}
        status = command.get("status")
        return str(status) if status else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        command = self.coordinator.last_commands.get(self._device_id) or {}
        return {
            "command_id": command.get("command_id"),
            "type": command.get("kind"),
            "date": command.get("updated_at"),
        }
