"""Authorization, selection state and write safety through the real HA layers."""

import json
import time

import probatio
import pytest
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import llm
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.torrent_tools.const import (
    CONF_AUTOMATION_OPS,
    CONF_USER_IDS,
    CONF_USER_OPS,
    CONF_VOICE_DEVICES,
    CONF_VOICE_OPS,
    DOMAIN,
)
from custom_components.torrent_tools.operations import OPERATIONS

from .conftest import (
    HASH_A,
    HASH_B,
    HASH_C,
    QBT,
    ctx,
    entry_data,
    entry_options,
    jackett_item,
    make_satellite,
    mock_services,
    override,
    setup_entry,
)

RESULTS = [
    jackett_item("Dune 2021 1080p WEB-DL x265", HASH_A, 40),
    jackett_item("Dune 2021 2160p HDR", HASH_B, 10),
    jackett_item("Dune Part Two 2024", HASH_C, 99),
]


async def call(hass, service, data, user=None):
    return await hass.services.async_call(
        DOMAIN,
        service,
        data,
        blocking=True,
        return_response=True,
        context=ctx(user.id if user else None),
    )


async def llm_call(
    hass, entry, name, args, *, user_id=None, device_id=None, assistant="conversation"
):
    api = llm._async_get_apis(hass)[DOMAIN]
    context = llm.LLMContext(
        platform="test",
        context=ctx(user_id),
        language="en",
        assistant=assistant,
        device_id=device_id,
    )
    instance = await api.async_get_api_instance(context)
    tool = next((t for t in instance.tools if t.name == name), None)
    if tool is None:
        return None, instance
    result = await tool.async_call(hass, llm.ToolInput(name, args), context)
    return result, instance


async def prepared(hass, aioclient_mock, entry, **kw):
    mock_services(aioclient_mock, results=RESULTS, **kw)
    await setup_entry(hass, entry)


# ------------------------------------------------------------------ authorization
async def test_admin_search_preview_add(hass, aioclient_mock, mock_entry, hass_admin_user):
    await prepared(hass, aioclient_mock, mock_entry)
    page = await call(hass, "search_torrents", {"query": "Dune", "year": 2021}, hass_admin_user)
    assert [r["position"] for r in page["results"]] == [1, 2, 3]
    assert (
        page["results"][0]["name"] == "Dune 2021 1080p WEB-DL x265"
    )  # title matches first, then seeders
    blob = json.dumps(page).lower()
    assert "magnet:" not in blob and "btih" not in blob and "tracker.example" not in blob
    # Add without preview is refused in code.
    with pytest.raises(ServiceValidationError, match="Preview"):
        await call(
            hass,
            "add_torrent",
            {"search_id": page["search_id"], "position": 1, "destination": "movies"},
            hass_admin_user,
        )
    prev = await call(
        hass, "preview_torrent", {"search_id": page["search_id"], "position": 1}, hass_admin_user
    )
    assert prev["download_started"] is False and prev["info_hash"] == HASH_A
    assert not [c for c in aioclient_mock.mock_calls if str(c[1]).endswith("torrents/add")]
    done = await call(
        hass,
        "add_torrent",
        {"search_id": page["search_id"], "position": 1, "destination": "movies"},
        hass_admin_user,
    )
    assert done["status"] == "submitted" and done["save_path"] == "/data/movies"
    add = [c for c in aioclient_mock.mock_calls if str(c[1]).endswith("torrents/add")]
    assert len(add) == 1 and add[0][2]["savepath"] == "/data/movies"


async def test_anonymous_service_call_denied_by_default(hass, aioclient_mock, mock_entry):
    await prepared(hass, aioclient_mock, mock_entry)
    with pytest.raises(ServiceValidationError, match="without a Home Assistant user"):
        await call(hass, "list_torrents", {})


async def test_automation_ops_are_explicit(hass, aioclient_mock):
    entry = MockConfigEntry(
        domain=DOMAIN, data=entry_data(), options=entry_options(**{CONF_AUTOMATION_OPS: ["read"]})
    )
    await prepared(hass, aioclient_mock, entry)
    assert (await call(hass, "list_torrents", {}))["total"] == 0
    with pytest.raises(ServiceValidationError):
        await call(hass, "pause_torrent", {"hash": HASH_A})


