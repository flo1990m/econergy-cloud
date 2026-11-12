"""Ambient-temperature and weekly-program sensors for Econergy radiators."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import UnitOfTemperature, UnitOfTime
from homeassistant.util import dt as dt_util
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
        consumption = self.coordinator.consumption.get(self._device_id) or {}
        consumption_days = consumption.get("days") or []
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
            "api_consumption_15_days": {
                **consumption,
                "days": consumption_days[-15:],
            },
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
    _attr_options = ["Arrêt", "Hors gel", "Manuel", "Confort", "Éco", "Programmation", "Non déterminé"]

    def __init__(self, coordinator: EconergyCoordinator, device: dict[str, Any]) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{DOMAIN}_{self._device_id}_setpoint_kind"

    @property
    def native_value(self) -> str:
        device = self._device or {}
        state = device.get("state") or {}

        # Prefer the explicit API field when it is available.
        kind = str(state.get("setpointKind") or "").strip().upper()
        kind_values = {
            "COMFORT": "Confort",
            "CONFORT": "Confort",
            "ECO": "Éco",
            "MANUAL": "Manuel",
            "FROST": "Hors gel",
            "OFF": "Arrêt",
        }
        if kind in kind_values:
            return kind_values[kind]

        mode = str(state.get("mode") or "").strip().upper()
        if mode == "OFF":
            return "Arrêt"
        if mode == "FROST":
            return "Hors gel"
        if mode == "MANUAL":
            return "Manuel"
        if mode != "PROG":
            return "Non déterminé"

        # In PROG, compare the live setpoint with the schedule targets first.
        program = self.coordinator.find_program(self._device_id) or {}
        try:
            setpoint = float(state.get("setpointC"))
            eco = float(program.get("ecoC"))
            comfort = float(program.get("comfortC"))
            if abs(setpoint - comfort) < 0.1:
                return "Confort"
            if abs(setpoint - eco) < 0.1:
                return "Éco"
        except (TypeError, ValueError):
            pass

        # If setpointKind is absent, use the current local time and the
        # published weekly comfort periods to determine the active regime.
        days = program.get("days") or {}
        day_keys = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
        now = dt_util.now()
        day_periods = days.get(day_keys[now.weekday()], [])
        now_minutes = now.hour * 60 + now.minute
        for period in day_periods if isinstance(day_periods, list) else []:
            if not isinstance(period, dict):
                continue
            try:
                start_hour, start_minute = (int(part) for part in str(period.get("start")).split(":"))
                end_hour, end_minute = (int(part) for part in str(period.get("end")).split(":"))
                start_minutes = start_hour * 60 + start_minute
                end_minutes = end_hour * 60 + end_minute
            except (TypeError, ValueError):
                continue
            if start_minutes <= now_minutes < end_minutes:
                return "Confort"

        return "Éco" if program else "Programmation"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        state = (self._device or {}).get("state") or {}
        program = self.coordinator.find_program(self._device_id) or {}
        return {
            "mode": state.get("mode"),
            "consigne_c": state.get("setpointC"),
            "setpoint_kind_api": state.get("setpointKind"),
            "eco_c": program.get("ecoC"),
            "comfort_c": program.get("comfortC"),
        }


class EconergyConsumptionSensor(_EconergyDeviceEntity, SensorEntity):
    """Most recent daily consumption point, with all 15 days retained as attributes."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: EconergyCoordinator, device: dict[str, Any], field: str) -> None:
        super().__init__(coordinator, device)
        self._field = field
        if field == "estimatedKWh":
            self._attr_state_class = SensorStateClass.TOTAL
            self._attr_name = "Consommation estimée (dernier jour)"
            self._attr_unique_id = f"{DOMAIN}_{self._device_id}_consumption_latest_day"
            self._attr_device_class = SensorDeviceClass.ENERGY
            self._attr_native_unit_of_measurement = "kWh"
            self._attr_suggested_display_precision = 2
            self._attr_icon = "mdi:lightning-bolt"
        else:
            self._attr_state_class = SensorStateClass.MEASUREMENT
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
        days = [
            day for day in (self._consumption.get("days") or [])
            if isinstance(day, dict) and isinstance(day.get("date"), str)
        ]
        return max(days, key=lambda day: day["date"]) if days else None

    @property
    def native_value(self) -> float | None:
        day = self._latest_day
        if not day:
            return None
        raw_value = day.get(self._field)
        # The API may return null when no report was received for the day.
        # Show zero in the dashboard tile while keeping the raw null in the archive.
        if raw_value is None:
            return 0.0
        try:
            value = float(raw_value)
            return value / 3600 if self._field == "heatingSeconds" else value
        except (TypeError, ValueError):
            return None

    @property
    def available(self) -> bool:
        return self._latest_day is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        days = self._consumption.get("days") or []
        api_days = days[-15:]
        statistic_suffix = (
            "estimated_consumption"
            if self._field == "estimatedKWh"
            else "heating_duration"
        )
        return {
            "econergy_device_id": self._device_id,
            "date_du_releve": (self._latest_day or {}).get("date"),
            "puissance_nominale_w": self._consumption.get("powerW"),
            "jours_disponibles": api_days,
            "nombre_de_jours": len(api_days),
            "nombre_de_jours_archive": len(days),
            "date_debut_archive": days[0].get("date") if days else None,
            "date_fin_archive": days[-1].get("date") if days else None,
            "identifiant_statistique_longue_duree": f"econergy:{self._device_id}_{statistic_suffix}",
            "valeur_null_signifie": "La tuile affiche 0 lorsque l'API ne fournit pas de mesure. La valeur brute reste null dans l'archive : une absence de remontée n'est pas une consommation nulle confirmée.",
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
        return str(status) if status else "Aucune commande enregistrée"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        command = self.coordinator.last_commands.get(self._device_id) or {}
        return {
            "command_id": command.get("command_id"),
            "type": command.get("kind"),
            "date": command.get("updated_at"),
        }
