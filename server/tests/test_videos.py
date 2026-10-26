from datetime import datetime, timedelta

import httpx
import pytest

from psc_mentor_server import config, videos

TOPIC = "constitution.rights_duties"
NOW = datetime(2026, 10, 28, 9, 0)


def video(vid, title, views, duration="PT25M10S", description=""):
    return {"id": vid, "snippet": {"title": title, "description": description, "channelTitle": "PSC Channel",
                                   "thumbnails": {"medium": {"url": f"https://i.ytimg.com/{vid}.jpg"}},
                                   "publishedAt": "2026-01-01T00:00:00Z"},
            "statistics": {"viewCount": str(views)}, "contentDetails": {"duration": duration}}


ITEMS = [
    video("a", "Fundamental Rights | Kerala PSC Degree Prelims", 250_000),
    video("b", "Fundamental Rights explained", 900_000),                        # not a PSC lesson
    video("c", "Kerala PSC Constitution class", 1_200_000, duration="PT45S"),  # a Short
    video("d", "മൗലികാവകാശങ്ങൾ", 480_000, description="പി.എസ്.സി ക്ലാസ്"),       # PSC in Malayalam
    video("e", "DPSP for PSC exam", 75_000),
    video("f", "Citizenship - Kerala PSC", 30_000),
]


def fake_youtube(calls, status=200, error_reason=None):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path.rsplit("/", 1)[-1])
        if status != 200:
            return httpx.Response(status, json={"error": {"errors": [{"reason": error_reason}]}})
        if request.url.path.endswith("/search"):
            assert "Kerala PSC" in request.url.params["q"]
            return httpx.Response(200, json={"items": [{"id": {"videoId": v["id"]}} for v in ITEMS]})
        assert request.url.params["id"] == "a,b,c,d,e,f"
        return httpx.Response(200, json={"items": ITEMS})
    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.fixture
def key(monkeypatch):
    monkeypatch.setattr(config, "YOUTUBE_API_KEY", "test-key")


def test_duration_parsing():
    assert videos.parse_duration("PT1H2M3S") == 3723
    assert videos.parse_duration("PT45S") == 45
    assert videos.parse_duration("P1DT1M") == 86460
    assert videos.parse_duration("") == 0


def test_top_three_real_psc_lessons_by_views(db, key):
    calls = []
    out = videos.topic_videos(db, TOPIC, client=fake_youtube(calls), now=NOW)
    assert [v["video_id"] for v in out["videos"]] == ["d", "a", "e"]  # b: not PSC, c: a Short
    assert out["videos"][0]["url"] == "https://www.youtube.com/watch?v=d"
    assert out["videos"][0]["views"] == 480_000 and out["stale"] is False
    assert calls == ["search", "videos"]


def test_results_are_cached_for_a_week(db, key):
    calls = []
    videos.topic_videos(db, TOPIC, client=fake_youtube(calls), now=NOW)
    again = videos.topic_videos(db, TOPIC, client=fake_youtube(calls), now=NOW + timedelta(days=6))
    assert calls == ["search", "videos"] and len(again["videos"]) == 3
    videos.topic_videos(db, TOPIC, client=fake_youtube(calls), now=NOW + timedelta(days=8))
    assert calls == ["search", "videos", "search", "videos"]


def test_quota_exhausted_serves_the_old_list(db, key):
    videos.topic_videos(db, TOPIC, client=fake_youtube([]), now=NOW)
    out = videos.topic_videos(db, TOPIC, client=fake_youtube([], 403, "quotaExceeded"), now=NOW + timedelta(days=9))
    assert out["stale"] is True and len(out["videos"]) == 3
    with pytest.raises(videos.VideoError, match="allowance is used up"):
        videos.topic_videos(db, "history.world_history", client=fake_youtube([], 403, "quotaExceeded"), now=NOW)


def test_no_key_is_a_clear_message(db, monkeypatch):
    monkeypatch.setattr(config, "YOUTUBE_API_KEY", None)
    with pytest.raises(videos.VideoError, match="YOUTUBE_API_KEY"):
        videos.topic_videos(db, TOPIC, now=NOW)


def test_empty_results_are_cached_too(db, key):
    calls = []

    def empty(request):
        calls.append(1)
        return httpx.Response(200, json={"items": []})

    for _ in range(2):
        assert videos.topic_videos(db, TOPIC, client=httpx.Client(transport=httpx.MockTransport(empty)), now=NOW)["videos"] == []
    assert len(calls) == 1
