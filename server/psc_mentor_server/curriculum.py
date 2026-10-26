"""The day-by-day course: Day 1 study this, Day 2 study that, until the exam.

Mon-Sat are study days with fixed topics; Sundays are weekly-test and revision days; the
last stretch before the exam alternates full mocks and revision. Every topic of the Degree
Prelims syllabus appears at least once. Extra days go to sections by `analysis.allocate`
(marks in the exam x how weak the student is), so the course changes after the diagnostic.
"""

import json
from datetime import date, timedelta

from .analysis import BLOCK_MINUTES, allocate, study_minutes_per_day
from .db import Database
from .progress import subject_stats, topic_stats
from .syllabus import TOPIC_DETAILS

DEFAULT_DAYS = 120
MIN_DAYS = 30
MAX_DAYS = 240
FINAL_PHASE_SHARE = 0.1
MIN_FINAL_DAYS = 4


def course_length(start: date, exam_date: date | None) -> int:
    if not exam_date:
        return DEFAULT_DAYS
    return max(MIN_DAYS, min(MAX_DAYS, (exam_date - start).days))


def _topic_slots(stats: list[dict], section_slots: dict[str, int]) -> dict[str, list[str]]:
    """Per section, the ordered topic slots: each topic's parts together, in syllabus order.
    A section's extra slots go round its topics, weakest first, so parts stay balanced."""
    out: dict[str, list[str]] = {}
    for subject_id, n in section_slots.items():
        topics = [t for t in stats if t["subject_id"] == subject_id]  # syllabus order
        if not topics or n <= 0:
            continue
        counts = {t["topic_id"]: 0 for t in topics}
        by_need = sorted(topics, key=lambda t: t["accuracy"] if t["accuracy"] is not None else 0.5)
        for i in range(n):
            counts[(topics[i] if i < len(topics) else by_need[(i - len(topics)) % len(topics)])["topic_id"]] += 1
        out[subject_id] = [t["topic_id"] for t in topics for _ in range(counts[t["topic_id"]])]
    return out


def _section_slots(stats: list[dict], total_slots: int) -> dict[str, int]:
    """Every topic gets one slot first (if the course is long enough), the rest by allocate()."""
    subjects = [s for s in subject_stats(stats) if s["weight"] > 0]
    topic_count = {s["subject_id"]: s["topics"] for s in subjects}
    base = sum(topic_count.values())
    if total_slots <= base:  # very short course: cover the highest-mark sections' topics first
        out, left = {}, total_slots
        for s in sorted(subjects, key=lambda s: -s["weight"]):
            out[s["subject_id"]] = min(topic_count[s["subject_id"]], left)
            left -= out[s["subject_id"]]
        return out
    extra = allocate(subjects, total_slots - base, step=1)
    return {sid: topic_count[sid] + extra.get(sid, 0) for sid in topic_count}


def build_course(stats: list[dict], start: date, exam_date: date | None, daily_minutes: int) -> list[dict]:
    total = course_length(start, exam_date)
    days = [start + timedelta(days=i) for i in range(total)]
    final_n = max(MIN_FINAL_DAYS, round(total * FINAL_PHASE_SHARE))
    final_days = set(days[-final_n:])
    study_days = [d for d in days if d.weekday() != 6 and d not in final_days]

    per_day = max(1, round(study_minutes_per_day(daily_minutes) / BLOCK_MINUTES))
    queues = _topic_slots(stats, _section_slots(stats, len(study_days) * per_day))
    planned = {s: len(q) for s, q in queues.items()}
    parts_total = {t: sum(q.count(t) for q in queues.values()) for t in {x for q in queues.values() for x in q}}
    parts_done: dict[str, int] = {}

    # Smooth weighted round-robin: every section earns credit at the rate of its planned slots,
    # so a section with 3x the slots comes up 3x as often from day 1, not just later in the course.
    credit = {s: 0.0 for s in queues}
    course: list[dict] = []
    for n, d in enumerate(days, start=1):
        if d in final_days:
            kind = "mock" if (total - n) % 2 == 0 else "revision"
            course.append({"day": n, "date": d.isoformat(), "kind": kind, "topics": []})
            continue
        if d.weekday() == 6:
            course.append({"day": n, "date": d.isoformat(), "kind": "weekly_test", "topics": []})
            continue
        topics, used = [], set()
        for _ in range(per_day):
            active = [s for s in queues if queues[s] and s not in used]  # one block per section per day
            if not active:
                break
            weight_sum = sum(planned[s] for s in active)
            for s in active:
                credit[s] += planned[s]
            subject_id = max(active, key=lambda s: credit[s])
            credit[subject_id] -= weight_sum
            used.add(subject_id)
            topic = queues[subject_id].pop(0)
            parts_done[topic] = parts_done.get(topic, 0) + 1
            topics.append({"topic_id": topic, "part": parts_done[topic], "parts": parts_total[topic]})
        course.append({"day": n, "date": d.isoformat(), "kind": "study" if topics else "revision",
                       "topics": topics})
    return course


