import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

from custom_components.torrent_tools.const import (
    CONF_JACKETT_API_KEY,
    CONF_JACKETT_URL,
    CONF_QBT_PASSWORD,
    CONF_QBT_URL,
    CONF_ROOT_MOVIES,
    CONF_VOICE_DEVICES,
    DOMAIN,
)

from .conftest import (
    API_KEY,
    JACKETT,
    QBT,
    make_satellite,
    mock_services,
    override,
    setup_entry,
)

QBT_INPUT = {
    "qbittorrent_url": QBT + "/",
    "qbittorrent_username": "admin",
    "qbittorrent_password": "pw",
    "qbittorrent_verify_ssl": True,
}
JK_INPUT = {"jackett_url": JACKETT, "jackett_api_key": API_KEY, "jackett_verify_ssl": True}


async def start(hass):
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )


async def test_full_flow_creates_entry_without_mutating(hass, aioclient_mock):
    mock_services(aioclient_mock)
    result = await start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], QBT_INPUT)
    assert result["step_id"] == "jackett"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], JK_INPUT)
    assert result["step_id"] == "destinations"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"root_movies": "/data/movies", "root_shows": "/data/shows"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_QBT_URL] == QBT  # normalised
    assert result["options"][CONF_ROOT_MOVIES] == "/data/movies"
    # Only non-mutating, non-search requests were made.
    for method, url, *_ in aioclient_mock.mock_calls:
        text = str(url)
        assert not text.endswith("torrents/add")
        assert "indexers/all/results?" not in text and not text.endswith("/results")
    await hass.async_block_till_done()


@pytest.mark.parametrize(
    ("setup", "error"),
    [
        (lambda m: override(m, "post", f"{QBT}/api/v2/auth/login", text="Fails."), "invalid_auth"),
        (
            lambda m: override(m, "post", f"{QBT}/api/v2/auth/login", exc=TimeoutError),
            "cannot_connect",
        ),
        (
            lambda m: override(
                m, "get", f"{QBT}/api/v2/app/version", status=302, headers={"Location": "/x"}
            ),
            "cannot_connect",
        ),
    ],
)
async def test_qbittorrent_errors_then_recover(hass, aioclient_mock, setup, error):
    mock_services(aioclient_mock)
    setup(aioclient_mock)
    result = await start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], QBT_INPUT)
    assert result["errors"] == {"base": error}
    mock_services(aioclient_mock)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], QBT_INPUT)
    assert result["step_id"] == "jackett"


async def test_jackett_errors(hass, aioclient_mock):
    mock_services(aioclient_mock)
    result = await start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], QBT_INPUT)
    url = f"{JACKETT}/api/v2.0/indexers/all/results/torznab/api"
    for kwargs, error in (
        ({"status": 401}, "invalid_auth"),
        ({"text": "<indexers/>"}, "no_indexers"),
        ({"text": "<html/>"}, "unexpected_response"),
        ({"exc": TimeoutError}, "cannot_connect"),
    ):
        override(aioclient_mock, "get", url, **kwargs)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], JK_INPUT)
        assert result["errors"] == {"base": error}, error


async def test_invalid_url_and_paths(hass, aioclient_mock):
    mock_services(aioclient_mock)
    result = await start(hass)
    bad = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**QBT_INPUT, "qbittorrent_url": "http://u:p@h"}
    )
    assert bad["errors"] == {"base": "invalid_url"}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], QBT_INPUT)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], JK_INPUT)
    bad = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"root_movies": "relative"}
    )
    assert bad["errors"] == {"root_movies": "invalid_path"}
    bad = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert bad["errors"] == {"base": "no_destination"}


async def test_single_instance(hass, aioclient_mock, mock_entry):
    mock_services(aioclient_mock)
    await setup_entry(hass, mock_entry)
    result = await start(hass)
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "single_instance_allowed"


async def test_reauth_keeps_api_key_when_empty_and_reloads(hass, aioclient_mock, mock_entry):
    mock_services(aioclient_mock)
    await setup_entry(hass, mock_entry)
    result = await mock_entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.MENU
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "reauth_qbittorrent"}
    )
    override(aioclient_mock, "post", f"{QBT}/api/v2/auth/login", text="Fails.")
    bad = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**QBT_INPUT, "qbittorrent_password": "wrong"}
    )
    assert bad["errors"] == {"base": "invalid_auth"}
    mock_services(aioclient_mock)
    done = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**QBT_INPUT, "qbittorrent_password": "new-pass"}
    )
    assert done["type"] is FlowResultType.ABORT and done["reason"] == "reauth_successful"
    assert mock_entry.data[CONF_QBT_PASSWORD] == "new-pass"


async def test_reconfigure_jackett_empty_key_keeps_stored(hass, aioclient_mock, mock_entry):
    mock_services(aioclient_mock)
    await setup_entry(hass, mock_entry)
    result = await mock_entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "reconfigure_jackett"}
    )
    done = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"jackett_url": JACKETT + "/", "jackett_verify_ssl": True}
    )
    assert done["reason"] == "reconfigure_successful"
    assert (
        mock_entry.data[CONF_JACKETT_API_KEY] == API_KEY
        and mock_entry.data[CONF_JACKETT_URL] == JACKETT
    )


async def test_options_destinations_and_permissions(
    hass, aioclient_mock, mock_entry, hass_read_only_user
):
    mock_services(aioclient_mock)
    await setup_entry(hass, mock_entry)
    sat = make_satellite(hass, mock_entry)
    result = await hass.config_entries.options.async_init(mock_entry.entry_id)
    assert result["type"] is FlowResultType.MENU
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "permissions"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "allowed_user_ids": [hass_read_only_user.id],
            "user_permissions": ["read"],
            "voice_devices": [sat],
            "voice_permissions": ["read", "add"],
            "automation_permissions": [],
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert mock_entry.options[CONF_VOICE_DEVICES] == [sat]
    assert mock_entry.options[CONF_ROOT_MOVIES] == "/data/movies"  # untouched
    result = await hass.config_entries.options.async_init(mock_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "destinations"}
    )
    bad = await hass.config_entries.options.async_configure(
        result["flow_id"], {"root_movies": "/a/../b"}
    )
    assert bad["errors"] == {"root_movies": "invalid_path"}


async def test_diagnostics_redacted(hass, aioclient_mock, mock_entry):
    import json

    from custom_components.torrent_tools.diagnostics import async_get_config_entry_diagnostics

    mock_services(aioclient_mock)
    await setup_entry(hass, mock_entry)
    blob = json.dumps(await async_get_config_entry_diagnostics(hass, mock_entry))
    for secret in (API_KEY, "secret-pass", "admin", "qbt.test", "jackett.test", "/data/movies"):
        assert secret not in blob
