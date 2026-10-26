from datetime import date

from psc_mentor_server import planner, progress

from .conftest import TODAY


def test_week_has_study_days_and_a_sunday_test(db, user):
    plan = planner.week_plan(db, user, TODAY)
    days = sorted({p["day"] for p in plan})
    assert days[0] == "2026-10-26" and days[-1] == "2026-11-01"  # Monday..Sunday
    for day in days[:6]:
        kinds = [p["kind"] for p in plan if p["day"] == day]
        assert kinds.count("study") == 3  # 120 min/day: 90 min of study in 30-minute blocks
        assert "daily_test" in kinds and "revision" in kinds
    assert [p["kind"] for p in plan if p["day"] == days[6]][0] == "weekly_test"


def test_a_subject_appears_at_most_once_a_day(db, user):
    plan = planner.week_plan(db, user, TODAY)
    for day in sorted({p["day"] for p in plan})[:6]:
        subjects = [p["subject_id"] for p in plan if p["day"] == day and p["kind"] == "study"]
        assert len(subjects) == len(set(subjects))


def test_before_the_diagnostic_time_follows_exam_marks(db, user):
    plan = planner.week_plan(db, user, TODAY)
    study = [p["subject_id"] for p in plan if p["kind"] == "study"]
    assert study.count("english") == max(study.count(s) for s in set(study))  # 20 marks


def test_last_sunday_of_month_is_the_monthly_mock(db, user):
    assert planner.is_last_sunday_of_month(date(2026, 10, 25))
    assert not planner.is_last_sunday_of_month(date(2026, 10, 18))
    plan = planner.week_plan(db, user, date(2026, 10, 21))
    assert [p["kind"] for p in plan if p["day"] == "2026-10-25"] == ["monthly_mock"]


def test_weak_topics_come_first():
    stats = [
        {"topic_id": "history.a", "attempts": 10, "accuracy": 0.9, "last_attempt": "2026-10-27T10:00:00"},
        {"topic_id": "history.b", "attempts": 10, "accuracy": 0.3, "last_attempt": "2026-10-27T10:00:00"},
        {"topic_id": "history.c", "attempts": 0, "accuracy": None, "last_attempt": None},
    ]
    ranked = sorted(stats, key=lambda s: planner.topic_priority(s, TODAY), reverse=True)
    assert [s["topic_id"] for s in ranked] == ["history.b", "history.c", "history.a"]


def test_plan_is_stable_until_regenerated(db, user):
    first = planner.week_plan(db, user, TODAY)
    assert planner.week_plan(db, user, TODAY) == first
    planner.ensure_week(db, user, TODAY, regenerate=True)
    after = planner.week_plan(db, user, TODAY)
    assert [p for p in after if p["day"] < TODAY.isoformat()] == [p for p in first if p["day"] < TODAY.isoformat()]
    assert len(after) == len(first)


def test_streak_counts_consecutive_days(db, user):
    qid = db.one("SELECT id FROM questions LIMIT 1")["id"]
    test_id = db.execute("INSERT INTO tests (user_id, type, title, question_ids_json, duration_minutes, "
                         "negative_mark, created_at) VALUES (?, 'topic', 't', '[]', 1, 0, '2026-10-01')", (user,))
    for d in ["2026-10-25", "2026-10-26", "2026-10-27", "2026-10-23"]:
        db.execute("INSERT INTO attempts (user_id, test_id, question_id, selected_index, is_correct, answered_at) "
                   "VALUES (?, ?, ?, 0, 1, ?)", (user, test_id, qid, d + "T09:00:00"))
    assert progress.study_streak(db, user, TODAY) == 3
