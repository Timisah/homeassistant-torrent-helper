"""Diagnostics with redaction."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import (
    CONF_AUTOMATION_OPS,
    CONF_JACKETT_API_KEY,
    CONF_JACKETT_URL,
    CONF_QBT_PASSWORD,
    CONF_QBT_URL,
    CONF_QBT_USERNAME,
    CONF_ROOT_DOWNLOADS,
    CONF_ROOT_MOVIES,
    CONF_ROOT_SHOWS,
    CONF_USER_IDS,
    CONF_USER_OPS,
    CONF_VOICE_DEVICES,
    CONF_VOICE_OPS,
)

REDACT = {
    CONF_JACKETT_API_KEY,
    CONF_QBT_PASSWORD,
    CONF_QBT_USERNAME,
    CONF_QBT_URL,
    CONF_JACKETT_URL,
    CONF_ROOT_MOVIES,
    CONF_ROOT_SHOWS,
    CONF_ROOT_DOWNLOADS,
    CONF_USER_IDS,
    CONF_VOICE_DEVICES,
}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry) -> dict[str, Any]:
    manager = entry.runtime_data
    options = dict(entry.options)
    return {
        "data": async_redact_data(dict(entry.data), REDACT),
        "options": async_redact_data(options, REDACT),
        "permissions": {
            "trusted_voice_device_count": len(options.get(CONF_VOICE_DEVICES) or []),
            "voice_operations": options.get(CONF_VOICE_OPS) or [],
            "extra_user_count": len(options.get(CONF_USER_IDS) or []),
            "user_operations": options.get(CONF_USER_OPS) or [],
            "automation_operations": options.get(CONF_AUTOMATION_OPS) or [],
        },
        "qbittorrent": {
            "app_version": manager.qbit.app_version,
            "api_version": ".".join(map(str, manager.qbit.api_version)),
            "metadata_planning_supported": manager.qbit.supports_metadata_fetch,
        },
        "stored_searches": len(manager.state.data.get("searches", {})),
        "pending_deletion_requests": manager.deletions.count(),
    }
