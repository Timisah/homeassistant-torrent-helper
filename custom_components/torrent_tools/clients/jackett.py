"""Jackett client: Torznab-style API key access only.

Home Assistant never contacts indexers or arbitrary download links. Every
request goes to the configured Jackett URL, which is what the VPN guide routes
through the protected network.
"""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit
from xml.etree import ElementTree

import aiohttp

from ..errors import (
    CannotConnect,
    InvalidAuth,
    ServiceResponseError,
    TlsError,
    UnsupportedFeature,
)
from ..validation import validate_magnet
from .http import REDIRECT_STATUSES, read_bounded

SEARCH_TIMEOUT = aiohttp.ClientTimeout(total=70, connect=6)
CHECK_TIMEOUT = aiohttp.ClientTimeout(total=20, connect=6)
_DANGEROUS_XML = re.compile(rb"<!(DOCTYPE|ENTITY)", re.IGNORECASE)


class JackettClient:
    """Jackett client bound to one config entry."""

    def __init__(self, session: aiohttp.ClientSession, base_url: str, api_key: str) -> None:
        self._session = session
        self._base = base_url.rstrip("/")
        self._key = api_key
        self._base_parts = urlsplit(self._base)

    async def _get(
        self, path: str, params: dict[str, str], timeout: aiohttp.ClientTimeout
    ) -> tuple[int, bytes, dict[str, str]]:
        try:
            async with self._session.get(
                f"{self._base}{path}",
                params={**params, "apikey": self._key},
                timeout=timeout,
                allow_redirects=False,
            ) as response:
                body = await read_bounded(response)
                return response.status, body, dict(response.headers)
        except (aiohttp.ClientConnectorCertificateError, aiohttp.ClientSSLError) as err:
            raise TlsError("The TLS certificate of Jackett could not be verified.") from err
        except aiohttp.ClientConnectorError as err:
            raise CannotConnect("Jackett could not be reached.") from err
        except (aiohttp.ClientError, TimeoutError) as err:
            raise CannotConnect("Jackett did not answer in time.") from err

    async def async_validate(self) -> int:
        """Check the API key without searching; return configured indexer count.

        Uses the Torznab ``t=indexers`` function of the aggregate indexer. It
        needs a valid API key (an invalid key yields HTTP 401 or an XML error)
        and lists indexers without querying any tracker.
        """
        status, body, _ = await self._get(
            "/api/v2.0/indexers/all/results/torznab/api",
            {"t": "indexers", "configured": "true"},
            CHECK_TIMEOUT,
        )
        if status in REDIRECT_STATUSES:
            raise CannotConnect("Jackett redirected the request. Use its direct URL.")
        if status in (401, 403):
            raise InvalidAuth("Jackett rejected the API key.")
        if status != 200:
            raise ServiceResponseError(f"Jackett returned HTTP {status}.")
        if _DANGEROUS_XML.search(body):
            raise ServiceResponseError("Jackett returned unexpected XML.")
        try:
            root = ElementTree.fromstring(body)  # noqa: S314 - DOCTYPE refused above
        except ElementTree.ParseError as err:
            raise ServiceResponseError("Jackett did not return the expected answer.") from err
        if root.tag == "error":
            if root.attrib.get("code") in ("100", "101", "102"):
                raise InvalidAuth("Jackett rejected the API key.")
            raise ServiceResponseError("Jackett reported an error.")
        if root.tag != "indexers":
            raise ServiceResponseError("Jackett did not return the expected answer.")
        return len(root.findall("indexer"))

    async def async_search(self, query: str) -> tuple[list[dict[str, Any]], int, int]:
        """Search all configured indexers. Returns (results, indexers, errors)."""
        status, body, _ = await self._get(
            "/api/v2.0/indexers/all/results", {"Query": query}, SEARCH_TIMEOUT
        )
        if status in (401, 403):
            raise InvalidAuth("Jackett rejected the API key.")
        if status != 200:
            raise ServiceResponseError(f"Jackett returned HTTP {status}.")
        try:
            data = json.loads(body)
        except ValueError as err:
            raise ServiceResponseError("Jackett returned invalid JSON.") from err
        if not isinstance(data, dict) or not isinstance(data.get("Results"), list):
            raise ServiceResponseError("Jackett returned an invalid result list.")
        indexers = data.get("Indexers") if isinstance(data.get("Indexers"), list) else []
        errors = sum(
            1 for i in indexers if isinstance(i, dict) and (i.get("Error") or i.get("ErrorMessage"))
        )
        return data["Results"], len(indexers), errors

    # ---------------------------------------------------------- references
    def safe_reference(self, link: object) -> str | None:
        """Convert a Jackett download link into a key-free relative reference.

        Only links that point at the configured Jackett (same scheme, host and
        port) under /dl/ are accepted. The API key is stripped so it is never
        stored or exposed; it is added again when the reference is resolved.
        """
        if not isinstance(link, str) or len(link) > 16000:
            return None
        try:
            parts = urlsplit(link)
            same = (
                (parts.scheme, parts.hostname, parts.port or None)
                == (
                    self._base_parts.scheme,
                    self._base_parts.hostname,
                    self._base_parts.port or None,
                )
                and not parts.username
                and not parts.password
            )
        except ValueError:
            return None
        base_path = self._base_parts.path.rstrip("/")
        if not same or not parts.path.startswith(f"{base_path}/dl/"):
            return None
        query = [(k, v) for k, v in parse_qsl(parts.query) if k != "jackett_apikey"]
        relative = parts.path[len(base_path) :]
        return relative + (f"?{urlencode(query)}" if query else "")

    async def async_resolve_magnet(self, reference: str) -> str:
        """Resolve a stored Jackett reference to a magnet via Jackett only."""
        if not reference.startswith("/dl/"):
            raise UnsupportedFeature("This result has no supported Jackett reference.")
        parts = urlsplit(reference)
        params = dict(parse_qsl(parts.query))
        params["jackett_apikey"] = self._key
        try:
            async with self._session.get(
                f"{self._base}{parts.path}",
                params=params,
                timeout=CHECK_TIMEOUT,
                allow_redirects=False,
            ) as response:
                location = response.headers.get("Location", "")
                if response.status in REDIRECT_STATUSES and location.lower().startswith("magnet:"):
                    return validate_magnet(location)
                if response.status in (401, 403):
                    raise InvalidAuth("Jackett rejected the API key.")
                if response.status >= 400:
                    raise ServiceResponseError(
                        f"Jackett could not resolve this result (HTTP {response.status}). "
                        "Search again."
                    )
        except aiohttp.ClientConnectorError as err:
            raise CannotConnect("Jackett could not be reached.") from err
        except (aiohttp.ClientError, TimeoutError) as err:
            raise CannotConnect("Jackett did not answer in time.") from err
        raise UnsupportedFeature(
            "This result is a .torrent file, not a magnet. Torrent-file results "
            "are not supported in this version; choose a magnet result."
        )
