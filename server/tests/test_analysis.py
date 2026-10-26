import pytest

from psc_mentor_server import analysis, engine, planner
from psc_mentor_server.syllabus import NEGATIVE_MARK

from .conftest import TODAY


def subject(sid, weight, accuracy):
    return {"subject_id": sid, "weight": weight, "accuracy": accuracy}


def test_status_thresholds():
    assert analysis.status(None) == "not_assessed"
    assert analysis.status(0.7) == "strong"
    assert analysis.status(0.69) == "average"
    assert analysis.status(0.5) == "average"
    assert analysis.status(0.49) == "weak"


def test_weak_high_mark_sections_get_most_time_and_strong_ones_keep_some():
    alloc = analysis.allocate([
        subject("english", 20, 0.3),      # weak, 20 marks
        subject("economics", 5, 0.3),     # weak, 5 marks
        subject("history", 10, 0.9),      # strong
        subject("special", 0, None),      # not in the exam
    ], weekly_minutes=600)
    assert sum(alloc.values()) == 600
    assert all(v % 5 == 0 for v in alloc.values())
    assert alloc["english"] > alloc["economics"] * 3.5
    assert alloc["english"] > alloc["history"] > 0
    assert "special" not in alloc


def test_unassessed_sections_count_as_halfway():
    alloc = analysis.allocate([subject("a", 10, None), subject("b", 10, 0.5)], weekly_minutes=100)
    assert alloc == {"a": 50, "b": 50}


def test_expected_marks_include_negative_marking():
    assert analysis.expected_marks(20, 1.0) == 20
    assert analysis.expected_marks(20, 0.5) == pytest.approx(20 * (0.5 - 0.5 * NEGATIVE_MARK))
    assert analysis.expected_marks(20, None) is None


def _take(db, user, type, pick):
    test_id = engine.create_test(db, user, type, TODAY)
    test = engine.get_test(db, user, test_id)
    rows = {r["id"]: r for r in db.query("SELECT id, answer_index, topic_id FROM questions")}
    engine.submit_test(db, user, test_id,
                       {q["id"]: {"selected": pick(rows[q["id"]])} for q in test["questions"]}, TODAY)
    return test_id


def test_report_after_diagnostic(db, user):
    before = analysis.report(db, user, TODAY)
    assert not before["assessed"] and before["estimated_score"] is None

    # Right on everything except English, which is all wrong.
    _take(db, user, "diagnostic",
          lambda q: (q["answer_index"] + 1) % 4 if q["topic_id"].startswith("english.") else q["answer_index"])
    report = analysis.report(db, user, TODAY)
    assert report["assessed"]
    sections = {s["subject_id"]: s for s in report["sections"]}
    assert sections["english"]["status"] == "weak"
    assert sections["english"]["potential_gain"] == 16.0  # 20 marks × (80% target − 0%)
    assert sections["history"]["status"] == "strong"
    assert report["sections"][0]["subject_id"] == "english"  # weakest, most to gain, listed first
    assert max(report["sections"], key=lambda s: s["weekly_minutes"])["subject_id"] == "english"
    assert sum(s["weekly_minutes"] for s in report["sections"]) == report["weekly_study_minutes"]
    assert sections["english"]["weak_topics"]
    assert report["estimated_score"] < report["max_score"]


def test_plan_after_diagnostic_gives_weak_sections_more_blocks(db, user):
    _take(db, user, "diagnostic",
          lambda q: (q["answer_index"] + 1) % 4 if q["topic_id"].startswith("english.") else q["answer_index"])
    plan = planner.week_plan(db, user, TODAY)
    study = [p["subject_id"] for p in plan if p["kind"] == "study"]
    counts = {s: study.count(s) for s in set(study)}
    assert counts["english"] == max(counts.values())
    assert counts["english"] > counts.get("history", 0)
