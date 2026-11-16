"""Constants for Torrent Tools."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "torrent_tools"

# Connection settings (config entry data)
CONF_QBT_URL: Final = "qbittorrent_url"
CONF_QBT_USERNAME: Final = "qbittorrent_username"
CONF_QBT_PASSWORD: Final = "qbittorrent_password"
CONF_QBT_VERIFY_SSL: Final = "qbittorrent_verify_ssl"
CONF_JACKETT_URL: Final = "jackett_url"
CONF_JACKETT_API_KEY: Final = "jackett_api_key"
CONF_JACKETT_VERIFY_SSL: Final = "jackett_verify_ssl"

# Options
CONF_ROOT_MOVIES: Final = "root_movies"
CONF_ROOT_SHOWS: Final = "root_shows"
CONF_ROOT_DOWNLOADS: Final = "root_downloads"
CONF_USER_IDS: Final = "allowed_user_ids"
CONF_USER_OPS: Final = "user_permissions"
CONF_VOICE_DEVICES: Final = "voice_devices"
CONF_VOICE_OPS: Final = "voice_permissions"
CONF_AUTOMATION_OPS: Final = "automation_permissions"

# Destinations offered to actions and the LLM
DEST_MOVIES: Final = "movies"
DEST_SHOWS: Final = "shows"
DEST_DOWNLOADS: Final = "downloads"
DESTINATIONS: Final = (DEST_MOVIES, DEST_SHOWS, DEST_DOWNLOADS)
DEST_OPTION_KEYS: Final = {
    DEST_MOVIES: CONF_ROOT_MOVIES,
    DEST_SHOWS: CONF_ROOT_SHOWS,
    DEST_DOWNLOADS: CONF_ROOT_DOWNLOADS,
}

# Permission groups. Administrators hold all of them except that approving
# file deletion is a separate, administrator-only action.
OP_READ: Final = "read"
OP_ADD: Final = "add"
OP_CONTROL: Final = "control"
OP_REQUEST_DELETION: Final = "request_deletion"
ALL_OPS: Final = (OP_READ, OP_ADD, OP_CONTROL, OP_REQUEST_DELETION)

# Search state
SEARCH_TTL_SECONDS: Final = 24 * 3600
MAX_SEARCHES: Final = 40
MAX_RESULTS_PER_SEARCH: Final = 100
DEFAULT_PAGE_SIZE: Final = 3
MAX_PAGE_SIZE: Final = 20

# File-deletion confirmations
DELETION_TTL_SECONDS: Final = 600
MAX_PENDING_DELETIONS: Final = 10

# A write whose outcome is unknown may only be repeated after this long and
# only if qBittorrent does not list the torrent.
UNCERTAIN_RETRY_AFTER_SECONDS: Final = 120

# Panel
PANEL_URL_PATH: Final = "torrent-tools-confirm"
PANEL_COMPONENT: Final = "torrent-tools-confirm-panel"
PANEL_STATIC_URL: Final = "/torrent_tools_static/confirm.js"

# Tested minimum qBittorrent WebUI API versions
QBT_API_STOP_START: Final = (2, 11)  # pause/resume renamed stop/start (5.0)
QBT_API_FETCH_METADATA: Final = (2, 17)  # torrents/fetchMetadata (unreleased docs)
