from datetime import timedelta

import pytest

from psc_mentor_server import auth, engine, planner, progress
from psc_mentor_server.questions import add_question

from .conftest import TODAY


def answer_all(db, user, test_id, pick):
    """pick(question_row) -> selected index or None"""
    test = engine.get_test(db, user, test_id)
    rows = {r["id"]: r for r in db.query("SELECT id, answer_index, topic_id FROM questions")}
    answers = {q["id"]: {"selected": pick(rows[q["id"]]), "time_ms": 1000} for q in test["questions"]}
    return engine.submit_test(db, user, test_id, answers, TODAY)


def wrong(q):
    return (q["answer_index"] + 1) % 4


def test_negative_marking_is_one_third():
    result = engine.score([0, 1, None, 2], [0, 0, 1, 2], 1 / 3)
    assert result == {"correct": 2, "wrong": 1, "skipped": 1, "score": 1.67, "max_score": 4.0}


def test_topic_test_hides_answers_until_submitted(db, user):
    test = engine.get_test(db, user, engine.create_test(db, user, "topic", TODAY, topic_id="constitution.rights_duties"))
    assert test["question_count"] == 20
    assert all("answer_index" not in q for q in test["questions"])


def test_small_topic_is_padded_from_the_same_subject_first(db, user):
    test = engine.get_test(db, user, engine.create_test(db, user, "topic", TODAY, topic_id="economics.finance"))
    topics = [q["topic_id"] for q in test["questions"]]
    assert topics.count("economics.finance") == 2
    assert topics.count("economics.planning") == 2  # all the subject has, before other subjects


def test_submit_scores_and_reveals_answers(db, user):
    test_id = engine.create_test(db, user, "topic", TODAY, topic_id="civics.government")
    result = answer_all(db, user, test_id, wrong)
    assert result["correct"] == 0 and result["wrong"] == result["question_count"]
    assert result["score"] == pytest.approx(-result["question_count"] / 3, abs=0.01)
    assert all("answer_index" in q and "selected_index" in q for q in result["questions"])
    with pytest.raises(engine.TestError):
        engine.submit_test(db, user, test_id, {}, TODAY)


def test_tests_are_private_to_their_owner(db, user):
    _, other = auth.signup(db, "Binu", "binu@example.com", "secret123")
    test_id = engine.create_test(db, user, "daily", TODAY)
    with pytest.raises(engine.TestError):
        engine.get_test(db, other, test_id)
    answer_all(db, user, test_id, wrong)
    assert progress.summary(db, other, TODAY)["attempts"] == 0
    assert progress.due_revision_ids(db, other, TODAY + timedelta(days=1)) == []


def test_wrong_answers_enter_revision_and_mistake_bank(db, user):
    test_id = engine.create_test(db, user, "topic", TODAY, topic_id="history.kerala_renaissance")
    answer_all(db, user, test_id, wrong)
    tomorrow = TODAY + timedelta(days=1)
    due = progress.due_revision_ids(db, user, tomorrow)
    assert len(due) == 20
    retest = engine.get_test(db, user, engine.create_test(db, user, "mistakes", tomorrow))
    assert {q["id"] for q in retest["questions"]} <= set(due)


def test_revision_interval_grows_and_retires(db, user):
    qid = db.one("SELECT id FROM questions LIMIT 1")["id"]
    progress.update_revision(db, user, qid, False, TODAY)
    day = TODAY
    for interval in progress.REVISION_INTERVALS[1:]:
        progress.update_revision(db, user, qid, True, day)
        row = db.one("SELECT due_on FROM revision WHERE user_id = ? AND question_id = ?", (user, qid))
        assert row["due_on"] == (day + timedelta(days=interval)).isoformat()
        day = day + timedelta(days=interval)
    progress.update_revision(db, user, qid, True, day)
    assert db.one("SELECT 1 FROM revision WHERE question_id = ?", (qid,)) is None


def test_exam_quota_follows_official_marks(db, user):
    quota = engine.exam_quota(progress.topic_stats(db, user))
    assert sum(quota.values()) == 100
    by_subject = {}
    for t, n in quota.items():
        by_subject[t.split(".")[0]] = by_subject.get(t.split(".")[0], 0) + n
    assert by_subject == {"history": 10, "geography": 5, "economics": 5, "civics": 5, "constitution": 5,
                          "culture": 10, "computer": 5, "science": 5, "arithmetic": 10,
                          "mental_ability": 10, "english": 20, "malayalam": 10}


def test_diagnostic_is_exam_pattern_in_section_order_and_unlocks_plan(db, user):
    test_id = engine.create_test(db, user, "diagnostic", TODAY)
    test = engine.get_test(db, user, test_id)
    bank = db.one("SELECT COUNT(*) AS n FROM questions WHERE topic_id NOT LIKE 'special.%'")["n"]
    assert test["question_count"] == min(100, bank)
    assert test["duration_minutes"] == 75
    positions = [db.one("SELECT s.position FROM topics t JOIN subjects s ON s.id = t.subject_id WHERE t.id = ?",
                        (q["topic_id"],))["position"] for q in test["questions"]]
    assert positions == sorted(positions)
    answer_all(db, user, test_id, lambda q: q["answer_index"])
    assert db.one("SELECT diagnostic_test_id FROM profiles WHERE user_id = ?", (user,))[0] == test_id


