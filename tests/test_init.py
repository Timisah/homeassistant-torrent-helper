"""Setup, retry, auth failure, unload, reload and cleanup."""

from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import llm

from custom_components.torrent_tools.const import DOMAIN, PANEL_URL_PATH

from .conftest import JACKETT, QBT, mock_services, override, setup_entry


async def test_setup_unload_reload(hass, aioclient_mock, mock_entry, _no_frontend):
    mock_services(aioclient_mock)
    await setup_entry(hass, mock_entry)
    assert mock_entry.state is ConfigEntryState.LOADED
    assert DOMAIN in llm._async_get_apis(hass)
    assert hass.services.has_service(DOMAIN, "search_torrents")
    _no_frontend.assert_awaited()
    assert _no_frontend.await_args.kwargs["require_admin"] is True
    assert _no_frontend.await_args.kwargs["frontend_url_path"] == PANEL_URL_PATH

    assert await hass.config_entries.async_unload(mock_entry.entry_id)
    assert mock_entry.state is ConfigEntryState.NOT_LOADED
    assert DOMAIN not in llm._async_get_apis(hass)  # API unregistered on unload

    assert await hass.config_entries.async_setup(mock_entry.entry_id)  # re-register works
    assert mock_entry.state is ConfigEntryState.LOADED
    assert await hass.config_entries.async_reload(mock_entry.entry_id)
    assert mock_entry.state is ConfigEntryState.LOADED


async def test_unloaded_actions_fail_cleanly(hass, aioclient_mock, mock_entry):
    import pytest
    from homeassistant.exceptions import ServiceValidationError

    mock_services(aioclient_mock)
    await setup_entry(hass, mock_entry)
    await hass.config_entries.async_unload(mock_entry.entry_id)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "list_torrents", {}, blocking=True, return_response=True
        )


async def test_qbittorrent_down_retries(hass, aioclient_mock, mock_entry):
    mock_services(aioclient_mock)
    override(aioclient_mock, "get", f"{QBT}/api/v2/app/version", exc=TimeoutError)
    mock_entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(mock_entry.entry_id)
    assert mock_entry.state is ConfigEntryState.SETUP_RETRY


async def test_jackett_down_retries(hass, aioclient_mock, mock_entry):
    mock_services(aioclient_mock)
    override(
        aioclient_mock,
        "get",
        f"{JACKETT}/api/v2.0/indexers/all/results/torznab/api",
        exc=TimeoutError,
    )
    mock_entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(mock_entry.entry_id)
    assert mock_entry.state is ConfigEntryState.SETUP_RETRY


async def test_bad_credentials_start_reauth(hass, aioclient_mock, mock_entry):
    mock_services(aioclient_mock)
    override(aioclient_mock, "post", f"{QBT}/api/v2/auth/login", text="Fails.")
    mock_entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(mock_entry.entry_id)
    assert mock_entry.state is ConfigEntryState.SETUP_ERROR
    assert any(
        f["context"]["source"] == "reauth" for f in hass.config_entries.flow.async_progress()
    )


async def test_bad_api_key_starts_reauth(hass, aioclient_mock, mock_entry):
    mock_services(aioclient_mock)
    override(
        aioclient_mock, "get", f"{JACKETT}/api/v2.0/indexers/all/results/torznab/api", status=401
    )
    mock_entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(mock_entry.entry_id)
    assert any(
        f["context"]["source"] == "reauth" for f in hass.config_entries.flow.async_progress()
    )


async def test_remove_entry_deletes_stored_state(hass, aioclient_mock, mock_entry, hass_storage):
    mock_services(aioclient_mock)
    await setup_entry(hass, mock_entry)
    key = f"{DOMAIN}.{mock_entry.entry_id}.searches"
    await mock_entry.runtime_data.store.async_save({"searches": {}})
    assert key in hass_storage
    await hass.config_entries.async_remove(mock_entry.entry_id)
    await hass.async_block_till_done()
    assert key not in hass_storage


async def test_prototype_entry_is_not_migrated(hass, aioclient_mock):
    """A version-1 entry from the earlier prototype fails cleanly, not with a KeyError."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    mock_services(aioclient_mock)
    legacy = MockConfigEntry(
        domain=DOMAIN,
        version=1,
        data={"jackett_url": JACKETT, "api_key": "x", "attach_openai": True},
    )
    legacy.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(legacy.entry_id)
    assert legacy.state is ConfigEntryState.MIGRATION_ERROR
