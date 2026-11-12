"""Data coordinator for the official Econergy Lab API integration."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
)
from homeassistant.components.recorder.statistics import async_add_external_statistics
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CoreState, EVENT_HOMEASSISTANT_STARTED, HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util.unit_conversion import EnergyConverter

from .api import (
    EconergyApi,
    EconergyApiError,
    EconergyAuthError,
    EconergyRateLimitError,
)
from .const import (
    DOMAIN,
    PROGRAM_CONFIRM_TIMEOUT_SECONDS,
    PROGRAM_POLL_INTERVAL_SECONDS,
    STATUS_REQUEST_COMMAND_TIMEOUT_SECONDS,
    STATUS_REQUEST_DEFAULT_RETRY_AFTER_SECONDS,
    INVENTORY_POLL_INTERVAL_SECONDS,
    STATUS_REQUEST_POLL_INTERVAL_SECONDS,
    STATUS_REQUEST_STATE_TIMEOUT_SECONDS,
)

_LOGGER = logging.getLogger(__name__)


class EconergyCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetch radiator states and cache weekly programs."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        api: EconergyApi,
        home_id: str,
        home_name: str,
    ) -> None:
        self.api = api
        self.home_id = home_id
        self.home_name = home_name
        self.programs: dict[str, dict[str, Any]] = {}
        self.program_errors: dict[str, str] = {}
        self.settings: dict[str, dict[str, Any]] = {}
        self.settings_errors: dict[str, str] = {}
        self.consumption: dict[str, dict[str, Any]] = {}
        self.consumption_errors: dict[str, str] = {}
        self.consumption_loaded_date: str | None = None
        self._consumption_store = Store(
            hass, 1, f"{DOMAIN}_{entry.entry_id}_consumption_history"
        )
        self._consumption_lock = asyncio.Lock()
        self._consumption_load_task: asyncio.Task | None = None
        self.last_commands: dict[str, dict[str, Any]] = {}
        self._last_commands_store = Store(hass, 1, f"{DOMAIN}_{entry.entry_id}_last_commands")
        self.program_locks: dict[str, asyncio.Lock] = {}
        self.status_request_cooldowns: dict[str, float] = {}
        self.status_request_last_attempt: dict[str, float] = {}
        self.device_write_locks: dict[str, asyncio.Lock] = {}
        self._initial_devices: list[dict[str, Any]] | None = None
        self._startup_task: asyncio.Task | None = None
        self._startup_unsubscribe: Callable[[], None] | None = None
        super().__init__(
            hass,
            _LOGGER,
            name=f"Econergy {home_id}",
            # The five-minute polling cadence starts after the first deferred
            # cloud refresh, not while Home Assistant is still starting.
            update_interval=None,
            config_entry=entry,
        )

    async def async_initialize(self) -> None:
        """Fetch the device inventory only; defer status commands and programs."""
        devices = await self.api.get_devices(self.home_id)
        self._initial_devices = [dict(device) for device in devices]
        known_ids = {str(device.get("id")) for device in self._initial_devices if device.get("id")}
        saved_consumption = await self._consumption_store.async_load()
        if isinstance(saved_consumption, dict):
            saved_devices = saved_consumption.get("devices") or {}
            if isinstance(saved_devices, dict):
                self.consumption = {
                    str(device_id): dict(value)
                    for device_id, value in saved_devices.items()
                    if str(device_id) in known_ids and isinstance(value, dict)
                }
            loaded_date = saved_consumption.get("loaded_date")
            if isinstance(loaded_date, str):
                self.consumption_loaded_date = loaded_date

        saved_commands = await self._last_commands_store.async_load()
        if isinstance(saved_commands, dict):
            self.last_commands = {
                str(device_id): dict(command)
                for device_id, command in saved_commands.items()
                if str(device_id) in known_ids and isinstance(command, dict)
            }
        for device in self._initial_devices:
            device_id = str(device.get("id") or "")
            if device_id:
                state = device.get("state") or {}
                device["_ha_status_request"] = {
                    "status": "NOT_REQUESTED",
                    "fresh": False,
                    "requested_at": None,
                    "state_updated_at": state.get("updatedAt"),
                    "error": None,
                }

        # Re-submit the local archive on startup as well. This repairs Recorder
        # statistics if they were unavailable during an earlier import or if
        # its database was restored separately from Home Assistant storage.
        for device in self._initial_devices:
            device_id = str(device.get("id") or "")
            archived = self.consumption.get(device_id) or {}
            archived_days = archived.get("days") or []
            if device_id and archived_days:
                self._import_consumption_statistics(
                    device_id,
                    str(device.get("name") or device_id),
                    archived_days,
                )

        # Publish a lightweight initial snapshot so climate and sensor entities
        # can be created immediately. No status POST, command polling or program
        # reads are awaited during config-entry setup.
        self.async_set_updated_data({
            "home_id": self.home_id,
            "home_name": self.home_name,
            "devices": self._initial_devices,
            "programs": {},
            "program_errors": {},
            "settings": {},
            "settings_errors": {},
            "consumption": dict(self.consumption),
            "consumption_errors": {},
            "consumption_loaded_date": self.consumption_loaded_date,
            "last_commands": dict(self.last_commands),
            "api_version": self.api.api_version,
            "expires_at": getattr(self, "token_expires_at", None),
        })


    def _schedule_consumption_save(self) -> None:
        """Persist the complete daily archive independently of the API's 15-day window."""
        self._consumption_store.async_delay_save(
            lambda: {
                "devices": dict(self.consumption),
                "loaded_date": self.consumption_loaded_date,
            },
            1,
        )

    @staticmethod
    def _merge_consumption_history(
        previous: dict[str, Any] | None,
        incoming: dict[str, Any],
    ) -> dict[str, Any]:
        """Merge the rolling API window into the permanent per-radiator history.

        A null value from the API means that no measurement was received. It
        must not erase an older valid value already archived for that date.
        A real zero remains a real zero and is kept as such.
        """
        records: dict[str, dict[str, Any]] = {}
        for day in (previous or {}).get("days") or []:
            if isinstance(day, dict) and isinstance(day.get("date"), str):
                records[day["date"]] = dict(day)

        for day in incoming.get("days") or []:
            if not isinstance(day, dict) or not isinstance(day.get("date"), str):
                continue
            date_key = day["date"]
            old = records.get(date_key, {})
            merged = {**old, **day}
            for field in ("heatingSeconds", "estimatedKWh"):
                if day.get(field) is None and old.get(field) is not None:
                    merged[field] = old[field]
            records[date_key] = merged

        merged_data = {**(previous or {}), **incoming}
        merged_data["days"] = [records[key] for key in sorted(records)]
        return merged_data

    def _import_consumption_statistics(
        self,
        device_id: str,
        device_name: str,
        days: list[dict[str, Any]],
    ) -> None:
        """Import daily energy and heating-duration points into Recorder statistics."""
        energy_id = f"{DOMAIN}:{device_id}_estimated_consumption"
        duration_id = f"{DOMAIN}:{device_id}_heating_duration"
        energy_metadata = StatisticMetaData(
            mean_type=StatisticMeanType.NONE,
            has_sum=True,
            name=(
                f"Econergy {device_name} - "
                "consommation estimée journalière"
            ),
            source=DOMAIN,
            statistic_id=energy_id,
            unit_class=EnergyConverter.UNIT_CLASS,
            unit_of_measurement="kWh",
        )
        duration_metadata = StatisticMetaData(
            mean_type=StatisticMeanType.NONE,
            has_sum=True,
            name=(
                f"Econergy {device_name} - "
                "durée de chauffe journalière"
            ),
            source=DOMAIN,
            statistic_id=duration_id,
            unit_class=None,
            unit_of_measurement="h",
        )

        energy_points: list[StatisticData] = []
        duration_points: list[StatisticData] = []
        energy_sum = 0.0
        duration_sum = 0.0
        paris_tz = ZoneInfo("Europe/Paris")

        for day in sorted(
            days,
            key=lambda item: str(item.get("date") or ""),
        ):
            date_text = day.get("date")
            if not isinstance(date_text, str):
                continue
            try:
                local_date = datetime.strptime(date_text, "%Y-%m-%d").date()
                start = datetime.combine(local_date, time.min, tzinfo=paris_tz)
            except ValueError:
                _LOGGER.debug("Date de consommation Econergy ignorée : %s", date_text)
                continue

            raw_energy = day.get("estimatedKWh")
            if raw_energy is not None:
                try:
                    energy = float(raw_energy)
                    if energy >= 0:
                        energy_sum += energy
                        energy_points.append(
                            StatisticData(start=start, state=energy, sum=energy_sum)
                        )
                except (TypeError, ValueError):
                    _LOGGER.debug(
                        "Consommation Econergy invalide pour %s (%s)",
                        date_text,
                        device_id,
                    )

            raw_duration = day.get("heatingSeconds")
            if raw_duration is not None:
                try:
                    duration_hours = float(raw_duration) / 3600
                    if duration_hours >= 0:
                        duration_sum += duration_hours
                        duration_points.append(
                            StatisticData(
                                start=start,
                                state=duration_hours,
                                sum=duration_sum,
                            )
                        )
                except (TypeError, ValueError):
                    _LOGGER.debug(
                        "Durée de chauffe Econergy invalide pour %s (%s)",
                        date_text,
                        device_id,
                    )

        try:
            if energy_points:
                async_add_external_statistics(self.hass, energy_metadata, energy_points)
            if duration_points:
                async_add_external_statistics(self.hass, duration_metadata, duration_points)
        except Exception:
            # Consumption data and its local archive remain usable even if the
            # Recorder statistics queue is temporarily unavailable.
            _LOGGER.exception(
                "Impossible d'importer les statistiques long terme Econergy pour %s",
                device_id,
            )

    def record_last_command(self, device_id: str, command: dict[str, Any]) -> None:
        """Update and persist the latest command summary for one radiator."""
        device_id = str(device_id)
        self.last_commands[device_id] = dict(command)
        self._last_commands_store.async_delay_save(lambda: dict(self.last_commands), 1)
        if self.data is not None:
            self.async_set_updated_data({
                **self.data,
                "last_commands": dict(self.last_commands),
            })

    def async_start_deferred_initialization(self, entry: ConfigEntry) -> None:
        """Start the full first refresh only after HA has finished booting."""
        entry.async_on_unload(self.async_stop_deferred_initialization)
        if self.hass.state == CoreState.running:
            self._start_deferred_initialization()
        else:
            self._startup_unsubscribe = self.hass.bus.async_listen_once(
                EVENT_HOMEASSISTANT_STARTED,
                self._handle_homeassistant_started,
            )

    async def _handle_homeassistant_started(self, _event: Any) -> None:
        # async_listen_once removes its listener before invoking this callback.
        # Clear the handle so unload cleanup does not attempt a second removal.
        self._startup_unsubscribe = None
        self._start_deferred_initialization()

    def _start_deferred_initialization(self) -> None:
        if self._startup_task is not None and not self._startup_task.done():
            return
        self._startup_task = self.hass.async_create_background_task(
            self._async_deferred_initialization(),
            f"Econergy initial cloud refresh {self.home_id}",
        )

    async def _async_deferred_initialization(self) -> None:
        """Retrieve live status and weekly programs without blocking HA startup."""
        try:
            await self.async_refresh()
            if self.last_update_success:
                await self.async_load_programs()
                await self.async_load_settings()
                await self.async_load_consumption()
            else:
                _LOGGER.warning(
                    "Initialisation différée Econergy incomplète ; nouvelle tentative au prochain cycle"
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            _LOGGER.exception("Échec de l'initialisation différée Econergy")

    def async_stop_deferred_initialization(self) -> None:
        """Unsubscribe from startup and cancel the startup task on unload."""
        unsubscribe = self._startup_unsubscribe
        self._startup_unsubscribe = None
        if unsubscribe is not None:
            unsubscribe()

        task = self._startup_task
        if task is not None and not task.done():
            task.cancel()
        self._startup_task = None

    @staticmethod
    def _timestamp_is_after(value: Any, reference: datetime) -> bool:
        """Compare an API ISO timestamp with the time at which we requested it."""
        if not isinstance(value, str) or not value.strip():
            return False
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc) > reference
        except (TypeError, ValueError, OverflowError):
            return False

    @staticmethod
    def _merge_status(device: dict[str, Any], status: dict[str, Any]) -> dict[str, Any]:
        """Merge a direct device status response without losing list metadata."""
        merged = {**device, **status}
        for key in ("info", "state"):
            old_value = device.get(key)
            new_value = status.get(key)
            if isinstance(old_value, dict) and isinstance(new_value, dict):
                merged[key] = {**old_value, **new_value}
        return merged

    async def _request_and_confirm_device_status(
        self, device: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        """Request one device report, follow its command, then require a newer state.updatedAt."""
        device_id = str(device.get("id") or "")
        if not device_id:
            return None, {"status": "SKIPPED", "fresh": False, "error": "Identifiant absent"}

        loop = asyncio.get_running_loop()
        cooldown_until = self.status_request_cooldowns.get(device_id, 0.0)
        last_attempt = self.status_request_last_attempt.get(device_id, 0.0)
        minimum_interval_remaining = 60.0 - (loop.time() - last_attempt) if last_attempt else 0.0
        if minimum_interval_remaining > 0:
            remaining = max(1, int(minimum_interval_remaining))
            return None, {
                "status": "RATE_LIMIT_COOLDOWN",
                "fresh": False,
                "retry_after_seconds": remaining,
                "error": f"Une actualisation a déjà été demandée il y a moins d'une minute ({remaining} s restantes)",
            }
        if loop.time() < cooldown_until:
            remaining = max(1, int(cooldown_until - loop.time()))
            return None, {
                "status": "RATE_LIMIT_COOLDOWN",
                "fresh": False,
                "retry_after_seconds": remaining,
                "error": f"Demande différée pendant encore {remaining} s après HTTP 429",
            }

        requested_at = datetime.now(timezone.utc)
        requested_at_iso = requested_at.isoformat()
        # The Lab allows at most one status request per minute and per radiator.
        self.status_request_last_attempt[device_id] = loop.time()
        result: dict[str, Any] = {
            "requested_at": requested_at_iso,
            "command_id": None,
            "command_status": None,
            "fresh": False,
            "state_updated_at": (device.get("state") or {}).get("updatedAt"),
            "error": None,
        }

        try:
            command = await self.api.request_device_status(device_id)
            created_at = command.get("createdAt")
            if isinstance(created_at, str) and created_at.strip():
                try:
                    api_created_at = datetime.fromisoformat(created_at.strip().replace("Z", "+00:00"))
                    if api_created_at.tzinfo is None:
                        api_created_at = api_created_at.replace(tzinfo=timezone.utc)
                    requested_at = api_created_at.astimezone(timezone.utc)
                    requested_at_iso = requested_at.isoformat()
                    result["requested_at"] = requested_at_iso
                except (TypeError, ValueError, OverflowError):
                    pass
        except EconergyAuthError:
            raise
        except EconergyRateLimitError as err:
            retry_after = err.retry_after
            if retry_after is None:
                retry_after = STATUS_REQUEST_DEFAULT_RETRY_AFTER_SECONDS
            retry_after = max(1.0, retry_after)
            self.status_request_cooldowns[device_id] = loop.time() + retry_after
            result.update({
                "status": "RATE_LIMITED",
                "retry_after_seconds": int(retry_after),
                "error": str(err),
            })
            _LOGGER.warning(
                "Demande de statut Econergy limitée pour %s (Retry-After=%ss)",
                device_id,
                int(retry_after),
            )
            return None, result
        except EconergyApiError as err:
            result.update({"status": "ERROR", "error": str(err)})
            _LOGGER.warning("Demande de statut Econergy impossible pour %s : %s", device_id, err)
            return None, result

        command_id = str(command["commandId"])
        command_status = str(command.get("status") or "SENT").strip().upper()
        result["command_id"] = command_id
        result["command_status"] = command_status
        failed_statuses = {"FAILED", "ERROR", "REJECTED", "CANCELLED", "CANCELED", "EXPIRED", "TIMEOUT"}
        acknowledged_statuses = {
            "ACKNOWLEDGED", "SUCCESS", "SUCCESSFUL", "SUCCEEDED", "COMPLETED",
            "COMPLETE", "DONE", "CONFIRMED", "APPLIED", "EXECUTED",
        }

        if command_status in failed_statuses:
            result.update({"status": "COMMAND_FAILED", "error": f"Commande {command_id} : {command_status}"})
            _LOGGER.warning("Demande de statut refusée pour %s (commande=%s, statut=%s)", device_id, command_id, command_status)
            return None, result

        # Follow the command with GET /commands/{commandId}. ACKNOWLEDGED means
        # the request reached the device; state.updatedAt is checked separately below.
        command_deadline = loop.time() + STATUS_REQUEST_COMMAND_TIMEOUT_SECONDS
        last_command_error: str | None = None
        while command_status not in acknowledged_statuses and loop.time() < command_deadline:
            await asyncio.sleep(STATUS_REQUEST_POLL_INTERVAL_SECONDS)
            try:
                latest_command = await self.api.get_command(command_id)
            except EconergyAuthError:
                raise
            except EconergyRateLimitError as err:
                last_command_error = str(err)
                delay = max(1.0, err.retry_after or STATUS_REQUEST_DEFAULT_RETRY_AFTER_SECONDS)
                remaining = max(0.0, command_deadline - loop.time())
                if delay >= remaining:
                    await asyncio.sleep(remaining)
                    break
                await asyncio.sleep(delay)
                continue
            except EconergyApiError as err:
                last_command_error = str(err)
                continue

            command_status = str(latest_command.get("status") or command_status or "UNKNOWN").strip().upper()
            result["command_status"] = command_status
            last_command_error = None
            if command_status in failed_statuses:
                result.update({"status": "COMMAND_FAILED", "error": f"Commande {command_id} : {command_status}"})
                _LOGGER.warning("Demande de statut échouée pour %s (commande=%s)", device_id, command_id)
                return None, result

        if command_status not in acknowledged_statuses:
            result["command_tracking"] = "TIMEOUT"
            result["error"] = (
                f"La commande {command_id} n'a pas été acquittée dans le délai imparti"
                + (f" ; dernier problème de suivi : {last_command_error}" if last_command_error else "")
            )
            _LOGGER.warning("Suivi de la demande de statut en attente pour %s (commande=%s, statut=%s)", device_id, command_id, command_status)

        # Even after the command acknowledgement, require a state timestamp later
        # than the request timestamp before calling the measurement refreshed.
        state_deadline = loop.time() + STATUS_REQUEST_STATE_TIMEOUT_SECONDS
        latest_device: dict[str, Any] | None = None
        last_state_error: str | None = None
        while loop.time() < state_deadline:
            try:
                latest_device = await self.api.get_device_status(device_id)
                last_state_error = None
            except EconergyAuthError:
                raise
            except EconergyRateLimitError as err:
                last_state_error = str(err)
                delay = max(1.0, err.retry_after or STATUS_REQUEST_DEFAULT_RETRY_AFTER_SECONDS)
                await asyncio.sleep(delay)
                continue
            except EconergyApiError as err:
                last_state_error = str(err)

            state = (latest_device or {}).get("state") or {}
            updated_at = state.get("updatedAt")
            if self._timestamp_is_after(updated_at, requested_at):
                result.update({
                    "status": "UPDATED",
                    "fresh": True,
                    "command_status": command_status,
                    "state_updated_at": updated_at,
                    "error": None,
                })
                self.status_request_cooldowns.pop(device_id, None)
                _LOGGER.info(
                    "État Econergy actualisé pour %s (commande=%s, updatedAt=%s)",
                    device_id,
                    command_id,
                    updated_at,
                )
                return latest_device, result

            await asyncio.sleep(STATUS_REQUEST_POLL_INTERVAL_SECONDS)

        if last_state_error:
            result["error"] = f"État non actualisé ; dernière erreur de lecture : {last_state_error}"
        elif result.get("error") is None:
            result["error"] = (
                "La commande a été suivie, mais state.updatedAt n'est pas postérieur à la demande"
            )
        result.update({
            "status": "STATE_NOT_UPDATED",
            "fresh": False,
            "command_status": command_status,
            "state_updated_at": ((latest_device or {}).get("state") or {}).get("updatedAt"),
        })
        _LOGGER.warning(
            "La température Econergy de %s n'a pas été confirmée fraîche après la demande (commande=%s, updatedAt=%s)",
            device_id,
            command_id,
            result.get("state_updated_at"),
        )
        return latest_device, result

    async def _async_update_data(self) -> dict[str, Any]:
        """Read the published inventory without waking every radiator.

        Econergy explicitly recommends using status-request only when a user
        needs a fresh measurement. The regular five-minute cycle is therefore
        a lightweight GET of already-published states; explicit refresh and
        command verification still use the wake-up/status-request route.
        """
        try:
            if self._initial_devices is not None:
                devices = self._initial_devices
                self._initial_devices = None
            else:
                devices = await self.api.get_devices(self.home_id)
        except EconergyAuthError as err:
            raise ConfigEntryAuthFailed(
                "Jeton Econergy expiré ou invalide. Renouvelez l'autorisation dans Econergy Lab."
            ) from err
        except EconergyApiError as err:
            raise UpdateFailed(f"Lecture de l'API Econergy impossible : {err}") from err

        existing = {
            str(item.get("id")): item
            for item in (self.data or {}).get("devices", [])
            if item.get("id")
        }
        refreshed_devices: list[dict[str, Any]] = []
        for device in devices:
            device_id = str(device.get("id") or "")
            prior = existing.get(device_id, {})
            merged = self._merge_status(prior, device) if prior else dict(device)
            if prior.get("_ha_status_request"):
                merged["_ha_status_request"] = prior["_ha_status_request"]
            elif device_id:
                state = merged.get("state") or {}
                merged["_ha_status_request"] = {
                    "status": "NOT_REQUESTED",
                    "fresh": False,
                    "requested_at": None,
                    "state_updated_at": state.get("updatedAt"),
                    "error": None,
                }
            refreshed_devices.append(merged)

        self.update_interval = timedelta(seconds=INVENTORY_POLL_INTERVAL_SECONDS)
        known_ids = {str(device.get("id")) for device in refreshed_devices if device.get("id")}
        self.programs = {key: value for key, value in self.programs.items() if key in known_ids}
        self.program_errors = {key: value for key, value in self.program_errors.items() if key in known_ids}
        self.settings = {key: value for key, value in self.settings.items() if key in known_ids}
        self.settings_errors = {key: value for key, value in self.settings_errors.items() if key in known_ids}
        self.consumption = {key: value for key, value in self.consumption.items() if key in known_ids}
        self.consumption_errors = {key: value for key, value in self.consumption_errors.items() if key in known_ids}
        self.last_commands = {key: value for key, value in self.last_commands.items() if key in known_ids}

        _LOGGER.debug(
            "Lecture Econergy terminée : %s radiateur(s) listé(s), sans demande radio automatique ; prochaine lecture dans 5 minutes",
            len(refreshed_devices),
        )

        # The consumption endpoint changes at most once per day. Read it after
        # the Europe/Paris date changes, in the background, without delaying
        # climate state updates.
        today = datetime.now(ZoneInfo("Europe/Paris")).date().isoformat()
        if self.consumption_loaded_date != today and (
            self._consumption_load_task is None or self._consumption_load_task.done()
        ):
            self._consumption_load_task = self.hass.async_create_background_task(
                self.async_load_consumption(),
                f"Econergy daily consumption refresh {self.home_id}",
            )

        return {
            "home_id": self.home_id,
            "home_name": self.home_name,
            "devices": refreshed_devices,
            "programs": dict(self.programs),
            "program_errors": dict(self.program_errors),
            "settings": dict(self.settings),
            "settings_errors": dict(self.settings_errors),
            "consumption": dict(self.consumption),
            "consumption_errors": dict(self.consumption_errors),
            "consumption_loaded_date": self.consumption_loaded_date,
            "last_commands": dict(self.last_commands),
            "api_version": self.api.api_version,
            "expires_at": getattr(self, "token_expires_at", None),
        }

    async def async_load_programs(self) -> None:
        """Load weekly schedules once when the integration starts."""
        devices = (self.data or {}).get("devices", [])
        for device in devices:
            device_id = str(device.get("id") or "")
            if not device_id:
                continue
            try:
                self.programs[device_id] = await self.api.get_program(device_id)
                self.program_errors.pop(device_id, None)
            except EconergyApiError as err:
                self.program_errors[device_id] = str(err)
                _LOGGER.warning("Programme Econergy indisponible pour %s : %s", device_id, err)
        if self.data is not None:
            self.async_set_updated_data({
                **self.data,
                "programs": dict(self.programs),
                "program_errors": dict(self.program_errors),
                "settings": dict(self.settings),
                "settings_errors": dict(self.settings_errors),
                "consumption": dict(self.consumption),
                "consumption_errors": dict(self.consumption_errors),
                "last_commands": dict(self.last_commands),
            })

    async def async_load_settings(self, *, refresh: bool = False) -> None:
        """Read the documented settings for every radiator, one request at a time."""
        devices = (self.data or {}).get("devices", [])
        for index, device in enumerate(devices):
            device_id = str(device.get("id") or "")
            if not device_id or (device_id in self.settings and not refresh):
                continue
            try:
                settings = await self.api.get_settings(device_id)
                self.settings[device_id] = settings
                self.settings_errors.pop(device_id, None)
            except EconergyAuthError:
                raise
            except EconergyApiError as err:
                self.settings_errors[device_id] = str(err)
                _LOGGER.warning("Réglages Econergy indisponibles pour %s : %s", device_id, err)
            if index < len(devices) - 1:
                await asyncio.sleep(0.25)
        if self.data is not None:
            self.async_set_updated_data({
                **self.data,
                "settings": dict(self.settings),
                "settings_errors": dict(self.settings_errors),
            })

    async def async_load_consumption(self, *, force: bool = False) -> None:
        """Load the rolling API window, merge it into the permanent archive and Recorder."""
        async with self._consumption_lock:
            today = datetime.now(ZoneInfo("Europe/Paris")).date().isoformat()
            if not force and self.consumption_loaded_date == today:
                return

            devices = (self.data or {}).get("devices", [])
            for index, device in enumerate(devices):
                device_id = str(device.get("id") or "")
                if not device_id:
                    continue
                try:
                    incoming = await self.api.get_consumption(device_id)
                    merged = self._merge_consumption_history(
                        self.consumption.get(device_id),
                        incoming,
                    )
                    self.consumption[device_id] = merged
                    self.consumption_errors.pop(device_id, None)
                    self._import_consumption_statistics(
                        device_id,
                        str(device.get("name") or device_id),
                        merged.get("days") or [],
                    )
                except EconergyAuthError:
                    raise
                except EconergyApiError as err:
                    self.consumption_errors[device_id] = str(err)
                    _LOGGER.warning("Consommation Econergy indisponible pour %s : %s", device_id, err)
                if index < len(devices) - 1:
                    await asyncio.sleep(0.25)

            # The endpoint is refreshed once per local day. Keep this
            # cadence even when one device fails; errors remain visible and
            # a manual refresh can retry that radiator without hammering the API.
            self.consumption_loaded_date = today

            self._schedule_consumption_save()
            if self.data is not None:
                self.async_set_updated_data({
                    **self.data,
                    "consumption": dict(self.consumption),
                    "consumption_errors": dict(self.consumption_errors),
                    "consumption_loaded_date": self.consumption_loaded_date,
                })

    async def async_refresh_consumption(self, device_id: str) -> dict[str, Any]:
        """Refresh one device's rolling report without discarding its older archive."""
        incoming = await self.api.get_consumption(device_id)
        merged = self._merge_consumption_history(
            self.consumption.get(str(device_id)),
            incoming,
        )
        self.consumption[str(device_id)] = merged
        self.consumption_errors.pop(str(device_id), None)
        device = self.find_device(str(device_id)) or {}
        self._import_consumption_statistics(
            str(device_id),
            str(device.get("name") or device_id),
            merged.get("days") or [],
        )
        self._schedule_consumption_save()
        if self.data is not None:
            self.async_set_updated_data({
                **self.data,
                "consumption": dict(self.consumption),
                "consumption_errors": dict(self.consumption_errors),
            })
        return merged

    async def async_ensure_settings(
        self, device_id: str, *, refresh: bool = False
    ) -> dict[str, Any]:
        """Load a radiator's settings before a write that depends on safety limits."""
        settings = self.settings.get(device_id)
        if settings is not None and not refresh:
            return settings
        settings = await self.api.get_settings(device_id)
        self.settings[device_id] = settings
        self.settings_errors.pop(device_id, None)
        if self.data is not None:
            self.async_set_updated_data({
                **self.data,
                "settings": dict(self.settings),
                "settings_errors": dict(self.settings_errors),
            })
        return settings

    async def async_ensure_program(
        self, device_id: str, *, refresh: bool = False
    ) -> dict[str, Any]:
        """Load one weekly program before validating a dependent setting."""
        program = self.programs.get(device_id)
        if program is not None and not refresh:
            return program
        program = await self.api.get_program(device_id)
        self.programs[device_id] = program
        self.program_errors.pop(device_id, None)
        if self.data is not None:
            self.async_set_updated_data({
                **self.data,
                "programs": dict(self.programs),
                "program_errors": dict(self.program_errors),
            })
        return program

    @staticmethod
    def _program_matches(program: dict[str, Any], changes: dict[str, Any]) -> bool:
        """Return True only when the API read-back matches every requested field."""
        for key in ("ecoC", "comfortC"):
            if key in changes:
                try:
                    if abs(float(program.get(key)) - float(changes[key])) > 0.01:
                        return False
                except (TypeError, ValueError):
                    return False

        expected_days = changes.get("days") or {}
        actual_days = program.get("days") or {}
        if not isinstance(expected_days, dict) or not isinstance(actual_days, dict):
            return False
        for day, expected_periods in expected_days.items():
            actual_periods = actual_days.get(day)
            if not isinstance(actual_periods, list):
                return False
            normalized_actual = []
            for period in actual_periods:
                if not isinstance(period, dict):
                    continue
                normalized_actual.append({
                    "start": str(period.get("start") or "")[:5],
                    "end": str(period.get("end") or "")[:5],
                })
            normalized_expected = [
                {
                    "start": str(period.get("start") or "")[:5],
                    "end": str(period.get("end") or "")[:5],
                }
                for period in expected_periods
            ]
            if normalized_actual != normalized_expected:
                return False
        return True

    async def async_update_program(self, device_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        """PATCH once, wait for command completion, then verify actual program read-back."""
        if "ecoC" in changes or "comfortC" in changes:
            current_program = await self.async_ensure_program(device_id, refresh=True)
            eco = changes.get("ecoC", current_program.get("ecoC"))
            comfort = changes.get("comfortC", current_program.get("comfortC"))
            try:
                eco_value = float(eco)
                comfort_value = float(comfort)
            except (TypeError, ValueError) as err:
                raise ValueError("Les consignes Éco et Confort actuelles sont introuvables.") from err
            if comfort_value < eco_value + 0.5:
                raise ValueError("La consigne Confort doit être au moins 0,5 °C au-dessus de la consigne Éco.")
            settings = await self.async_ensure_settings(device_id, refresh=True)
            try:
                maximum = float(settings.get("maxSetpointC", 30))
            except (TypeError, ValueError) as err:
                raise ValueError("La butée maximale du radiateur est invalide.") from err
            if comfort_value > maximum:
                raise ValueError(
                    f"La consigne Confort ({comfort_value:g} °C) dépasse la butée maximale ({maximum:g} °C)."
                )
        lock = self.program_locks.setdefault(device_id, asyncio.Lock())
        async with lock:
            _LOGGER.info(
                "Envoi d'une modification de programme Econergy (radiateur=%s, champs=%s)",
                device_id,
                ",".join(sorted(changes)),
            )
            result = await self.api.patch_program(device_id, changes)
            _LOGGER.info(
                "Commande programme Econergy reçue (commande=%s, statut=%s)",
                result.get("command_id"),
                result.get("command_status"),
            )
            deadline = asyncio.get_running_loop().time() + PROGRAM_CONFIRM_TIMEOUT_SECONDS
            program: dict[str, Any] | None = None
            last_read_error: str | None = None

            while asyncio.get_running_loop().time() < deadline:
                try:
                    program = await self.api.get_program(device_id)
                    last_read_error = None
                    if self._program_matches(program, changes):
                        break
                except EconergyAuthError:
                    raise
                except EconergyApiError as err:
                    last_read_error = str(err)

                await asyncio.sleep(PROGRAM_POLL_INTERVAL_SECONDS)

            if program is None or not self._program_matches(program, changes):
                details = f" Dernière erreur de lecture : {last_read_error}." if last_read_error else ""
                observed: dict[str, Any] = {}
                if program is not None:
                    if "ecoC" in changes:
                        observed["ecoC"] = program.get("ecoC")
                    if "comfortC" in changes:
                        observed["comfortC"] = program.get("comfortC")
                    for day_key in (changes.get("days") or {}):
                        observed[day_key] = (program.get("days") or {}).get(day_key)
                _LOGGER.error(
                    "Lecture de confirmation Econergy différente de la demande (commande=%s, demandé=%s, relu=%s)",
                    result.get("command_id"),
                    changes,
                    observed,
                )
                raise UpdateFailed(
                    f"Commande Econergy {result.get('command_id')} acceptée ({result.get('command_status')}), "
                    f"mais l'API ne retourne pas les valeurs demandées. Valeurs relues : {observed!r}. "
                    "Aucune nouvelle commande n'a été envoyée."
                    f"{details} Vérifie le programme dans l'application avant de réessayer."
                )

            _LOGGER.info(
                "Programme Econergy confirmé par relecture API (commande=%s, radiateur=%s)",
                result.get("command_id"),
                device_id,
            )
            self.programs[device_id] = program
            self.program_errors.pop(device_id, None)
            self.record_last_command(device_id, {
                "command_id": result.get("command_id"),
                "status": result.get("command_status"),
                "kind": "programme",
                "updated_at": result.get("observed_at"),
            })
            if self.data is not None:
                self.async_set_updated_data({
                    **self.data,
                    "programs": dict(self.programs),
                    "program_errors": dict(self.program_errors),
                    "last_commands": dict(self.last_commands),
                })
            return result

    @staticmethod
    def _deep_merge(old: Any, new: Any) -> Any:
        if isinstance(old, dict) and isinstance(new, dict):
            merged = dict(old)
            for key, value in new.items():
                merged[key] = EconergyCoordinator._deep_merge(merged.get(key), value)
            return merged
        return new

    async def _async_reload_device_inventory(self) -> None:
        """Reload the inventory after a device property change and preserve HA metadata."""
        latest = await self.api.get_devices(self.home_id)
        existing = {str(item.get("id")): item for item in (self.data or {}).get("devices", [])}
        merged_devices = []
        for device in latest:
            device_id = str(device.get("id") or "")
            prior = existing.get(device_id, {})
            merged = self._deep_merge(prior, device)
            if prior.get("_ha_status_request"):
                merged["_ha_status_request"] = prior["_ha_status_request"]
            merged_devices.append(merged)
        if self.data is not None:
            self.async_set_updated_data({**self.data, "devices": merged_devices})

    async def async_rename_device(self, device_id: str, name: str) -> None:
        """Rename (or clear the custom name of) a radiator; API limit is 50 chars."""
        clean_name = " ".join(str(name).strip().split())
        if len(clean_name) > 50:
            raise ValueError("Le nom du radiateur ne doit pas dépasser 50 caractères.")
        payload = {"name": clean_name or None}
        lock = self.device_write_locks.setdefault(device_id, asyncio.Lock())
        async with lock:
            await self.api.patch_device(device_id, payload)
            await self._async_reload_device_inventory()
            current = self.find_device(device_id) or {}
            if clean_name and str(current.get("name") or "") != clean_name:
                raise UpdateFailed("Econergy n'a pas confirmé le nouveau nom du radiateur.")

    async def async_update_device_setting(self, device_id: str, key: str, value: Any) -> dict[str, Any]:
        """Update only the three settings that Econergy documents as writable."""
        if key not in {"maxSetpointC", "keypadLocked", "childProtection"}:
            raise ValueError("Ce réglage n'est pas exposé comme modifiable par l'API Econergy.")
        if key in {"keypadLocked", "childProtection"} and not isinstance(value, bool):
            raise ValueError("Ce réglage attend une valeur marche/arrêt.")
        if key == "maxSetpointC":
            if isinstance(value, bool):
                raise ValueError("La butée maximale doit être une température numérique.")
            value = float(value)
            if not 13.5 <= value <= 30 or abs(value * 2 - round(value * 2)) > 0.0001:
                raise ValueError("La butée maximale doit être comprise entre 13,5 et 30 °C par pas de 0,5 °C.")
            device = self.find_device(device_id) or {}
            # Read the latest mode/consigne directly before lowering a hardware
            # safety limit; the 5-minute inventory may be older than the app.
            latest_device = await self.api.get_device_status(device_id)
            self.update_device_from_status(latest_device)
            state = latest_device.get("state") or {}
            program = await self.async_ensure_program(device_id, refresh=True)
            mode = str(state.get("mode") or "").upper()
            if mode == "MANUAL" and state.get("setpointC") is not None:
                if value < float(state["setpointC"]):
                    raise ValueError("Baisse d'abord la consigne manuelle avant de réduire la butée maximale.")
            if program.get("comfortC") is not None and value < float(program["comfortC"]):
                raise ValueError("Baisse d'abord la consigne Confort avant de réduire la butée maximale.")

        lock = self.device_write_locks.setdefault(device_id, asyncio.Lock())
        async with lock:
            result = await self.api.patch_settings(device_id, {key: value})
            self.record_last_command(device_id, {
                "command_id": result.get("command_id"),
                "status": result.get("command_status"),
                "kind": "réglages",
                "updated_at": result.get("observed_at"),
            })
            latest: dict[str, Any] | None = None
            last_error: str | None = None
            deadline = asyncio.get_running_loop().time() + 20
            while asyncio.get_running_loop().time() < deadline:
                try:
                    latest = await self.api.get_settings(device_id)
                    last_error = None
                    observed = latest.get(key)
                    if isinstance(value, float):
                        matched = observed is not None and abs(float(observed) - value) < 0.01
                    else:
                        matched = observed == value
                    if matched:
                        break
                except EconergyAuthError:
                    raise
                except (EconergyApiError, TypeError, ValueError) as err:
                    last_error = str(err)
                await asyncio.sleep(2)

            if latest is None:
                raise UpdateFailed(f"Impossible de relire les réglages Econergy après la commande : {last_error or 'aucune réponse'}")
            observed = latest.get(key)
            matched = (observed is not None and abs(float(observed) - value) < 0.01) if isinstance(value, float) else observed == value
            if not matched:
                raise UpdateFailed(
                    f"Commande Econergy {result.get('command_id')} reçue ({result.get('command_status')}), "
                    f"mais {key} vaut encore {observed!r}. Aucune seconde commande n'a été envoyée."
                )
            self.settings[device_id] = latest
            self.settings_errors.pop(device_id, None)
            if self.data is not None:
                self.async_set_updated_data({
                    **self.data,
                    "settings": dict(self.settings),
                    "settings_errors": dict(self.settings_errors),
                    "last_commands": dict(self.last_commands),
                })
            return result

    async def async_get_manual(self, device_id: str, lang: str = "fr") -> dict[str, Any]:
        """Retrieve a fresh, temporary PDF URL for the requested radiator."""
        return await self.api.get_manual(device_id, lang)

    async def async_request_device_status(self, device_id: str) -> dict[str, Any]:
        """Request and confirm a fresh radiator status on user demand."""
        device = self.find_device(device_id)
        if device is None:
            raise ValueError("Radiateur Econergy introuvable.")
        latest, status = await self._request_and_confirm_device_status(device)
        refreshed = self._merge_status(device, latest) if latest else dict(device)
        refreshed["_ha_status_request"] = status
        if self.data is not None:
            devices = [
                refreshed if str(item.get("id")) == str(device_id) else item
                for item in self.data.get("devices", [])
            ]
            self.async_set_updated_data({**self.data, "devices": devices})
        return status

    def update_device_from_status(self, status: dict[str, Any]) -> bool:
        """Merge a direct device/status response into cached data immediately."""
        if not isinstance(status, dict) or not status.get("id") or not self.data:
            return False

        device_id = str(status["id"])
        devices = list(self.data.get("devices", []))
        for index, cached in enumerate(devices):
            if str(cached.get("id")) != device_id:
                continue
            merged = dict(cached)
            merged.update(status)
            for key in ("info", "state"):
                old_value = cached.get(key)
                new_value = status.get(key)
                if isinstance(old_value, dict) and isinstance(new_value, dict):
                    merged[key] = {**old_value, **new_value}
            devices[index] = merged
            break
        else:
            devices.append(status)

        self.async_set_updated_data({**self.data, "devices": devices})
        return True

    def find_device(self, device_id: str) -> dict[str, Any] | None:
        if not self.data:
            return None
        return next(
            (device for device in self.data.get("devices", []) if str(device.get("id")) == str(device_id)),
            None,
        )

    def find_program(self, device_id: str) -> dict[str, Any] | None:
        return self.programs.get(str(device_id))
