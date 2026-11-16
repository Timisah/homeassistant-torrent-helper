import pytest

from custom_components.torrent_tools.errors import InvalidInput
from custom_components.torrent_tools.tv import plan_tv_destination

ROOT = "/data/shows"


def meta(name, paths):
    return {"info": {"name": name, "files": [{"path": p, "length": 1} for p in paths]}}


def test_flat_episodes_get_season_folder():
    m = meta("Show.S02", [f"Show.S02/Show.S02E0{i}.mkv" for i in (1, 2, 3)])
    plan = plan_tv_destination(m, ROOT, "Show", 2020)
    assert plan["save_path"] == "/data/shows/Show (2020)/Season 02"
    assert plan["content_layout"] == "NoSubfolder"


def test_existing_season_folders_not_duplicated():
    m = meta("Show Complete", ["Show Complete/Season 1/e1.mkv", "Show Complete/Season 2/e2.mkv"])
    plan = plan_tv_destination(m, ROOT, "Show", 2020)
    assert plan["save_path"] == "/data/shows/Show (2020)"
    assert plan["seasons"] == [1, 2]


def test_requires_unambiguous_season():
    m = meta("Show", ["Show/a.mkv", "Show/b.mkv"])
    with pytest.raises(InvalidInput):
        plan_tv_destination(m, ROOT, "Show")
    assert plan_tv_destination(m, ROOT, "Show", season=3)["save_path"].endswith("/Season 03")


def test_mixed_seasons_in_flat_folder_refused():
    m = meta("Show", ["Show/Show.S01E01.mkv", "Show/Show.S02E01.mkv"])
    with pytest.raises(InvalidInput):
        plan_tv_destination(m, ROOT, "Show", season=1)


def test_unsafe_and_nonvideo_refused():
    with pytest.raises(InvalidInput):
        plan_tv_destination(meta("x", ["x/../../etc/passwd.mkv"]), ROOT, "Show", season=1)
    with pytest.raises(InvalidInput):
        plan_tv_destination(meta("x", ["x/readme.txt"]), ROOT, "Show", season=1)
    with pytest.raises(InvalidInput):
        plan_tv_destination({"info": {}}, ROOT, "Show", season=1)


def test_show_name_is_sanitised():
    m = meta("x", ["x/a.S01E01.mkv"])
    plan = plan_tv_destination(m, ROOT, "A/B: ../C", 1999)
    assert "/.." not in plan["save_path"] and plan["save_path"].startswith("/data/shows/")
    assert plan["save_path"].count("/") == 4
