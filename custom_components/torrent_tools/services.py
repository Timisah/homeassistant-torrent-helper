"""Home Assistant actions. They call the same backend as the LLM tools."""

from __future__ import annotations

from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from .const import DOMAIN
from .errors import InvalidInput, NotFound, PermissionDenied, TorrentToolsError
from .operations import OPERATIONS
from .permissions import async_resolve_principal


def async_register_services(hass: HomeAssistant) -> None:
    """Register all actions once, at integration setup."""

    def make_handler(name: str):
        async def handler(call: ServiceCall) -> ServiceResponse:
            entries = hass.config_entries.async_loaded_entries(DOMAIN)
            if not entries:
                raise ServiceValidationError("Torrent Tools is not set up or not loaded.")
            entry = entries[0]
            try:
                # Service calls carry no device identity: a missing user id never
                # means "trusted voice device".
                principal = await async_resolve_principal(hass, entry, call.context)
                return await entry.runtime_data.async_execute(name, dict(call.data), principal)
            except (InvalidInput, NotFound, PermissionDenied) as err:
                raise ServiceValidationError(str(err)) from err
            except TorrentToolsError as err:
                raise HomeAssistantError(str(err)) from err

        return handler

    for name, operation in OPERATIONS.items():
        hass.services.async_register(
            DOMAIN,
            name,
            make_handler(name),
            schema=operation.schema,
            supports_response=SupportsResponse.ONLY,
        )
