"""Parse release names. Everything here is an unverified claim."""

from __future__ import annotations

import re


def _has(text: str, pattern: str) -> bool:
    return re.search(pattern, text, re.IGNORECASE) is not None


def claimed_metadata(name: str) -> dict[str, object]:
    """Return codec/quality claims found in a release name, never verified."""
    s = name.upper().replace("_", " ")
    resolution = next((r for r in ("2160p", "1080p", "720p", "480p") if r.upper() in s), None)
    hdr: list[str] = []
    if _has(s, r"\b(?:DV|DOVI)\b|DOLBY[ .-]?VISION"):
        hdr.append("Dolby Vision")
    if _has(s, r"HDR10\+|HDR10PLUS"):
        hdr.append("HDR10+")
    elif _has(s, r"HDR10\b"):
        hdr.append("HDR10")
    elif _has(s, r"\bHDR\b"):
        hdr.append("HDR")
    video = next(
        (
            label
            for pattern, label in (
                (r"\bAV1\b", "AV1"),
                (r"HEVC|[HX][ .-]?265", "HEVC"),
                (r"AVC|[HX][ .-]?264", "H.264"),
            )
            if _has(s, pattern)
        ),
        None,
    )
    source = next(
        (
            label
            for pattern, label in (
                (r"REMUX", "REMUX"),
                (r"WEB[ .-]?DL", "WEB-DL"),
                (r"WEB[ .-]?RIP", "WEBRip"),
                (r"BLU[ .-]?RAY|BDRIP", "Blu-ray"),
            )
            if _has(s, pattern)
        ),
        None,
    )
    audio = [
        label
        for pattern, label in (
            (r"TRUEHD", "TrueHD"),
            (r"\bATMOS\b", "Atmos"),
            (r"DDP|DD\+|EAC3|E-AC-3", "DD+"),
            (r"DTS[ .-]?HD[ .-]?MA", "DTS-HD MA"),
            (r"\bAAC\b", "AAC"),
            (r"\bFLAC\b", "FLAC"),
        )
        if _has(s, pattern)
    ]
    languages = [
        label
        for pattern, label in (
            (r"\bGERMAN\b|\bDEUTSCH\b", "de"),
            (r"\bENGLISH\b", "en"),
            (r"\bFRENCH\b", "fr"),
            (r"\bMULTI\b", "multi"),
        )
        if _has(s, pattern)
    ]
    year = re.search(r"\b((?:19|20)\d{2})\b", s)
    episode = re.search(r"\bS(\d{1,2})(?:E(\d{1,3}))?\b", s)
    return {
        "resolution": resolution,
        "hdr": hdr,
        "video_codec": video,
        "audio": audio,
        "source": source,
        "languages": languages,
        "year": int(year[1]) if year else None,
        "season": int(episode[1]) if episode else None,
        "episode": int(episode[2]) if episode and episode[2] else None,
        "verification": "unverified claims parsed from the release name",
    }


def title_tokens(query: str) -> list[str]:
    """Lowercase alphanumeric tokens (>=2 chars) of a title, for relevance."""
    return [t for t in re.findall(r"[^\W_]+", query.casefold()) if len(t) >= 2]


def matches_title(name: str, tokens: list[str]) -> bool:
    """True if every token appears in the name."""
    haystack = set(re.findall(r"[^\W_]+", name.casefold()))
    return bool(tokens) and all(t in haystack for t in tokens)
