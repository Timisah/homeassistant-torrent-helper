# Torrent Tools for Home Assistant

Search torrents through **Jackett**, add the one you choose to **qBittorrent**, and manage
your downloads from Home Assistant actions and **Assist** (text or voice, English and German).
It plugs into Home Assistant's native LLM API, so any conversation agent that supports
LLM tools can use it. Domain: `torrent_tools`.

> **Status: v0.1.0, unreleased, not yet reviewed or run against live services.** All tests use
> mocked services. Nothing has been run against a real Jackett, qBittorrent or voice
> satellite yet. Work through the [acceptance checklist](docs/acceptance-checklist.md) on a
> test setup before relying on it.

## What it does

* Search Jackett by title, with optional year and release terms. Results are stored, numbered
  and stable for 24 hours (also across restarts), so "the second one" always means the second
  result you were shown.
* Preview an exact result, then add it to a configured destination (movies, shows, downloads).
* List, pause, resume and remove jobs in qBittorrent (downloaded files are kept).
* Deleting files is never done by the AI. It can only request it; an administrator approves
  the exact torrent on a confirmation page in Home Assistant.
* Voice satellites work **only** for devices an administrator explicitly trusts, with the
  operations an administrator picked. See [permissions](docs/permissions.md).

## What it is not

* Not a VPN, kill switch or leak test. See the VPN section below.
* Not a Claude/ChatGPT plugin, add-on or hosted service. No AI account or key is needed or stored here.
  Speech recognition, text-to-speech, wake words, firmware and the choice of language model are
  outside this project. Not every model/provider supports LLM tools; you select **Torrent Tools**
  as an LLM API in your conversation agent's settings (nothing is attached automatically).
* Does not download or fetch anything itself. Home Assistant only talks to your Jackett and
  qBittorrent APIs. It never contacts indexers or arbitrary download links.
* Not part of the HACS default catalogue and not an official Home Assistant integration.

## VPN: strongly recommended for both services

**A VPN connection with a working kill switch is highly recommended for BOTH Jackett's indexer
traffic and qBittorrent's torrent traffic.** VPN use is optional and provider independent.
This integration does not set up a VPN, check for leaks or provide a kill switch; it only calls
the local APIs of services you deploy. Home Assistant never bypasses them. Use the example in
[docs/vpn.md](docs/vpn.md) (Gluetun, both services in the protected network) and run its
tunnel-down test.

## Requirements

| Component | Version |
|---|---|
| Home Assistant | 2026.10 or newer (Python 3.14). Tested against 2026.10.4 only. |
| qBittorrent | WebUI API v2 (qBittorrent 4.x/5.x). `stop`/`start` are used from WebUI API 2.11 (5.0); `pause`/`resume` before. Automatic TV folder planning needs `torrents/fetchMetadata` (WebUI API 2.17, found in current qBittorrent sources; not yet in the released API documentation). Without it, use an explicit sub-folder. |
| Jackett | Current Jackett with API key (`/api/v2.0/indexers/all/results`, Torznab `t=indexers`). Verified against Jackett's source on 2026-11-16, not against a running instance. |

## Install (HACS custom repository)

1. HACS → ⋮ → **Custom repositories** → add `https://github.com/Timisah/homeassistant-torrent-helper`, category **Integration**.
2. Install **Torrent Tools**, restart Home Assistant.
3. Settings → Devices & services → **Add integration** → *Torrent Tools*.

Manual install: copy `custom_components/torrent_tools` into your config's `custom_components/`.

Setup steps, fields and options: [docs/setup.md](docs/setup.md).

## Using it

Select **Torrent Tools** under *Control Home Assistant / LLM APIs* of your conversation agent.
Then, for example:

| English | Deutsch |
|---|---|
| "Search for Dune 2021 in 1080p." | „Suche nach Dune 2021 in 1080p.“ |
| "Download the second one as a movie." | „Lade die zweite als Film herunter.“ |
| "What is downloading right now?" | „Was wird gerade heruntergeladen?“ |
| "Pause the Ubuntu download." | „Pausiere den Ubuntu-Download.“ |
| "Delete the files of that one." → asks an admin to approve | „Lösche die Dateien davon.“ → Admin muss bestätigen |

Actions (usable in scripts and automations) are listed in [docs/usage.md](docs/usage.md).

## Documentation

* [Setup guide](docs/setup.md) · [Usage and actions](docs/usage.md) · [Permissions and architecture](docs/permissions.md)
* [VPN deployment guide](docs/vpn.md) · [Troubleshooting](docs/troubleshooting.md)
* [Acceptance checklist](docs/acceptance-checklist.md) · [Legacy notes](docs/legacy-notes.md)
* [Contributing](CONTRIBUTING.md) · [Releasing](RELEASING.md) · [Changelog](CHANGELOG.md)

## License

[MIT](LICENSE).
