"""Strength report: strong and weak areas, and how much study time each section deserves.

Time is split across sections in proportion to

    marks_in_exam × (1 − accuracy + MAINTENANCE)

so a weak, high-mark section (often English or Arithmetic) gets the most time, and
strong sections still get a little practice to stay strong.
"""

from datetime import date

from .db import Database
from .progress import subject_stats, topic_stats
from .syllabus import NEGATIVE_MARK

STRONG = 0.70
WEAK = 0.50
TARGET = 0.80
MAINTENANCE = 0.15
UNASSESSED_PRIOR = 0.5
MIN_TOPIC_ATTEMPTS = 2  # the diagnostic gives each topic only a few questions
REVISION_MINUTES = 15
DAILY_TEST_MINUTES = 15
STUDY_DAYS = 6  # Sunday is test day


def status(accuracy: float | None) -> str:
    if accuracy is None:
        return "not_assessed"
    if accuracy >= STRONG:
        return "strong"
    if accuracy >= WEAK:
        return "average"
    return "weak"


def study_minutes_per_day(daily_minutes: int) -> int:
    return max(daily_minutes - REVISION_MINUTES - DAILY_TEST_MINUTES, 20)


def allocate(subjects: list[dict], weekly_minutes: int, step: int = 5) -> dict[str, int]:
    """Weekly study minutes per subject, in multiples of `step`, summing to weekly_minutes."""
    general = [s for s in subjects if s["weight"] > 0]
    need = {
        s["subject_id"]: s["weight"] * (1 - (s["accuracy"] if s["accuracy"] is not None else UNASSESSED_PRIOR)
                                        + MAINTENANCE)
        for s in general
    }
    total = sum(need.values()) or 1
    units = weekly_minutes // step
    exact = {k: units * v / total for k, v in need.items()}
    alloc = {k: int(v) for k, v in exact.items()}
    leftover = units - sum(alloc.values())
    for k in sorted(exact, key=lambda k: exact[k] - alloc[k], reverse=True)[:leftover]:
        alloc[k] += 1
    return {k: v * step for k, v in alloc.items()}


def expected_marks(weight: int, accuracy: float | None) -> float | None:
    """Marks this section would earn if every question were attempted at this accuracy."""
    if accuracy is None:
        return None
    return weight * (accuracy - (1 - accuracy) * NEGATIVE_MARK)


def report(db: Database, user_id: int, today: date) -> dict:
    profile = db.one("SELECT * FROM profiles WHERE user_id = ?", (user_id,))
    stats = topic_stats(db, user_id)
    subjects = [s for s in subject_stats(stats) if s["weight"] > 0]
    weekly = study_minutes_per_day(profile["daily_minutes"]) * STUDY_DAYS
    minutes = allocate(subjects, weekly)

    sections = []
    for s in subjects:
        topics = [t for t in stats if t["subject_id"] == s["subject_id"]]
        assessed = [t for t in topics if t["attempts"] >= MIN_TOPIC_ATTEMPTS]
        exp = expected_marks(s["weight"], s["accuracy"])
        sections.append({
            "subject_id": s["subject_id"],
            "subject": s["subject"],
            "marks": s["weight"],
            "attempts": s["attempts"],
            "accuracy": s["accuracy"],
            "status": status(s["accuracy"]),
            "weekly_minutes": minutes[s["subject_id"]],
            "expected_marks": None if exp is None else round(exp, 1),
            "potential_gain": None if s["accuracy"] is None
            else round(max(0.0, s["weight"] * (TARGET - s["accuracy"])), 1),
            "weak_topics": [{"topic_id": t["topic_id"], "topic": t["topic"], "accuracy": t["accuracy"]}
                            for t in sorted(assessed, key=lambda t: t["accuracy"]) if t["accuracy"] < WEAK],
            "strong_topics": [{"topic_id": t["topic_id"], "topic": t["topic"], "accuracy": t["accuracy"]}
                              for t in assessed if t["accuracy"] >= STRONG],
        })

    assessed_sections = [x for x in sections if x["expected_marks"] is not None]
    diagnostic = None
    if profile["diagnostic_test_id"]:
        t = db.one("SELECT id, score, max_score, correct, wrong, skipped, submitted_at FROM tests WHERE id = ?",
                   (profile["diagnostic_test_id"],))
        diagnostic = dict(t) if t else None
    order = {"weak": 0, "average": 1, "not_assessed": 2, "strong": 3}
    return {
        "date": today.isoformat(),
        "assessed": diagnostic is not None,
        "diagnostic": diagnostic,
        "daily_minutes": profile["daily_minutes"],
        "weekly_study_minutes": weekly,
        "estimated_score": round(sum(x["expected_marks"] for x in assessed_sections), 1)
        if assessed_sections else None,
        "max_score": sum(x["marks"] for x in sections),
        "thresholds": {"strong": STRONG, "weak": WEAK, "target": TARGET},
        "sections": sorted(sections, key=lambda x: (order[x["status"]], -(x["potential_gain"] or 0))),
    }
