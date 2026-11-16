"""Torrent Tools: Jackett search and qBittorrent control for Home Assistant."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import llm
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .clients.jackett import JackettClient
from .clients.qbittorrent import QBittorrentClient
from .const import (
    CONF_JACKETT_API_KEY,
    CONF_JACKETT_URL,
    CONF_JACKETT_VERIFY_SSL,
    CONF_QBT_PASSWORD,
    CONF_QBT_URL,
    CONF_QBT_USERNAME,
    CONF_QBT_VERIFY_SSL,
    DOMAIN,
    PANEL_COMPONENT,
    PANEL_STATIC_URL,
    PANEL_URL_PATH,
)
from .errors import CannotConnect, InvalidAuth, ServiceResponseError
from .llm_api import TorrentToolsAPI
from .manager import TorrentManager
from .services import async_register_services
from .websocket import async_register_websocket

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type TorrentToolsConfigEntry = ConfigEntry[TorrentManager]

_STATIC_REGISTERED = f"{DOMAIN}_static_registered"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register actions and websocket commands once."""
    async_register_services(hass)
    async_register_websocket(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: TorrentToolsConfigEntry) -> bool:
    """Connect to both services, then expose actions, LLM API and the panel."""
    qbit = QBittorrentClient(
        async_get_clientsession(hass, verify_ssl=entry.data[CONF_QBT_VERIFY_SSL]),
        entry.data[CONF_QBT_URL],
        entry.data.get(CONF_QBT_USERNAME, ""),
        entry.data.get(CONF_QBT_PASSWORD, ""),
    )
    jackett = JackettClient(
        async_get_clientsession(hass, verify_ssl=entry.data[CONF_JACKETT_VERIFY_SSL]),
        entry.data[CONF_JACKETT_URL],
        entry.data[CONF_JACKETT_API_KEY],
    )
    try:
        await qbit.async_validate()
    except InvalidAuth as err:
        raise ConfigEntryAuthFailed("qBittorrent rejected the credentials.") from err
    except (CannotConnect, ServiceResponseError) as err:
        raise ConfigEntryNotReady(f"qBittorrent is not available: {err}") from err
    try:
        await jackett.async_validate()
    except InvalidAuth as err:
        raise ConfigEntryAuthFailed("Jackett rejected the API key.") from err
    except (CannotConnect, ServiceResponseError) as err:
        raise ConfigEntryNotReady(f"Jackett is not available: {err}") from err

    manager = TorrentManager(hass, entry, jackett, qbit)
    await manager.async_load()
    entry.runtime_data = manager

    entry.async_on_unload(llm.async_register_api(hass, TorrentToolsAPI(hass, entry, manager)))

    if not hass.data.get(_STATIC_REGISTERED):
        await hass.http.async_register_static_paths(
            [
                StaticPathConfig(
                    PANEL_STATIC_URL,
                    str(Path(__file__).parent / "panel" / "confirm.js"),
                    cache_headers=False,
                )
            ]
        )
        hass.data[_STATIC_REGISTERED] = True
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_URL_PATH,
        webcomponent_name=PANEL_COMPONENT,
        sidebar_title="Torrent Tools",
        sidebar_icon="mdi:shield-alert",
        module_url=f"{PANEL_STATIC_URL}?v=1",
        require_admin=True,
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: TorrentToolsConfigEntry) -> bool:
    """Remove the panel and drop pending deletion requests."""
    frontend.async_remove_panel(hass, PANEL_URL_PATH)
    entry.runtime_data.deletions.clear()
    return True


async def async_remove_entry(hass: HomeAssistant, entry: TorrentToolsConfigEntry) -> None:
    """Delete stored search state with the entry."""
    from homeassistant.helpers.storage import Store

    await Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.searches", private=True).async_remove()


async def async_migrate_entry(hass: HomeAssistant, entry: TorrentToolsConfigEntry) -> bool:
    """Refuse to load an entry from the earlier prototype instead of crashing.

    Version 1 entries (prototype: Jackett URL and API key only, qBittorrent
    borrowed from another integration) lack the data this version needs and
    cannot be converted automatically.
    """
    if entry.version == 1:
        _LOGGER.error(
            "This Torrent Tools entry was created by the earlier prototype and "
            "cannot be migrated. Remove it and add Torrent Tools again."
        )
        return False
    return entry.version == 2
