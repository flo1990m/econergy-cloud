"""OAuth 2.0 Authorization Code flow with PKCE for Econergy Lab."""
from __future__ import annotations

from typing import override

from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_entry_oauth2_flow

from .const import (
    DOMAIN,
    OAUTH_AUTHORIZE_URL,
    OAUTH_CLIENT_ID,
    OAUTH_SCOPES,
    OAUTH_TOKEN_URL,
)


class EconergyOAuth2Implementation(
    config_entry_oauth2_flow.LocalOAuth2ImplementationWithPkce
):
    """Public Econergy OAuth client using PKCE S256 and no client secret."""

    def __init__(self, hass: HomeAssistant) -> None:
        super().__init__(
            hass,
            DOMAIN,
            OAUTH_CLIENT_ID,
            OAUTH_AUTHORIZE_URL,
            OAUTH_TOKEN_URL,
            client_secret="",
        )

    @property
    @override
    def name(self) -> str:
        return "Econergy Lab (OAuth PKCE)"

    @property
    @override
    def redirect_uri(self) -> str:
        # Match the URI registered in Econergy Lab, regardless of HA's `my` component state.
        return config_entry_oauth2_flow.MY_AUTH_CALLBACK_PATH

    @property
    @override
    def extra_authorize_data(self) -> dict[str, str]:
        # Preserve the code_challenge and code_challenge_method created by HA.
        return {**super().extra_authorize_data, "scope": OAUTH_SCOPES}


def async_register_oauth_implementation(hass: HomeAssistant) -> None:
    """Register a fresh PKCE verifier for the next config flow."""
    implementation = EconergyOAuth2Implementation(hass)
    config_entry_oauth2_flow.async_register_implementation(
        hass, DOMAIN, implementation
    )
