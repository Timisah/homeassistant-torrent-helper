"""Operation catalogue shared by Home Assistant actions and the LLM API."""

from __future__ import annotations

from dataclasses import dataclass

import probatio as vol

from .const import (
    DESTINATIONS,
    MAX_PAGE_SIZE,
    OP_ADD,
    OP_CONTROL,
    OP_READ,
    OP_REQUEST_DELETION,
)

LIMIT = vol.All(vol.Coerce(int), vol.Range(min=1, max=MAX_PAGE_SIZE))
OFFSET = vol.All(vol.Coerce(int), vol.Range(min=0, max=10000))
TEXT = vol.All(str, vol.Length(min=1, max=300))
HASH = vol.All(str, vol.Length(min=40, max=64))
SELECTION = {
    vol.Required("search_id"): vol.All(str, vol.Length(min=1, max=64)),
    vol.Optional("result_id"): vol.All(str, vol.Length(min=1, max=64)),
    vol.Optional("position"): vol.All(vol.Coerce(int), vol.Range(min=1, max=1000)),
}


@dataclass(frozen=True, slots=True)
class Operation:
    """One backend operation."""

    name: str
    permission: str
    description: str
    schema: vol.Schema
    read_only: bool
    destructive: bool = False
    open_world: bool = False


OPERATIONS: dict[str, Operation] = {
    op.name: op
    for op in (
        Operation(
            "search_torrents",
            OP_READ,
            "Search Jackett for torrents by title. Optional year and release terms "
            "(quality, language). Returns a stored, numbered result list with ids. "
            "Does not download.",
            vol.Schema(
                {
                    vol.Required("query"): TEXT,
                    vol.Optional("year"): vol.All(vol.Coerce(int), vol.Range(min=1900, max=2100)),
                    vol.Optional("terms"): vol.All(str, vol.Length(max=100)),
                    vol.Optional("limit", default=3): LIMIT,
                }
            ),
            read_only=True,
            open_world=True,
        ),
        Operation(
            "get_search_results",
            OP_READ,
            "Show more results of an existing stored search by search_id. Never "
            "re-runs the search.",
            vol.Schema(
                {
                    vol.Required("search_id"): vol.All(str, vol.Length(min=1, max=64)),
                    vol.Optional("offset", default=0): OFFSET,
                    vol.Optional("limit", default=3): LIMIT,
                }
            ),
            read_only=True,
        ),
        Operation(
            "preview_torrent",
            OP_READ,
            "Select one stored result (result_id, or its 1-based position in the "
            "stored list) and verify it can be added. Does not start a download.",
            vol.Schema(SELECTION),
            read_only=False,
            open_world=True,
        ),
        Operation(
            "add_torrent",
            OP_ADD,
            "Start downloading a previewed result, only if the user asked for the "
            "download. destination: movies, shows or downloads. For shows give "
            "show_name (and season) or an explicit subfolder.",
            vol.Schema(
                {
                    **SELECTION,
                    vol.Required("destination"): vol.In(DESTINATIONS),
                    vol.Optional("subfolder"): vol.All(str, vol.Length(min=1, max=500)),
                    vol.Optional("show_name"): TEXT,
                    vol.Optional("show_year"): vol.All(
                        vol.Coerce(int), vol.Range(min=1900, max=2100)
                    ),
                    vol.Optional("season"): vol.All(vol.Coerce(int), vol.Range(min=0, max=9999)),
                }
            ),
            read_only=False,
            open_world=True,
        ),
        Operation(
            "list_torrents",
            OP_READ,
            "List current qBittorrent torrents with progress, state, speeds, size "
            "and paths. Optional name filter; follow next_offset for more.",
            vol.Schema(
                {
                    vol.Optional("query", default=""): vol.All(str, vol.Length(max=200)),
                    vol.Optional("offset", default=0): OFFSET,
                    vol.Optional("limit", default=10): LIMIT,
                }
            ),
            read_only=True,
        ),
        Operation(
            "get_torrent",
            OP_READ,
            "Show one torrent by its exact hash.",
            vol.Schema({vol.Required("hash"): HASH}),
            read_only=True,
        ),
        Operation(
            "pause_torrent",
            OP_CONTROL,
            "Pause one torrent by exact hash.",
            vol.Schema({vol.Required("hash"): HASH}),
            read_only=False,
        ),
        Operation(
            "resume_torrent",
            OP_CONTROL,
            "Resume one torrent by exact hash.",
            vol.Schema({vol.Required("hash"): HASH}),
            read_only=False,
        ),
        Operation(
            "remove_torrent",
            OP_CONTROL,
            "Remove one torrent job from qBittorrent by exact hash. Downloaded "
            "files are kept. Never use this to delete files.",
            vol.Schema({vol.Required("hash"): HASH}),
            read_only=False,
            destructive=True,
        ),
        Operation(
            "request_file_deletion",
            OP_REQUEST_DELETION,
            "Ask for deletion of a torrent AND its files. Deletes nothing: an "
            "administrator must approve it in Home Assistant.",
            vol.Schema({vol.Required("hash"): HASH}),
            read_only=False,
        ),
    )
}

NAME_TO_PERMISSION = {name: op.permission for name, op in OPERATIONS.items()}