async def test_non_admin_needs_explicit_grant(hass, aioclient_mock, hass_read_only_user):
    entry = MockConfigEntry(domain=DOMAIN, data=entry_data(), options=entry_options())
    await prepared(hass, aioclient_mock, entry)
    with pytest.raises(ServiceValidationError, match="no torrent permissions"):
        await call(hass, "list_torrents", {}, hass_read_only_user)
    hass.config_entries.async_update_entry(
        entry,
        options=entry_options(**{CONF_USER_IDS: [hass_read_only_user.id], CONF_USER_OPS: ["read"]}),
    )
    await hass.async_block_till_done()
    assert (await call(hass, "list_torrents", {}, hass_read_only_user))["total"] == 0
    with pytest.raises(ServiceValidationError, match="not permitted"):
        await call(hass, "pause_torrent", {"hash": HASH_A}, hass_read_only_user)


async def test_voice_device_trust_matrix(
    hass, aioclient_mock, mock_entry, hass_admin_user, hass_read_only_user
):
    await prepared(hass, aioclient_mock, mock_entry, torrents=[])
    sat = make_satellite(hass, mock_entry, "kitchen")
    other = make_satellite(hass, mock_entry, "bedroom")

    # Nothing trusted yet: denied, and no tools are offered.
    result, instance = await llm_call(hass, mock_entry, "list_torrents", {}, device_id=sat)
    assert result is None and not instance.tools and "not available" in instance.api_prompt

    hass.config_entries.async_update_entry(
        mock_entry, options=entry_options(**{CONF_VOICE_DEVICES: [sat], CONF_VOICE_OPS: ["read"]})
    )
    await hass.async_block_till_done()

    ok, instance = await llm_call(hass, mock_entry, "list_torrents", {}, device_id=sat)
    assert not ok.error and {t.name for t in instance.tools} == {
        n for n, o in OPERATIONS.items() if o.permission == "read"
    }
    # Another satellite that is not trusted.
    assert (await llm_call(hass, mock_entry, "list_torrents", {}, device_id=other))[0] is None
    # Not an Assist conversation origin.
    assert (
        await llm_call(hass, mock_entry, "list_torrents", {}, device_id=sat, assistant="other")
    )[0] is None
    # No device at all, no user.
    assert (await llm_call(hass, mock_entry, "list_torrents", {}))[0] is None
    # A device that is trusted but owns no satellite entity cannot be verified.
    from homeassistant.helpers import device_registry as dr

    plain = dr.async_get(hass).async_get_or_create(
        config_entry_id=mock_entry.entry_id, identifiers={("t", "plain")}
    )
    hass.config_entries.async_update_entry(
        mock_entry,
        options=entry_options(**{CONF_VOICE_DEVICES: [sat, plain.id], CONF_VOICE_OPS: ["read"]}),
    )
    await hass.async_block_till_done()
    assert (await llm_call(hass, mock_entry, "list_torrents", {}, device_id=plain.id))[0] is None
    # Trusted voice may not add/control/delete when only read is granted.
    assert (await llm_call(hass, mock_entry, "add_torrent", {}, device_id=sat))[0] is None
    # Even a direct call of a hidden tool class is re-checked by the backend.
    api = llm._async_get_apis(hass)[DOMAIN]
    from custom_components.torrent_tools.llm_api import TorrentTool

    tool = TorrentTool(mock_entry, mock_entry.runtime_data, OPERATIONS["pause_torrent"])
    context = llm.LLMContext("t", ctx(), "en", "conversation", sat)
    res = await tool.async_call(hass, llm.ToolInput("pause_torrent", {"hash": HASH_A}), context)
    assert res.error and "not permitted" in res.data["error"]

    # Forged: a logged-in non-admin user claiming the trusted device id is only ever that user.
    res, _ = await llm_call(
        hass, mock_entry, "list_torrents", {}, user_id=hass_read_only_user.id, device_id=sat
    )
    assert res is None  # no tools offered: user has no grant, device claim ignored
    res = await tool.async_call(
        hass,
        llm.ToolInput("list_torrents", {}),
        llm.LLMContext("t", ctx(hass_read_only_user.id), "en", "conversation", sat),
    )
    assert res.error


