"""The AI mentor: a Kerala PSC teacher that sees the student's progress and can act on it."""

import json
from datetime import date

from . import ai, analysis, engine, planner
from .db import Database
from .progress import summary
from .syllabus import all_topic_ids

HISTORY_LIMIT = 20
MAX_TOOL_ROUNDS = 4

SYSTEM = """You are PSC Mentor, a personal teacher for a student preparing for the Kerala Public
Service Commission (Kerala PSC) Degree Level Common Preliminary exam: 100 questions in
75 minutes, 1/3 mark cut per wrong answer. Sections and marks: History 10, Geography 5,
Economics 5, Civics 5, Indian Constitution 5, Arts/Literature/Culture/Sports 10, Basics of
Computer 5, Science & Technology 5, Simple Arithmetic 10, Mental Ability 10, General
English 20, Malayalam 10. Current affairs is asked inside each section.

How you teach:
- Be warm, direct and practical, like a good coaching-centre teacher. Keep replies short
  enough to read on a phone. The app shows plain text, so write without Markdown
  (no headings, bold or tables); use simple "-" bullet lines when a list helps.
- Ground advice in the student's real numbers from <student_context>: the strength
  report (each section's status, accuracy, recommended weekly minutes and the marks they
  could gain), weak topics, the week's plan, recent scores and days left to the exam.
- Your goal is to make every section strong. Push hardest where the marks are: a weak
  20-mark section (English) or 10-mark section matters more than a weak 5-mark one.
  Remind the student to keep practising strong sections a little so they stay strong.
- If the student hasn't taken the diagnostic mock yet, encourage them to take it first.
- When explaining a concept, add the facts PSC likes to ask about it (years, firsts,
  places, articles), and a memory trick when one exists.
- When the student wants practice, create a test with the create_test tool instead of
  writing questions in chat. Use pyq_examples to show how PSC has actually asked a topic.
- If the student says the plan doesn't suit them, or their weak areas changed a lot,
  use replan_week.
- Reply in the language the student writes in. If they write Malayalam or Manglish,
  answer in Malayalam. The context says their preferred language.
- Be honest about uncertainty, especially for recent current affairs: say what you are
  unsure of and suggest checking an official source rather than guessing a fact."""

TOOLS = [
    {
        "name": "create_test",
        "description": "Create a practice test the student can start from the chat. "
                       "type: topic (needs topic_id), daily, weekly, monthly (full 100-question mock) "
                       "or mistakes (retest wrong answers). Use an empty topic_id unless type is topic.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": ["topic", "daily", "weekly", "monthly", "mistakes"]},
                "topic_id": {"type": "string", "enum": [""] + all_topic_ids()},
            },
            "required": ["type", "topic_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "pyq_examples",
        "description": "Fetch up to 5 real Kerala PSC previous-year questions (with official answers) "
                       "on a topic, to teach from.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"topic_id": {"type": "string", "enum": all_topic_ids()}},
            "required": ["topic_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "replan_week",
        "description": "Rebuild the rest of this week's study plan from the student's latest performance.",
        "strict": True,
        "input_schema": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
    },
]


def student_context(db: Database, user_id: int, today: date) -> str:
    student = dict(db.one(
        "SELECT u.name, p.* FROM users u JOIN profiles p ON p.user_id = u.id WHERE u.id = ?", (user_id,)))
    s = summary(db, user_id, today)
    report = analysis.report(db, user_id, today)
    plan = [p for p in planner.week_plan(db, user_id, today) if p["day"] == today.isoformat()]
    recent = db.query(
        "SELECT title, score, max_score, submitted_at FROM tests WHERE user_id = ? AND submitted_at IS NOT NULL "
        "ORDER BY id DESC LIMIT 5", (user_id,))
    days_left = None
    if student.get("exam_date"):
        days_left = (date.fromisoformat(student["exam_date"]) - today).days

    def pct(x):
        return None if x is None else round(x * 100)

    data = {
        "today": today.isoformat(),
        "student": {"name": student["name"], "target_exam": "Degree Level Preliminary",
                    "daily_minutes": student["daily_minutes"], "exam_date": student["exam_date"],
                    "days_to_exam": days_left,
                    "preferred_language": "Malayalam" if student["language"] == "ml" else "English"},
        "overall_accuracy_pct": pct(s["accuracy"]),
        "last_7_days": {"questions": s["week_attempts"], "accuracy_pct": pct(s["week_accuracy"])},
        "study_streak_days": s["streak_days"],
        "revision_due": s["revision_due"],
        "syllabus_coverage_pct": pct(s["syllabus_coverage"]),
        "weak_topics": [{"topic_id": w["topic_id"], "topic": w["topic"], "accuracy_pct": pct(w["accuracy"])}
                        for w in s["weak_topics"]],
        "diagnostic_taken": report["assessed"],
        "estimated_score_out_of_100": report["estimated_score"],
        "strength_report": [{"section": x["subject"], "marks": x["marks"], "status": x["status"],
                             "accuracy_pct": pct(x["accuracy"]), "weekly_minutes": x["weekly_minutes"],
                             "marks_to_gain": x["potential_gain"],
                             "weak_topics": [t["topic"] for t in x["weak_topics"]]}
                            for x in report["sections"]],
        "todays_plan": [{"kind": p["kind"], "topic": p["topic"], "minutes": p["minutes"], "done": p["done"]}
                        for p in plan],
        "recent_tests": [{"title": r["title"], "score": r["score"], "out_of": r["max_score"],
                          "on": r["submitted_at"][:10]} for r in recent],
    }
    return json.dumps(data, ensure_ascii=False)


