# Permissions and architecture

## Who may do what

Every call resolves a *principal* from information Home Assistant supplies, never from tool
arguments (tool schemas reject unknown keys such as `user_id` or `device_id`).

| Caller | Access |
|---|---|
| Active administrator | All operations. Approving file deletion is a separate action in the confirmation panel. |
| Other user | Only if listed under *Additional non-admin users*, with the operations chosen there. |
| Voice (Assist satellite, no user id) | Only if the device is on the *trusted voice devices* list **and** the request comes from an Assist conversation **and** the device owns an `assist_satellite` entity. Operations are those chosen for trusted devices. |
| Action without a user (automation) | Only the operations listed under *automation permissions* (none by default). |

Operation groups: **read** (search, results, preview, list, details), **add**, **control**
(pause, resume, remove job, files kept), **request_deletion** (create a request only).

Rules that cannot be bypassed from the model side:

* A request with a user id is evaluated as that user only. A user who is denied is never
  downgraded to voice-device or anonymous access, so a logged-in client cannot borrow a trusted
  room device by sending its id. A missing user id alone grants nothing.
* Without a user id, device identity comes from the `LLMContext` that Home Assistant builds
  from the conversation request, forwarded in full (device id *and* assistant), not just the
  `context` object. If the device cannot be verified, access is denied.
* Tools are only offered if the caller may use them, and every call is checked again.
* Stored searches and selections are scoped to the owner (`user:<id>`, `device:<id>` or
  `automation`). Another caller gets the same "expired or does not exist" error as for a
  missing id.

**Trusting a room device authorizes everyone who can speak to it.** It is not speaker
identification. Anyone who can create automations or scripts is effectively an administrator
for this purpose (they can call the actions with their own identity or craft calls).
Voice access can never approve file deletion.

## File deletion

1. `request_file_deletion` (administrator, or a trusted device/user with that permission)
   validates the torrent: exact hash, known size, content strictly inside a configured
   destination folder, no overlap with another torrent's files. It stores an in-memory request
   (expires in 10 minutes, at most 10 pending) and raises a Home Assistant notification.
2. An administrator opens the **Torrent Tools** sidebar panel, sees the exact torrent, and
   confirms. The websocket command is admin-only and needs the request id and its one-time nonce.
3. The request is removed before anything else happens (single use). The torrent is fetched
   again; if its fingerprint (hash, name, size, paths) changed, or the safety checks no longer
   pass, nothing is deleted.
4. Policy: a request made by an administrator can only be approved by that same administrator;
   a request from a device, automation or non-admin user can be approved by any administrator.

Pending requests are not stored: a restart cancels them. No LLM tool can delete files.
Content shared with another torrent or sitting at a destination root is never deleted by this
integration; delete such files manually.

## Components

```
custom_components/torrent_tools/
  clients/qbittorrent.py   WebUI client, own cookie store, bounded, no redirects
  clients/jackett.py       API-key client, key-free stored references
  permissions.py           principal resolution
  manager.py               all operations, locks, add/uncertain logic
  store.py                 owner-scoped search state with expiry
  tv.py / deletion.py      TV layout planning / deletion safety and requests
  operations.py            one schema catalogue for actions and LLM tools
  services.py llm_api.py websocket.py panel/confirm.js
```

Security properties: credentials and cookies are kept per client object; requests have timeouts
and an 8 MiB response cap; redirects are never followed; errors contain no URLs or secrets;
diagnostics redact URLs, credentials, user/device ids and paths; the Jackett API key is stripped
from stored download references and re-added only when talking to Jackett.
