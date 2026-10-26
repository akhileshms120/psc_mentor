"""The Claude-backed flows, with Claude replaced by canned responses."""

from types import SimpleNamespace

import pytest

from psc_mentor_server import ai, auth, engine, importer, mentor, psc_source

from .conftest import FIXTURES, TODAY


def text(t):
    return SimpleNamespace(type="text", text=t)


def tool(name, args, id="call_1"):
    return SimpleNamespace(type="tool_use", id=id, name=name, input=args)


def test_mentor_runs_tools_and_links_the_created_test(db, user, monkeypatch):
    calls = []

    def fake_chat(system, messages, tools):
        calls.append(list(messages))
        if len(calls) == 1:
            return SimpleNamespace(stop_reason="tool_use", content=[
                text("Let's check that."), tool("create_test", {"type": "topic", "topic_id": "english.verbs_tenses"})])
        return SimpleNamespace(stop_reason="end_turn", content=[text("Your tenses test is ready.")])

    monkeypatch.setattr(ai, "chat", fake_chat)
    reply = mentor.chat(db, user, "Test me on tenses", TODAY)

    assert reply["reply"].endswith("Your tenses test is ready.")
    assert "Tenses" in reply["tests"][0]["title"]
    context, question = calls[0][-1]["content"]
    assert "<student_context>" in context["text"] and '"strength_report"' in context["text"]
    assert question["text"] == "Test me on tenses"
    tool_result = calls[1][-1]["content"][0]
    assert tool_result["type"] == "tool_result" and '"created": true' in tool_result["content"]
    history = mentor.history(db, user)
    assert [m["role"] for m in history] == ["user", "assistant"]
    assert history[1]["test_id"] == reply["tests"][0]["id"]


def test_mentor_history_is_per_user_plain_text(db, user, monkeypatch):
    _, other = auth.signup(db, "Binu", "binu@example.com", "secret123")
    seen = []
    monkeypatch.setattr(ai, "chat", lambda s, m, t: seen.append(list(m)) or SimpleNamespace(
        stop_reason="end_turn", content=[text("ok")]))
    mentor.chat(db, user, "first", TODAY)
    mentor.chat(db, user, "second", TODAY)
    mentor.chat(db, other, "hello", TODAY)
    assert seen[1][0] == {"role": "user", "content": "first"}
    assert seen[1][1] == {"role": "assistant", "content": "ok"}
    assert len(seen[2]) == 1  # Binu doesn't see Anu's conversation
    assert len(mentor.history(db, other)) == 2


@pytest.fixture
def ai_on(monkeypatch, tmp_path):
    monkeypatch.setattr(importer, "ai_enabled", lambda: True)
    monkeypatch.setattr(importer, "PAPERS_DIR", tmp_path)


ML_QUESTION = {"number": 1, "stem": "കേരളത്തിലെ ഏറ്റവും നീളം കൂടിയ നദി?",
               "options": ["ഭാരതപ്പുഴ", "പെരിയാർ", "പമ്പ", "ചാലിയാർ"],
               "topic_id": "geography.kerala", "explanation": "പെരിയാർ", "claude_answer": 3}


def test_official_malayalam_paper_goes_to_claude_and_uses_only_the_official_key(db, ai_on, monkeypatch):
    key_pdf = (FIXTURES / "pKey-92-26-M.pdf").read_bytes()
    garbled = (FIXTURES / "paper_092_2026_M.txt").read_text()
    real_pdf_text = psc_source.pdf_text
    monkeypatch.setattr(psc_source, "fetch_pdf", lambda url: key_pdf if "Key" in url else b"%PDF-paper")
    monkeypatch.setattr(psc_source, "pdf_text", lambda d: garbled if d == b"%PDF-paper" else real_pdf_text(d))
    seen = {}

    def fake_extract(files, answers, catalog, topic_ids, key_files=None):
        seen["answers"], seen["key_files"] = answers, key_files
        return [dict(ML_QUESTION)]

    monkeypatch.setattr(ai, "extract_paper", fake_extract)
    paper_id = importer.queue_paper(db, {
        "title": "VILLAGE FIELD ASSISTANT", "key_url": "https://www.keralapsc.gov.in/pKey.pdf",
        "question_url": "https://www.keralapsc.gov.in/qn-092-2026-M-A.pdf", "key_type": "Final Answer Key"})
    importer.import_paper(db, paper_id)

    paper = db.one("SELECT * FROM papers WHERE id = ?", (paper_id,))
    assert paper["status"] == "done", paper["error"]
    assert paper["level"] == "general" and paper["answer_source"] == "official_key"
    assert len(seen["answers"]) == 100 and seen["key_files"] is None
    q = db.one("SELECT q.* FROM paper_questions pq JOIN questions q ON q.id = pq.question_id WHERE pq.paper_id = ?",
               (paper_id,))
    assert q["answer_index"] == 1  # the official key's B, not Claude's D
    assert q["verification"] == "final_key" and q["type"] == "verified_pyq" and q["lang"] == "ml"


