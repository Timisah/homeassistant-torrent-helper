"""Pure validation helpers. No Home Assistant imports, fully unit-testable."""

from __future__ import annotations

import base64
import re
from pathlib import PurePosixPath
from urllib.parse import parse_qs, urlsplit

from .errors import InvalidInput

_HASH_RE = re.compile(r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}")
_V1_HEX_RE = re.compile(r"[0-9a-fA-F]{40}")
_V1_B32_RE = re.compile(r"[A-Za-z2-7]{32}")
_DRIVE_RE = re.compile(r"^[A-Za-z]:/")
_BAD_SEGMENT_CHARS = set('<>:"|?*\\')
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


def clean_text(value: object, *, maximum: int = 300, required: bool = True) -> str:
    """Return a stripped single-line string or raise InvalidInput."""
    if not isinstance(value, str):
        raise InvalidInput("A text value is required.")
    value = value.strip()
    if required and not value:
        raise InvalidInput("A non-empty value is required.")
    if len(value) > maximum:
        raise InvalidInput(f"Value is longer than {maximum} characters.")
    if _CONTROL_RE.search(value):
        raise InvalidInput("Control characters are not allowed.")
    return value


def sanitize_untrusted(value: object, maximum: int = 300) -> str:
    """Make indexer-supplied text safe to display: single line, bounded."""
    if not isinstance(value, str):
        return ""
    value = _CONTROL_RE.sub(" ", value)
    value = " ".join(value.split())
    return value[:maximum]


def torrent_hash(value: object) -> str:
    """Return a normalized exact torrent hash (v1 40 hex or v2 64 hex)."""
    if not isinstance(value, str) or not _HASH_RE.fullmatch(value.strip()):
        raise InvalidInput(
            "Supply exactly one full torrent hash (40 or 64 hex characters), not a name or a list."
        )
    return value.strip().lower()


def normalize_service_url(value: object) -> str:
    """Validate a service base URL. Credentials in the URL are refused."""
    url = clean_text(value, maximum=1024).rstrip("/")
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise InvalidInput("Use a URL such as http://host:port.")
    if parts.username or parts.password or parts.query or parts.fragment:
        raise InvalidInput("Do not put credentials, query strings or fragments in the URL.")
    try:
        _ = parts.port
    except ValueError as err:
        raise InvalidInput("The URL contains an invalid port.") from err
    return url


def _btih_values(magnet_uri: str) -> set[str]:
    hashes: set[str] = set()
    for topic in parse_qs(urlsplit(magnet_uri).query).get("xt", []):
        if not topic.lower().startswith("urn:btih:"):
            continue
        candidate = topic[9:]
        if _V1_HEX_RE.fullmatch(candidate):
            hashes.add(candidate.lower())
        elif _V1_B32_RE.fullmatch(candidate):
            try:
                raw = base64.b32decode(candidate.upper())
            except ValueError:
                continue
            if len(raw) == 20:
                hashes.add(raw.hex())
    return hashes


def validate_magnet(value: object) -> str:
    """Return the magnet unchanged if it names exactly one v1 info hash."""
    magnet_uri = clean_text(value, maximum=8192)
    if not magnet_uri.lower().startswith("magnet:?"):
        raise InvalidInput("This result has no supported BitTorrent magnet.")
    if len(_btih_values(magnet_uri)) != 1:
        raise InvalidInput("The magnet must identify exactly one valid info hash.")
    return magnet_uri


def magnet_hash(value: str) -> str:
    """Return the lowercase v1 info hash of a validated magnet."""
    return next(iter(_btih_values(validate_magnet(value))))


def validate_root_path(value: object) -> str:
    """Validate a destination root as qBittorrent sees it (forward slashes)."""
    path = clean_text(value, maximum=1024).rstrip("/") if value != "/" else "/"
    if path in ("", "/"):
        raise InvalidInput("The filesystem root cannot be used as a destination.")
    if "\\" in path or "//" in path.replace("://", ""):
        raise InvalidInput("Use forward slashes and no empty path segments.")
    if not (path.startswith("/") or _DRIVE_RE.match(path)):
        raise InvalidInput("Use an absolute path as seen by qBittorrent.")
    if any(seg in (".", "..") for seg in path.split("/")):
        raise InvalidInput("Path traversal segments are not allowed.")
    return path


def validate_subfolder(value: object) -> str:
    """Validate a relative sub-folder below a destination root."""
    sub = clean_text(value, maximum=500)
    if sub.startswith("/"):
        raise InvalidInput("The sub-folder must be relative to the destination.")
    sub = sub.rstrip("/")
    if not sub:
        raise InvalidInput("The sub-folder is empty.")
    segments = sub.split("/")
    if len(segments) > 6:
        raise InvalidInput("The sub-folder is nested too deeply.")
    for segment in segments:
        if not segment or segment in (".", "..") or len(segment) > 150:
            raise InvalidInput("The sub-folder contains an invalid segment.")
        if any(ch in _BAD_SEGMENT_CHARS for ch in segment):
            raise InvalidInput("The sub-folder contains unsupported characters.")
        if segment != segment.strip(" ."):
            raise InvalidInput("Folder names must not start or end with space or dot.")
    return "/".join(segments)


def join_destination(root: str, subfolder: str | None) -> str:
    """Join a validated root and optional sub-folder."""
    return root if not subfolder else f"{root}/{validate_subfolder(subfolder)}"


def is_within(path: str, root: str, *, strict: bool = True) -> bool:
    """True if path is inside root (strictly below it when strict)."""
    p, r = PurePosixPath(path), PurePosixPath(root)
    if ".." in p.parts:
        return False
    if not p.is_relative_to(r):
        return False
    return p != r if strict else True


def to_int(value: object) -> int | None:
    """Parse a non-negative integer or return None."""
    try:
        number = int(value)  # type: ignore[call-overload]
    except TypeError, ValueError, OverflowError:
        return None
    return number if number >= 0 else None
