"""Administrator-only websocket commands for file-deletion approval."""

from __future__ import annotations

import probatio as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN
from .errors import TorrentToolsError


def _manager(hass: HomeAssistant):
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    return entries[0].runtime_data if entries else None


@callback
def async_register_websocket(hass: HomeAssistant) -> None:
    websocket_api.async_register_command(hass, ws_pending)
    websocket_api.async_register_command(hass, ws_approve)


@websocket_api.websocket_command({vol.Required("type"): "torrent_tools/pending_deletions"})
@websocket_api.require_admin
@callback
def ws_pending(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    manager = _manager(hass)
    if manager is None:
        connection.send_error(msg["id"], "not_loaded", "Torrent Tools is not loaded.")
        return
    connection.send_result(msg["id"], manager.pending_deletions(connection.user.id))


@websocket_api.websocket_command(
    {
        vol.Required("type"): "torrent_tools/approve_deletion",
        vol.Required("request_id"): str,
        vol.Required("nonce"): str,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_approve(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    manager = _manager(hass)
    if manager is None:
        connection.send_error(msg["id"], "not_loaded", "Torrent Tools is not loaded.")
        return
    try:
        result = await manager.async_approve_deletion(
            connection.user.id, msg["request_id"], msg["nonce"]
        )
    except TorrentToolsError as err:
        connection.send_error(msg["id"], "torrent_tools_error", str(err))
        return
    connection.send_result(msg["id"], result)
