"""Building, serving and scoring tests (per user)."""

import json
import random
from datetime import date, datetime

from . import ai, curriculum, planner
from .config import ai_enabled
from .db import Database
from .progress import apply_revisions, due_revision_ids, topic_stats, weak_topics
from .questions import add_question, get_questions, question_dict
from .syllabus import EXAM_MINUTES, EXAM_NAME, EXAM_QUESTIONS, NEGATIVE_MARK, all_topic_ids, topic_catalog

# type: (questions, minutes)
TEST_SIZES = {
    "topic": (20, 20),
    "daily": (15, 15),
    "weekly": (50, 40),
    "monthly": (EXAM_QUESTIONS, EXAM_MINUTES),
    "diagnostic": (EXAM_QUESTIONS, EXAM_MINUTES),
    "mistakes": (25, 25),
}
TEST_TITLES = {
    "topic": "Topic test",
    "daily": "Daily practice",
    "weekly": "Weekly test",
    "monthly": f"{EXAM_NAME} full mock",
    "diagnostic": f"{EXAM_NAME} diagnostic mock",
    "mistakes": "Mistake bank retest",
    "paper": "Previous paper",
}
PLAN_KIND = {"daily": "daily_test", "weekly": "weekly_test", "monthly": "monthly_mock",
             "mistakes": "revision"}
MAX_GENERATED_PER_TEST = 40


class TestError(ValueError):
    pass


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _spread(topics: list[str], total: int) -> dict[str, int]:
    """Split `total` questions as evenly as possible over `topics`, in order."""
    quota: dict[str, int] = {}
    if not topics:
        return quota
    for i in range(total):
        t = topics[i % len(topics)]
        quota[t] = quota.get(t, 0) + 1
    return quota


def _merge(*quotas: dict[str, int]) -> dict[str, int]:
    out: dict[str, int] = {}
    for q in quotas:
        for k, v in q.items():
            out[k] = out.get(k, 0) + v
    return out


def exam_quota(stats: list[dict], total: int = EXAM_QUESTIONS) -> dict[str, int]:
    """Exam-pattern questions per subject by marks; inside a subject, weakest topics first."""
    by_subject: dict[str, list[dict]] = {}
    weights: dict[str, int] = {}
    for s in stats:
        if s["weight"] > 0:
            by_subject.setdefault(s["subject_id"], []).append(s)
            weights[s["subject_id"]] = s["weight"]
    weight_sum = sum(weights.values())
    quota: dict[str, int] = {}
    assigned = 0
    subjects = list(by_subject)
    for i, subject in enumerate(subjects):
        n = total - assigned if i == len(subjects) - 1 else round(total * weights[subject] / weight_sum)
        assigned += n
        topics = sorted(by_subject[subject],
                        key=lambda s: (s["accuracy"] if s["accuracy"] is not None else 0.5))
        quota = _merge(quota, _spread([t["topic_id"] for t in topics], n))
    return quota


def _plan_topics(db: Database, user_id: int, today: date, only_today: bool) -> list[str]:
    plan = planner.week_plan(db, user_id, today)
    return list(dict.fromkeys(
        p["topic_id"] for p in plan
        if p["kind"] == "study" and (p["day"] == today.isoformat() if only_today else p["day"] <= today.isoformat())
    ))


def _candidate_rows(db: Database, user_id: int, topic_id: str | None = None) -> dict[str, list]:
    """Every answerable question this user may see, grouped by topic, in one query.

    One round trip matters on a hosted database: a 100-question mock touches ~45 topics.
    """
    rows = db.query(
        "SELECT q.id, q.topic_id, q.type, q.lang, p.level, p.uploaded_on, MAX(a.answered_at) AS last_seen "
        "FROM questions q LEFT JOIN papers p ON p.id = q.source_paper_id "
        "LEFT JOIN attempts a ON a.question_id = q.id AND a.user_id = ? "
        "WHERE q.answer_index IS NOT NULL AND (p.owner_user_id IS NULL OR p.owner_user_id = ?) "  # uploads stay private
        + ("AND q.topic_id = ? " if topic_id else "")
        + "GROUP BY q.id, q.topic_id, q.type, q.lang, p.level, p.uploaded_on",
        (user_id, user_id, topic_id) if topic_id else (user_id, user_id),
    )
    by_topic: dict[str, list] = {}
    for r in rows:
        by_topic.setdefault(r["topic_id"], []).append(r)
    return by_topic


