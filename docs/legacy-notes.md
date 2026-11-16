# Legacy implementation: what was reused and what changed

The earlier private prototype (`torrent-tools-work`, supplied as a reference only) was read for
ideas. **No code was copied verbatim**; this repository is a rewrite. Credentials, hosts, storage
and history from that workspace were not imported.

| Legacy behaviour | Now |
|---|---|
| Jackett URL/key only, site-specific default URL | Full UI flow for qBittorrent *and* Jackett, no default hosts, reauth/reconfigure/options. |
| qBittorrent credentials borrowed from the native integration; adds via a separate `qbittorrent_submit` integration | Own qBittorrent client, no dependency on either. |
| Hardcoded `/movies`, `/shows`, `/downloads`, PIA wording | Configurable destination roots; provider-independent VPN guidance. |
| Every call needs an authenticated administrator, so voice satellites failed | Explicit principals: admin, listed users, trusted satellites, automations. Device identity from the full LLM context. |
| Automatically attached the tools to OpenAI agents | Removed. Users select the LLM API themselves. |
| Search probe did a real search to validate the key | `t=indexers` call that needs the key and queries no tracker. |
| qBittorrent `fetchMetadata` assumed available | Used only when WebUI API ≥ 2.17 is reported; clear fallback otherwise. |
| Deletion via a panel with a nonce | Kept and tightened: policy binding, single use, fingerprint, path-safety checks, admin-only websocket. |
| TV folder planning | Kept as tested pure logic (no duplicate season folders, mixed layouts refused). |

**Licensing and provenance:** this repository is MIT licensed (owner's choice). The prototype's own license is unknown to the author of this rewrite; the owner should confirm they hold the rights to the prototype ideas reused here.

**Repository name:** the specification suggested `ha-torrent-tools`; work was done in the existing
repository `homeassistant-torrent-helper` as instructed. The integration domain is `torrent_tools`.
Renaming the repository or changing its visibility was not done.
