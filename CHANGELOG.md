# Changelog

## 0.1.0 (unreleased)

Initial implementation.

* Config flow (qBittorrent + Jackett), reauth, reconfigure, options (destinations, permissions).
* Jackett search with stored, owner-scoped, 24 h results; preview/add with duplicate and
  uncertain-outcome handling; list/pause/resume/remove; TV folder planning from metadata.
* Home Assistant actions and native LLM API with identical, server-side authorization.
* Trusted Assist satellites, explicit user and automation permissions.
* File deletion only by administrator approval in a panel.
* English and German translations, diagnostics with redaction, VPN guide and Gluetun example, CI.
* qBittorrent login accepts HTTP 204 (5.x) as well as 200 `Ok.`; the session is verified by the follow-up read. Config entries are version 2; prototype (version 1) entries fail cleanly with a migration error instead of crashing.
* Not yet validated against live services; see the acceptance checklist.
