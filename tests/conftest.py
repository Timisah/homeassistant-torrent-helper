"""Shared fixtures. All service traffic is mocked; nothing here touches a network."""

from __future__ import annotations

import json
from collections.abc import Generator
from typing import Any
from unittest.mock import patch

import pytest
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry, mock_component
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.torrent_tools.const import (
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

QBT = "http://qbt.test:8080"
JACKETT = "http://jackett.test:9117"
API_KEY = "test-api-key-123"
HASH_A = "a" * 40
HASH_B = "b" * 40
HASH_C = "c" * 40


def magnet(h: str, name: str = "x") -> str:
    return f"magnet:?xt=urn:btih:{h}&dn={name}&tr=udp%3A%2F%2Ftracker.example%3A1337"


def jackett_item(title: str, h: str | None, seeders: int, **extra: Any) -> dict[str, Any]:
    item = {
        "Title": title,
        "Guid": f"guid-{title}",
        "Tracker": "ExampleTracker",
        "Seeders": seeders,
        "Peers": seeders + 1,
        "Size": 2_000_000_000,
        "PublishDate": "2026-01-01T00:00:00Z",
        "MagnetUri": magnet(h) if h else None,
        "Link": f"{JACKETT}/dl/example/?jackett_apikey={API_KEY}&path=abc&file=x",
    }
    item.update(extra)
    return item


@pytest.fixture(autouse=True)
def _custom_integrations(enable_custom_integrations: None) -> None:
    return None


@pytest.fixture(autouse=True)
def _frontend_components(hass: HomeAssistant) -> None:
    """The frontend package is not installed in the test environment."""
    mock_component(hass, "frontend")
    mock_component(hass, "panel_custom")


@pytest.fixture(autouse=True)
def _no_frontend() -> Generator[None]:
    """Panel/static registration needs the real frontend; stub it out in unit tests."""
    with (
        patch("custom_components.torrent_tools.panel_custom.async_register_panel") as panel,
        patch("custom_components.torrent_tools.frontend.async_remove_panel"),
        patch(
            "homeassistant.components.http.HomeAssistantHTTP.async_register_static_paths",
            create=True,
        ),
    ):
        yield panel


class Backend:
    """Mutable fake of both services."""

    def __init__(self, mocker: AiohttpClientMocker) -> None:
        self.mocker = mocker
        self.torrents: list[dict[str, Any]] = []
        self.search_results: list[dict[str, Any]] = []
        self.add_calls: list[dict[str, Any]] = []


def mock_services(mocker: AiohttpClientMocker, **kw: Any) -> None:
    mocker.clear_requests()
    login_headers = {"Set-Cookie": "SID=session123; HttpOnly; Path=/"}
    mocker.post(f"{QBT}/api/v2/auth/login", text="Ok.", cookies={"SID": "session123"})
    mocker.get(f"{QBT}/api/v2/app/version", text="v5.0.0")
    mocker.get(f"{QBT}/api/v2/app/webapiVersion", text=kw.get("api_version", "2.11.3"))
    mocker.get(f"{QBT}/api/v2/torrents/info", text=json.dumps(kw.get("torrents", [])))
    mocker.post(f"{QBT}/api/v2/torrents/add", text=kw.get("add_text", "Ok."))
    mocker.post(f"{QBT}/api/v2/torrents/stop", text="")
    mocker.post(f"{QBT}/api/v2/torrents/start", text="")
    mocker.post(f"{QBT}/api/v2/torrents/delete", text="")
    mocker.get(
        f"{JACKETT}/api/v2.0/indexers/all/results/torznab/api",
        text='<?xml version="1.0"?><indexers><indexer id="a" configured="true"/></indexers>',
    )
    mocker.get(
        f"{JACKETT}/api/v2.0/indexers/all/results",
        text=json.dumps({"Results": kw.get("results", []), "Indexers": [{"ID": "a"}]}),
    )
    mocker.get(f"{JACKETT}/dl/example/", status=302, headers={"Location": magnet(HASH_A)})


def entry_data() -> dict[str, Any]:
    return {
        CONF_QBT_URL: QBT,
        CONF_QBT_USERNAME: "admin",
        CONF_QBT_PASSWORD: "secret-pass",
        CONF_QBT_VERIFY_SSL: True,
        CONF_JACKETT_URL: JACKETT,
        CONF_JACKETT_API_KEY: API_KEY,
        CONF_JACKETT_VERIFY_SSL: True,
    }


def entry_options(**over: Any) -> dict[str, Any]:
    options = {
        CONF_ROOT_MOVIES: "/data/movies",
        CONF_ROOT_SHOWS: "/data/shows",
        CONF_ROOT_DOWNLOADS: "/data/downloads",
        CONF_USER_IDS: [],
        CONF_USER_OPS: [],
        CONF_VOICE_DEVICES: [],
        CONF_VOICE_OPS: [],
        CONF_AUTOMATION_OPS: [],
    }
    options.update(over)
    return options


@pytest.fixture
def mock_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN, version=2, data=entry_data(), options=entry_options(), title="Torrent Tools"
    )


async def setup_entry(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def make_satellite(hass: HomeAssistant, entry: MockConfigEntry, name: str = "kitchen") -> str:
    """Create a device that owns an assist_satellite entity; return its device id."""
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={("test", name)}
    )
    er.async_get(hass).async_get_or_create(
        "assist_satellite", "test", name, device_id=device.id, config_entry=entry
    )
    return device.id


def ctx(user_id: str | None = None) -> Context:
    return Context(user_id=user_id)


def override(mocker: AiohttpClientMocker, method: str, url: str, **kwargs: Any) -> None:
    """Register a mock that takes precedence over earlier registrations."""
    getattr(mocker, method)(url, **kwargs)
    mocker._mocks.insert(0, mocker._mocks.pop())