def _run_tool(db: Database, user_id: int, today: date, name: str, args: dict, created: list[dict]) -> str:
    try:
        if name == "create_test":
            test_id = engine.create_test(db, user_id, args["type"], today, topic_id=args.get("topic_id") or None)
            test = engine.test_summary(db.one("SELECT * FROM tests WHERE id = ?", (test_id,)))
            created.append(test)
            return json.dumps({"created": True, "title": test["title"],
                               "questions": test["question_count"], "minutes": test["duration_minutes"]})
        if name == "pyq_examples":
            rows = db.query(
                "SELECT q.stem, q.options_json, q.answer_index, p.title, p.test_date FROM questions q "
                "LEFT JOIN papers p ON p.id = q.source_paper_id "
                "WHERE q.topic_id = ? AND q.type = 'verified_pyq' AND q.answer_index IS NOT NULL "
                "ORDER BY p.id DESC, RANDOM() LIMIT 5", (args["topic_id"],))
            if not rows:
                return "No previous-year questions imported for this topic yet."
            return json.dumps([{"question": r["stem"], "options": json.loads(r["options_json"]),
                                "answer": "ABCD"[r["answer_index"]], "exam": r["title"], "date": r["test_date"]}
                               for r in rows], ensure_ascii=False)
        if name == "replan_week":
            planner.ensure_week(db, user_id, today, regenerate=True)
            rest = [p for p in planner.week_plan(db, user_id, today) if p["day"] >= today.isoformat()]
            return json.dumps([{"day": p["day"], "kind": p["kind"], "topic": p["topic"]} for p in rest])
        return f"Unknown tool {name}"
    except engine.TestError as e:
        return f"Error: {e}"


def chat(db: Database, user_id: int, text: str, today: date) -> dict:
    history = list(reversed(db.query(
        "SELECT role, content FROM chat_messages WHERE user_id = ? ORDER BY id DESC LIMIT ?",
        (user_id, HISTORY_LIMIT))))
    messages = [{"role": r["role"], "content": r["content"]} for r in history]
    while messages and messages[0]["role"] != "user":
        messages.pop(0)
    messages.append({"role": "user", "content": [
        {"type": "text", "text": f"<student_context>\n{student_context(db, user_id, today)}\n</student_context>"},
        {"type": "text", "text": text},
    ]})

    created: list[dict] = []
    for _ in range(MAX_TOOL_ROUNDS):
        message = ai.chat(SYSTEM, messages, TOOLS)
        messages.append({"role": "assistant", "content": message.content})
        if message.stop_reason != "tool_use":
            break
        results = [
            {"type": "tool_result", "tool_use_id": b.id,
             "content": _run_tool(db, user_id, today, b.name, b.input, created)}
            for b in message.content if b.type == "tool_use"
        ]
        messages.append({"role": "user", "content": results})

    reply = "\n\n".join(b.text for b in message.content if b.type == "text").strip()
    if not reply:
        reply = "I've set that up for you." if created else "Sorry, I couldn't come up with an answer."
    db.execute("INSERT INTO chat_messages (user_id, role, content) VALUES (?, 'user', ?)", (user_id, text))
    db.execute("INSERT INTO chat_messages (user_id, role, content, test_id) VALUES (?, 'assistant', ?, ?)",
               (user_id, reply, created[-1]["id"] if created else None))
    return {"reply": reply, "tests": created}


def history(db: Database, user_id: int, limit: int = 50) -> list[dict]:
    rows = db.query("SELECT * FROM chat_messages WHERE user_id = ? ORDER BY id DESC LIMIT ?", (user_id, limit))
    return [{"id": r["id"], "role": r["role"], "content": r["content"], "test_id": r["test_id"],
             "created_at": r["created_at"]} for r in reversed(rows)]
