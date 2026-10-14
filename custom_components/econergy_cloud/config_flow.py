"""Configuration flow."""
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from .api import EconergyApi, EconergyApiError, EconergyAuthError
from .const import DOMAIN


class EconergyCloudConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            api = EconergyApi(
                async_get_clientsession(self.hass),
                user_input["email"], user_input["password"],
            )
            try:
                await api.login()
                await api.get_home()
            except EconergyAuthError:
                errors["base"] = "invalid_auth"
            except EconergyApiError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(api.home_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=api.home_name or "Econergy", data=user_input,
                )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("email", default=(user_input or {}).get("email", "")): str,
                vol.Required("password"): str,
            }),
            errors=errors,
        )
