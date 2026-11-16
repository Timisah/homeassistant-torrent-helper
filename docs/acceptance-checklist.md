# Manual acceptance checklist

Automated tests mock both services and prove the logic, not a working installation. Do this on a
test setup (a throwaway qBittorrent and Jackett, a harmless legal torrent such as a Linux ISO)
before any live migration. Back up Home Assistant first and have a rollback plan.

## Clean install
- [ ] Install through HACS as a custom repository; restart; integration is listed.
- [ ] Setup rejects a wrong qBittorrent password, wrong Jackett key, wrong URL with clear errors.
- [ ] Setup creates no torrent and runs no search (check qBittorrent and Jackett logs).
- [ ] Destinations validate (relative path and `..` rejected).
- [ ] Diagnostics download contains no keys, passwords, hosts, paths or user/device ids.

## Administrator, text Assist (English and German)
- [ ] EN: "Search for <title> <year> 1080p" shows 3 results with name, size, seeders.
- [ ] DE: „Suche nach <Titel> <Jahr>“ answers in German.
- [ ] "Show more results" continues the same search (no new Jackett query).
- [ ] "Download the second one" / „Lade die zweite herunter“ adds exactly the second listed item to the right folder.
- [ ] Same request again reports it is already present, no duplicate.
- [ ] A result that only has a .torrent file is refused with an explanation.
- [ ] List, pause, resume, remove job (files remain on disk).
- [ ] Ask to delete files: nothing deleted; notification appears; the panel shows the exact torrent; approve deletes only that torrent's files; a second approval attempt fails.
- [ ] TV: with a new qBittorrent, a flat season pack lands in `Show (Year)/Season NN`; a pack with season folders does not get a duplicate season folder. With an older qBittorrent the message offers `subfolder`.
- [ ] Restart Home Assistant: an earlier search is still available; after 24 h it is gone.

## Voice satellite (for example ATOM Echo)
- [ ] Before trusting: spoken request is refused with the "not trusted" explanation.
- [ ] Trust the satellite with `read` only: search works; "download" and "pause" are refused.
- [ ] Add `add`/`control`: works. Another, untrusted satellite still refused.
- [ ] A logged-in non-admin user in the Assist dialog gets no access unless granted individually.
- [ ] Spoken "delete the files" never deletes (only a pending request an admin must approve).
- [ ] Search made by voice is not usable from a different satellite or user.

## Lifecycle and failure
- [ ] Reconfigure URL/credentials; reload; reauth flow after changing the qBittorrent password.
- [ ] Stop qBittorrent: calls fail cleanly; start it: setup/calls recover without restart of Home Assistant.
- [ ] Stop Jackett: searches fail with a clear message.
- [ ] Remove the integration: panel, LLM API and stored searches are gone; torrents untouched.

## VPN outage (see docs/vpn.md)
- [ ] Tunnel-down test shows no leaking traffic from Jackett and qBittorrent.
- [ ] While the tunnel is down a search fails and no peers connect; after restore both work.

## Voice/language
- [ ] Share the results of the German and English runs in the issue tracker, including the model used.