async def test_model_cannot_supply_identity_arguments(hass, aioclient_mock, mock_entry):
    await prepared(hass, aioclient_mock, mock_entry)
    sat = make_satellite(hass, mock_entry)
    hass.config_entries.async_update_entry(
        mock_entry,
        options=entry_options(
            **{CONF_VOICE_DEVICES: [sat], CONF_VOICE_OPS: ["read", "add", "control"]}
        ),
    )
    await hass.async_block_till_done()
    for forged in (
        {"user_id": "x"},
        {"device_id": sat},
        {"is_admin": True},
        {"context": {"user_id": "x"}},
    ):
        res, _ = await llm_call(hass, mock_entry, "list_torrents", forged, device_id=sat)
        assert res.error and "not a valid option" in res.data["error"]


async def test_tool_schemas_convert_for_llm_providers(hass, aioclient_mock, mock_entry):
    await prepared(hass, aioclient_mock, mock_entry)
    for op in OPERATIONS.values():
        schema = probatio.to_openapi(op.schema, openapi_version="3.1.0")
        assert schema["type"] == "object"
    assert OPERATIONS["remove_torrent"].destructive and OPERATIONS["search_torrents"].read_only


# -------------------------------------------------------------- stored selections
async def test_other_owner_cannot_use_someones_search(
    hass, aioclient_mock, mock_entry, hass_admin_user
):
    await prepared(hass, aioclient_mock, mock_entry)
    sat = make_satellite(hass, mock_entry)
    hass.config_entries.async_update_entry(
        mock_entry,
        options=entry_options(**{CONF_VOICE_DEVICES: [sat], CONF_VOICE_OPS: ["read", "add"]}),
    )
    await hass.async_block_till_done()
    page = await call(hass, "search_torrents", {"query": "Dune"}, hass_admin_user)
    res, _ = await llm_call(
        hass, mock_entry, "get_search_results", {"search_id": page["search_id"]}, device_id=sat
    )
    assert res.error and "expired or does not exist" in res.data["error"]
    res, _ = await llm_call(
        hass,
        mock_entry,
        "preview_torrent",
        {"search_id": page["search_id"], "position": 1},
        device_id=sat,
    )
    assert res.error


async def test_selection_survives_restart(
    hass, aioclient_mock, mock_entry, hass_admin_user, hass_storage
):
    await prepared(hass, aioclient_mock, mock_entry)
    page = await call(hass, "search_torrents", {"query": "Dune"}, hass_admin_user)
    await hass.config_entries.async_reload(mock_entry.entry_id)
    again = await call(
        hass, "get_search_results", {"search_id": page["search_id"]}, hass_admin_user
    )
    assert again["results"] == page["results"]


async def test_search_expires_after_24h(hass, aioclient_mock, mock_entry, hass_admin_user):
    await prepared(hass, aioclient_mock, mock_entry)
    page = await call(hass, "search_torrents", {"query": "Dune"}, hass_admin_user)
    state = mock_entry.runtime_data.state
    state.data["searches"][page["search_id"]]["expires_at"] = time.time() - 1
    with pytest.raises(ServiceValidationError, match="expired"):
        await call(hass, "get_search_results", {"search_id": page["search_id"]}, hass_admin_user)


async def test_unsupported_torrent_file_result(hass, aioclient_mock, mock_entry, hass_admin_user):
    items = [jackett_item("File only", None, 5, Link="http://elsewhere.example/a.torrent")]
    mock_services(aioclient_mock, results=items)
    await setup_entry(hass, mock_entry)
    page = await call(hass, "search_torrents", {"query": "File"}, hass_admin_user)
    assert page["results"][0]["can_add"] is False
    with pytest.raises(HomeAssistantError, match="no supported magnet"):
        await call(
            hass,
            "preview_torrent",
            {"search_id": page["search_id"], "position": 1},
            hass_admin_user,
        )


