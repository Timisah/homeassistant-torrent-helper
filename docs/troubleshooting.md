# Troubleshooting

| Symptom | Cause and fix |
|---|---|
| Setup: *Cannot connect* | Wrong URL/port, container stopped, VPN gateway down, or Home Assistant cannot reach the published port. |
| Setup: *unexpected response* | The URL points at a login page, reverse proxy or redirect. Use the direct service URL. |
| qBittorrent *Authentication failed* repeatedly, then *cannot connect* | qBittorrent bans an IP after failed logins. Wait or clear the ban in qBittorrent, then retry with correct credentials. |
| *TLS certificate could not be verified* | Fix the certificate chain, or disable verification for a trusted self-signed LAN service. |
| *Jackett has no configured indexers* | Add an indexer in Jackett first. |
| Integration shows *Retrying setup* | A service is unreachable. It reconnects automatically; check both URLs and the VPN. |
| *Re-authentication required* | A service rejected the credentials (changed password or API key). Use the repair prompt. |
| Assist does not offer torrent tools | Enable *Torrent Tools* in the conversation agent's LLM API settings; use a tool-capable model; check permissions (below). |
| Voice satellite: "not available" / "not trusted" | The satellite is not in *trusted voice devices*, has no operations enabled, or the request was not an Assist conversation from that satellite device. |
| *Calls without a Home Assistant user are not allowed* | Actions called from automations need *automation permissions* or must run as a user. |
| *Preview this exact result before adding it* | Call `preview_torrent` for that result first. |
| *This result has no supported magnet* | The result only offers a `.torrent` file. Choose another result. |
| *Automatic TV folder planning is not available* | qBittorrent is too old for metadata lookup. Pass `subfolder`, e.g. `Show (2020)/Season 01`. |
| *Submission has an unknown outcome* | qBittorrent did not answer. Check its torrent list; the integration reconciles automatically on the next try. |
| File deletion refused | Content is outside the destination folders, at a destination root, or shared with another torrent. Delete manually. |
| Pause says the torrent was not found | Use the full hash from the list, not the name. |

Enable debug logging: `logger: logs: custom_components.torrent_tools: debug`. Logs never contain
credentials or URLs. Use *Download diagnostics* (redacted) when reporting a bug and still review it.
