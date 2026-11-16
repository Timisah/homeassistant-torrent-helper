"""Minimal qBittorrent WebUI API client (API v2).

* Uses a shared Home Assistant aiohttp session but keeps its own cookie store,
  so a session cookie never leaks to another service or config entry.
* Redirects are never followed.
* Writes distinguish "definitely not sent" (CannotConnect), "definitely
  refused" (RejectedByService) and "outcome unknown" (UncertainOutcome).
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import aiohttp

from ..const import QBT_API_FETCH_METADATA, QBT_API_STOP_START
from ..errors import (
    CannotConnect,
    InvalidAuth,
    RejectedByService,
    ServiceResponseError,
    TlsError,
    UncertainOutcome,
    UnsupportedFeature,
)
from ..validation import validate_magnet
from .http import REDIRECT_STATUSES, read_bounded

_LOGGER = logging.getLogger(__name__)

TIMEOUT = aiohttp.ClientTimeout(total=20, connect=6)
TORRENT_KEYS = (
    "hash",
    "name",
    "size",
    "total_size",
    "save_path",
    "content_path",
    "state",
    "progress",
    "dlspeed",
    "upspeed",
    "eta",
    "category",
    "num_seeds",
    "num_leechs",
    "ratio",
    "added_on",
)


def parse_api_version(text: str) -> tuple[int, ...]:
    """Parse '2.11.3' into a tuple; unknown formats give an empty tuple."""
    try:
        return tuple(int(p) for p in text.strip().split(".")[:3])
    except ValueError:
        return ()


class QBittorrentClient:
    """qBittorrent WebUI client bound to one config entry."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        base_url: str,
        username: str,
        password: str,
    ) -> None:
        self._session = session
        self._base = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._cookies: dict[str, str] = {}
        self._login_lock = asyncio.Lock()
        self.app_version: str | None = None
        self.api_version: tuple[int, ...] = ()

    # ------------------------------------------------------------------ http
    def _headers(self) -> dict[str, str]:
        # qBittorrent's CSRF protection wants Referer/Origin to match the host.
        return {"Referer": self._base, "Origin": self._base}

    async def _send(
        self,
        method: str,
        route: str,
        *,
        params: dict[str, str] | None = None,
        data: dict[str, str] | None = None,
        timeout: aiohttp.ClientTimeout = TIMEOUT,
    ) -> tuple[int, bytes]:
        headers = self._headers()
        if self._cookies:
            headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in self._cookies.items())
        async with self._session.request(
            method,
            f"{self._base}/api/v2/{route}",
            params=params,
            data=data,
            headers=headers,
            timeout=timeout,
            allow_redirects=False,
        ) as response:
            if response.status in REDIRECT_STATUSES:
                raise CannotConnect(
                    "qBittorrent redirected the request. Use the direct WebUI URL "
                    "(no login page or proxy redirect)."
                )
            body = await read_bounded(response)
            return response.status, body

    async def async_login(self) -> None:
        """Log in (no-op when no credentials are configured)."""
        if not self._username and not self._password:
            self._cookies = {}
            return
        try:
            async with self._session.post(
                f"{self._base}/api/v2/auth/login",
                data={"username": self._username, "password": self._password},
                headers=self._headers(),
                timeout=TIMEOUT,
                allow_redirects=False,
            ) as response:
                if response.status in REDIRECT_STATUSES:
                    raise CannotConnect("qBittorrent redirected the login request.")
                body = (await read_bounded(response, 4096)).decode("utf-8", "replace")
                if response.status == 403:
                    raise CannotConnect(
                        "qBittorrent refused the login (the IP may be banned after "
                        "failed attempts)."
                    )
                # Older versions answer 200 "Ok."; newer ones (5.x) answer 204 with
                # a session cookie. Wrong credentials answer 200 "Fails." or 401.
                accepted = (response.status == 200 and body.strip() == "Ok.") or (
                    response.status == 204
                )
                if not accepted:
                    raise InvalidAuth("qBittorrent rejected the username or password.")
                cookies = {k: m.value for k, m in response.cookies.items()}
        except (aiohttp.ClientConnectorCertificateError, aiohttp.ClientSSLError) as err:
            raise TlsError("The TLS certificate of qBittorrent could not be verified.") from err
        except (aiohttp.ClientError, TimeoutError) as err:
            raise CannotConnect("qBittorrent could not be reached.") from err
        if not cookies:
            raise InvalidAuth("qBittorrent did not return a session.")
        self._cookies = cookies

    async def _request(
        self,
        method: str,
        route: str,
        *,
        params: dict[str, str] | None = None,
        data: dict[str, str] | None = None,
        write: bool = False,
        timeout: aiohttp.ClientTimeout = TIMEOUT,
        accept: tuple[int, ...] = (200,),
    ) -> tuple[int, bytes]:
        """Send a request, logging in again once if the session expired."""
        has_credentials = bool(self._username or self._password)
        for attempt in (1, 2):
            try:
                status, body = await self._send(
                    method, route, params=params, data=data, timeout=timeout
                )
            except (aiohttp.ClientConnectorCertificateError, aiohttp.ClientSSLError) as err:
                raise TlsError("The TLS certificate of qBittorrent could not be verified.") from err
            except aiohttp.ClientConnectorError as err:
                raise CannotConnect("qBittorrent could not be reached.") from err
            except (aiohttp.ClientError, TimeoutError) as err:
                if write:
                    raise UncertainOutcome(
                        "qBittorrent did not confirm the request. Check its "
                        "current state before repeating it."
                    ) from err
                raise CannotConnect("qBittorrent did not answer in time.") from err
            if status == 403:
                # 403 means rejected before execution, so one re-login is safe.
                if attempt == 1 and has_credentials:
                    async with self._login_lock:
                        await self.async_login()
                    continue
                raise InvalidAuth("qBittorrent denied access. Check the credentials.")
            if status in accept:
                return status, body
            if status >= 500 and write:
                raise UncertainOutcome(f"qBittorrent answered with HTTP {status}. Check its state.")
            if write and 400 <= status < 500:
                raise RejectedByService(f"qBittorrent refused the request (HTTP {status}).")
            raise ServiceResponseError(f"qBittorrent returned HTTP {status}.")
        raise InvalidAuth("qBittorrent denied access.")  # pragma: no cover

    # --------------------------------------------------------------- queries
    async def async_validate(self) -> tuple[str, tuple[int, ...]]:
        """Authenticate and read versions with non-mutating requests."""
        await self.async_login()
        _, app = await self._request("GET", "app/version")
        _, api = await self._request("GET", "app/webapiVersion")
        self.app_version = app.decode("utf-8", "replace").strip()[:40]
        self.api_version = parse_api_version(api.decode("utf-8", "replace"))
        return self.app_version, self.api_version

    async def async_list_torrents(self, hashes: list[str] | None = None) -> list[dict[str, Any]]:
        """List torrents (optionally only the given hashes)."""
        params = {"hashes": "|".join(hashes)} if hashes else None
        _, body = await self._request("GET", "torrents/info", params=params)
        try:
            data = json.loads(body)
        except ValueError as err:
            raise ServiceResponseError("qBittorrent returned invalid JSON.") from err
        if not isinstance(data, list):
            raise ServiceResponseError("qBittorrent returned an invalid torrent list.")
        return [t for t in data if isinstance(t, dict)]

    async def _ensure_version(self) -> None:
        if not self.api_version:
            await self.async_validate()

    # ---------------------------------------------------------------- writes
    async def async_add_magnet(
        self, magnet: str, save_path: str, content_layout: str | None = None
    ) -> None:
        """Add a magnet with an explicit save path (automatic management off)."""
        data = {
            "urls": validate_magnet(magnet),
            "savepath": save_path,
            "autoTMM": "false",
        }
        if content_layout:
            data["contentLayout"] = content_layout
        _, body = await self._request("POST", "torrents/add", data=data, write=True)
        text = body.decode("utf-8", "replace").strip()
        if text in ("Ok.", ""):
            return
        if text == "Fails.":
            raise RejectedByService("qBittorrent rejected the torrent.")
        try:
            result = json.loads(text)
        except ValueError:
            raise UncertainOutcome(
                "qBittorrent gave an unclear answer. Check its torrent list."
            ) from None
        if isinstance(result, dict):
            ok = int(result.get("success_count", 0)) + int(result.get("pending_count", 0))
            if ok == 0 and int(result.get("failure_count", 0)) > 0:
                raise RejectedByService("qBittorrent rejected the torrent.")
            return
        raise UncertainOutcome("qBittorrent gave an unclear answer. Check its torrent list.")

    async def async_set_paused(self, torrent_hash: str, paused: bool) -> None:
        """Pause or resume one torrent (route names depend on the API version)."""
        await self._ensure_version()
        new_names = self.api_version[:2] >= QBT_API_STOP_START
        route = ("stop" if paused else "start") if new_names else ("pause" if paused else "resume")
        await self._request("POST", f"torrents/{route}", data={"hashes": torrent_hash}, write=True)

    async def async_delete(self, torrent_hash: str, *, delete_files: bool) -> None:
        """Remove one torrent, optionally with its files."""
        await self._request(
            "POST",
            "torrents/delete",
            data={"hashes": torrent_hash, "deleteFiles": "true" if delete_files else "false"},
            write=True,
        )

    # -------------------------------------------------------------- metadata
    @property
    def supports_metadata_fetch(self) -> bool:
        """Whether torrents/fetchMetadata is expected to exist."""
        return self.api_version[:2] >= QBT_API_FETCH_METADATA

    async def async_fetch_metadata(self, magnet: str, *, wait: float = 45.0) -> dict[str, Any]:
        """Ask qBittorrent for torrent metadata without adding the torrent.

        Uses the metadata-only endpoint of newer qBittorrent versions and polls
        while it answers HTTP 202. No media data is transferred.
        """
        await self._ensure_version()
        if not self.supports_metadata_fetch:
            raise UnsupportedFeature(
                "This qBittorrent version cannot inspect torrent metadata without "
                "adding the torrent."
            )
        source = validate_magnet(magnet)
        try:
            async with asyncio.timeout(wait):
                while True:
                    status, body = await self._request(
                        "POST",
                        "torrents/fetchMetadata",
                        data={"source": source},
                        accept=(200, 202),
                    )
                    if status == 200:
                        try:
                            result = json.loads(body)
                        except ValueError as err:
                            raise ServiceResponseError(
                                "qBittorrent returned invalid metadata."
                            ) from err
                        if isinstance(result, dict) and isinstance(result.get("info"), dict):
                            return result
                    await asyncio.sleep(1.5)
        except TimeoutError as err:
            raise CannotConnect(
                "Torrent metadata was not available in time. Nothing was added."
            ) from err
