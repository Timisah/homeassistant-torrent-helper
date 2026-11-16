import time

import pytest

from custom_components.torrent_tools.deletion import (
    DeletionManager,
    assert_safe_to_delete,
    fingerprint,
)
from custom_components.torrent_tools.errors import InvalidInput, NotFound, PermissionDenied

ROOTS = ["/data/movies", "/data/shows"]


def torrent(h="a" * 40, content="/data/movies/Film (2020)", size=10):
    return {
        "hash": h,
        "name": "Film",
        "size": size,
        "total_size": size,
        "save_path": "/data/movies",
        "content_path": content,
    }


def test_safe_target_ok():
    assert_safe_to_delete(torrent(), [torrent(), torrent("b" * 40, "/data/movies/Other")], ROOTS)


@pytest.mark.parametrize(
    "content",
    ["/data/movies", "/data", "/etc/passwd", "/data/movies/../x", "/data/moviesX/a", "relative"],
)
def test_unsafe_locations_refused(content):
    with pytest.raises(InvalidInput):
        assert_safe_to_delete(torrent(content=content), [], ROOTS)


def test_overlap_and_unknown_peer_refused():
    with pytest.raises(InvalidInput):
        assert_safe_to_delete(torrent(), [torrent("b" * 40, "/data/movies/Film (2020)/sub")], ROOTS)
    with pytest.raises(InvalidInput):
        assert_safe_to_delete(torrent(), [torrent("b" * 40, "")], ROOTS)


def test_zero_size_refused():
    with pytest.raises(InvalidInput):
        assert_safe_to_delete(torrent(size=0), [], ROOTS)


def test_single_use_and_policy():
    mgr = DeletionManager()
    req = mgr.create("user:1", "admin-1", torrent())
    assert req.policy == "requester"
    with pytest.raises(PermissionDenied):
        mgr.consume(req.request_id, req.nonce, "admin-2")  # wrong administrator
    assert mgr.consume(req.request_id, req.nonce, "admin-1") is req
    with pytest.raises(NotFound):
        mgr.consume(req.request_id, req.nonce, "admin-1")  # replay


def test_bad_nonce_does_not_consume():
    mgr = DeletionManager()
    req = mgr.create("device:x", None, torrent())
    assert req.policy == "any_admin"
    with pytest.raises(PermissionDenied):
        mgr.consume(req.request_id, "wrong", "admin-9")
    assert mgr.consume(req.request_id, req.nonce, "admin-9")


def test_expiry_and_listing():
    now = [time.time()]
    mgr = DeletionManager(clock=lambda: now[0])
    req = mgr.create("user:1", "admin-1", torrent())
    assert mgr.list_for("admin-1") and not mgr.list_for("admin-2")
    now[0] += 601
    assert not mgr.list_for("admin-1")
    with pytest.raises(NotFound):
        mgr.consume(req.request_id, req.nonce, "admin-1")


def test_fingerprint_changes_with_target():
    assert fingerprint(torrent()) != fingerprint(torrent(content="/data/movies/Other"))
