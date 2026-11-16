"""Who may do what. Identity comes only from Home Assistant, never from tool arguments."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import (
    ALL_OPS,
    CONF_AUTOMATION_OPS,
    CONF_USER_IDS,
    CONF_USER_OPS,
    CONF_VOICE_DEVICES,
    CONF_VOICE_OPS,
)
from .errors import PermissionDenied

CONVERSATION_ASSISTANT = "conversation"


@dataclass(frozen=True, slots=True)
class Principal:
    """An authorized caller. ``owner`` scopes stored searches."""

    kind: str  # "user" | "device" | "automation"
    ident: str
    ops: frozenset[str]
    is_admin: bool = False

    @property
    def owner(self) -> str:
        return f"{self.kind}:{self.ident}"

    def require(self, op: str) -> None:
        if op not in self.ops:
            raise PermissionDenied(
                "You are not permitted to do that. An administrator can grant this "
                "permission in the Torrent Tools options."
            )


def _ops(raw: Any) -> frozenset[str]:
    return frozenset(op for op in (raw or []) if op in ALL_OPS)


def is_satellite_device(hass: HomeAssistant, device_id: str) -> bool:
    """True if the device exists and owns an Assist satellite entity."""
    if dr.async_get(hass).async_get(device_id) is None:
        return False
    return any(
        entry.domain == "assist_satellite"
        for entry in er.async_entries_for_device(er.async_get(hass), device_id)
    )


async def async_resolve_principal(
    hass: HomeAssistant,
    entry: ConfigEntry,
    context: Context | None,
    *,
    device_id: str | None = None,
    assistant: str | None = None,
) -> Principal:
    """Resolve the caller or raise PermissionDenied.

    * A request with a user id is evaluated as that user only. A denied user
      is never downgraded to device or anonymous access, so a logged-in
      client cannot borrow a trusted room device by claiming its id.
    * Without a user id, only a server-provided Assist conversation context
      from an explicitly trusted satellite device is accepted.
    * Service calls without a user id (automations) get only the operations an
      administrator listed for automations (none by default).
    """
    options = entry.options
    user_id = context.user_id if context else None
    if user_id:
        user = await hass.auth.async_get_user(user_id)
        if user is None or not user.is_active or user.system_generated:
            raise PermissionDenied("This Home Assistant user is not active.")
        if user.is_admin:
            return Principal("user", user.id, frozenset(ALL_OPS), True)
        if user.id in (options.get(CONF_USER_IDS) or []):
            ops = _ops(options.get(CONF_USER_OPS))
            if ops:
                return Principal("user", user.id, ops, False)
        raise PermissionDenied(
            "This user has no torrent permissions. An administrator can grant them "
            "in the Torrent Tools options."
        )
    if device_id is not None or assistant is not None:
        if assistant != CONVERSATION_ASSISTANT or not device_id:
            raise PermissionDenied(
                "Voice access requires an Assist conversation from a trusted device."
            )
        if device_id not in (options.get(CONF_VOICE_DEVICES) or []):
            raise PermissionDenied(
                "This device is not trusted for torrent tools. An administrator can "
                "trust it in the Torrent Tools options."
            )
        if not is_satellite_device(hass, device_id):
            raise PermissionDenied(
                "The origin of this request could not be verified as an Assist satellite."
            )
        ops = _ops(options.get(CONF_VOICE_OPS))
        if not ops:
            raise PermissionDenied("No voice operations are enabled for trusted devices.")
        return Principal("device", device_id, ops, False)
    ops = _ops(options.get(CONF_AUTOMATION_OPS))
    if not ops:
        raise PermissionDenied(
            "Calls without a Home Assistant user are not allowed. Call this action "
            "as a permitted user, or enable automation permissions in the options."
        )
    return Principal("automation", "service", ops, False)