def _rank(rows: list, topic_id: str, exclude: set[int], due: set[int], language: str) -> list[int]:
    """Unseen first, then due for revision; within those, the student's language, real
    PYQs from the newest degree-level papers, then everything else."""
    rows = [r for r in rows if r["id"] not in exclude]
    random.shuffle(rows)
    rows.sort(key=lambda r: (
        r["last_seen"] is not None,
        r["id"] not in due,
        r["last_seen"] or "",
        r["lang"] != language and not topic_id.startswith(("english.", "malayalam.")),
        r["type"] != "verified_pyq",
        r["level"] != "degree",
        _neg_date(r["uploaded_on"]),
    ))
    return [r["id"] for r in rows]


def _candidates(db: Database, user_id: int, topic_id: str, exclude: set[int], due: set[int],
                language: str) -> list[int]:
    return _rank(_candidate_rows(db, user_id, topic_id).get(topic_id, []), topic_id, exclude, due, language)


def _neg_date(uploaded_on: str | None) -> int:
    """Sort key putting the newest paper first; PSC lists dates as dd-mm-yyyy."""
    if not uploaded_on:
        return 0
    try:
        return -datetime.strptime(uploaded_on, "%d-%m-%Y").toordinal()
    except ValueError:
        return 0


def _generate(db: Database, shortfall: dict[str, int], language: str) -> None:
    requests = []
    names = {r["id"]: r["name"] for r in db.query("SELECT id, name FROM topics")}
    budget = MAX_GENERATED_PER_TEST
    for topic, n in shortfall.items():
        n = min(n, budget)
        if n <= 0:
            continue
        requests.append({"topic_id": topic, "topic": names.get(topic, topic), "count": n})
        budget -= n
    if not requests:
        return
    topics = [r["topic_id"] for r in requests]
    examples = db.query(
        f"SELECT q.stem, q.options_json FROM questions q JOIN papers p ON p.id = q.source_paper_id "
        f"WHERE q.type = 'verified_pyq' AND p.source = 'psc' AND q.topic_id IN ({','.join('?' * len(topics))}) "
        f"ORDER BY p.id DESC LIMIT 8",
        topics,
    )
    generated = ai.generate_questions(
        requests,
        [{"stem": e["stem"], "options": json.loads(e["options_json"])} for e in examples],
        language, topic_catalog(db), all_topic_ids(),
    )
    for q in generated:
        add_question(db, type="pyq_derived" if examples else "original_mock", topic_id=q["topic_id"],
                     stem=q["stem"], options=q["options"], answer_index=q["answer_index"],
                     explanation=q["explanation"], difficulty=q["difficulty"],
                     verification="ai_generated")


def _fill(db: Database, user_id: int, quota: dict[str, int], today: date, allow_generate: bool,
          language: str) -> list[int]:
    due = set(due_revision_ids(db, user_id, today, limit=1000))
    pool = _candidate_rows(db, user_id)
    chosen: list[int] = []
    taken: set[int] = set()

    def take(topic: str, n: int) -> int:
        got = _rank(pool.get(topic, []), topic, taken, due, language)[:n]
        chosen.extend(got)
        taken.update(got)
        return len(got)

    shortfall = {t: n - take(t, n) for t, n in quota.items()}
    shortfall = {t: n for t, n in shortfall.items() if n > 0}
    if shortfall and allow_generate and ai_enabled():
        try:
            _generate(db, shortfall, language)
            pool = _candidate_rows(db, user_id)
        except ai.AIError:
            pass  # fall back to whatever the bank has
        shortfall = {t: n - take(t, n) for t, n in shortfall.items()}
        shortfall = {t: n for t, n in shortfall.items() if n > 0}

    # Still short: borrow from the same subject first, then any general topic.
    for t in list(shortfall):
        subject = t.split(".")[0]
        for other in all_topic_ids():
            if shortfall[t] <= 0:
                break
            if other != t and other.startswith(subject + "."):
                shortfall[t] -= take(other, shortfall[t])
    missing = sum(n for n in shortfall.values() if n > 0)
    if missing:
        others = [t for t in pool if not t.startswith("special.")]
        random.shuffle(others)
        for topic in others:
            if missing <= 0:
                break
            missing -= take(topic, missing)
    return chosen


