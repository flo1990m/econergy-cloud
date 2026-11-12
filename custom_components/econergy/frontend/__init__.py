"""Register the bundled Econergy Lovelace card."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from homeassistant.components.http import StaticPathConfig
from homeassistant.components.lovelace import LOVELACE_DATA
from homeassistant.components import frontend
from homeassistant.components.frontend import add_extra_js_url
from homeassistant.core import (
    CoreState,
    EVENT_HOMEASSISTANT_STARTED,
    HomeAssistant,
)
from homeassistant.helpers.event import async_call_later

_LOGGER = logging.getLogger(__name__)
URL_BASE = "/econergy"
CARD_VERSION = "2.1.2"
CARD_FILENAME = "econergy-weekly-program-card.js"
FRONTEND_DIR = Path(__file__).parent
REGISTRATION_FLAG = "econergy_frontend_registered"


async def async_register_frontend(hass: HomeAssistant) -> None:
    """Serve the bundled card and register it in storage-mode Lovelace."""
    if hass.data.get(REGISTRATION_FLAG):
        return
    hass.data[REGISTRATION_FLAG] = True

    try:
        await hass.http.async_register_static_paths(
            [StaticPathConfig(URL_BASE, FRONTEND_DIR, False)]
        )
        _LOGGER.debug("Econergy frontend path registered: %s", URL_BASE)
    except RuntimeError:
        # This can happen during a reload because the route is global to HA.
        _LOGGER.debug("Econergy frontend path already registered: %s", URL_BASE)
    except Exception:
        # The optional dashboard card must never prevent climate control setup.
        _LOGGER.exception("Unable to register the Econergy frontend path")

    # Load a lightweight module globally so the explicit device-page button
    # can navigate to the editor without the generic "Visiter" device link.
    add_extra_js_url(hass, f"{URL_BASE}/econergy-navigation.js?v={CARD_VERSION}")

    try:
        if not frontend.async_panel_exists(hass, "econergy-program"):
            frontend.async_register_built_in_panel(
                hass,
                component_name="custom",
                frontend_url_path="econergy-program",
                config={
                    "_panel_custom": {
                        "name": "econergy-program-panel",
                        "module_url": f"/econergy/econergy-program-panel.js?v={CARD_VERSION}",
                        "embed_iframe": False,
                    }
                },
                show_in_sidebar=False,
            )
    except Exception:
        _LOGGER.exception("Unable to register the Econergy programming page")

    async def _after_start(_event: Any = None) -> None:
        await _register_lovelace_resource(hass)

    if hass.state == CoreState.running:
        await _after_start()
    else:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _after_start)


async def _register_lovelace_resource(hass: HomeAssistant) -> None:
    """Add or update the card resource once Lovelace storage is ready.

    Home Assistant's Lovelace resource registry is used only in storage
    resource mode. YAML resource mode must declare the URL itself; the static
    path remains available in either mode.
    """
    attempts = 0

    async def _try_register(_now: Any = None) -> None:
        nonlocal attempts
        lovelace = hass.data.get(LOVELACE_DATA)
        resources = getattr(lovelace, "resources", None) if lovelace else None

        if lovelace is None or resources is None:
            attempts += 1
            if attempts <= 60:
                async_call_later(
                    hass,
                    5,
                    lambda now: hass.async_create_task(_try_register(now)),
                )
            else:
                _LOGGER.warning(
                    "Econergy card resource was not registered: Lovelace resources did not become ready."
                )
            return

        resource_mode = getattr(
            lovelace, "resource_mode", getattr(lovelace, "mode", "storage")
        )
        if resource_mode != "storage":
            _LOGGER.info(
                "Econergy card is served at %s/%s; add it manually to Lovelace YAML resources.",
                URL_BASE,
                CARD_FILENAME,
            )
            return

        url = f"{URL_BASE}/{CARD_FILENAME}"
        legacy_url = f"/econergy-cloud-v2/{CARD_FILENAME}"
        versioned_url = f"{url}?v={CARD_VERSION}"
        try:
            # Ensure the storage collection has loaded before inspecting it;
            # otherwise creating a resource could overwrite existing entries.
            await resources.async_get_info()
            existing = [
                item for item in resources.async_items()
                if str(item.get("url", "")).split("?", 1)[0] in {url, legacy_url}
            ]
            if existing:
                item = existing[0]
                if item.get("url") != versioned_url or item.get("res_type") != "module":
                    await resources.async_update_item(
                        item["id"],
                        {"res_type": "module", "url": versioned_url},
                    )
                    _LOGGER.info("Econergy weekly-program card resource updated to %s", CARD_VERSION)
            else:
                await resources.async_create_item(
                    {"res_type": "module", "url": versioned_url}
                )
                _LOGGER.info("Econergy weekly-program card resource registered (%s)", CARD_VERSION)
        except Exception:  # Do not prevent the climate integration from loading.
            _LOGGER.exception("Unable to register the Econergy Lovelace card resource")

    await _try_register()
