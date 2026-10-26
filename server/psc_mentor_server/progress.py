"""Attempts, topic mastery, weak areas and the spaced-revision queue (all per user)."""

from datetime import date, timedelta

from .db import Database

# Days until a question comes back after each successful revision.
REVISION_INTERVALS = [1, 3, 7, 15, 30]
WEAK_THRESHOLD = 0.6
MIN_ATTEMPTS_FOR_WEAK = 5
RECENT_WINDOW = 20  # per-topic accuracy looks at the latest N attempts


def update_revision(db: Database, user_id: int, question_id: int, is_correct: bool, today: date) -> None:
    row = db.one("SELECT stage FROM revision WHERE user_id = ? AND question_id = ?", (user_id, question_id))
    if not is_correct:
        due = today + timedelta(days=REVISION_INTERVALS[0])
        db.execute(
            "INSERT INTO revision (user_id, question_id, due_on, stage) VALUES (?, ?, ?, 0) "
            "ON CONFLICT(user_id, question_id) DO UPDATE SET due_on = excluded.due_on, stage = 0",
            (user_id, question_id, due.isoformat()),
        )
    elif row is not None:
        stage = row["stage"] + 1
        if stage >= len(REVISION_INTERVALS):
            db.execute("DELETE FROM revision WHERE user_id = ? AND question_id = ?", (user_id, question_id))
        else:
            due = today + timedelta(days=REVISION_INTERVALS[stage])
            db.execute("UPDATE revision SET due_on = ?, stage = ? WHERE user_id = ? AND question_id = ?",
                       (due.isoformat(), stage, user_id, question_id))


def apply_revisions(db: Database, user_id: int, results: list[tuple[int, bool]], today: date) -> None:
    """update_revision for a whole test at once: three round trips instead of two per question."""
    if not results:
        return
    ids = [qid for qid, _ in results]
    stages = {r["question_id"]: r["stage"] for r in db.query(
        f"SELECT question_id, stage FROM revision WHERE user_id = ? AND question_id IN ({','.join('?' * len(ids))})",
        [user_id, *ids])}
    upserts, deletes = [], []
    for qid, is_correct in results:
        if not is_correct:
            upserts.append((user_id, qid, (today + timedelta(days=REVISION_INTERVALS[0])).isoformat(), 0))
        elif qid in stages:
            stage = stages[qid] + 1
            if stage >= len(REVISION_INTERVALS):
                deletes.append((user_id, qid))
            else:
                upserts.append((user_id, qid, (today + timedelta(days=REVISION_INTERVALS[stage])).isoformat(), stage))
    if upserts:
        db.executemany(
            "INSERT INTO revision (user_id, question_id, due_on, stage) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(user_id, question_id) DO UPDATE SET due_on = excluded.due_on, stage = excluded.stage",
            upserts)
    if deletes:
        db.executemany("DELETE FROM revision WHERE user_id = ? AND question_id = ?", deletes)


def due_revision_ids(db: Database, user_id: int, today: date, limit: int = 100) -> list[int]:
    rows = db.query(
        "SELECT question_id FROM revision WHERE user_id = ? AND due_on <= ? ORDER BY due_on, stage LIMIT ?",
        (user_id, today.isoformat(), limit),
    )
    return [r["question_id"] for r in rows]