def create_test(db: Database, user_id: int, type: str, today: date, topic_id: str | None = None,
                paper_id: int | None = None, allow_generate: bool = True) -> int:
    profile = db.one("SELECT language FROM profiles WHERE user_id = ?", (user_id,))
    language = profile["language"]
    title = TEST_TITLES.get(type)
    if title is None:
        raise TestError(f"Unknown test type {type!r}")

    if type == "paper":
        paper = db.one("SELECT * FROM papers WHERE id = ? AND (owner_user_id IS NULL OR owner_user_id = ?)",
                       (paper_id, user_id))
        if not paper or paper["status"] != "done":
            raise TestError("Paper not found")
        ids = [r["question_id"] for r in db.query(
            "SELECT pq.question_id FROM paper_questions pq JOIN questions q ON q.id = pq.question_id "
            "WHERE pq.paper_id = ? AND q.answer_index IS NOT NULL ORDER BY pq.qno", (paper_id,))]
        suffix = paper["paper_code"] or paper["test_date"]
        title = f"{paper['title']} ({suffix})" if suffix else paper["title"]
        minutes = max(round(len(ids) * 0.75), 10)
    elif type == "mistakes":
        size, minutes = TEST_SIZES[type]
        ids = due_revision_ids(db, user_id, today, limit=size)
        if len(ids) < size:
            wrong = db.query(
                "SELECT question_id FROM attempts WHERE user_id = ? AND is_correct = 0 "
                "GROUP BY question_id ORDER BY MAX(answered_at) DESC LIMIT ?", (user_id, size))
            ids = list(dict.fromkeys(ids + [r["question_id"] for r in wrong]))[:size]
    else:
        size, minutes = TEST_SIZES[type]
        stats = topic_stats(db, user_id)
        weak = [w["topic_id"] for w in weak_topics(stats)]
        quota: dict[str, int] | None
        if type == "topic":
            row = db.one("SELECT name FROM topics WHERE id = ?", (topic_id,))
            if not row:
                raise TestError("Unknown topic")
            quota = {topic_id: size}
            title = f"{title}: {row['name']}"
        elif type == "daily":
            todays = _plan_topics(db, user_id, today, only_today=True) or weak[:2]
            revision = due_revision_ids(db, user_id, today, limit=size * 2 // 5)
            n_weak = min(3, len(weak))
            quota = _merge(_spread(todays, size - len(revision) - n_weak), _spread(weak[:3], n_weak))
            if not quota:
                quota = exam_quota(stats, size - len(revision))
            ids = _fill(db, user_id, quota, today, allow_generate, language)
            ids = list(dict.fromkeys(revision + ids))[:size]
            quota = None
        elif type == "weekly":
            studied = _plan_topics(db, user_id, today, only_today=False)
            n_weak = size * 3 // 10 if weak else 0
            quota = _merge(_spread(studied, size - n_weak), _spread(weak, n_weak))
            if not quota:
                quota = exam_quota(stats, size)
        else:  # monthly mock or diagnostic: the full exam pattern
            quota = exam_quota(stats, size)
        if quota is not None:
            ids = _fill(db, user_id, quota, today, allow_generate, language)
        if type not in ("monthly", "diagnostic"):
            random.shuffle(ids)
        else:
            ids = _exam_order(db, ids)

    if not ids:
        raise TestError("Not enough questions yet. Import a previous paper or enable AI generation.")
    return db.execute(
        "INSERT INTO tests (user_id, type, title, topic_id, paper_id, question_ids_json, duration_minutes, "
        "negative_mark, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (user_id, type, title, topic_id, paper_id, json.dumps(ids), minutes, NEGATIVE_MARK, _now()),
    )


def _exam_order(db: Database, ids: list[int]) -> list[int]:
    """Full mocks follow the paper's section order (GK, maths, English, Malayalam)."""
    if not ids:
        return ids
    rows = db.query(
        f"SELECT q.id, s.position FROM questions q JOIN topics t ON t.id = q.topic_id "
        f"JOIN subjects s ON s.id = t.subject_id WHERE q.id IN ({','.join('?' * len(ids))})", ids)
    position = {r["id"]: r["position"] for r in rows}
    random.shuffle(ids)
    return sorted(ids, key=lambda i: position.get(i, 99))


def _test_row(db: Database, user_id: int, test_id: int):
    row = db.one("SELECT * FROM tests WHERE id = ? AND user_id = ?", (test_id, user_id))
    if not row:
        raise TestError("Test not found")
    return row


def test_summary(row) -> dict:
    return {
        "id": row["id"], "type": row["type"], "title": row["title"], "topic_id": row["topic_id"],
        "paper_id": row["paper_id"], "question_count": len(json.loads(row["question_ids_json"])),
        "duration_minutes": row["duration_minutes"], "negative_mark": row["negative_mark"],
        "created_at": row["created_at"], "submitted_at": row["submitted_at"],
        "score": row["score"], "max_score": row["max_score"],
        "correct": row["correct"], "wrong": row["wrong"], "skipped": row["skipped"],
    }


def get_test(db: Database, user_id: int, test_id: int) -> dict:
    row = _test_row(db, user_id, test_id)
    submitted = row["submitted_at"] is not None
    data = test_summary(row)
    data["questions"] = [question_dict(q, reveal=submitted)
                         for q in get_questions(db, json.loads(row["question_ids_json"]))]
    return data


def score(answers: list[int | None], correct: list[int], negative: float) -> dict:
    right = sum(1 for a, c in zip(answers, correct) if a is not None and a == c)
    wrong = sum(1 for a, c in zip(answers, correct) if a is not None and a != c)
    skipped = sum(1 for a in answers if a is None)
    return {"correct": right, "wrong": wrong, "skipped": skipped,
            "score": round(right - wrong * negative, 2), "max_score": float(len(correct))}


def submit_test(db: Database, user_id: int, test_id: int, answers: dict[int, dict], today: date) -> dict:
    """answers: {question_id: {"selected": int | None, "time_ms": int | None}}"""
    row = _test_row(db, user_id, test_id)
    if row["submitted_at"]:
        raise TestError("Test already submitted")
    questions = get_questions(db, json.loads(row["question_ids_json"]))
    now = _now()
    selected, attempt_rows, answered = [], [], []
    for q in questions:
        given = answers.get(q["id"], {})
        sel = given.get("selected")
        sel = sel if sel in (0, 1, 2, 3) else None
        selected.append(sel)
        is_correct = None if sel is None else int(sel == q["answer_index"])
        attempt_rows.append((user_id, test_id, q["id"], sel, is_correct, given.get("time_ms"), now))
        if sel is not None:
            answered.append((q["id"], bool(is_correct)))
    db.executemany(
        "INSERT INTO attempts (user_id, test_id, question_id, selected_index, is_correct, time_ms, answered_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)", attempt_rows)
    apply_revisions(db, user_id, answered, today)
    result = score(selected, [q["answer_index"] for q in questions], row["negative_mark"])
    db.execute(
        "UPDATE tests SET submitted_at = ?, score = ?, max_score = ?, correct = ?, wrong = ?, skipped = ? "
        "WHERE id = ?",
        (now, result["score"], result["max_score"], result["correct"], result["wrong"],
         result["skipped"], test_id),
    )
    if row["type"] == "diagnostic":
        db.execute("UPDATE profiles SET diagnostic_test_id = ? WHERE user_id = ?", (test_id, user_id))
        curriculum.ensure_course(db, user_id, today, rebuild=True)  # now we know the weak sections
        planner.ensure_week(db, user_id, today, regenerate=True)
    elif row["type"] == "topic":
        planner.mark_done(db, user_id, today, "study", row["topic_id"])
    elif row["type"] in PLAN_KIND:
        planner.mark_done(db, user_id, today, PLAN_KIND[row["type"]])
    return get_result(db, user_id, test_id)


def get_result(db: Database, user_id: int, test_id: int) -> dict:
    row = _test_row(db, user_id, test_id)
    if not row["submitted_at"]:
        raise TestError("Test not submitted yet")
    data = test_summary(row)
    attempts = {a["question_id"]: a for a in db.query(
        "SELECT * FROM attempts WHERE test_id = ?", (test_id,))}
    topic_names = {r["id"]: r["name"] for r in db.query("SELECT id, name FROM topics")}
    questions, by_topic = [], {}
    for q in get_questions(db, json.loads(row["question_ids_json"])):
        qd = question_dict(q, reveal=True)
        a = attempts.get(q["id"])
        qd["selected_index"] = a["selected_index"] if a else None
        qd["topic"] = topic_names.get(q["topic_id"], q["topic_id"])
        questions.append(qd)
        t = by_topic.setdefault(q["topic_id"], {"topic_id": q["topic_id"], "topic": qd["topic"],
                                                "correct": 0, "wrong": 0, "skipped": 0})
        if qd["selected_index"] is None:
            t["skipped"] += 1
        elif qd["selected_index"] == qd["answer_index"]:
            t["correct"] += 1
        else:
            t["wrong"] += 1
    data["questions"] = questions
    data["topics"] = sorted(by_topic.values(), key=lambda t: t["correct"] - t["wrong"])
    return data


def list_tests(db: Database, user_id: int, limit: int = 50) -> list[dict]:
    return [test_summary(r) for r in db.query(
        "SELECT * FROM tests WHERE user_id = ? ORDER BY id DESC LIMIT ?", (user_id, limit))]
