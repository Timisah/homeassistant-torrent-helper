"""Bounded HTTP helpers shared by the service clients."""

from __future__ import annotations

import aiohttp

from ..errors import ServiceResponseError

MAX_RESPONSE_BYTES = 8 * 1024 * 1024
REDIRECT_STATUSES = (301, 302, 303, 307, 308)


async def read_bounded(response: aiohttp.ClientResponse, limit: int = MAX_RESPONSE_BYTES) -> bytes:
    """Read a response body, refusing anything larger than limit."""
    try:
        declared = int(response.headers.get("Content-Length", "-1"))
    except ValueError:
        declared = -1
    if declared > limit:
        raise ServiceResponseError("The service response exceeded the size limit.")
    chunks: list[bytes] = []
    size = 0
    async for chunk in response.content.iter_chunked(65536):
        size += len(chunk)
        if size > limit:
            raise ServiceResponseError("The service response exceeded the size limit.")
        chunks.append(chunk)
    return b"".join(chunks)