async def test_jackett_reference_resolved_via_jackett_only(
    hass, aioclient_mock, mock_entry, hass_admin_user
):
    items = [jackett_item("Proxy Dune", None, 5)]
    mock_services(aioclient_mock, results=items)
    await setup_entry(hass, mock_entry)
    page = await call(hass, "search_torrents", {"query": "Dune"}, hass_admin_user)
    assert page["results"][0]["reference_type"] == "jackett_reference"
    prev = await call(
        hass, "preview_torrent", {"search_id": page["search_id"], "position": 1}, hass_admin_user
    )
    assert prev["info_hash"] == HASH_A
    hosts = {str(c[1]).split("/")[2] for c in aioclient_mock.mock_calls}
    assert hosts <= {"jackett.test:9117", "qbt.test:8080"}  # nothing else was ever contacted


# --------------------------------------------------------------- write safety
async def _selected(hass, user, query="Dune 2021", position=1):
    page = await call(hass, "search_torrents", {"query": query}, user)
    await call(
        hass, "preview_torrent", {"search_id": page["search_id"], "position": position}, user
    )
    return page["search_id"]


async def test_duplicate_is_not_resubmitted(hass, aioclient_mock, mock_entry, hass_admin_user):
    await prepared(hass, aioclient_mock, mock_entry)
    sid = await _selected(hass, hass_admin_user)
    args = {"search_id": sid, "position": 1, "destination": "movies"}
    await call(hass, "add_torrent", args, hass_admin_user)
    override(
        aioclient_mock,
        "get",
        f"{QBT}/api/v2/torrents/info",
        text=json.dumps([{"hash": HASH_A, "name": "Dune"}]),
    )
    again = await call(hass, "add_torrent", args, hass_admin_user)
    assert again["status"] == "already_present"
    assert len([c for c in aioclient_mock.mock_calls if str(c[1]).endswith("torrents/add")]) == 1


async def test_lost_response_is_uncertain_and_not_blindly_retried(
    hass, aioclient_mock, mock_entry, hass_admin_user
):
    await prepared(hass, aioclient_mock, mock_entry)
    sid = await _selected(hass, hass_admin_user)
    args = {"search_id": sid, "position": 1, "destination": "movies"}
    override(aioclient_mock, "post", f"{QBT}/api/v2/torrents/add", exc=TimeoutError)
    with pytest.raises(HomeAssistantError, match="did not confirm"):
        await call(hass, "add_torrent", args, hass_admin_user)
    assert (
        mock_entry.runtime_data.state.data["searches"][sid]["results"][0]["submission"]["state"]
        == "uncertain"
    )
    # Immediate retry: qBittorrent has nothing yet -> still uncertain, no second write.
    override(aioclient_mock, "post", f"{QBT}/api/v2/torrents/add", text="Ok.")
    with pytest.raises(HomeAssistantError, match="unknown outcome"):
        await call(hass, "add_torrent", args, hass_admin_user)
    assert (
        len([c for c in aioclient_mock.mock_calls if str(c[1]).endswith("torrents/add")]) == 1
    )  # no second write
    # Reconciliation: the torrent did arrive after all.
    override(
        aioclient_mock,
        "get",
        f"{QBT}/api/v2/torrents/info",
        text=json.dumps([{"hash": HASH_A, "name": "Dune"}]),
    )
    res = await call(hass, "add_torrent", args, hass_admin_user)
    assert res["status"] == "already_present"


async def test_uncertain_retry_allowed_only_after_wait_and_if_absent(
    hass, aioclient_mock, mock_entry, hass_admin_user
):
    await prepared(hass, aioclient_mock, mock_entry)
    sid = await _selected(hass, hass_admin_user)
    args = {"search_id": sid, "position": 1, "destination": "movies"}
    override(aioclient_mock, "post", f"{QBT}/api/v2/torrents/add", exc=TimeoutError)
    with pytest.raises(HomeAssistantError):
        await call(hass, "add_torrent", args, hass_admin_user)
    sub = mock_entry.runtime_data.state.data["searches"][sid]["results"][0]["submission"]
    sub["at"] -= 1000
    override(aioclient_mock, "post", f"{QBT}/api/v2/torrents/add", text="Ok.")
    assert (await call(hass, "add_torrent", args, hass_admin_user))["status"] == "submitted"


