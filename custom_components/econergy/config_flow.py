"""OAuth configuration flow for Econergy Cloud."""
from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any, override

import voluptuous as vol

from homeassistant.config_entries import SOURCE_REAUTH, ConfigFlowResult
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import EconergyApi, EconergyApiError, EconergyAuthError
from .const import DOMAIN
from .oauth import async_register_oauth_implementation

_LOGGER = logging.getLogger(__name__)


class EconergyConfigFlow(
    config_entry_oauth2_flow.AbstractOAuth2FlowHandler, domain=DOMAIN
):
    """Configure Econergy through its public OAuth 2.0 PKCE application."""

    DOMAIN = DOMAIN
    VERSION = 1

    def __init__(self) -> None:
        super().__init__()
        self._oauth_data: dict[str, Any] | None = None
        self._homes: list[dict[str, Any]] = []

    @property
    @override
    def logger(self) -> logging.Logger:
        return _LOGGER

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        # This is a public app: the client ID is public and PKCE replaces a secret.
        async_register_oauth_implementation(self.hass)
        return await self.async_step_pick_implementation(user_input)

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Ask the user to reconnect the Econergy account."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Start OAuth again after the user confirms reauthentication."""
        if user_input is None:
            return self.async_show_form(step_id="reauth_confirm", data_schema=vol.Schema({}))
        async_register_oauth_implementation(self.hass)
        entry = self._get_reauth_entry()
        implementation = str(entry.data.get("auth_implementation") or DOMAIN)
        return await self.async_step_pick_implementation(
            user_input={"implementation": implementation}
        )

    async def async_oauth_create_entry(
        self, data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Validate the granted account and choose the home for this entry."""
        token = data.get("token") or {}
        if not token.get("access_token"):
            return self.async_abort(reason="oauth_invalid_token")
        if not token.get("refresh_token"):
            # HA's OAuth session renews access tokens with refresh_token. Do not
            # create an entry that would silently stop working at token expiry.
            return self.async_abort(reason="refresh_token_missing")

        api = EconergyApi(
            async_get_clientsession(self.hass), str(token["access_token"]),
        )
        try:
            me = await api.get_me()
            scopes = me.get("scopes") or token.get("scope") or []
            if isinstance(scopes, str):
                granted_scopes = set(scopes.replace(",", " ").split())
            else:
                granted_scopes = set(scopes) if isinstance(scopes, (list, tuple, set)) else set()
            missing = {"readonly", "write"} - granted_scopes
            if missing:
                return self.async_abort(
                    reason="missing_scopes",
                    description_placeholders={"scopes": ", ".join(sorted(missing))},
                )

            homes = await api.get_homes()
            allowed_ids = {str(value) for value in (me.get("homeIds") or [])}
            if allowed_ids:
                homes = [home for home in homes if str(home.get("id")) in allowed_ids]
            if not homes:
                return self.async_abort(reason="no_homes")
        except EconergyAuthError:
            return self.async_abort(reason="oauth_invalid_token")
        except EconergyApiError as err:
            _LOGGER.warning("Unable to validate Econergy OAuth grant: %s", err)
            return self.async_abort(
                reason="cannot_connect",
                description_placeholders={"detail": str(err)},
            )

        # Reauthentication must preserve the already configured home.
        if self.source == SOURCE_REAUTH:
            entry = self._get_reauth_entry()
            home_id = str(entry.data.get("home_id") or "")
            home = next((item for item in homes if str(item.get("id")) == home_id), None)
            if home is None:
                return self.async_abort(reason="reauth_home_unavailable")
            await self.async_set_unique_id(home_id)
            self._abort_if_unique_id_mismatch()
            return self.async_update_reload_and_abort(
                entry,
                data_updates={
                    **data,
                    "home_id": home_id,
                    "home_name": str(home.get("name") or "Econergy"),
                },
            )

        self._oauth_data = data
        self._homes = homes
        if len(homes) == 1:
            return await self._create_entry(homes[0])
        return await self.async_step_select_home()

    async def async_step_select_home(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select one authorized home for this Home Assistant config entry."""
        if not self._homes or self._oauth_data is None:
            return self.async_abort(reason="oauth_flow_expired")

        if user_input is not None:
            selected_id = str(user_input["home_id"])
            home = next(
                (item for item in self._homes if str(item.get("id")) == selected_id),
                None,
            )
            if home is None:
                return self.async_abort(reason="home_not_found")
            return await self._create_entry(home)

        options = {
            str(home["id"]): str(home.get("name") or home["id"])
            for home in self._homes
        }
        return self.async_show_form(
            step_id="select_home",
            data_schema=vol.Schema({vol.Required("home_id"): vol.In(options)}),
        )

    async def _create_entry(self, home: dict[str, Any]) -> ConfigFlowResult:
        home_id = str(home["id"])
        home_name = str(home.get("name") or "Econergy")
        await self.async_set_unique_id(home_id)
        self._abort_if_unique_id_configured()
        assert self._oauth_data is not None
        return self.async_create_entry(
            title=f"Econergy – {home_name}",
            data={**self._oauth_data, "home_id": home_id, "home_name": home_name},
        )
