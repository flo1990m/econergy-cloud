"""Asynchronous client for the official Econergy SmartHome API."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable

from aiohttp import ClientError, ClientSession

from homeassistant.exceptions import OAuth2TokenRequestReauthError
from homeassistant.helpers.config_entry_oauth2_flow import OAuth2Session

from .const import (
    BASE_URL,
    COMMAND_ACK_TIMEOUT_SECONDS,
    MODE_FROST,
    MODE_MANUAL,
    PROGRAM_COMMAND_TIMEOUT_SECONDS,
    PROGRAM_POLL_INTERVAL_SECONDS,
    REQUEST_TIMEOUT_SECONDS,
    STATE_CONFIRM_TIMEOUT_SECONDS,
    SUPPORTED_MODES,
    WEEKDAYS,
)
from .program_helpers import validate_periods

_LOGGER = logging.getLogger(__name__)


class EconergyApiError(Exception):
    """An API request failed or returned an unexpected response."""


class EconergyAuthError(EconergyApiError):
    """The Econergy OAuth access token is invalid or expired."""


class EconergyCommandError(EconergyApiError):
    """A command was explicitly rejected by the radiator/API."""

    def __init__(self, message: str, *, command_id: str | None = None, status: str | None = None) -> None:
        super().__init__(message)
        self.command_id = command_id
        self.status = status


class EconergyRateLimitError(EconergyApiError):
    """The API rate-limited a request and supplied a Retry-After delay."""

    def __init__(self, message: str, *, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class EconergyApi:
    """Client for the official Econergy SmartHome API."""

    def __init__(
        self,
        session: ClientSession,
        token: str | None = None,
        *,
        oauth_session: OAuth2Session | None = None,
    ) -> None:
        """Initialize the API client. Bearer auth is used only before entry creation."""
        if oauth_session is None and not token:
            raise ValueError("An OAuth session or access token is required")
        self._session = session
        self._token = token.strip() if token else None
        self._oauth_session = oauth_session
        self.api_version: str | None = None

    async def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        """Make one request; never retry writes."""
        headers = {"Accept": "application/json"}
        if self._oauth_session is None:
            headers["Authorization"] = f"Bearer {self._token}"
        if payload is not None:
            headers["Content-Type"] = "application/json"

        try:
            url = f"{BASE_URL}{path}"
            if self._oauth_session is not None:
                response = await self._oauth_session.async_request(
                    method,
                    url,
                    headers=headers,
                    json=payload,
                    timeout=REQUEST_TIMEOUT_SECONDS,
                )
            else:
                response = await self._session.request(
                    method,
                    url,
                    headers=headers,
                    json=payload,
                    timeout=REQUEST_TIMEOUT_SECONDS,
                )

            async with response:
                version = response.headers.get("X-Econergy-Api-Version")
                if version:
                    self.api_version = version

                try:
                    body = await response.json(content_type=None)
                except (ValueError, ClientError):
                    body = None

                if response.status == 401:
                    error = body.get("error", {}) if isinstance(body, dict) else {}
                    raise EconergyAuthError(
                        str(error.get("message") or "Jeton Econergy invalide ou expiré")
                    )

                if response.status == 429:
                    retry_after_header = response.headers.get("Retry-After")
                    retry_after: float | None = None
                    if retry_after_header:
                        try:
                            retry_after = max(0.0, float(retry_after_header))
                        except (TypeError, ValueError):
                            try:
                                retry_at = parsedate_to_datetime(retry_after_header)
                                if retry_at.tzinfo is None:
                                    retry_at = retry_at.replace(tzinfo=timezone.utc)
                                retry_after = max(
                                    0.0,
                                    (retry_at - datetime.now(timezone.utc)).total_seconds(),
                                )
                            except (TypeError, ValueError, OverflowError):
                                retry_after = None
                    error = body.get("error", {}) if isinstance(body, dict) else {}
                    message = str(error.get("message") or "Limite de requêtes atteinte")
                    raise EconergyRateLimitError(
                        f"HTTP 429 : {message}", retry_after=retry_after
                    )

                if response.status >= 400:
                    error = body.get("error", {}) if isinstance(body, dict) else {}
                    code = str(error.get("code") or f"HTTP_{response.status}")
                    message = str(error.get("message") or "La requête a échoué")
                    if response.status == 403:
                        message = f"Accès refusé ({code}) : {message}"
                    raise EconergyApiError(f"{code} : {message}")

        except OAuth2TokenRequestReauthError as err:
            raise EconergyAuthError(
                "L'autorisation Econergy doit être renouvelée. Reconnectez le compte."
            ) from err
        except (EconergyApiError, EconergyAuthError):
            raise
        except (ClientError, asyncio.TimeoutError, OSError) as err:
            # Do not include request headers or the token in logs/errors.
            raise EconergyApiError(f"Erreur réseau Econergy ({type(err).__name__})") from err

        if not isinstance(body, dict) or "data" not in body:
            raise EconergyApiError("Réponse Econergy inattendue (objet data absent)")
        return body["data"]

    async def get_me(self) -> dict[str, Any]:
        data = await self._request("GET", "/me")
        if not isinstance(data, dict):
            raise EconergyApiError("Réponse /me invalide")
        return data

    async def get_homes(self) -> list[dict[str, Any]]:
        data = await self._request("GET", "/homes")
        if not isinstance(data, list):
            raise EconergyApiError("Réponse /homes invalide")
        return [item for item in data if isinstance(item, dict) and item.get("id")]

    async def validate_home_access(self, home_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        """Validate token scopes and that the selected home belongs to it."""
        me = await self.get_me()
        scopes = me.get("scopes") or []
        missing = {"readonly", "write"} - set(scopes if isinstance(scopes, list) else [])
        if missing:
            raise EconergyApiError(
                "L'application doit disposer des autorisations readonly et write. "
                f"Autorisations manquantes : {', '.join(sorted(missing))}."
            )
        homes = await self.get_homes()
        allowed_ids = set(str(value) for value in (me.get("homeIds") or []))
        home = next(
            (item for item in homes if str(item.get("id")) == str(home_id)),
            None,
        )
        if home is None or (allowed_ids and str(home_id) not in allowed_ids):
            raise EconergyApiError("Ce jeton n'a pas accès au domicile sélectionné")
        return me, home

    async def get_devices(self, home_id: str) -> list[dict[str, Any]]:
        data = await self._request("GET", f"/homes/{home_id}/devices")
        if not isinstance(data, list):
            raise EconergyApiError("Réponse de la liste des radiateurs invalide")
        return [
            item for item in data
            if isinstance(item, dict) and item.get("id") and str(item.get("type", "RADIATOR")).upper() == "RADIATOR"
        ]


    async def patch_device(self, device_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        """Update documented writable device properties (for example its name)."""
        if not isinstance(changes, dict) or not changes:
            raise EconergyApiError("Aucune modification de radiateur fournie")
        data = await self._request("PATCH", f"/devices/{device_id}", payload=changes)
        if not isinstance(data, dict):
            raise EconergyApiError("Réponse de mise à jour du radiateur invalide")
        return data

    async def get_device_status(self, device_id: str) -> dict[str, Any]:
        data = await self._request("GET", f"/devices/{device_id}/status")
        if not isinstance(data, dict) or not data.get("id"):
            raise EconergyApiError("Réponse d'état du radiateur invalide")
        return data

    async def get_manual(self, device_id: str, lang: str = "fr") -> dict[str, Any]:
        """Fetch a fresh, temporary radiator manual URL (never cache the URL)."""
        language = (lang or "fr").strip().lower()[:2]
        data = await self._request(
            "GET", f"/devices/{device_id}/manual?lang={language}"
        )
        if not isinstance(data, dict) or not data.get("url"):
            raise EconergyApiError("Econergy n'a pas retourné de lien de notice")
        return data

    async def get_settings(self, device_id: str) -> dict[str, Any]:
        """Read the documented radiator settings (API 1.4.0+)."""
        data = await self._request("GET", f"/devices/{device_id}/settings")
        if not isinstance(data, dict) or str(data.get("deviceId")) != str(device_id):
            raise EconergyApiError("Réponse des réglages Econergy invalide")
        return data

    async def get_consumption(self, device_id: str) -> dict[str, Any]:
        """Read the last 15 complete daily consumption records for a radiator."""
        data = await self._request("GET", f"/devices/{device_id}/consumption")
        if not isinstance(data, dict) or not isinstance(data.get("days"), list):
            raise EconergyApiError("Réponse de consommation Econergy invalide")
        return data

    async def patch_settings(
        self, device_id: str, changes: dict[str, Any]
    ) -> dict[str, Any]:
        """PATCH documented radiator settings and wait for command acknowledgement."""
        allowed = {"maxSetpointC", "keypadLocked", "childProtection"}
        if not isinstance(changes, dict) or not changes or set(changes) - allowed:
            raise EconergyApiError("Réglages Econergy invalides ou non documentés")
        if "maxSetpointC" in changes:
            value = changes["maxSetpointC"]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise EconergyApiError("La butée maximale attend une température numérique")
            if not 13.5 <= float(value) <= 30 or abs(float(value) * 2 - round(float(value) * 2)) > 0.0001:
                raise EconergyApiError("La butée maximale doit être comprise entre 13,5 et 30 °C, par pas de 0,5 °C")
        for key in ("keypadLocked", "childProtection"):
            if key in changes and not isinstance(changes[key], bool):
                raise EconergyApiError(f"Le réglage {key} attend une valeur booléenne")

        command = await self._request(
            "PATCH", f"/devices/{device_id}/settings", payload=changes
        )
        if not isinstance(command, dict) or not command.get("commandId"):
            raise EconergyApiError("Econergy n'a pas retourné de commandId pour les réglages")
        command_id = str(command["commandId"])
        failed = {"FAILED", "ERROR", "REJECTED", "CANCELLED", "CANCELED", "EXPIRED", "TIMEOUT"}
        terminal = {"ACKNOWLEDGED", "SUCCESS", "SUCCESSFUL", "SUCCEEDED", "COMPLETED", "COMPLETE", "DONE", "ACK", "RECEIVED", "CONFIRMED", "DELIVERED", "APPLIED", "EXECUTED"}
        status = str(command.get("status") or "SENT").upper()
        deadline = asyncio.get_running_loop().time() + PROGRAM_COMMAND_TIMEOUT_SECONDS
        while status not in terminal:
            if status in failed:
                raise EconergyCommandError(
                    f"Le radiateur a refusé les réglages (statut {status}).",
                    command_id=command_id,
                    status=status,
                )
            if asyncio.get_running_loop().time() >= deadline:
                raise EconergyCommandError(
                    f"La commande de réglages {command_id} n'a pas été confirmée. Elle n'a pas été renvoyée.",
                    command_id=command_id,
                    status=status,
                )
            await asyncio.sleep(PROGRAM_POLL_INTERVAL_SECONDS)
            latest = await self.get_command(command_id)
            status = str(latest.get("status") or status).upper()
        return {
            "command_id": command_id,
            "command_status": status,
            "changes": dict(changes),
            "api_version": self.api_version,
            "observed_at": datetime.now(timezone.utc).isoformat(),
        }

    async def get_command(self, command_id: str) -> dict[str, Any]:
        """Read a command status. The status endpoint may omit commandId."""
        data = await self._request("GET", f"/commands/{command_id}")
        if not isinstance(data, dict) or not data.get("status"):
            raise EconergyApiError("Réponse de suivi de commande invalide (statut absent)")
        return data

    async def request_device_status(self, device_id: str) -> dict[str, Any]:
        """Ask one radiator to publish its complete state (official API 1.5.0+)."""
        data = await self._request("POST", f"/devices/{device_id}/status-request")
        if not isinstance(data, dict) or not data.get("commandId"):
            raise EconergyApiError(
                "Econergy n'a pas retourné de commandId pour la demande d'actualisation"
            )
        return data

    async def get_program(self, device_id: str) -> dict[str, Any]:
        """Read a radiator's weekly comfort schedule and Eco/comfort targets."""
        data = await self._request("GET", f"/devices/{device_id}/program")
        if not isinstance(data, dict) or str(data.get("deviceId")) != str(device_id):
            raise EconergyApiError("Réponse de programme hebdomadaire invalide")
        days = data.get("days")
        if not isinstance(days, dict):
            raise EconergyApiError("Le programme Econergy ne contient pas les jours")
        return data

    async def patch_program(
        self,
        device_id: str,
        changes: dict[str, Any],
    ) -> dict[str, Any]:
        """Send one program PATCH and wait for an explicit terminal command status."""
        if not isinstance(changes, dict) or not changes:
            raise EconergyApiError("Aucune modification de programme fournie")
        allowed = {"ecoC", "comfortC", "days"}
        if set(changes) - allowed:
            raise EconergyApiError("Le programme contient un champ non documenté")
        payload = dict(changes)
        for key, minimum, maximum in (("ecoC", 13.0, 19.0), ("comfortC", 13.5, 30.0)):
            if key not in payload:
                continue
            value = payload[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise EconergyApiError(f"{key} doit être une température numérique")
            if not minimum <= float(value) <= maximum or abs(float(value) * 2 - round(float(value) * 2)) > 0.0001:
                raise EconergyApiError(
                    f"{key} doit être comprise entre {minimum:g} et {maximum:g} °C, par pas de 0,5 °C"
                )
        if "days" in payload:
            raw_days = payload["days"]
            if not isinstance(raw_days, dict) or not raw_days or set(raw_days) - set(WEEKDAYS):
                raise EconergyApiError("Les jours du programme doivent être monday à sunday")
            try:
                payload["days"] = {day: validate_periods(periods) for day, periods in raw_days.items()}
            except ValueError as err:
                raise EconergyApiError(str(err)) from err

        command = await self._request(
            "PATCH", f"/devices/{device_id}/program", payload=payload
        )
        if not isinstance(command, dict) or not command.get("commandId"):
            raise EconergyApiError("Econergy n'a pas retourné de commandId pour le programme")

        command_id = str(command["commandId"])
        failed_statuses = {
            "FAILED", "ERROR", "REJECTED", "CANCELLED", "CANCELED", "EXPIRED", "TIMEOUT",
        }
        success_statuses = {
            "SUCCESS", "SUCCESSFUL", "SUCCEEDED", "COMPLETED", "COMPLETE", "DONE",
            "ACK", "ACKNOWLEDGED", "RECEIVED", "CONFIRMED", "DELIVERED", "APPLIED", "EXECUTED",
        }
        status = str(command.get("status") or "SENT").strip().upper()
        _LOGGER.debug("Econergy program command %s initial status: %s", command_id, status)

        if status in failed_statuses:
            raise EconergyCommandError(
                f"Econergy a refusé le programme (statut {status}).",
                command_id=command_id,
                status=status,
            )

        deadline = asyncio.get_running_loop().time() + PROGRAM_COMMAND_TIMEOUT_SECONDS
        last_status_error: str | None = None
        while status not in success_statuses:
            if asyncio.get_running_loop().time() >= deadline:
                detail = f" (dernier statut : {status})" if status else ""
                if last_status_error:
                    detail += f" ; suivi indisponible : {last_status_error}"
                raise EconergyCommandError(
                    f"La commande Econergy {command_id} n'a pas confirmé l'application du programme dans le délai imparti"
                    f"{detail}. Elle n'a pas été renvoyée automatiquement.",
                    command_id=command_id,
                    status=status or "UNKNOWN",
                )

            await asyncio.sleep(PROGRAM_POLL_INTERVAL_SECONDS)
            try:
                latest = await self.get_command(command_id)
            except EconergyAuthError:
                raise
            except EconergyApiError as err:
                # The write has already been sent. Continue read-only status checks;
                # never repeat a PATCH because confirmation is temporarily unavailable.
                last_status_error = str(err)
                continue

            status = str(latest.get("status") or status or "UNKNOWN").strip().upper()
            last_status_error = None
            _LOGGER.debug("Econergy program command %s status: %s", command_id, status)
            if status in failed_statuses:
                raise EconergyCommandError(
                    f"Econergy a signalé l'échec du programme (statut {status}).",
                    command_id=command_id,
                    status=status,
                )

        return {
            "command_id": command_id,
            "command_status": status,
            "api_version": self.api_version,
            "observed_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def _state_matches(
        state: dict[str, Any], mode: str, setpoint_c: float | None
    ) -> bool:
        if str(state.get("mode", "")).upper() != mode:
            return False
        if setpoint_c is None:
            return True
        try:
            return abs(float(state.get("setpointC")) - float(setpoint_c)) < 0.06
        except (TypeError, ValueError):
            return False

    async def send_command(
        self,
        device_id: str,
        *,
        mode: str,
        setpoint_c: float | None = None,
    ) -> dict[str, Any]:
        """Send a command once and return as soon as the API accepts it.

        Confirmation is intentionally handled by ``verify_command`` in a
        background task so Home Assistant can update the requested mode/target
        immediately instead of waiting for the radiator's next state report.
        Writes are never retried.
        """
        mode = mode.upper()
        if mode not in SUPPORTED_MODES:
            raise EconergyApiError(f"Mode non pris en charge : {mode}")
        if setpoint_c is not None:
            if mode != MODE_MANUAL:
                raise EconergyApiError("Une consigne ne peut être envoyée qu'en mode MANUAL")
            if setpoint_c < 13.5 or setpoint_c > 30:
                raise EconergyApiError("La consigne doit être comprise entre 13,5 et 30 °C")
            if abs(setpoint_c * 2 - round(setpoint_c * 2)) > 0.0001:
                raise EconergyApiError("La consigne doit être un multiple de 0,5 °C")

        # Read the previous timestamp so the background verifier can distinguish
        # a fresh report from the cached state. This is read-only.
        before = await self.get_device_status(device_id)
        previous_state = before.get("state") or {}
        previous_updated_at = previous_state.get("updatedAt")
        previously_matching = self._state_matches(previous_state, mode, setpoint_c)

        payload: dict[str, Any] = {"mode": mode}
        if setpoint_c is not None:
            payload["setpointC"] = float(setpoint_c)

        # Exactly one write request. Never retry a command if its result is uncertain.
        command = await self._request(
            "POST", f"/devices/{device_id}/commands", payload=payload
        )
        if not isinstance(command, dict) or not command.get("commandId"):
            raise EconergyApiError("Econergy n'a pas retourné de commandId")

        command_id = str(command["commandId"])
        command_status = str(command.get("status") or "SENT").upper()
        if command_status == "FAILED":
            raise EconergyCommandError(
                "Econergy a immédiatement signalé l'échec de la commande.",
                command_id=command_id,
                status=command_status,
            )

        return {
            "command_id": command_id,
            "command_status": command_status,
            "confirmed": None,
            "verification_error": None,
            "mode_sent": mode,
            "setpoint_sent": setpoint_c,
            "previous_updated_at": previous_updated_at,
            "previously_matching": previously_matching,
            "acknowledged": command_status == "ACKNOWLEDGED",
            "api_version": self.api_version,
            "observed_at": datetime.now(timezone.utc).isoformat(),
        }

    async def verify_command(
        self,
        device_id: str,
        *,
        command_id: str,
        command_status: str,
        mode: str,
        setpoint_c: float | None,
        previous_updated_at: str | None,
        previously_matching: bool = False,
        status_callback: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        """Confirm command receipt and a matching fresh state in the background."""
        command_status = str(command_status or "SENT").upper()
        if status_callback:
            status_callback(command_status)
        verification_error: str | None = None
        latest_device: dict[str, Any] | None = None

        # Poll SENT -> ACKNOWLEDGED / FAILED away from the service-call path.
        ack_deadline = asyncio.get_running_loop().time() + COMMAND_ACK_TIMEOUT_SECONDS
        while command_status == "SENT" and asyncio.get_running_loop().time() < ack_deadline:
            await asyncio.sleep(1)
            try:
                command_result = await self.get_command(command_id)
            except EconergyAuthError:
                verification_error = "Jeton refusé pendant le suivi de la commande"
                break
            except EconergyApiError as err:
                verification_error = f"Suivi de commande indisponible : {err}"
                break

            command_status = str(command_result.get("status") or "SENT").upper()
            if status_callback:
                status_callback(command_status)
            if command_status == "FAILED":
                raise EconergyCommandError(
                    "Le radiateur a signalé l'échec de la commande.",
                    command_id=command_id,
                    status=command_status,
                )

        if command_status == "FAILED":
            raise EconergyCommandError(
                "Le radiateur a signalé l'échec de la commande.",
                command_id=command_id,
                status=command_status,
            )

        # The official API notes that ACKNOWLEDGED means received, not applied.
        # Its state.updatedAt can lag by ~10 seconds, so this polling must not
        # block Home Assistant's climate service call.
        state_deadline = asyncio.get_running_loop().time() + STATE_CONFIRM_TIMEOUT_SECONDS
        confirmed = False
        while True:
            try:
                latest_device = await self.get_device_status(device_id)
            except EconergyAuthError:
                verification_error = "Jeton refusé lors de la vérification de l'état"
                break
            except EconergyApiError as err:
                verification_error = str(err)
                break

            state = latest_device.get("state") or {}
            actual_match = self._state_matches(state, mode, setpoint_c)
            state_updated_at = state.get("updatedAt")
            fresh = bool(state_updated_at and state_updated_at != previous_updated_at)
            if actual_match and (fresh or previously_matching):
                confirmed = True
                verification_error = None
                break

            if asyncio.get_running_loop().time() >= state_deadline:
                break
            await asyncio.sleep(2)

        if not confirmed:
            detail = verification_error or "l'état n'a pas été confirmé par une nouvelle remontée"
            _LOGGER.warning(
                "Econergy: commande %s (%s) accusée %s, mais état non confirmé : %s",
                command_id, mode, command_status, detail,
            )
            verification_error = detail

        return {
            "command_id": command_id,
            "command_status": command_status,
            "confirmed": confirmed,
            "device": latest_device,
            "verification_error": verification_error,
            "mode_sent": mode,
            "setpoint_sent": setpoint_c,
            "acknowledged": command_status == "ACKNOWLEDGED",
            "api_version": self.api_version,
            "observed_at": datetime.now(timezone.utc).isoformat(),
        }