def _upload(db, user, files, keys, booklet="A"):
    paper_id = importer.queue_upload(db, user, "Coaching mock")
    importer.import_upload(db, paper_id, files, keys, booklet)
    paper = db.one("SELECT * FROM papers WHERE id = ?", (paper_id,))
    assert paper["status"] == "done", paper["error"]
    return paper, db.query("SELECT q.* FROM paper_questions pq JOIN questions q ON q.id = pq.question_id "
                           "WHERE pq.paper_id = ? ORDER BY pq.qno", (paper_id,))


def test_upload_text_pdf_with_text_key_needs_no_claude(db, user, fixture_text, monkeypatch, tmp_path):
    monkeypatch.setattr(importer, "PAPERS_DIR", tmp_path)
    paper_text = fixture_text("paper_090_2026_A.txt")
    key_pdf = (FIXTURES / "pKey-92-26-M.pdf").read_bytes()
    real_pdf_text = psc_source.pdf_text
    monkeypatch.setattr(psc_source, "pdf_text", lambda d: paper_text if d == b"%PDF-paper" else real_pdf_text(d))
    paper, questions = _upload(db, user, [(b"%PDF-paper", "application/pdf")], [(key_pdf, "application/pdf")])
    assert paper["answer_source"] == "uploaded_key" and len(questions) == 100
    assert questions[0]["answer_index"] == 1 and questions[0]["type"] == "uploaded"
    assert questions[0]["topic_id"] == "special.technical"  # untagged without Claude


def test_upload_photos_with_photo_key_lets_claude_read_both(db, user, ai_on, monkeypatch):
    seen = {}

    def fake_extract(files, answers, catalog, topic_ids, key_files=None):
        seen.update(files=files, answers=answers, key_files=key_files)
        return [dict(ML_QUESTION)]

    monkeypatch.setattr(ai, "extract_paper", fake_extract)
    pages = [(b"jpg1", "image/jpeg"), (b"jpg2", "image/jpeg")]
    key = [(b"keyjpg", "image/png")]
    paper, questions = _upload(db, user, pages, key)
    assert seen["files"] == pages and seen["key_files"] == key and seen["answers"] == {}
    assert paper["answer_source"] == "ai_read_key"
    assert questions[0]["answer_index"] == 3 and questions[0]["verification"] == "ai_read_key"


def test_upload_without_key_is_solved_by_claude(db, user, ai_on, monkeypatch):
    monkeypatch.setattr(ai, "extract_paper", lambda files, answers, c, t, key_files=None: [dict(ML_QUESTION)])
    paper, questions = _upload(db, user, [(b"jpg", "image/jpeg")], [])
    assert paper["answer_source"] == "ai_solved" and questions[0]["answer_index"] == 3


def test_upload_without_key_or_ai_explains_what_to_do(db, user, monkeypatch, tmp_path):
    monkeypatch.setattr(importer, "PAPERS_DIR", tmp_path)
    paper_id = importer.queue_upload(db, user, "x")
    importer.import_upload(db, paper_id, [(b"%PDF-1.4", "application/pdf")], [])
    paper = db.one("SELECT * FROM papers WHERE id = ?", (paper_id,))
    assert paper["status"] == "failed" and "answer key" in paper["error"]


def test_test_shortfall_is_filled_by_generated_questions(db, user, monkeypatch):
    monkeypatch.setattr(engine, "ai_enabled", lambda: True)
    requested = {}

    def fake_generate(requests, examples, language, catalog, topic_ids):
        requested["r"] = requests
        return [{"number": i, "stem": f"Generated budget question {i}", "options": ["a", "b", "c", "d"],
                 "answer_index": 0, "topic_id": "economics.finance", "explanation": "x", "difficulty": 2}
                for i in range(requests[0]["count"])]

    monkeypatch.setattr(ai, "generate_questions", fake_generate)
    test = engine.get_test(db, user, engine.create_test(db, user, "topic", TODAY, topic_id="economics.finance"))
    assert requested["r"] == [{"topic_id": "economics.finance", "topic": "RBI, budget, taxes & fiscal policy",
                               "count": 18}]
    assert sum(q["topic_id"] == "economics.finance" for q in test["questions"]) == 20
    assert db.one("SELECT COUNT(*) AS n FROM questions WHERE verification = 'ai_generated'")["n"] == 18


def test_ai_failure_falls_back_to_the_bank(db, user, monkeypatch):
    monkeypatch.setattr(engine, "ai_enabled", lambda: True)

    def boom(*a, **k):
        raise ai.AIError("rate limited")

    monkeypatch.setattr(ai, "generate_questions", boom)
    test = engine.get_test(db, user, engine.create_test(db, user, "topic", TODAY, topic_id="economics.finance"))
    assert test["question_count"] == 20
