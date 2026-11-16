"""Plan a television destination from torrent metadata.

Only used when qBittorrent supplied the file list. Never renames or moves
existing media; refuses layouts that cannot be placed safely.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any

from .errors import InvalidInput
from .validation import clean_text

VIDEO_EXTENSIONS = {
    ".mkv",
    ".mp4",
    ".avi",
    ".m4v",
    ".mov",
    ".webm",
    ".ts",
    ".m2ts",
    ".mpg",
    ".mpeg",
    ".wmv",
}
_EPISODE_RE = re.compile(r"(?:\bS(\d{1,4})E\d{1,3}\b|\b(\d{1,4})x\d{1,3}\b)", re.IGNORECASE)
_SEASON_DIR_RE = re.compile(r"Season[ ._-]+(\d{1,4})", re.IGNORECASE)


def show_folder_name(show_name: str, show_year: int | None) -> str:
    """Build 'Show Name (Year)' safely."""
    name = clean_text(show_name, maximum=180)
    name = re.sub(r'[<>:"/\\|?*]', " - ", name)
    name = " ".join(name.split()).strip(" .-")
    if not name:
        raise InvalidInput("Enter the show's title.")
    if show_year is not None:
        if not 1900 <= show_year <= 2100:
            raise InvalidInput("Use the series premiere year, or omit an unknown year.")
        match = re.search(r"\((\d{4})\)$", name)
        if match and int(match[1]) != show_year:
            raise InvalidInput("The title's year conflicts with the supplied year.")
        if not match:
            name = f"{name} ({show_year})"
    return name


def plan_tv_destination(
    metadata: dict[str, Any],
    root: str,
    show_name: str,
    show_year: int | None = None,
    season: int | None = None,
) -> dict[str, Any]:
    """Return {'save_path', 'content_layout', 'seasons'} or raise InvalidInput."""
    folder = show_folder_name(show_name, show_year)
    if season is not None and not 0 <= season <= 9999:
        raise InvalidInput("Use a valid season number (specials are season 0).")
    info = metadata.get("info")
    files = info.get("files") if isinstance(info, dict) else None
    if not isinstance(files, list) or not files:
        raise InvalidInput("Torrent file metadata is unavailable. Nothing was added.")
    paths: list[PurePosixPath] = []
    for entry in files:
        value = entry.get("path") if isinstance(entry, dict) else None
        if not isinstance(value, str) or not value or "\\" in value:
            raise InvalidInput("Unsafe file paths in this torrent. Choose another release.")
        if any(ord(c) < 32 for c in value):
            raise InvalidInput("Unsafe file paths in this torrent. Choose another release.")
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts:
            raise InvalidInput("Unsafe file paths in this torrent. Choose another release.")
        paths.append(path)
    # NoSubfolder drops the common outer folder; keep genuine inner season folders.
    outer = info.get("name")
    if all(len(p.parts) > 1 and p.parts[0] == outer for p in paths):
        paths = [PurePosixPath(*p.parts[1:]) for p in paths]
    videos = [
        p
        for p in paths
        if p.suffix.lower() in VIDEO_EXTENSIONS
        and not re.search(r"(^|[ ._-])sample([ ._-]|$)", p.stem, re.IGNORECASE)
    ]
    if not videos:
        raise InvalidInput("No playable TV files were found, so a TV layout cannot be verified.")
    base = f"{root}/{folder}"
    if all(len(p.parts) == 1 for p in videos):
        detected = {
            int(m[1] or m[2]) for p in videos if (m := _EPISODE_RE.search(p.name.replace("_", " ")))
        }
        if season is None:
            if len(detected) != 1:
                raise InvalidInput(
                    "State exactly one season, or choose a release with season folders."
                )
            season = next(iter(detected))
        if detected - {season}:
            raise InvalidInput(
                "This release mixes seasons in one folder. Choose per-season releases."
            )
        return {
            "save_path": f"{base}/Season {season:02d}",
            "content_layout": "NoSubfolder",
            "seasons": [season],
        }
    seasons: set[int] = set()
    for p in videos:
        m = _SEASON_DIR_RE.fullmatch(p.parts[0])
        if len(p.parts) != 2 or not m:
            raise InvalidInput(
                "This torrent has nested or mixed folders that cannot be placed "
                "automatically. Choose another release or a sub-folder."
            )
        seasons.add(int(m[1]))
    if season is not None and seasons != {season}:
        raise InvalidInput("The torrent's season folders do not match the requested season.")
    return {"save_path": base, "content_layout": "NoSubfolder", "seasons": sorted(seasons)}
