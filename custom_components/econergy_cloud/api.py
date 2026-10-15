"""Econergy Cloud API: read data and guarded experimental setpoint write."""
from __future__ import annotations

from aiohttp import ClientSession
from copy import deepcopy
import asyncio
import logging

_LOGGER = logging.getLogger(__name__)

from .const import APP_VERSION, BASE_URL


class EconergyApiError(Exception):
    """Cloud request failed."""


class EconergyAuthError(EconergyApiError):
    """Cloud authentication failed."""


class EconergyApi:
    def __init__(self, session: ClientSession, email: str, password: str) -> None:
        self.session = session
        self.email = email
        self.password = password
        self.token: str | None = None
        self.home_id: str | None = None
        self.home_name: str | None = None

    async def _request(self, method: str, path: str, *, payload=None, auth=False):
        headers = {"x-app-version": APP_VERSION}
        if auth and self.token:
            headers["x-session"] = self.token
        try:
            async with self.session.request(
                method, BASE_URL + path, headers=headers, json=payload,
                timeout=20,
            ) as response:
                if response.status in (401, 403):
                    raise EconergyAuthError(f"HTTP {response.status}")
                if response.status >= 400:
                    raise EconergyApiError(f"HTTP {response.status}: {(await response.text())[:160]}")
                data = await response.json(content_type=None)
        except (EconergyApiError, EconergyAuthError):
            raise
        except Exception as exc:
            raise EconergyApiError(str(exc)) from exc
        if not isinstance(data, dict) or data.get("status") != "OK":
            raise EconergyApiError("Unexpected API response")
        return data.get("result")

    async def login(self) -> None:
        result = await self._request("PUT", "/auth", payload={
            "email": self.email,
            "password": self.password,
            "agent": "android",
            "version": APP_VERSION,
        })
        if not isinstance(result, dict) or not result.get("token") or not result.get("homeId"):
            raise EconergyAuthError("Missing token or homeId")
        self.token = result["token"]
        self.home_id = str(result["homeId"])
        self.home_name = result.get("homeName")

    async def get_home(self) -> dict:
        if not self.token:
            await self.login()
        try:
            result = await self._request("GET", f"/v2/homes/{self.home_id}", auth=True)
        except EconergyAuthError:
            await self.login()
            result = await self._request("GET", f"/v2/homes/{self.home_id}", auth=True)
        if not isinstance(result, dict):
            raise EconergyApiError("Home response is not an object")
        return result

    # Fields confirmed from the unmodified radiator configuration returned
    # by /v2/homes/{homeId}. Never create defaults for missing fields.
    REQUIRED_CONFIG_FIELDS = frozenset({
        "mode", "setPoint", "eco", "comfort", "setPointLimit",
        "programs", "openWindowsDetectionEnabled", "vacationReturnDate",
        "limitCoreTemp", "lock", "offset", "detectionPresence", "crc",
    })

    def __init_write_lock(self):
        if not hasattr(self, "_write_lock"):
            self._write_lock = asyncio.Lock()
        return self._write_lock

    @classmethod
    def _validate_config(cls, config: object) -> dict:
        if not isinstance(config, dict):
            raise EconergyApiError("Configuration absente : écriture bloquée")
        missing = cls.REQUIRED_CONFIG_FIELDS.difference(config)
        if missing:
            raise EconergyApiError(
                "Configuration incomplète : écriture bloquée (manque "
                + ", ".join(sorted(missing)) + ")"
            )
        if len(config) != 13:
            raise EconergyApiError(
                f"Configuration inattendue ({len(config)} champs au lieu de 13) : écriture bloquée"
            )
        programs = config.get("programs")
        if not isinstance(programs, list) or len(programs) != 21:
            raise EconergyApiError("Programmation incomplète : écriture bloquée")
        if not isinstance(config.get("mode"), int) or isinstance(config["mode"], bool):
            raise EconergyApiError("Mode actuel invalide : écriture bloquée")
        if not isinstance(config.get("setPoint"), (float, int)) or isinstance(config["setPoint"], bool):
            raise EconergyApiError("Consigne actuelle invalide : écriture bloquée")
        if not isinstance(config.get("crc"), int) or isinstance(config["crc"], bool):
            raise EconergyApiError("CRC absent ou invalide : écriture bloquée")
        return config

    @staticmethod
    def _device_in_home(home: dict, device_id: str) -> dict:
        device = next(
            (d for d in home.get("devices", []) if str(d.get("_id")) == str(device_id)),
            None,
        )
        if device is None:
            raise EconergyApiError("Radiateur introuvable dans le foyer Econergy")
        return device

    async def set_radiator(self, device_id: str, *, mode: int | None = None,
                           temperature: float | None = None) -> None:
        """Preserve all manufacturer configuration, never retry an uncertain write.

        POST-write verification protects against future API changes. An unexpected
        response raises an error rather than silently claiming success.
        """
        if mode is not None and mode not in (0, 1, 3, 4):
            raise EconergyApiError("Mode non pris en charge : écriture bloquée")

        async with self.__init_write_lock():
            # Retry READS only when the API returns a partial configuration.
            # Never send an incomplete configuration or retry a PUT.
            for attempt in range(4):  # Initial read + 3 retries.
                if attempt:
                    await asyncio.sleep(2)
                home = await self.get_home()  # Always fresh, never cached data.
                device = self._device_in_home(home, device_id)
                try:
                    original = self._validate_config(device.get("config"))
                except EconergyApiError as exc:
                    if attempt == 3 or not str(exc).startswith((
                        "Configuration incomplète", "Configuration absente"
                    )):
                        raise
                    _LOGGER.warning(
                        "Econergy: configuration partielle pour %s "
                        "(lecture %s/4) ; nouvelle lecture dans 2 s : %s",
                        device_id, attempt + 1, exc,
                    )
                    continue
                break
            payload = deepcopy(original)
            if mode is not None:
                payload["mode"] = mode
            if temperature is not None:
                if not isinstance(temperature, (int, float)) or isinstance(temperature, bool):
                    raise EconergyApiError("Consigne invalide : écriture bloquée")
                payload["setPoint"] = temperature

            if payload == original:
                return

            # CRC is preserved verbatim. Its generation algorithm is unverified.
            # Never synthesize a new CRC or change any other manufacturer setting.
            await self._request(
                "PUT", f"/devices/{device_id}/config", payload=payload, auth=True,
            )

            # GET may lag behind a successful API write; check a few times.
            # These are READS only, not write retries.
            last_error = None
            for attempt in range(3):
                if attempt:
                    await asyncio.sleep(2)
                try:
                    after = self._device_in_home(await self.get_home(), device_id)
                    checked = self._validate_config(after.get("config"))
                except EconergyApiError as exc:
                    last_error = str(exc)
                    continue
                if (checked.get("mode") == payload["mode"]
                        and checked.get("setPoint") == payload["setPoint"]
                        and checked.get("programs") == original["programs"]
                        and set(checked) == set(original)):
                    return
                last_error = "valeurs ou programmation différentes après écriture"
            _LOGGER.error("Econergy: configuration non confirmée après écriture pour %s: %s",
                          device_id, last_error)
            raise EconergyApiError(
                "Écriture envoyée mais configuration non confirmée. "
                "Ne renvoie pas de commande avant vérification dans Econergy. "
                f"Détail : {last_error}"
            )

    async def set_target_temperature(self, device_id: str, temperature: float) -> None:
        await self.set_radiator(device_id, mode=3, temperature=temperature)

    async def set_mode(self, device_id: str, mode: int) -> None:
        await self.set_radiator(device_id, mode=mode)
