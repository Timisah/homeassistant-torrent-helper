# Usage and actions

Every operation is available as a Home Assistant action (with a response) and as an LLM tool.
Both use the same code and the same permission checks.

| Action | Needs | What it does |
|---|---|---|
| `torrent_tools.search_torrents` | read | Search Jackett (`query`, optional `year`, `terms`, `limit`, default 3). Returns a stored, ranked, numbered list. Ranking: title (and year) matches first, then most seeders. |
| `torrent_tools.get_search_results` | read | More results of a stored search (`search_id`, `offset`, `limit`). Never searches again. |
| `torrent_tools.preview_torrent` | read | Select one result by `result_id` or 1-based `position`; verifies it can be added. Downloads nothing. |
| `torrent_tools.add_torrent` | add | Add a previewed result to `destination` (`movies`, `shows`, `downloads`), optional `subfolder`. |
| `torrent_tools.list_torrents` | read | List torrents (progress, state, speeds, size, paths). |
| `torrent_tools.get_torrent` | read | One torrent by exact hash. |
| `torrent_tools.pause_torrent` / `resume_torrent` | control | By exact 40/64-character hash. |
| `torrent_tools.remove_torrent` | control | Removes the job; files are kept. |
| `torrent_tools.request_file_deletion` | request_deletion | Only creates a request. An administrator approves it in the *Torrent Tools* sidebar panel. |

Action calls need an authenticated user (or enabled *automation* permissions): a call with no
user is **not** treated as a trusted voice device.

## Results

Names, sizes, seeders, indexer and the claims parsed from the release name (resolution, HDR,
codec, audio, languages) are shown. Claims are unverified guesses from the name; bitrate and
Dolby Vision profile are never invented. Magnet links, trackers, API keys and Jackett download
URLs are never returned to the model or to action responses.

Results that only offer a `.torrent` file are shown with `can_add: false`: v1 supports magnets
and Jackett references that resolve (inside Jackett) to a magnet, so that no file is fetched
outside the protected route.

## Destinations and TV folders

`add_torrent` saves to the configured root for the destination, optionally plus a validated
relative `subfolder` (no `..`, no absolute paths, no special characters).

For `shows` without a `subfolder` give `show_name` (optionally `show_year`, `season`). The
integration asks qBittorrent for the torrent's *metadata only* (no media is downloaded), then
chooses `Show (Year)/Season NN` for flat episode files, or `Show (Year)` when the torrent already
contains `Season N` folders (no duplicate season folders). It refuses mixed or nested layouts.
If qBittorrent is too old to provide metadata, planning is unavailable: the call fails with a
clear message and you pass an explicit `subfolder` (for example `Show (2020)/Season 01`) or use
`downloads`. Existing media is never renamed or moved.

## Duplicate and uncertain submissions

* A torrent already in qBittorrent is reported as `already_present`; nothing is changed.
* If qBittorrent does not confirm an add (timeout or server error), the result is marked
  **uncertain** and the write is **not** repeated. The next attempt first checks qBittorrent;
  if the torrent is there it is reported as present, otherwise a retry is allowed only after
  two minutes. A definite rejection can be retried at once.
