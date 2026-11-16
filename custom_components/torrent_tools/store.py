"""Persistent, owner-scoped search state with expiry."""

from __future__ import annotations

import secrets
import time
from collections.abc import Callable
from typing import Any

from .const import MAX_RESULTS_PER_SEARCH, MAX_SEARCHES, SEARCH_TTL_SECONDS
from .errors import InvalidInput, NotFound
from .release import claimed_metadata, matches_title, title_tokens
from .validation import sanitize_untrusted, to_int, validate_magnet

STORAGE_VERSION = 1

# Submission lifecycle of one stored result.
SUB_PENDING = "pending"
SUB_SUBMITTED = "submitted"
SUB_UNCERTAIN = "uncertain"
SUB_FAILED = "failed"

PUBLIC_KEYS = (
    "result_id",
    "position",
    "name",
    "indexer",
    "size_bytes",
    "seeders",
    "peers",
    "published",
    "claims",
    "reference_type",
    "can_add",
    "selected",
    "submission",
)


class SearchState:
    """All stored searches for one config entry."""

    def __init__(
        self, data: dict[str, Any] | None = None, clock: Callable[[], float] = time.time
    ) -> None:
        self.data: dict[str, Any] = data if isinstance(data, dict) else {}
        self.data.setdefault("searches", {})
        self._clock = clock
        self.prune()

    def prune(self) -> bool:
        """Drop expired searches and enforce the cap. Returns True if changed."""
        searches = self.data["searches"]
        now = self._clock()
        before = len(searches)
        for sid in [s for s, v in searches.items() if v.get("expires_at", 0) <= now]:
            del searches[sid]
        while len(searches) > MAX_SEARCHES:
            del searches[min(searches, key=lambda s: searches[s]["created_at"])]
        return len(searches) != before

    def create(
        self,
        owner: str,
        query: str,
        raw_results: list[Any],
        safe_reference: Callable[[object], str | None],
        *,
        title_query: str | None = None,
        ttl: int = SEARCH_TTL_SECONDS,
    ) -> str:
        """Store a new search. Results are ranked once and keep that order."""
        self.prune()
        now = self._clock()
        tokens = title_tokens(title_query or query)
        candidates: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for item in raw_results:
            if not isinstance(item, dict):
                continue
            name = sanitize_untrusted(item.get("Title"), 500)
            if not name:
                continue
            indexer = sanitize_untrusted(
                item.get("Tracker") or item.get("Indexer") or "unknown", 100
            )
            magnet_uri = item.get("MagnetUri")
            link = item.get("Link")
            reference: str | None = None
            ref_type = "none"
            if isinstance(magnet_uri, str) and magnet_uri:
                try:
                    reference, ref_type = validate_magnet(magnet_uri), "magnet"
                except InvalidInput:
                    reference = None
            if reference is None and isinstance(link, str) and link.lower().startswith("magnet:"):
                try:
                    reference, ref_type = validate_magnet(link), "magnet"
                except InvalidInput:
                    reference = None
            if reference is None:
                ref = safe_reference(link)
                if ref:
                    reference, ref_type = ref, "jackett_reference"
                elif isinstance(link, str) and link:
                    ref_type = "torrent_file_unsupported"
            identity = (indexer, str(item.get("Guid") or reference or name)[:500])
            if identity in seen:
                continue
            seen.add(identity)
            seeders = to_int(item.get("Seeders"))
            candidates.append(
                {
                    "name": name,
                    "indexer": indexer,
                    "size_bytes": to_int(item.get("Size")),
                    "seeders": seeders,
                    "peers": to_int(item.get("Peers")),
                    "published": sanitize_untrusted(item.get("PublishDate"), 40) or None,
                    "claims": claimed_metadata(name),
                    "reference_type": ref_type,
                    "can_add": ref_type in ("magnet", "jackett_reference"),
                    "_reference": reference,
                    "_match": matches_title(name, tokens),
                }
            )
        candidates.sort(
            key=lambda r: (r["_match"], r["seeders"] if r["seeders"] is not None else -1),
            reverse=True,
        )
        results = []
        for position, cand in enumerate(candidates[:MAX_RESULTS_PER_SEARCH], start=1):
            cand["result_id"] = secrets.token_hex(8)
            cand["position"] = position
            cand["selected"] = False
            cand["submission"] = None
            results.append(cand)
        search_id = secrets.token_hex(12)
        self.data["searches"][search_id] = {
            "owner": owner,
            "query": query,
            "created_at": now,
            "expires_at": now + ttl,
            "results": results,
        }
        self.prune()
        return search_id

    def get(self, search_id: str, owner: str) -> dict[str, Any]:
        """Return a search owned by owner or raise NotFound."""
        self.prune()
        search = self.data["searches"].get(search_id)
        if not isinstance(search, dict) or search.get("owner") != owner:
            # Identical error for "missing" and "someone else's": no oracle.
            raise NotFound("That search expired or does not exist. Search again.")
        return search

    @staticmethod
    def public(result: dict[str, Any]) -> dict[str, Any]:
        """Return a result without internal fields."""
        out = {k: result.get(k) for k in PUBLIC_KEYS}
        sub = result.get("submission")
        out["submission"] = sub.get("state") if isinstance(sub, dict) else None
        return out

    def page(self, search_id: str, owner: str, offset: int, limit: int) -> dict[str, Any]:
        """Return one page of a stored search."""
        search = self.get(search_id, owner)
        total = len(search["results"])
        return {
            "search_id": search_id,
            "query": search["query"],
            "expires_at": search["expires_at"],
            "ranking": "title match first, then seeders (descending)",
            "total": total,
            "offset": offset,
            "next_offset": offset + limit if offset + limit < total else None,
            "results": [self.public(r) for r in search["results"][offset : offset + limit]],
        }

    def result(
        self, search_id: str, owner: str, *, result_id: str | None, position: int | None
    ) -> dict[str, Any]:
        """Return the raw stored result addressed by id or by 1-based position."""
        search = self.get(search_id, owner)
        if (result_id is None) == (position is None):
            raise InvalidInput("Give either result_id or position, not both.")
        for res in search["results"]:
            if (result_id is not None and res["result_id"] == result_id) or (
                position is not None and res["position"] == position
            ):
                return res
        raise NotFound("That result is not in this stored search.")
