"""Config, reauth, reconfigure and options flows."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import probatio as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    DeviceSelector,
    DeviceSelectorConfig,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .clients.jackett import JackettClient
from .clients.qbittorrent import QBittorrentClient
from .const import (
    ALL_OPS,
    CONF_AUTOMATION_OPS,
    CONF_JACKETT_API_KEY,
    CONF_JACKETT_URL,
    CONF_JACKETT_VERIFY_SSL,
    CONF_QBT_PASSWORD,
    CONF_QBT_URL,
    CONF_QBT_USERNAME,
    CONF_QBT_VERIFY_SSL,
    CONF_ROOT_DOWNLOADS,
    CONF_ROOT_MOVIES,
    CONF_ROOT_SHOWS,
    CONF_USER_IDS,
    CONF_USER_OPS,
    CONF_VOICE_DEVICES,
    CONF_VOICE_OPS,
    DOMAIN,
)
from .errors import (
    CannotConnect,
    InvalidAuth,
    InvalidInput,
    ServiceResponseError,
    TlsError,
)
from .validation import normalize_service_url, validate_root_path

_LOGGER = logging.getLogger(__name__)

SECRET = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))
URL = TextSelector(TextSelectorConfig(type=TextSelectorType.URL))
TEXT = TextSelector(TextSelectorConfig())
OPS_SELECTOR = SelectSelector(
    SelectSelectorConfig(
        options=list(ALL_OPS),
        multiple=True,
        mode=SelectSelectorMode.LIST,
        translation_key="operations",
    )
)
ROOT_KEYS = (CONF_ROOT_MOVIES, CONF_ROOT_SHOWS, CONF_ROOT_DOWNLOADS)


def _error_key(err: Exception) -> str:
    if isinstance(err, TlsError):
        return "ssl_error"
    if isinstance(err, InvalidAuth):
        return "invalid_auth"
    if isinstance(err, CannotConnect):
        return "cannot_connect"
    if isinstance(err, InvalidInput):
        return "invalid_url"
    if isinstance(err, ServiceResponseError):
        return "unexpected_response"
    return "unknown"


async def validate_qbittorrent(hass: HomeAssistant, data: Mapping[str, Any]) -> dict[str, Any]:
    """Validate with non-mutating requests; return normalized data."""
    url = normalize_service_url(data[CONF_QBT_URL])
    client = QBittorrentClient(
        async_get_clientsession(hass, verify_ssl=data[CONF_QBT_VERIFY_SSL]),
        url,
        data.get(CONF_QBT_USERNAME, ""),
        data.get(CONF_QBT_PASSWORD, ""),
    )
    await client.async_validate()
    return {**data, CONF_QBT_URL: url}


async def validate_jackett(hass: HomeAssistant, data: Mapping[str, Any]) -> dict[str, Any]:
    url = normalize_service_url(data[CONF_JACKETT_URL])
    client = JackettClient(
        async_get_clientsession(hass, verify_ssl=data[CONF_JACKETT_VERIFY_SSL]),
        url,
        data[CONF_JACKETT_API_KEY],
    )
    if await client.async_validate() == 0:
        raise ServiceResponseError("no configured indexers")
    return {**data, CONF_JACKETT_URL: url}


def _qbt_schema(defaults: Mapping[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_QBT_URL, default=defaults.get(CONF_QBT_URL, vol.UNDEFINED)): URL,
            vol.Optional(CONF_QBT_USERNAME, default=defaults.get(CONF_QBT_USERNAME, "")): TEXT,
            vol.Optional(CONF_QBT_PASSWORD, default=""): SECRET,
            vol.Required(
                CONF_QBT_VERIFY_SSL, default=defaults.get(CONF_QBT_VERIFY_SSL, True)
            ): BooleanSelector(),
        }
    )


def _jackett_schema(defaults: Mapping[str, Any], *, key_required: bool = True) -> vol.Schema:
    key_marker = vol.Required if key_required else vol.Optional
    return vol.Schema(
        {
            vol.Required(
                CONF_JACKETT_URL, default=defaults.get(CONF_JACKETT_URL, vol.UNDEFINED)
            ): URL,
            key_marker(CONF_JACKETT_API_KEY, default=""): SECRET,
            vol.Required(
                CONF_JACKETT_VERIFY_SSL, default=defaults.get(CONF_JACKETT_VERIFY_SSL, True)
            ): BooleanSelector(),
        }
    )


def _roots_schema(defaults: Mapping[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Optional(key, description={"suggested_value": defaults.get(key, "")}): TEXT
            for key in ROOT_KEYS
        }
    )


def _clean_roots(user_input: Mapping[str, Any]) -> tuple[dict[str, str], dict[str, str]]:
    roots: dict[str, str] = {}
    errors: dict[str, str] = {}
    for key in ROOT_KEYS:
        value = (user_input.get(key) or "").strip()
        if not value:
            continue
        try:
            roots[key] = validate_root_path(value)
        except InvalidInput:
            errors[key] = "invalid_path"
    if not roots and not errors:
        errors["base"] = "no_destination"
    return roots, errors


class TorrentToolsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up one Jackett + qBittorrent pair."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    # ------------------------------------------------------------------ setup
    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                self._data.update(await validate_qbittorrent(self.hass, user_input))
            except Exception as err:  # noqa: BLE001
                errors["base"] = _error_key(err)
            else:
                return await self.async_step_jackett()
        return self.async_show_form(
            step_id="user", data_schema=_qbt_schema(user_input or {}), errors=errors
        )

    async def async_step_jackett(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                self._data.update(await validate_jackett(self.hass, user_input))
            except ServiceResponseError as err:
                errors["base"] = (
                    "no_indexers" if "no configured" in str(err) else "unexpected_response"
                )
            except Exception as err:  # noqa: BLE001
                errors["base"] = _error_key(err)
            else:
                return await self.async_step_destinations()
        return self.async_show_form(
            step_id="jackett", data_schema=_jackett_schema(user_input or {}), errors=errors
        )

    async def async_step_destinations(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            roots, errors = _clean_roots(user_input)
            if not errors:
                return self.async_create_entry(
                    title="Torrent Tools",
                    data=self._data,
                    options={
                        **roots,
                        CONF_USER_IDS: [],
                        CONF_USER_OPS: [],
                        CONF_VOICE_DEVICES: [],
                        CONF_VOICE_OPS: [],
                        CONF_AUTOMATION_OPS: [],
                    },
                )
        return self.async_show_form(
            step_id="destinations", data_schema=_roots_schema(user_input or {}), errors=errors
        )

    # ----------------------------------------------------------------- reauth
    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_menu()

    async def async_step_reauth_menu(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="reauth_menu", menu_options=["reauth_qbittorrent", "reauth_jackett"]
        )

    async def async_step_reauth_qbittorrent(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self._update_service("reauth_qbittorrent", user_input, qbit=True, reauth=True)

    async def async_step_reauth_jackett(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self._update_service("reauth_jackett", user_input, qbit=False, reauth=True)

    # ------------------------------------------------------------ reconfigure
    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="reconfigure", menu_options=["reconfigure_qbittorrent", "reconfigure_jackett"]
        )

    async def async_step_reconfigure_qbittorrent(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self._update_service(
            "reconfigure_qbittorrent", user_input, qbit=True, reauth=False
        )

    async def async_step_reconfigure_jackett(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self._update_service(
            "reconfigure_jackett", user_input, qbit=False, reauth=False
        )

    async def _update_service(
        self, step_id: str, user_input: dict[str, Any] | None, *, qbit: bool, reauth: bool
    ) -> ConfigFlowResult:
        entry = self._get_reauth_entry() if reauth else self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            merged = {**entry.data, **user_input}
            # An empty secret keeps the stored one.
            secret = CONF_QBT_PASSWORD if qbit else CONF_JACKETT_API_KEY
            if not user_input.get(secret):
                merged[secret] = entry.data.get(secret, "")
            try:
                validated = await (validate_qbittorrent if qbit else validate_jackett)(
                    self.hass, merged
                )
            except ServiceResponseError as err:
                errors["base"] = (
                    "no_indexers" if "no configured" in str(err) else "unexpected_response"
                )
            except Exception as err:  # noqa: BLE001
                errors["base"] = _error_key(err)
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    data=validated,
                    reason="reauth_successful" if reauth else "reconfigure_successful",
                )
        schema = (
            _qbt_schema(entry.data) if qbit else _jackett_schema(entry.data, key_required=False)
        )
        return self.async_show_form(step_id=step_id, data_schema=schema, errors=errors)

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> TorrentToolsOptionsFlow:
        return TorrentToolsOptionsFlow()


class TorrentToolsOptionsFlow(OptionsFlowWithReload):
    """Destinations and explicit permissions."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_show_menu(step_id="init", menu_options=["destinations", "permissions"])

    async def async_step_destinations(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            roots, errors = _clean_roots(user_input)
            if not errors:
                options = {k: v for k, v in self.config_entry.options.items() if k not in ROOT_KEYS}
                return self.async_create_entry(data={**options, **roots})
        return self.async_show_form(
            step_id="destinations",
            data_schema=_roots_schema(user_input or self.config_entry.options),
            errors=errors,
        )

    async def async_step_permissions(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            options = dict(self.config_entry.options)
            options.update(
                {
                    CONF_USER_IDS: user_input.get(CONF_USER_IDS, []),
                    CONF_USER_OPS: user_input.get(CONF_USER_OPS, []),
                    CONF_VOICE_DEVICES: user_input.get(CONF_VOICE_DEVICES, []),
                    CONF_VOICE_OPS: user_input.get(CONF_VOICE_OPS, []),
                    CONF_AUTOMATION_OPS: user_input.get(CONF_AUTOMATION_OPS, []),
                }
            )
            return self.async_create_entry(data=options)
        users = [
            SelectOptionDict(value=u.id, label=u.name or u.id)
            for u in await self.hass.auth.async_get_users()
            if u.is_active and not u.system_generated and not u.is_admin
        ]
        current = self.config_entry.options
        user_selector = SelectSelector(
            SelectSelectorConfig(options=users, multiple=True, mode=SelectSelectorMode.DROPDOWN)
        )
        schema = vol.Schema(
            {
                vol.Optional(CONF_USER_IDS): user_selector,
                vol.Optional(CONF_USER_OPS): OPS_SELECTOR,
                vol.Optional(CONF_VOICE_DEVICES): DeviceSelector(
                    DeviceSelectorConfig(multiple=True, entity=[{"domain": "assist_satellite"}])
                ),
                vol.Optional(CONF_VOICE_OPS): OPS_SELECTOR,
                vol.Optional(CONF_AUTOMATION_OPS): OPS_SELECTOR,
            }
        )
        return self.async_show_form(
            step_id="permissions",
            data_schema=self.add_suggested_values_to_schema(schema, user_input or current),
        )
