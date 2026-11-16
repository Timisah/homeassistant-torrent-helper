"""Two-step file deletion: the AI may only prepare; an administrator approves."""

from __future__ import annotations

import asyncio
import hashlib
import secrets
import time
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any

from .const import DELETION_TTL_SECONDS, MAX_PENDING_DELETIONS
from .errors import InvalidInput, NotFound, PermissionDenied
from .validation import is_within, to_int

SNAPSHOT_KEYS = ("hash", "name", "size", "total_size", "save_path", "content_path")


def fingerprint(torrent: dict[str, Any]) -> str:
    """Hash of the identity-relevant fields of a torrent."""
    parts = [f"{k}={torrent.get(k)!r}" for k in SNAPSHOT_KEYS]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def assert_safe_to_delete(
    target: dict[str, Any], others: list[dict[str, Any]], roots: list[str]
) -> None:
    """Refuse shared, broad or out-of-scope content. Conservative by design."""
    content = target.get("content_path")
    if (
        not isinstance(content, str)
        or not content.startswith(("/",))
        and not (len(content) > 2 and content[1:3] == ":/")
    ):
        raise InvalidInput("The torrent's content path could not be verified.")
    if to_int(target.get("total_size") or target.get("size")) in (None, 0):
        raise InvalidInput("Deletion requires a known, non-zero torrent size.")
    if not any(is_within(content, root) for root in roots):
        raise InvalidInput(
            "The content is not strictly inside a configured destination folder, "
            "so file deletion is refused."
        )
    mine = PurePosixPath(content)
    for other in others:
        if other.get("hash") == target.get("hash"):
            continue
        peer = other.get("content_path")
        if not isinstance(peer, str) or not peer:
            raise InvalidInput("Another torrent's files could not be verified. Inspect manually.")
        theirs = PurePosixPath(peer)
        if mine.is_relative_to(theirs) or theirs.is_relative_to(mine):
            raise InvalidInput(
                "Another torrent shares these files or folder. Delete manually after checking."
            )


@dataclass
class DeletionRequest:
    """One expiring, single-use deletion request."""

    request_id: str
    nonce: str
    owner: str
    policy: str  # "requester" (only that administrator) | "any_admin"
    requester_user_id: str | None
    torrent: dict[str, Any]
    fingerprint: str
    expires_at: float
    created_at: float = field(default_factory=time.time)

    def public(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "nonce": self.nonce,
            "policy": self.policy,
            "expires_at": self.expires_at,
            "torrent": {k: self.torrent.get(k) for k in SNAPSHOT_KEYS},
        }


class DeletionManager:
    """Holds pending requests in memory only: a restart cancels them all."""

    def __init__(self, clock=time.time) -> None:
        self._pending: dict[str, DeletionRequest] = {}
        self._clock = clock
        self.lock = asyncio.Lock()

    def _prune(self) -> None:
        now = self._clock()
        for rid in [r for r, v in self._pending.items() if v.expires_at <= now]:
            del self._pending[rid]

    def create(
        self,
        owner: str,
        requester_user_id: str | None,
        torrent: dict[str, Any],
    ) -> DeletionRequest:
        self._prune()
        if len(self._pending) >= MAX_PENDING_DELETIONS:
            raise InvalidInput(
                "Too many pending deletion requests. Review or wait for them to expire."
            )
        # Same torrent requested again: replace the old request.
        for rid in [
            r for r, v in self._pending.items() if v.torrent.get("hash") == torrent.get("hash")
        ]:
            del self._pending[rid]
        request = DeletionRequest(
            request_id=secrets.token_hex(12),
            nonce=secrets.token_urlsafe(32),
            owner=owner,
            policy="requester" if requester_user_id else "any_admin",
            requester_user_id=requester_user_id,
            torrent={k: torrent.get(k) for k in SNAPSHOT_KEYS},
            fingerprint=fingerprint(torrent),
            expires_at=self._clock() + DELETION_TTL_SECONDS,
        )
        self._pending[request.request_id] = request
        return request

    def list_for(self, admin_user_id: str) -> list[DeletionRequest]:
        self._prune()
        return [
            r
            for r in self._pending.values()
            if r.policy == "any_admin" or r.requester_user_id == admin_user_id
        ]

    def consume(self, request_id: str, nonce: str, admin_user_id: str) -> DeletionRequest:
        """Validate and remove a request. Single use: removed before any I/O."""
        self._prune()
        request = self._pending.get(request_id)
        if request is None:
            raise NotFound("The deletion request expired or does not exist.")
        if request.policy == "requester" and request.requester_user_id != admin_user_id:
            raise PermissionDenied("Only the administrator who asked can approve this request.")
        if not secrets.compare_digest(request.nonce, nonce):
            raise PermissionDenied("Invalid confirmation. Reopen the confirmation page.")
        del self._pending[request_id]
        return request

    def count(self) -> int:
        self._prune()
        return len(self._pending)

    def clear(self) -> None:
        self._pending.clear()