async def test_rejected_and_unreachable_writes(hass, aioclient_mock, mock_entry, hass_admin_user):
    await prepared(hass, aioclient_mock, mock_entry)
    sid = await _selected(hass, hass_admin_user)
    args = {"search_id": sid, "position": 1, "destination": "movies"}
    override(aioclient_mock, "post", f"{QBT}/api/v2/torrents/add", text="Fails.")
    with pytest.raises(HomeAssistantError, match="rejected"):
        await call(hass, "add_torrent", args, hass_admin_user)
    assert (
        mock_entry.runtime_data.state.data["searches"][sid]["results"][0]["submission"]["state"]
        == "failed"
    )
    override(aioclient_mock, "post", f"{QBT}/api/v2/torrents/add", text="Ok.")
    assert (await call(hass, "add_torrent", args, hass_admin_user))[
        "status"
    ] == "submitted"  # definite failure may be retried


async def test_destination_rules(hass, aioclient_mock, hass_admin_user):
    entry = MockConfigEntry(
        domain=DOMAIN, data=entry_data(), options=entry_options(root_downloads="")
    )
    await prepared(hass, aioclient_mock, entry)
    sid = await _selected(hass, hass_admin_user)
    base = {"search_id": sid, "position": 1}
    with pytest.raises(ServiceValidationError, match="not configured"):
        await call(hass, "add_torrent", {**base, "destination": "downloads"}, hass_admin_user)
    for bad in ("../etc", "/abs", "a/../../b", "x:y"):
        with pytest.raises(ServiceValidationError):
            await call(
                hass,
                "add_torrent",
                {**base, "destination": "movies", "subfolder": bad},
                hass_admin_user,
            )
    with pytest.raises(Exception):
        await call(hass, "add_torrent", {**base, "destination": "/etc"}, hass_admin_user)
    ok = await call(
        hass,
        "add_torrent",
        {**base, "destination": "movies", "subfolder": "Dune (2021)"},
        hass_admin_user,
    )
    assert ok["save_path"] == "/data/movies/Dune (2021)"


async def test_tv_requires_metadata_or_explicit_subfolder(
    hass, aioclient_mock, mock_entry, hass_admin_user
):
    await prepared(hass, aioclient_mock, mock_entry)  # API 2.11: no metadata endpoint
    sid = await _selected(hass, hass_admin_user)
    base = {"search_id": sid, "position": 1, "destination": "shows"}
    with pytest.raises(ServiceValidationError, match="show_name"):
        await call(hass, "add_torrent", base, hass_admin_user)
    with pytest.raises(ServiceValidationError, match="explicit subfolder"):
        await call(hass, "add_torrent", {**base, "show_name": "Show", "season": 1}, hass_admin_user)
    assert not [c for c in aioclient_mock.mock_calls if str(c[1]).endswith("torrents/add")]
    ok = await call(
        hass, "add_torrent", {**base, "subfolder": "Show (2020)/Season 01"}, hass_admin_user
    )
    assert ok["save_path"] == "/data/shows/Show (2020)/Season 01"


