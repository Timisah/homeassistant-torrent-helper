import aiohttp
import pytest
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.torrent_tools.clients.jackett import JackettClient
from custom_components.torrent_tools.clients.qbittorrent import QBittorrentClient
from custom_components.torrent_tools.errors import (
    CannotConnect,
    InvalidAuth,
    RejectedByService,
    ServiceResponseError,
    UncertainOutcome,
    UnsupportedFeature,
)

from .conftest import API_KEY, HASH_A, JACKETT, QBT, magnet, mock_services, override


def qbit(hass, user="admin", pw="pw"):
    return QBittorrentClient(async_get_clientsession(hass), QBT, user, pw)


def jackett(hass):
    return JackettClient(async_get_clientsession(hass), JACKETT, API_KEY)


async def test_qbit_validate_and_cookie_isolated(hass, aioclient_mock):
    mock_services(aioclient_mock)
    client = qbit(hass)
    app, api = await client.async_validate()
    assert app == "v5.0.0" and api == (2, 11, 3)
    # The login cookie is replayed explicitly, scoped to this client only.
    last = aioclient_mock.mock_calls[-1]
    assert "SID=session123" in last[3]["Cookie"]
    other = qbit(hass)
    assert other._cookies == {}


async def test_qbit_bad_password(hass, aioclient_mock):
    mock_services(aioclient_mock)
    override(aioclient_mock, "post", f"{QBT}/api/v2/auth/login", text="Fails.")
    with pytest.raises(InvalidAuth):
        await qbit(hass).async_validate()


async def test_qbit_banned_ip_is_not_invalid_auth(hass, aioclient_mock):
    mock_services(aioclient_mock)
    override(aioclient_mock, "post", f"{QBT}/api/v2/auth/login", status=403)
    with pytest.raises(CannotConnect):
        await qbit(hass).async_validate()


async def test_qbit_redirect_refused(hass, aioclient_mock):
    mock_services(aioclient_mock)
    override(
        aioclient_mock,
        "get",
        f"{QBT}/api/v2/app/version",
        status=302,
        headers={"Location": "http://x/login"},
    )
    with pytest.raises(CannotConnect):
        await qbit(hass).async_validate()


async def test_qbit_no_credentials_requires_open_api(hass, aioclient_mock):
    mock_services(aioclient_mock)
    override(aioclient_mock, "get", f"{QBT}/api/v2/app/version", status=403)
    with pytest.raises(InvalidAuth):
        await qbit(hass, "", "").async_validate()


async def test_qbit_relogin_on_403(hass, aioclient_mock):
    mock_services(aioclient_mock)
    client = qbit(hass)
    await client.async_validate()
    aioclient_mock.clear_requests()
    mock_services(aioclient_mock)
    override(aioclient_mock, "get", f"{QBT}/api/v2/torrents/info", status=403)
    with pytest.raises(InvalidAuth):  # second attempt still 403 -> auth failure, bounded retries
        await client.async_list_torrents()
    logins = [c for c in aioclient_mock.mock_calls if str(c[1]).endswith("auth/login")]
    assert len(logins) == 1


async def test_qbit_write_outcomes(hass, aioclient_mock):
    mock_services(aioclient_mock)
    client = qbit(hass)
    await client.async_validate()
    await client.async_add_magnet(magnet(HASH_A), "/data/movies")
    override(aioclient_mock, "post", f"{QBT}/api/v2/torrents/add", text="Fails.")
    with pytest.raises(RejectedByService):
        await client.async_add_magnet(magnet(HASH_A), "/data/movies")
    override(aioclient_mock, "post", f"{QBT}/api/v2/torrents/add", exc=TimeoutError)
    with pytest.raises(UncertainOutcome):
        await client.async_add_magnet(magnet(HASH_A), "/data/movies")
    override(aioclient_mock, "post", f"{QBT}/api/v2/torrents/add", status=500)
    with pytest.raises(UncertainOutcome):
        await client.async_add_magnet(magnet(HASH_A), "/data/movies")
    override(
        aioclient_mock,
        "post",
        f"{QBT}/api/v2/torrents/add",
        exc=aiohttp.ClientConnectionError("down"),
    )
    with pytest.raises(UncertainOutcome):
        await client.async_add_magnet(magnet(HASH_A), "/data/movies")
    with pytest.raises(Exception):
        await client.async_add_magnet("http://evil.example/x.torrent", "/data/movies")


