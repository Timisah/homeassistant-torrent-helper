# Setup guide

## Before you start

1. **Deploy Jackett and qBittorrent yourself**, ideally both behind a VPN with a kill switch
   ([VPN guide](vpn.md)). Home Assistant must be able to reach both URLs.
2. In **Jackett**, add at least one indexer and copy the **API key** (top right of its dashboard).
3. In **qBittorrent**, enable the WebUI (Tools → Options → WebUI). Note the port and user.
   Use the direct WebUI URL, not a reverse proxy that shows a login page or redirects.
4. Decide your destination folders **as qBittorrent sees them**. If qBittorrent runs in a
   container, these are container paths (for example `/data/movies`), not Home Assistant paths.

## Add the integration

Settings → Devices & services → Add integration → **Torrent Tools**. One setup (one Jackett +
one qBittorrent) is supported.

| Step | Field | Notes |
|---|---|---|
| qBittorrent | URL | `http://host:8080`. No credentials in the URL. |
| | Username / password | Leave both empty only if qBittorrent bypasses authentication for Home Assistant's address. |
| | Verify TLS certificate | On by default. Turn off only for a self-signed certificate on a trusted LAN. |
| Jackett | URL, API key, Verify TLS | Authentication is the Jackett API key only. A reverse proxy that adds its own login (SSO, basic auth) in front of Jackett or qBittorrent is **not supported**; use the direct URLs. |
| Destinations | Movies, TV shows, downloads | At least one. Absolute paths with forward slashes. |

Validation is read-only: it logs in to qBittorrent, reads its version, and lists Jackett's
configured indexers with the Torznab `t=indexers` call (which requires the API key and queries
no tracker). No torrent is added and no search is run during setup.

## Reconfigure, reauthenticate, options

* **Reconfigure** (⋮ on the integration): change URL or credentials per service. An empty
  password/API key keeps the stored one.
* **Reauthentication** starts automatically when a service rejects the stored credentials.
* **Configure** (options): destination folders and permissions. Changes reload the integration.

## Enable the tools in Assist

1. Settings → Voice assistants → your assistant → conversation agent settings.
2. Under *Control Home Assistant* / LLM APIs, enable **Torrent Tools** (nothing is enabled for you).
3. Use a model that supports tool calling. Provider support varies.

Allow people and devices in **Configure → Permissions**; see [permissions](permissions.md).
Administrators work immediately. Voice devices do not until you trust them.

## Backups and removal

Stored searches live in `.storage/torrent_tools.<entry id>.searches` and are deleted with the entry.
Removing the integration never touches qBittorrent, Jackett or any downloaded file.
