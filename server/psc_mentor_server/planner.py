"""Weekly study plan built from the strength report.

Mon-Sat: revision, ~30-minute study blocks shared out across sections by
`analysis.allocate` (weak, high-mark sections get more), and a daily test.
Sunday: the weekly test, or the full mock on the last Sunday of the month.
"""

from datetime import date, datetime, timedelta

from . import curriculum
from .analysis import BLOCK_MINUTES, DAILY_TEST_MINUTES, REVISION_MINUTES, STUDY_DAYS, allocate, study_minutes_per_day
from .db import Database
from .progress import WEAK_THRESHOLD, subject_stats, topic_stats

STALE_DAYS = 14


def week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def is_last_sunday_of_month(day: date) -> bool:
    return day.weekday() == 6 and (day + timedelta(days=7)).month != day.month


def topic_priority(stat: dict, today: date) -> float:
    """Higher = study sooner. Weak beats unseen beats stale beats strong."""
    if stat["attempts"] == 0:
        return 2
    acc = stat["accuracy"]
    if stat["attempts"] >= 2 and acc < WEAK_THRESHOLD:
        return 3 + (WEAK_THRESHOLD - acc) * 5
    last = datetime.fromisoformat(stat["last_attempt"]).date()
    if (today - last).days > STALE_DAYS:
        return 1.5
    return 1 - acc


def study_blocks(stats: list[dict], daily_minutes: int, today: date) -> tuple[list[list[dict]], int]:
    """Six days of (topic) study blocks and the minutes per block."""
    per_day_minutes = study_minutes_per_day(daily_minutes)
    per_day = max(1, round(per_day_minutes / BLOCK_MINUTES))
    block_minutes = per_day_minutes // per_day
    subjects = [s for s in subject_stats(stats) if s["weight"] > 0]
    counts = allocate(subjects, STUDY_DAYS * per_day, step=1)

    days: list[list[dict]] = [[] for _ in range(STUDY_DAYS)]
    slot = 0
    # Dealing each subject's blocks to consecutive days keeps a subject to once a day
    # (unless it has more blocks than there are days).
    for subject_id in sorted(counts, key=lambda k: counts[k], reverse=True):
        topics = sorted((t for t in stats if t["subject_id"] == subject_id),
                        key=lambda t: topic_priority(t, today), reverse=True)
        for i in range(counts[subject_id]):
            days[slot % STUDY_DAYS].append(topics[i % len(topics)])
            slot += 1
    return days, block_minutes


def build_week(stats: list[dict], start: date, daily_minutes: int, today: date,
               course: dict[str, list[str]] | None = None) -> list[dict]:
    """course: {date: [topic_id, ...]} from the day-by-day course; those days study exactly that."""
    days, block_minutes = study_blocks(stats, daily_minutes, today)
    by_id = {t["topic_id"]: t for t in stats}
    for offset in range(STUDY_DAYS):
        planned = (course or {}).get((start + timedelta(days=offset)).isoformat())
        if planned:
            days[offset] = [by_id[t] for t in planned if t in by_id]
    items: list[dict] = []
    for offset in range(7):
        day = (start + timedelta(days=offset)).isoformat()
        if offset == 6:
            sunday = start + timedelta(days=6)
            if is_last_sunday_of_month(sunday):
                items.append({"day": day, "kind": "monthly_mock", "topic_id": None, "minutes": 75})
            else:
                items.append({"day": day, "kind": "weekly_test", "topic_id": None, "minutes": 40})
                items.append({"day": day, "kind": "revision", "topic_id": None, "minutes": REVISION_MINUTES})
            continue
        items.append({"day": day, "kind": "revision", "topic_id": None, "minutes": REVISION_MINUTES})
        for topic in days[offset]:
            minutes = study_minutes_per_day(daily_minutes) // max(len(days[offset]), 1)
            items.append({"day": day, "kind": "study", "topic_id": topic["topic_id"], "minutes": minutes})
        items.append({"day": day, "kind": "daily_test", "topic_id": None, "minutes": DAILY_TEST_MINUTES})
    return items


def ensure_week(db: Database, user_id: int, today: date, regenerate: bool = False) -> str:
    start = week_start(today).isoformat()
    exists = db.one("SELECT 1 FROM plan_items WHERE user_id = ? AND week_start = ? LIMIT 1", (user_id, start))
    if exists and not regenerate:
        return start
    profile = db.one("SELECT daily_minutes FROM profiles WHERE user_id = ?", (user_id,))
    curriculum.ensure_course(db, user_id, today)
    monday = week_start(today)
    course = {}
    for i in range(STUDY_DAYS):
        topics = curriculum.course_topics_on(db, user_id, monday + timedelta(days=i))
        if topics:
            course[(monday + timedelta(days=i)).isoformat()] = topics
    items = build_week(topic_stats(db, user_id), monday, profile["daily_minutes"], today, course)
    if regenerate:
        # keep what was already done; only re-plan from today onwards
        db.execute("DELETE FROM plan_items WHERE user_id = ? AND week_start = ? AND day >= ? AND done = 0",
                   (user_id, start, today.isoformat()))
        kept = {(r["day"], r["kind"], r["topic_id"]) for r in db.query(
            "SELECT day, kind, topic_id FROM plan_items WHERE user_id = ? AND week_start = ?", (user_id, start))}
        items = [i for i in items if i["day"] >= today.isoformat()
                 and (i["day"], i["kind"], i["topic_id"]) not in kept]
    db.executemany(
        "INSERT INTO plan_items (user_id, week_start, day, kind, topic_id, minutes) VALUES (?, ?, ?, ?, ?, ?)",
        [(user_id, start, i["day"], i["kind"], i["topic_id"], i["minutes"]) for i in items],
    )
    return start


def week_plan(db: Database, user_id: int, today: date) -> list[dict]:
    start = ensure_week(db, user_id, today)
    rows = db.query(
        "SELECT p.*, t.name AS topic, s.name AS subject, s.id AS subject_id FROM plan_items p "
        "LEFT JOIN topics t ON t.id = p.topic_id LEFT JOIN subjects s ON s.id = t.subject_id "
        "WHERE p.user_id = ? AND p.week_start = ? ORDER BY p.day, p.id",
        (user_id, start),
    )
    return [
        {"id": r["id"], "day": r["day"], "kind": r["kind"], "topic_id": r["topic_id"], "topic": r["topic"],
         "subject": r["subject"], "subject_id": r["subject_id"], "minutes": r["minutes"], "done": bool(r["done"])}
        for r in rows
    ]


def mark_done(db: Database, user_id: int, today: date, kind: str, topic_id: str | None = None) -> None:
    """Tick off the matching plan item when the student finishes the activity."""
    start = ensure_week(db, user_id, today)
    if kind in ("weekly_test", "monthly_mock"):
        # these count whichever day of the week they are taken
        db.execute("UPDATE plan_items SET done = 1 WHERE user_id = ? AND week_start = ? AND kind = ?",
                   (user_id, start, kind))
    elif topic_id:
        db.execute("UPDATE plan_items SET done = 1 WHERE user_id = ? AND day = ? AND kind = ? AND topic_id = ?",
                   (user_id, today.isoformat(), kind, topic_id))
    else:
        db.execute("UPDATE plan_items SET done = 1 WHERE user_id = ? AND day = ? AND kind = ?",
                   (user_id, today.isoformat(), kind))