def test_newest_degree_level_pyqs_are_preferred(db, user):
    old = db.execute("INSERT INTO papers (title, key_url, status, level, uploaded_on) "
                     "VALUES ('LDC', 'k1', 'done', 'general', '01-01-2025')")
    new = db.execute("INSERT INTO papers (title, key_url, status, level, uploaded_on) "
                     "VALUES ('University Assistant', 'k2', 'done', 'degree', '14-10-2026')")
    for paper, n in [(old, 3), (new, 3)]:
        for i in range(n):
            add_question(db, type="verified_pyq", topic_id="computer.cyber_law", stem=f"Cyber q {paper}-{i}",
                         options=["a", "b", "c", "d"], answer_index=0, source_paper_id=paper)
    ids = engine._candidates(db, user, "computer.cyber_law", set(), set(), "en")
    sources = [db.one("SELECT source_paper_id FROM questions WHERE id = ?", (i,))[0] for i in ids]
    assert sources[:6] == [new] * 3 + [old] * 3


def test_uploaded_papers_stay_private(db, user):
    _, other = auth.signup(db, "Binu", "binu@example.com", "secret123")
    paper = db.execute("INSERT INTO papers (title, key_url, status, source, owner_user_id) "
                       "VALUES ('My notes', 'upload://x', 'done', 'upload', ?)", (user,))
    qid = add_question(db, type="uploaded", topic_id="computer.cyber_law", stem="Private upload question",
                       options=["a", "b", "c", "d"], answer_index=0, source_paper_id=paper)
    db.execute("INSERT INTO paper_questions (paper_id, qno, question_id) VALUES (?, 1, ?)", (paper, qid))
    assert qid in engine._candidates(db, user, "computer.cyber_law", set(), set(), "en")
    assert qid not in engine._candidates(db, other, "computer.cyber_law", set(), set(), "en")
    with pytest.raises(engine.TestError):
        engine.create_test(db, other, "paper", TODAY, paper_id=paper)
    assert engine.get_test(db, user, engine.create_test(db, user, "paper", TODAY, paper_id=paper))["question_count"] == 1


def test_students_language_comes_first_except_language_sections(db, user):
    add_question(db, type="original_mock", topic_id="history.kerala_history", stem="കേരള ചരിത്രം ചോദ്യം",
                 options=["a", "b", "c", "d"], answer_index=0)
    ids = engine._candidates(db, user, "history.kerala_history", set(), set(), "en")
    assert db.one("SELECT lang FROM questions WHERE id = ?", (ids[-1],))[0] == "ml"
    ids = engine._candidates(db, user, "history.kerala_history", set(), set(), "ml")
    assert db.one("SELECT lang FROM questions WHERE id = ?", (ids[0],))[0] == "ml"


def test_daily_test_marks_plan_done(db, user):
    test_id = engine.create_test(db, user, "daily", TODAY)
    answer_all(db, user, test_id, lambda q: q["answer_index"])
    today_items = [p for p in planner.week_plan(db, user, TODAY) if p["day"] == TODAY.isoformat()]
    assert next(p for p in today_items if p["kind"] == "daily_test")["done"]


def test_paper_test_follows_paper_links_and_skips_deleted(db, user):
    paper_id = db.execute("INSERT INTO papers (title, key_url, status) VALUES ('VFA', 'k', 'done')")
    existing = db.one("SELECT id FROM questions LIMIT 1")["id"]  # also in the bank from elsewhere
    links = [(1, existing)]
    for n, ans in [(2, 1), (3, None)]:
        qid = add_question(db, type="verified_pyq", topic_id="geography.kerala", stem=f"Paper question {n}",
                           options=["a", "b", "c", "d"], answer_index=ans, source_paper_id=paper_id, source_qno=n)
        links.append((n, qid))
    for n, qid in links:
        db.execute("INSERT INTO paper_questions (paper_id, qno, question_id) VALUES (?, ?, ?)", (paper_id, n, qid))
    test = engine.get_test(db, user, engine.create_test(db, user, "paper", TODAY, paper_id=paper_id))
    assert [q["id"] for q in test["questions"]] == [existing, links[1][1]]


def test_duplicate_questions_are_stored_once(db):
    a = add_question(db, type="original_mock", topic_id="geography.kerala", stem="Capital of Kerala?",
                     options=["Kochi", "Thiruvananthapuram", "Kozhikode", "Thrissur"], answer_index=1)
    b = add_question(db, type="verified_pyq", topic_id="geography.kerala", stem="capital of kerala ?",
                     options=["Thiruvananthapuram", "Kochi", "Thrissur", "Kozhikode"], answer_index=0)
    assert a == b