async def test_tv_plan_from_metadata_without_adding(
    hass, aioclient_mock, mock_entry, hass_admin_user
):
    await prepared(hass, aioclient_mock, mock_entry, api_version="2.17.0")
    meta = {
        "infohash_v1": HASH_A,
        "id": HASH_A,
        "info": {
            "name": "Show.S02",
            "files": [
                {"path": "Show.S02/Show.S02E01.mkv", "length": 5},
                {"path": "Show.S02/Show.S02E02.mkv", "length": 5},
            ],
        },
    }
    override(aioclient_mock, "post", f"{QBT}/api/v2/torrents/fetchMetadata", json=meta)
    sid = await _selected(hass, hass_admin_user)
    res = await call(
        hass,
        "add_torrent",
        {
            "search_id": sid,
            "position": 1,
            "destination": "shows",
            "show_name": "Show",
            "show_year": 2020,
        },
        hass_admin_user,
    )
    assert res["save_path"] == "/data/shows/Show (2020)/Season 02"
    adds = [c for c in aioclient_mock.mock_calls if str(c[1]).endswith("torrents/add")]
    assert len(adds) == 1 and adds[0][2]["contentLayout"] == "NoSubfolder"
    # Metadata for a different torrent must be refused.
    sid2 = await _selected(hass, hass_admin_user, position=2)
    meta["infohash_v1"] = meta["id"] = "f" * 40
    override(aioclient_mock, "post", f"{QBT}/api/v2/torrents/fetchMetadata", json=meta)
    with pytest.raises(ServiceValidationError, match="did not match"):
        await call(
            hass,
            "add_torrent",
            {
                "search_id": sid2,
                "position": 2,
                "destination": "shows",
                "show_name": "Show",
                "season": 2,
            },
            hass_admin_user,
        )


# ------------------------------------------------------------------ management
TORRENT = {
    "hash": HASH_A,
    "name": "Dune",
    "size": 10,
    "total_size": 10,
    "progress": 0.5,
    "state": "downloading",
    "save_path": "/data/movies",
    "content_path": "/data/movies/Dune",
    "dlspeed": 1,
    "upspeed": 0,
}


async def test_control_uses_exact_hash_and_keeps_files(hass, aioclient_mock, hass_admin_user):
    entry = MockConfigEntry(domain=DOMAIN, data=entry_data(), options=entry_options())
    await prepared(hass, aioclient_mock, entry, torrents=[TORRENT])
    listed = await call(hass, "list_torrents", {}, hass_admin_user)
    assert listed["torrents"][0]["progress_percent"] == 50.0
    for bad in ("Dune", HASH_A[:10], f"{HASH_A}|{HASH_B}", "all"):
        with pytest.raises(Exception):
            await call(hass, "pause_torrent", {"hash": bad}, hass_admin_user)
    with pytest.raises(ServiceValidationError, match="No torrent"):
        await call(hass, "pause_torrent", {"hash": HASH_B}, hass_admin_user)
    await call(hass, "pause_torrent", {"hash": HASH_A.upper()}, hass_admin_user)
    await call(hass, "remove_torrent", {"hash": HASH_A}, hass_admin_user)
    deletes = [c for c in aioclient_mock.mock_calls if str(c[1]).endswith("torrents/delete")]
    assert deletes[-1][2]["deleteFiles"] == "false" and deletes[-1][2]["hashes"] == HASH_A


