"""Exceptions with messages that are safe to show to users and models."""

from __future__ import annotations


class TorrentToolsError(Exception):
    """Base error. The message never contains credentials or URLs."""


class CannotConnect(TorrentToolsError):
    """A service could not be reached. Nothing was sent or processed."""


class TlsError(CannotConnect):
    """TLS certificate verification failed."""


class InvalidAuth(TorrentToolsError):
    """A service rejected the stored credentials."""


class ServiceResponseError(TorrentToolsError):
    """A service answered with something unusable."""


class RejectedByService(TorrentToolsError):
    """A write was definitely refused by the service."""


class UncertainOutcome(TorrentToolsError):
    """A write was sent but its outcome is unknown. Do not blindly retry."""


class PermissionDenied(TorrentToolsError):
    """The caller is not allowed to perform the operation."""


class UnsupportedFeature(TorrentToolsError):
    """The connected service does not support the requested feature."""


class InvalidInput(TorrentToolsError):
    """User or model supplied an invalid value."""


class NotFound(TorrentToolsError):
    """A stored search, result or torrent could not be found."""
