"""Climate entities for Econergy radiators."""
from __future__ import annotations

import asyncio
from datetime import datetime
import logging
from typing import Any

from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature, HVACMode
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import EconergyApiError, EconergyAuthError, EconergyCommandError
from .const import (
    DEFAULT_MANUAL_SETPOINT_C,
    FROST_SETPOINT_C,
    DOMAIN,
    MODE_FROST,
    MODE_MANUAL,
    MODE_OFF,
    MODE_PROG,
    MODE_TO_PRESET,
    PRESET_FROST,
    PRESET_MANUAL,
    PRESET_PROGRAM,
    PRESET_TO_MODE,
)
from .coordinator import EconergyCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: EconergyCoordinator = data["coordinator"]
    api = data["api"]
    async_add_entities(
        EconergyRadiatorClimate(api, coordinator, device)
        for device in coordinator.data.get("devices", [])
        if device.get("id")
    )


class EconergyRadiatorClimate(CoordinatorEntity, RestoreEntity, ClimateEntity):
    """One climate entity per stable radiator ID returned by the official API."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.PRESET_MODE
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
    _attr_preset_modes = [PRESET_MANUAL, PRESET_FROST, PRESET_PROGRAM]
    _attr_target_temperature_step = 0.5
    _attr_min_temp = 13.5
    _attr_max_temp = 30.0
    _attr_icon = "mdi:radiator"

    def __init__(self, api, coordinator: EconergyCoordinator, device: dict[str, Any]) -> None:
        super().__init__(coordinator)
        self._api = api
        self._device_id = str(device["id"])
        self._attr_unique_id = f"{DOMAIN}_{self._device_id}_climate"
        self._last_command_id: str | None = None
        self._last_command_status: str | None = None
        self._last_command_confirmed: bool | None = None
        self._last_command_message: str | None = None
        self._last_command_at: str | None = None
        # Optimistic display state is kept only while this command is being
        # verified in the background. The API state remains authoritative.
        self._pending_command_id: str | None = None
        self._pending_mode: str | None = None
        self._pending_setpoint: float | None = None
        self._verification_task: asyncio.Task | None = None

        # Keep the last valid MANUAL target separately from the current API
        # setpoint: OFF returns 0 °C and FROST is displayed at 7.5 °C, neither of which
        # is a valid manual target in Home Assistant. This value is display-only
        # until a user explicitly changes the temperature.
        self._last_manual_setpoint = DEFAULT_MANUAL_SETPOINT_C
        self._remember_manual_setpoint_from_device(device)

    @staticmethod
    def _valid_manual_setpoint(value: Any) -> float | None:
        """Return a valid manual target (13,5–30 °C, 0.5 °C steps), if any."""
        try:
            value = float(value)
        except (TypeError, ValueError):
            return None
        if not 13.5 <= value <= 30.0:
            return None
        if abs(value * 2 - round(value * 2)) > 0.0001:
            return None
        return value

    def _remember_manual_setpoint_from_device(
        self, device: dict[str, Any] | None
    ) -> bool:
        """Cache the target only when the API reports a valid MANUAL state."""
        if not isinstance(device, dict):
            return False
        state = device.get("state") or {}
        if not isinstance(state, dict) or str(state.get("mode", "")).upper() != MODE_MANUAL:
            return False
        value = self._valid_manual_setpoint(state.get("setpointC"))
        if value is None:
            return False
        self._last_manual_setpoint = value
        return True

    async def async_added_to_hass(self) -> None:
        """Restore the last known manual target when HA restarts."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None:
            restored = self._valid_manual_setpoint(
                last_state.attributes.get("econergy_manual_setpoint_c")
            )
            if restored is None:
                # Compatibility with states recorded before this attribute was
                # added, when a previous MANUAL mode may have stored temperature.
                restored = self._valid_manual_setpoint(
                    last_state.attributes.get(ATTR_TEMPERATURE)
                )
            if restored is not None:
                self._last_manual_setpoint = restored

        # Current live MANUAL data takes precedence over an older restored value.
        self._remember_manual_setpoint_from_device(self._device)
        self.async_write_ha_state()

    def _handle_coordinator_update(self) -> None:
        """Remember real MANUAL targets when the coordinator refreshes."""
        if not self._pending_command_id:
            self._remember_manual_setpoint_from_device(self._device)
        super()._handle_coordinator_update()

    @property
    def _device(self) -> dict[str, Any] | None:
        return self.coordinator.find_device(self._device_id)

    @property
    def _state(self) -> dict[str, Any]:
        device = self._device or {}
        state = device.get("state") or {}
        return state if isinstance(state, dict) else {}

    @property
    def _mode(self) -> str | None:
        value = self._state.get("mode")
        return str(value).upper() if value is not None else None

    @property
    def _display_mode(self) -> str | None:
        """Return the requested mode while a command is pending confirmation."""
        if self._pending_command_id and self._pending_mode:
            return self._pending_mode
        return self._mode

    @property
    def device_info(self) -> DeviceInfo:
        device = self._device or {}
        info = device.get("info") or {}
        name = str(device.get("name") or "Radiateur")
        reference = info.get("reference")
        firmware = info.get("firmware") or {}
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=f"Econergy {name}",
            manufacturer="Econergy / Carrera",
            model=str(reference or "Radiateur connecté"),
            sw_version=str(firmware.get("version")) if firmware.get("version") else None,
        )

    @property
    def max_temp(self) -> float:
        """Expose the radiator's configured upper temperature limit in HA."""
        settings = self.coordinator.settings.get(self._device_id) or {}
        try:
            return max(13.5, min(30.0, float(settings.get("maxSetpointC", 30.0))))
        except (TypeError, ValueError):
            return 30.0

    @property
    def hvac_mode(self) -> HVACMode | None:
        mode = self._display_mode
        if mode is None:
            return None
        return HVACMode.OFF if mode == MODE_OFF else HVACMode.HEAT

    @property
    def preset_mode(self) -> str | None:
        return MODE_TO_PRESET.get(self._display_mode or "")

    @property
    def native_current_temperature(self) -> float | None:
        value = self._state.get("measuredC")
        try:
            return round(float(value), 1) if value is not None else None
        except (ValueError, TypeError):
            return None

    @property
    def native_target_temperature(self) -> float | None:
        mode = self._display_mode
        if mode == MODE_OFF:
            return None

        # In MANUAL, never expose OFF's 0 °C or FROST's 7.0 °C as the target:
        # HA may hide its temperature controls when the target is outside the
        # entity's 13,5–30 °C manual range. Keep the prior valid target visible
        # while a mode-only command is being confirmed.
        if mode == MODE_FROST:
            return FROST_SETPOINT_C
        if mode == MODE_MANUAL:
            if self._pending_command_id and self._pending_setpoint is not None:
                return self._pending_setpoint
            current = self._valid_manual_setpoint(self._state.get("setpointC"))
            if self._mode == MODE_MANUAL and current is not None:
                return current
            return self._last_manual_setpoint

        value = self._state.get("setpointC")
        try:
            return float(value) if value is not None else None
        except (ValueError, TypeError):
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        device = self._device or {}
        info = device.get("info") or {}
        firmware = info.get("firmware") or {}
        state = self._state
        request = device.get("_ha_status_request") or {}
        return {
            "econergy_device_id": self._device_id,
            "econergy_reference": info.get("reference"),
            "econergy_power_w": info.get("powerW"),
            "econergy_firmware_type": firmware.get("type"),
            "econergy_firmware_version": firmware.get("version"),
            "econergy_mode": state.get("mode"),
            "econergy_setpoint_c": state.get("setpointC"),
            "econergy_manual_setpoint_c": self._last_manual_setpoint,
            "econergy_measured_c": state.get("measuredC"),
            "econergy_setpoint_kind": state.get("setpointKind"),
            "econergy_heating": state.get("heating"),
            "econergy_window_open": state.get("windowOpen"),
            "econergy_fan_boost": state.get("fanBoost"),
            "econergy_last_seen_at": device.get("lastSeenAt"),
            "econergy_settings": self.coordinator.settings.get(self._device_id),
            "econergy_state_updated_at": state.get("updatedAt"),
            "econergy_status_request_at": request.get("requested_at"),
            "econergy_status_request_command_id": request.get("command_id"),
            "econergy_status_request_command_status": request.get("command_status"),
            "econergy_status_request_confirmed": request.get("fresh"),
            "econergy_status_request_result": request.get("status"),
            "econergy_status_request_error": request.get("error"),
            "econergy_command_id": self._last_command_id,
            "econergy_command_status": self._last_command_status,
            "econergy_command_confirmed": self._last_command_confirmed,
            "econergy_command_pending": bool(self._pending_command_id),
            "econergy_requested_mode": self._pending_mode,
            "econergy_requested_setpoint_c": self._pending_setpoint,
            "econergy_command_time": self._last_command_at,
            "econergy_command_note": self._last_command_message,
            "econergy_api_version": self.coordinator.data.get("api_version") if self.coordinator.data else None,
            "econergy_token_expires_at": self.coordinator.data.get("expires_at") if self.coordinator.data else None,
        }

    async def _send_command(self, *, mode: str, setpoint: float | None = None) -> None:
        """Send once, display the requested state immediately, verify in background."""
        self._last_command_at = datetime.now().astimezone().isoformat()
        self._last_command_status = "SENDING"
        self._last_command_confirmed = None
        self._last_command_message = "Envoi de la commande Econergy…"

        try:
            # The device-side maximum is authoritative. Ensure it has been read
            # even if a user sends a command before deferred setup has finished.
            if setpoint is not None:
                settings = await self.coordinator.async_ensure_settings(self._device_id, refresh=True)
                maximum = float(settings.get("maxSetpointC", 30))
                if float(setpoint) > maximum:
                    raise HomeAssistantError(
                        f"La consigne ({float(setpoint):g} °C) dépasse la butée maximale du radiateur ({maximum:g} °C)."
                    )
            result = await self._api.send_command(
                self._device_id,
                mode=mode,
                setpoint_c=setpoint,
            )
        except HomeAssistantError:
            self._last_command_status = "REFUSED"
            self._last_command_confirmed = False
            self._last_command_message = "Commande refusée : la température dépasse la butée maximale configurée."
            self._clear_pending_state()
            self.async_write_ha_state()
            raise
        except EconergyCommandError as err:
            self._last_command_id = err.command_id
            self._last_command_status = err.status or "FAILED"
            self._last_command_confirmed = False
            self._last_command_message = str(err)
            self._clear_pending_state()
            self.async_write_ha_state()
            raise HomeAssistantError(f"Commande Econergy échouée : {err}") from err
        except (EconergyAuthError, EconergyApiError) as err:
            self._last_command_status = "ERROR"
            self._last_command_confirmed = False
            self._last_command_message = str(err)
            self._clear_pending_state()
            self.async_write_ha_state()
            raise HomeAssistantError(f"Commande Econergy impossible : {err}") from err

        command_id = result.get("command_id")
        self._last_command_id = command_id
        self._last_command_status = result.get("command_status") or "SENT"
        self._last_command_confirmed = None
        self._last_command_message = "Commande envoyée ; affichage provisoire, confirmation de l'état en cours."
        self.coordinator.record_last_command(self._device_id, {
            "command_id": command_id,
            "status": self._last_command_status,
            "kind": "chauffage",
            "updated_at": self._last_command_at,
        })
        if self.coordinator.data is not None:
            self.coordinator.async_set_updated_data({
                **self.coordinator.data,
                "last_commands": dict(self.coordinator.last_commands),
            })

        if mode == MODE_MANUAL and setpoint is not None:
            # The requested value has been accepted by the API; preserve it for
            # immediate display and for the next transition out of MANUAL.
            self._last_manual_setpoint = float(setpoint)

        self._pending_command_id = command_id
        self._pending_mode = mode
        self._pending_setpoint = setpoint
        self.async_write_ha_state()

        # A newer command supersedes the previous verifier. It does not resend
        # or cancel any API write; only its read-only checks are cancelled.
        self._cancel_verification_task()
        if command_id:
            self._verification_task = self.hass.async_create_task(
                self._async_verify_command(
                    command_id=str(command_id),
                    mode=mode,
                    setpoint=setpoint,
                    command_status=str(result.get("command_status") or "SENT"),
                    previous_updated_at=result.get("previous_updated_at"),
                    previously_matching=bool(result.get("previously_matching")),
                )
            )

    async def _async_verify_command(
        self,
        *,
        command_id: str,
        mode: str,
        setpoint: float | None,
        command_status: str,
        previous_updated_at: str | None,
        previously_matching: bool,
    ) -> None:
        """Confirm ACK and a fresh state without blocking the climate service."""
        status_applied = False
        try:
            result = await self._api.verify_command(
                self._device_id,
                command_id=command_id,
                command_status=command_status,
                mode=mode,
                setpoint_c=setpoint,
                previous_updated_at=previous_updated_at,
                previously_matching=previously_matching,
                status_callback=lambda status: self._update_pending_command_status(command_id, status),
            )
            if self._last_command_id != command_id:
                return

            # verify_command has already performed a direct, read-only status
            # query. Apply that exact snapshot now, instead of waiting for the
            # five-minute bulk poll or a debounced coordinator refresh.
            latest_device = result.get("device")
            if isinstance(latest_device, dict):
                self._remember_manual_setpoint_from_device(latest_device)
                status_applied = self.coordinator.update_device_from_status(latest_device)

            self._last_command_status = result.get("command_status")
            self.coordinator.record_last_command(self._device_id, {
                "command_id": command_id,
                "status": self._last_command_status,
                "kind": "chauffage",
                "updated_at": datetime.now().astimezone().isoformat(),
            })
            if self.coordinator.data is not None:
                self.coordinator.async_set_updated_data({
                    **self.coordinator.data,
                    "last_commands": dict(self.coordinator.last_commands),
                })
            self._last_command_confirmed = bool(result.get("confirmed"))
            if self._last_command_confirmed:
                self._last_command_message = "État confirmé par une nouvelle remontée du radiateur."
            else:
                self._last_command_message = (
                    result.get("verification_error")
                    or "Commande reçue ou envoyée, mais nouvelle remontée d'état non confirmée."
                )
                _LOGGER.warning(
                    "Econergy %s : commande %s (%s) non confirmée par une nouvelle remontée d'état",
                    self._device_id, command_id, mode,
                )
        except EconergyCommandError as err:
            if self._last_command_id == command_id:
                self._last_command_status = err.status or "FAILED"
                self._last_command_confirmed = False
                self._last_command_message = str(err)
                _LOGGER.warning("Econergy %s : commande %s échouée : %s", self._device_id, command_id, err)
        except (EconergyAuthError, EconergyApiError) as err:
            if self._last_command_id == command_id:
                self._last_command_status = "ERROR"
                self._last_command_confirmed = False
                self._last_command_message = str(err)
                _LOGGER.warning("Econergy %s : vérification de commande %s impossible : %s", self._device_id, command_id, err)
        except asyncio.CancelledError:
            raise
        finally:
            # Never let a stale verifier clear the optimistic display of a newer
            # command. If no usable status snapshot was returned, force one
            # immediate, read-only refresh before dropping pending state.
            if self._last_command_id == command_id:
                if not status_applied:
                    try:
                        await self.coordinator.async_refresh()
                    except Exception:  # noqa: BLE001 - the command may already be applied
                        _LOGGER.debug("Actualisation Econergy après vérification impossible", exc_info=True)
                self._clear_pending_state(command_id=command_id)
                self.async_write_ha_state()

    def _update_pending_command_status(self, command_id: str, status: str) -> None:
        """Expose SENT/ACKNOWLEDGED promptly while state verification continues."""
        if self._last_command_id != command_id:
            return
        self._last_command_status = status
        self.coordinator.record_last_command(self._device_id, {
            "command_id": command_id,
            "status": status,
            "kind": "chauffage",
            "updated_at": datetime.now().astimezone().isoformat(),
        })
        if self.coordinator.data is not None:
            self.coordinator.async_set_updated_data({
                **self.coordinator.data,
                "last_commands": dict(self.coordinator.last_commands),
            })
        if status == "ACKNOWLEDGED":
            self._last_command_message = "Radiateur ayant reçu la commande ; vérification de l'état en cours."
        elif status == "SENT":
            self._last_command_message = "Commande envoyée ; en attente de l'accusé de réception."
        self.async_write_ha_state()

    def _clear_pending_state(self, *, command_id: str | None = None) -> None:
        if command_id is not None and self._pending_command_id != command_id:
            return
        self._pending_command_id = None
        self._pending_mode = None
        self._pending_setpoint = None

    def _cancel_verification_task(self) -> None:
        task = self._verification_task
        if task is not None and not task.done():
            task.cancel()
        self._verification_task = None

    async def async_will_remove_from_hass(self) -> None:
        self._cancel_verification_task()
        await super().async_will_remove_from_hass()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        value = kwargs.get(ATTR_TEMPERATURE)
        if value is None:
            return
        try:
            temperature = float(value)
        except (TypeError, ValueError) as err:
            raise HomeAssistantError("Consigne Econergy invalide") from err
        if not 13.5 <= temperature <= self.max_temp:
            raise HomeAssistantError(
                f"La consigne Econergy doit être comprise entre 13,5 et {self.max_temp:g} °C "
                "selon la butée maximale configurée sur le radiateur."
            )
        if abs(temperature * 2 - round(temperature * 2)) > 0.0001:
            raise HomeAssistantError("La consigne doit être un multiple de 0,5 °C")
        await self._send_command(mode=MODE_MANUAL, setpoint=temperature)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.OFF:
            await self._send_command(mode=MODE_OFF)
        elif hvac_mode == HVACMode.HEAT:
            await self._send_command(mode=MODE_MANUAL)
        else:
            raise HomeAssistantError("Mode de chauffage non pris en charge")

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        mode = PRESET_TO_MODE.get(preset_mode)
        if mode is None:
            raise HomeAssistantError("Préréglage Econergy inconnu")
        await self._send_command(mode=mode)