def ensure_course(db: Database, user_id: int, today: date, rebuild: bool = False) -> None:
    """Build the course on first use; with rebuild, re-plan from today on and keep past days."""
    have = db.one("SELECT MIN(date) AS first, COUNT(*) AS n FROM course_days WHERE user_id = ?", (user_id,))
    if have["n"] and not rebuild:
        return
    profile = db.one("SELECT daily_minutes, exam_date FROM profiles WHERE user_id = ?", (user_id,))
    exam = date.fromisoformat(profile["exam_date"]) if profile["exam_date"] else None
    first = date.fromisoformat(have["first"]) if have["n"] else today
    start = max(today, first)
    past = db.one("SELECT MAX(day) AS d FROM course_days WHERE user_id = ? AND date < ?",
                  (user_id, start.isoformat()))["d"] or 0
    remaining_exam = exam if exam else first + timedelta(days=DEFAULT_DAYS)
    days = build_course(topic_stats(db, user_id), start, remaining_exam, profile["daily_minutes"])
    db.execute("DELETE FROM course_days WHERE user_id = ? AND date >= ?", (user_id, start.isoformat()))
    db.executemany(
        "INSERT INTO course_days (user_id, day, date, kind, topics_json) VALUES (?, ?, ?, ?, ?)",
        [(user_id, past + d["day"], d["date"], d["kind"], json.dumps(d["topics"])) for d in days])


def course_topics_on(db: Database, user_id: int, day: date) -> list[str] | None:
    """The course's topics for a date, or None if the course has nothing planned then."""
    row = db.one("SELECT kind, topics_json FROM course_days WHERE user_id = ? AND date = ?",
                 (user_id, day.isoformat()))
    if not row or row["kind"] != "study":
        return None
    return [t["topic_id"] for t in json.loads(row["topics_json"])]


def course_view(db: Database, user_id: int, today: date) -> dict:
    ensure_course(db, user_id, today)
    names = {r["id"]: (r["name"], r["subject"], r["subject_id"]) for r in db.query(
        "SELECT t.id, t.name, s.name AS subject, s.id AS subject_id FROM topics t "
        "JOIN subjects s ON s.id = t.subject_id")}
    done_dates = {r["day"] for r in db.query(
        "SELECT day FROM plan_items WHERE user_id = ? AND kind = 'study' GROUP BY day HAVING MIN(done) = 1",
        (user_id,))}
    # A topic counts as practised when its study block that day is ticked off (a topic test does that).
    tested = {(r["day"], r["topic_id"]) for r in db.query(
        "SELECT day, topic_id FROM plan_items WHERE user_id = ? AND kind = 'study' AND done = 1", (user_id,))}
    days = []
    for r in db.query("SELECT * FROM course_days WHERE user_id = ? ORDER BY day", (user_id,)):
        topics = []
        for t in json.loads(r["topics_json"]):
            name, subject, subject_id = names.get(t["topic_id"], (t["topic_id"], "", ""))
            topics.append({**t, "topic": name, "subject": subject, "subject_id": subject_id,
                           "details": TOPIC_DETAILS.get(t["topic_id"], ""),
                           "practised": (r["date"], t["topic_id"]) in tested})
        days.append({"day": r["day"], "date": r["date"], "kind": r["kind"], "topics": topics,
                     "done": r["date"] in done_dates or (bool(topics) and all(t["practised"] for t in topics))})
    today_row = next((d for d in days if d["date"] == today.isoformat()), None)
    return {"total_days": len(days), "today_day": today_row["day"] if today_row else None,
            "start": days[0]["date"] if days else None, "end": days[-1]["date"] if days else None,
            "days": days}
