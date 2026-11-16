import pytest

from custom_components.torrent_tools.errors import InvalidInput
from custom_components.torrent_tools.validation import (
    is_within,
    join_destination,
    magnet_hash,
    normalize_service_url,
    torrent_hash,
    validate_magnet,
    validate_root_path,
    validate_subfolder,
)

H = "0123456789abcdef0123456789abcdef01234567"


def test_torrent_hash_exact_only():
    assert torrent_hash(H.upper()) == H
    for bad in ("", "abc", H + "0", "Ubuntu 24.04", H + "," + H, None, 5):
        with pytest.raises(InvalidInput):
            torrent_hash(bad)


def test_magnet_requires_exactly_one_btih():
    assert magnet_hash(f"magnet:?xt=urn:btih:{H}&dn=a") == H
    with pytest.raises(InvalidInput):
        validate_magnet("http://example.com/x.torrent")
    with pytest.raises(InvalidInput):
        validate_magnet("magnet:?dn=nohash")
    with pytest.raises(InvalidInput):
        validate_magnet(f"magnet:?xt=urn:btih:{H}&xt=urn:btih:{'1' * 40}")


def test_magnet_base32():
    import base64

    b32 = base64.b32encode(bytes.fromhex(H)).decode()
    assert magnet_hash(f"magnet:?xt=urn:btih:{b32}") == H


@pytest.mark.parametrize("bad", ["/", "relative/path", "/a/../b", "/a//b", "C:\\x", "", "/a/./b"])
def test_root_rejects(bad):
    with pytest.raises(InvalidInput):
        validate_root_path(bad)


def test_root_accepts():
    assert validate_root_path("/data/movies/") == "/data/movies"
    assert validate_root_path("D:/Media") == "D:/Media"


@pytest.mark.parametrize(
    "bad",
    ["", "..", "a/../b", "/abs/../x", "a/b:c", "a\\b", "x" * 200, "a/b/c/d/e/f/g", "a/ b ", "a//b"],
)
def test_subfolder_rejects(bad):
    with pytest.raises(InvalidInput):
        validate_subfolder(bad)


def test_join_and_within():
    assert (
        join_destination("/data/shows", "Show (2020)/Season 01")
        == "/data/shows/Show (2020)/Season 01"
    )
    assert is_within("/data/shows/x", "/data/shows")
    assert not is_within("/data/shows", "/data/shows")
    assert not is_within("/data/showsX/y", "/data/shows")
    assert not is_within("/data/shows/../etc", "/data/shows")


def test_urls():
    assert normalize_service_url("http://host:8080/") == "http://host:8080"
    for bad in ("ftp://x", "http://user:pw@host", "http://host?x=1", "http://host:99999", "host"):
        with pytest.raises(InvalidInput):
            normalize_service_url(bad)
