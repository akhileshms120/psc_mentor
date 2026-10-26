"""Most-viewed YouTube lessons for each syllabus topic (YouTube Data API v3).

A search costs 100 of the free 10,000 daily quota units, so results are cached per topic
for a week; all 52 topics fit in one day's quota with room to spare.
"""

import re
from datetime import datetime, timedelta

import httpx

from . import config
from .db import Database

API = "https://www.googleapis.com/youtube/v3"
CACHE_DAYS = 7
TOP_N = 3
SEARCH_RESULTS = 25
MIN_SECONDS = 180  # skips Shorts and trailers; a real lesson is longer
# Mentions of PSC in English or Malayalam ("പി.എസ്.സി", "പിഎസ്‌സി").
_PSC = re.compile(r"\bpsc\b|പി\.?\s?എസ്\.?\s?‌?സി", re.IGNORECASE)


class VideoError(RuntimeError):
    pass


def parse_duration(iso: str) -> int:
    """'PT1H2M3S' -> 3723 seconds."""
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return 0
    d, h, mi, s = (int(x) if x else 0 for x in m.groups())
    return ((d * 24 + h) * 60 + mi) * 60 + s


def search_query(subject: str, topic: str) -> str:
    return f"Kerala PSC {subject} {re.sub(r'[&:,/]+', ' ', topic)}".strip()


def _get(client: httpx.Client, path: str, params: dict) -> dict:
    try:
        resp = client.get(f"{API}/{path}", params={**params, "key": config.YOUTUBE_API_KEY})
    except httpx.HTTPError as e:
        raise VideoError("Could not reach YouTube.") from e
    if resp.status_code != 200:
        reason = ""
        try:
            reason = resp.json()["error"]["errors"][0]["reason"]
        except (ValueError, KeyError, IndexError, TypeError):
            pass
        if reason in ("quotaExceeded", "dailyLimitExceeded"):
            raise VideoError("Today's YouTube search allowance is used up; videos refresh tomorrow.")
        if resp.status_code in (400, 403) and reason in ("keyInvalid", "accessNotConfigured", "forbidden", ""):
            raise VideoError("The YouTube API key isn't valid for the YouTube Data API.")
        raise VideoError(f"YouTube error {resp.status_code} {reason}".strip())
    return resp.json()


def fetch_videos(client: httpx.Client, subject: str, topic: str) -> list[dict]:
    """Search, keep real PSC lessons, and rank them by views."""
    found = _get(client, "search", {
        "part": "snippet", "q": search_query(subject, topic), "type": "video",
        "maxResults": SEARCH_RESULTS, "regionCode": "IN", "safeSearch": "moderate",
    })
    ids = [i["id"]["videoId"] for i in found.get("items", []) if i.get("id", {}).get("videoId")]
    if not ids:
        return []
    details = _get(client, "videos", {"part": "snippet,statistics,contentDetails", "id": ",".join(ids)})
    videos = []
    for v in details.get("items", []):
        sn, stats = v.get("snippet", {}), v.get("statistics", {})
        seconds = parse_duration(v.get("contentDetails", {}).get("duration", ""))
        text = f"{sn.get('title', '')} {sn.get('description', '')} {' '.join(sn.get('tags', []))}"
        if seconds < MIN_SECONDS or not _PSC.search(text):
            continue
        thumbs = sn.get("thumbnails", {})
        videos.append({
            "video_id": v["id"],
            "title": sn.get("title", ""),
            "channel": sn.get("channelTitle", ""),
            "views": int(stats.get("viewCount", 0)),
            "duration_seconds": seconds,
            "thumbnail": (thumbs.get("medium") or thumbs.get("default") or {}).get("url"),
            "published_at": sn.get("publishedAt"),
        })
    return sorted(videos, key=lambda v: v["views"], reverse=True)[:TOP_N]


def _with_url(row) -> dict:
    v = {k: row[k] for k in ("video_id", "title", "channel", "views", "duration_seconds", "thumbnail", "published_at")}
    v["url"] = f"https://www.youtube.com/watch?v={v['video_id']}"
    return v


def topic_videos(db: Database, topic_id: str, client: httpx.Client | None = None,
                 now: datetime | None = None) -> dict:
    now = now or datetime.now()
    topic = db.one("SELECT t.name, s.name AS subject FROM topics t JOIN subjects s ON s.id = t.subject_id "
                   "WHERE t.id = ?", (topic_id,))
    if not topic:
        raise VideoError("Unknown topic")
    cached = db.query("SELECT * FROM topic_videos WHERE topic_id = ? ORDER BY rank", (topic_id,))
    last = db.one("SELECT fetched_at FROM topic_video_fetches WHERE topic_id = ?", (topic_id,))
    fresh = last and datetime.fromisoformat(last["fetched_at"]) > now - timedelta(days=CACHE_DAYS)
    if fresh:
        return {"topic_id": topic_id, "videos": [_with_url(r) for r in cached], "stale": False}
    if not config.YOUTUBE_API_KEY:
        if cached:
            return {"topic_id": topic_id, "videos": [_with_url(r) for r in cached], "stale": True}
        raise VideoError("Video suggestions are off: set YOUTUBE_API_KEY on the server.")
    try:
        with (client or httpx.Client(timeout=20)) as c:
            videos = fetch_videos(c, topic["subject"], topic["name"])
    except VideoError:
        if cached:  # an old list beats none when YouTube's quota runs out
            return {"topic_id": topic_id, "videos": [_with_url(r) for r in cached], "stale": True}
        raise
    stamp = now.isoformat(timespec="seconds")
    db.execute("DELETE FROM topic_videos WHERE topic_id = ?", (topic_id,))
    db.executemany(
        "INSERT INTO topic_videos (topic_id, rank, video_id, title, channel, views, duration_seconds, thumbnail, "
        "published_at, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [(topic_id, i, v["video_id"], v["title"], v["channel"], v["views"], v["duration_seconds"], v["thumbnail"],
          v["published_at"], stamp) for i, v in enumerate(videos)])
    db.execute("INSERT INTO topic_video_fetches (topic_id, fetched_at) VALUES (?, ?) "
               "ON CONFLICT (topic_id) DO UPDATE SET fetched_at = excluded.fetched_at", (topic_id, stamp))
    return {"topic_id": topic_id, "videos": [{**v, "url": f"https://www.youtube.com/watch?v={v['video_id']}"}
                                             for v in videos], "stale": False}