# --------------------------------------------------------------------- deletion
async def test_file_deletion_needs_admin_approval(
    hass,
    aioclient_mock,
    hass_ws_client,
    hass_admin_user,
    hass_read_only_user,
    hass_admin_credential,
):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=entry_data(),
        options=entry_options(**{CONF_AUTOMATION_OPS: ["request_deletion"]}),
    )
    await prepared(hass, aioclient_mock, entry, torrents=[TORRENT])
    sat = make_satellite(hass, entry)
    hass.config_entries.async_update_entry(
        entry,
        options=entry_options(
            **{
                CONF_VOICE_DEVICES: [sat],
                CONF_VOICE_OPS: ["read", "request_deletion", "control", "add"],
            }
        ),
    )
    await hass.async_block_till_done()

    # The voice device can only request. Nothing is deleted.
    res, _ = await llm_call(hass, entry, "request_file_deletion", {"hash": HASH_A}, device_id=sat)
    assert (
        not res.error and res.data["files_deleted"] is False and "nonce" not in json.dumps(res.data)
    )
    assert not [c for c in aioclient_mock.mock_calls if str(c[1]).endswith("torrents/delete")]
    # There is no LLM tool that approves or deletes files.
    assert "approve" not in " ".join(OPERATIONS)

    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": "torrent_tools/pending_deletions"})
    pending = (await client.receive_json())["result"]
    assert len(pending) == 1 and pending[0]["policy"] == "any_admin"
    rid, nonce = pending[0]["request_id"], pending[0]["nonce"]

    # Wrong nonce fails and does not consume the request.
    await client.send_json(
        {"id": 2, "type": "torrent_tools/approve_deletion", "request_id": rid, "nonce": "bad"}
    )
    assert not (await client.receive_json())["success"]
    # Fingerprint binding: if the torrent changes, approval is refused.
    changed = dict(TORRENT, content_path="/data/movies/Other")
    override(aioclient_mock, "get", f"{QBT}/api/v2/torrents/info", text=json.dumps([changed]))
    await client.send_json(
        {"id": 3, "type": "torrent_tools/approve_deletion", "request_id": rid, "nonce": nonce}
    )
    msg = await client.receive_json()
    assert not msg["success"] and "changed" in msg["error"]["message"]
    # Single use: request already consumed by the failed attempt above.
    override(aioclient_mock, "get", f"{QBT}/api/v2/torrents/info", text=json.dumps([TORRENT]))
    await client.send_json(
        {"id": 4, "type": "torrent_tools/approve_deletion", "request_id": rid, "nonce": nonce}
    )
    assert not (await client.receive_json())["success"]
    assert not [c for c in aioclient_mock.mock_calls if str(c[1]).endswith("torrents/delete")]

    # Fresh request, approved by an administrator -> files deleted exactly once.
    res, _ = await llm_call(hass, entry, "request_file_deletion", {"hash": HASH_A}, device_id=sat)
    await client.send_json({"id": 5, "type": "torrent_tools/pending_deletions"})
    pending = (await client.receive_json())["result"]
    await client.send_json(
        {
            "id": 6,
            "type": "torrent_tools/approve_deletion",
            "request_id": pending[0]["request_id"],
            "nonce": pending[0]["nonce"],
        }
    )
    done = await client.receive_json()
    assert done["success"] and done["result"]["deleted"]
    deletes = [c for c in aioclient_mock.mock_calls if str(c[1]).endswith("torrents/delete")]
    assert len(deletes) == 1 and deletes[0][2]["deleteFiles"] == "true"
    await client.send_json(
        {
            "id": 7,
            "type": "torrent_tools/approve_deletion",
            "request_id": pending[0]["request_id"],
            "nonce": pending[0]["nonce"],
        }
    )
    assert not (await client.receive_json())["success"]


async def test_requesting_admin_policy_blocks_other_admins(hass, aioclient_mock, hass_admin_user):
    entry = MockConfigEntry(domain=DOMAIN, data=entry_data(), options=entry_options())
    await prepared(hass, aioclient_mock, entry, torrents=[TORRENT])
    res = await call(hass, "request_file_deletion", {"hash": HASH_A}, hass_admin_user)
    assert res["approval"] == "requesting administrator"
    manager = entry.runtime_data
    assert manager.pending_deletions(hass_admin_user.id) and not manager.pending_deletions(
        "other-admin"
    )
    from custom_components.torrent_tools.errors import PermissionDenied

    req = manager.pending_deletions(hass_admin_user.id)[0]
    with pytest.raises(PermissionDenied):
        # an active non-admin is rejected before anything else
        await manager.async_approve_deletion("not-a-user", req["request_id"], req["nonce"])


async def test_deletion_refused_for_unsafe_paths(hass, aioclient_mock, hass_admin_user):
    entry = MockConfigEntry(domain=DOMAIN, data=entry_data(), options=entry_options())
    await prepared(hass, aioclient_mock, entry, torrents=[TORRENT])
    outside = dict(TORRENT, content_path="/etc")
    shared = dict(TORRENT, hash=HASH_B, content_path="/data/movies/Dune/extra")
    for torrents in ([outside], [TORRENT, shared]):
        override(aioclient_mock, "get", f"{QBT}/api/v2/torrents/info", text=json.dumps(torrents))
        with pytest.raises(ServiceValidationError):
            await call(hass, "request_file_deletion", {"hash": HASH_A}, hass_admin_user)
    assert entry.runtime_data.deletions.count() == 0
