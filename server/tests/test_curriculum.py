from collections import Counter
from datetime import date, timedelta

from psc_mentor_server import curriculum, engine, planner, progress

from .conftest import TODAY

EXAM_TOPICS = 49  # topics in the Degree Prelims syllabus (special.technical is not examined)


def test_default_course_covers_the_whole_syllabus(db, user):
    course = curriculum.build_course(progress.topic_stats(db, user), TODAY, None, 120)
    assert len(course) == curriculum.DEFAULT_DAYS
    topics = [t["topic_id"] for d in course for t in d["topics"]]
    assert len(set(topics)) == EXAM_TOPICS and not any(t.startswith("special.") for t in topics)
    for d in course:
        if date.fromisoformat(d["date"]).weekday() == 6 and d["kind"] not in ("mock", "revision"):
            assert d["kind"] == "weekly_test"
    assert course[-1]["kind"] == "mock" and {d["kind"] for d in course[-12:]} == {"mock", "revision"}


def test_each_study_day_has_one_block_per_section_and_parts_count_up(db, user):
    course = curriculum.build_course(progress.topic_stats(db, user), TODAY, None, 120)
    study = [d for d in course if d["kind"] == "study"]
    assert all(len(d["topics"]) == 3 for d in study[:20])  # 120 min/day -> 3 blocks of 30
    for d in study:
        sections = [t["topic_id"].split(".")[0] for t in d["topics"]]
        assert len(sections) == len(set(sections))
    seen = Counter()
    for d in study:
        for t in d["topics"]:
            seen[t["topic_id"]] += 1
            assert t["part"] == seen[t["topic_id"]] <= t["parts"]


def test_exam_date_sets_the_length_within_limits():
    assert curriculum.course_length(TODAY, TODAY + timedelta(days=75)) == 75
    assert curriculum.course_length(TODAY, TODAY + timedelta(days=5)) == curriculum.MIN_DAYS
    assert curriculum.course_length(TODAY, TODAY + timedelta(days=900)) == curriculum.MAX_DAYS


def test_short_course_puts_high_mark_sections_first(db, user):
    course = curriculum.build_course(progress.topic_stats(db, user), TODAY, TODAY + timedelta(days=30), 60)
    sections = Counter(t["topic_id"].split(".")[0] for d in course for t in d["topics"])
    assert sections["english"] == 5  # all English topics even when the course is too short for everything


def test_weekly_plan_follows_the_course(db, user):
    curriculum.ensure_course(db, user, TODAY)
    plan = planner.week_plan(db, user, TODAY)
    for offset in range(4):  # today (Wednesday) to Saturday
        day = (TODAY + timedelta(days=offset)).isoformat()
        assert [p["topic_id"] for p in plan if p["day"] == day and p["kind"] == "study"] == \
            curriculum.course_topics_on(db, user, TODAY + timedelta(days=offset))


def test_diagnostic_replans_only_the_future(db, user):
    curriculum.ensure_course(db, user, TODAY - timedelta(days=3))
    before = {r["day"]: (r["date"], r["topics_json"]) for r in db.query("SELECT * FROM course_days WHERE user_id = ?", (user,))}
    test_id = engine.create_test(db, user, "diagnostic", TODAY)
    test = engine.get_test(db, user, test_id)
    rows = {r["id"]: r for r in db.query("SELECT id, answer_index, topic_id FROM questions")}
    engine.submit_test(db, user, test_id, {q["id"]: {"selected": (rows[q["id"]]["answer_index"] + 1) % 4
                                                      if rows[q["id"]]["topic_id"].startswith("english.")
                                                      else rows[q["id"]]["answer_index"]} for q in test["questions"]}, TODAY)
    after = {r["day"]: (r["date"], r["topics_json"]) for r in db.query("SELECT * FROM course_days WHERE user_id = ?", (user,))}
    past = [d for d, (dt, _) in before.items() if dt < TODAY.isoformat()]
    assert past and all(after[d] == before[d] for d in past)
    assert [after[d][0] for d in sorted(after)] == sorted(after[d][0] for d in after)  # dates in order, no gaps
    future_english = sum('"english.' in t for d, (dt, t) in after.items() if dt >= TODAY.isoformat())
    future_english_before = sum('"english.' in t for d, (dt, t) in before.items() if dt >= TODAY.isoformat())
    assert future_english > future_english_before  # weak, 20-mark English got more days


def test_course_view_marks_practised_topics(db, user):
    view = curriculum.course_view(db, user, TODAY)
    today = next(d for d in view["days"] if d["date"] == TODAY.isoformat())
    assert view["today_day"] == today["day"] == 1 and not today["done"]
    first = today["topics"][0]
    assert first["details"] and first["subject"]
    test_id = engine.create_test(db, user, "topic", TODAY, topic_id=first["topic_id"])
    test = engine.get_test(db, user, test_id)
    engine.submit_test(db, user, test_id, {q["id"]: {"selected": 0} for q in test["questions"]}, TODAY)
    again = next(d for d in curriculum.course_view(db, user, TODAY)["days"] if d["date"] == TODAY.isoformat())
    assert again["topics"][0]["practised"]