async def test_qbit_add_sends_explicit_path_and_no_auto_tmm(hass, aioclient_mock):
    mock_services(aioclient_mock)
    client = qbit(hass)
    await client.async_validate()
    await client.async_add_magnet(magnet(HASH_A), "/data/shows/S", "NoSubfolder")
    data = aioclient_mock.mock_calls[-1][2]
    assert data["savepath"] == "/data/shows/S" and data["autoTMM"] == "false"
    assert data["contentLayout"] == "NoSubfolder"


async def test_pause_route_follows_api_version(hass, aioclient_mock):
    mock_services(aioclient_mock, api_version="2.8.3")
    override(aioclient_mock, "post", f"{QBT}/api/v2/torrents/pause", text="")
    client = qbit(hass)
    await client.async_validate()
    await client.async_set_paused(HASH_A, True)
    assert str(aioclient_mock.mock_calls[-1][1]).endswith("/torrents/pause")
    mock_services(aioclient_mock, api_version="2.11.3")
    new = qbit(hass)
    await new.async_validate()
    await new.async_set_paused(HASH_A, True)
    assert str(aioclient_mock.mock_calls[-1][1]).endswith("/torrents/stop")


async def test_metadata_requires_new_api(hass, aioclient_mock):
    mock_services(aioclient_mock)
    client = qbit(hass)
    await client.async_validate()
    with pytest.raises(UnsupportedFeature):
        await client.async_fetch_metadata(magnet(HASH_A))


async def test_jackett_validate_ok_and_counts(hass, aioclient_mock):
    mock_services(aioclient_mock)
    assert await jackett(hass).async_validate() == 1
    assert "t=indexers" in str(aioclient_mock.mock_calls[-1][1])  # no search performed


@pytest.mark.parametrize(
    ("kwargs", "exc"),
    [
        ({"status": 401}, InvalidAuth),
        (
            {"text": '<?xml version="1.0"?><error code="100" description="Invalid API Key"/>'},
            InvalidAuth,
        ),
        ({"text": "<html>login</html>"}, ServiceResponseError),
        ({"text": '<!DOCTYPE x [<!ENTITY a "b">]><indexers/>'}, ServiceResponseError),
        ({"status": 302, "headers": {"Location": "/UI/Login"}}, CannotConnect),
        ({"exc": TimeoutError}, CannotConnect),
    ],
)
async def test_jackett_validate_failures(hass, aioclient_mock, kwargs, exc):
    mock_services(aioclient_mock)
    override(
        aioclient_mock, "get", f"{JACKETT}/api/v2.0/indexers/all/results/torznab/api", **kwargs
    )
    with pytest.raises(exc):
        await jackett(hass).async_validate()


async def test_jackett_safe_reference_strips_key_and_foreign_hosts(hass):
    client = jackett(hass)
    ref = client.safe_reference(f"{JACKETT}/dl/idx/?jackett_apikey={API_KEY}&path=abc&file=f")
    assert ref == "/dl/idx/?path=abc&file=f" and API_KEY not in ref
    assert client.safe_reference("http://evil.example:9117/dl/idx/?path=a") is None
    assert client.safe_reference(f"{JACKETT}/other/x") is None
    assert client.safe_reference("http://u:p@jackett.test:9117/dl/x") is None
    assert client.safe_reference(None) is None


async def test_jackett_resolve(hass, aioclient_mock):
    mock_services(aioclient_mock)
    client = jackett(hass)
    assert (await client.async_resolve_magnet("/dl/example/?path=abc")).startswith("magnet:?xt=")
    assert f"jackett_apikey={API_KEY}" in str(aioclient_mock.mock_calls[-1][1])
    override(aioclient_mock, "get", f"{JACKETT}/dl/example/", status=200, content=b"d8:announce")
    with pytest.raises(UnsupportedFeature):
        await client.async_resolve_magnet("/dl/example/?path=abc")
    override(
        aioclient_mock,
        "get",
        f"{JACKETT}/dl/example/",
        status=302,
        headers={"Location": "http://evil.example/x"},
    )
    with pytest.raises(UnsupportedFeature):
        await client.async_resolve_magnet("/dl/example/?path=abc")
    with pytest.raises(UnsupportedFeature):
        await client.async_resolve_magnet("http://evil.example/dl/x")