def topic_stats(db: Database, user_id: int) -> list[dict]:
    """Every topic with this user's recent accuracy; never-attempted topics have accuracy None."""
    rows = db.query(
        """
        WITH ranked AS (
            SELECT q.topic_id, a.is_correct, a.answered_at,
                   ROW_NUMBER() OVER (PARTITION BY q.topic_id ORDER BY a.answered_at DESC, a.id DESC) AS rn
            FROM attempts a JOIN questions q ON q.id = a.question_id
            WHERE a.user_id = ? AND a.selected_index IS NOT NULL
        )
        SELECT t.id, t.name, t.subject_id, s.name AS subject, s.weight,
               (SELECT COUNT(*) FROM questions WHERE topic_id = t.id) AS bank_size,
               COUNT(r.is_correct) AS attempts,
               COALESCE(SUM(r.is_correct), 0) AS correct,
               MAX(r.answered_at) AS last_attempt
        FROM topics t
        JOIN subjects s ON s.id = t.subject_id
        LEFT JOIN ranked r ON r.topic_id = t.id AND r.rn <= ?
        GROUP BY t.id, t.name, t.subject_id, t.position, s.name, s.weight, s.position
        ORDER BY s.position, t.position
        """,
        (user_id, RECENT_WINDOW),
    )
    return [
        {
            "topic_id": r["id"],
            "topic": r["name"],
            "subject_id": r["subject_id"],
            "subject": r["subject"],
            "weight": r["weight"],
            "bank_size": r["bank_size"],
            "attempts": r["attempts"],
            "accuracy": (r["correct"] / r["attempts"]) if r["attempts"] else None,
            "last_attempt": r["last_attempt"],
        }
        for r in rows
    ]


def weak_topics(stats: list[dict]) -> list[dict]:
    weak = [
        s for s in stats
        if s["weight"] > 0 and s["attempts"] >= MIN_ATTEMPTS_FOR_WEAK and s["accuracy"] < WEAK_THRESHOLD
    ]
    return sorted(weak, key=lambda s: s["accuracy"])


def subject_stats(stats: list[dict]) -> list[dict]:
    subjects: dict[str, dict] = {}
    for s in stats:
        entry = subjects.setdefault(s["subject_id"], {
            "subject_id": s["subject_id"], "subject": s["subject"], "weight": s["weight"],
            "attempts": 0, "correct": 0.0, "topics": 0, "topics_started": 0,
        })
        entry["topics"] += 1
        if s["attempts"]:
            entry["topics_started"] += 1
            entry["attempts"] += s["attempts"]
            entry["correct"] += s["accuracy"] * s["attempts"]
    out = []
    for e in subjects.values():
        e["accuracy"] = e["correct"] / e["attempts"] if e["attempts"] else None
        del e["correct"]
        out.append(e)
    return out


def study_streak(db: Database, user_id: int, today: date) -> int:
    days = {r["d"] for r in db.query(
        "SELECT DISTINCT substr(answered_at, 1, 10) AS d FROM attempts WHERE user_id = ?", (user_id,))}
    streak, day = 0, today
    if day.isoformat() not in days:
        day -= timedelta(days=1)  # today not studied yet doesn't break the streak
    while day.isoformat() in days:
        streak += 1
        day -= timedelta(days=1)
    return streak


def summary(db: Database, user_id: int, today: date) -> dict:
    stats = topic_stats(db, user_id)
    week_ago = (today - timedelta(days=6)).isoformat()
    overall = db.one(
        "SELECT COUNT(*) AS n, COALESCE(SUM(is_correct), 0) AS c FROM attempts "
        "WHERE user_id = ? AND selected_index IS NOT NULL", (user_id,))
    week = db.one(
        "SELECT COUNT(*) AS n, COALESCE(SUM(is_correct), 0) AS c FROM attempts "
        "WHERE user_id = ? AND selected_index IS NOT NULL AND answered_at >= ?",
        (user_id, week_ago),
    )
    tests = db.one("SELECT COUNT(*) AS n FROM tests WHERE user_id = ? AND submitted_at IS NOT NULL", (user_id,))
    general = [s for s in stats if s["weight"] > 0]
    return {
        "attempts": overall["n"],
        "accuracy": overall["c"] / overall["n"] if overall["n"] else None,
        "week_attempts": week["n"],
        "week_accuracy": week["c"] / week["n"] if week["n"] else None,
        "tests_taken": tests["n"],
        "streak_days": study_streak(db, user_id, today),
        "revision_due": len(due_revision_ids(db, user_id, today, limit=1000)),
        "syllabus_coverage": sum(1 for s in general if s["attempts"]) / len(general) if general else 0,
        "question_bank": db.one("SELECT COUNT(*) AS n FROM questions")["n"],
        "subjects": subject_stats(stats),
        "weak_topics": weak_topics(stats)[:8],
    }
