"""The Gemini and Claude adapters, with each SDK client replaced by a fake."""

import json
from types import SimpleNamespace

import pytest
from google.genai import types

from psc_mentor_server import ai, ai_claude, ai_gemini, config

TOOLS = [{"name": "create_test", "description": "Make a test",
          "schema": {"type": "object", "properties": {"type": {"type": "string"}},
                     "required": ["type"], "additionalProperties": False}}]


@pytest.mark.parametrize("env,expected", [
    ({}, None),
    ({"GEMINI_API_KEY": "g"}, "gemini"),
    ({"GOOGLE_API_KEY": "g", "ANTHROPIC_API_KEY": "a"}, "gemini"),
    ({"ANTHROPIC_API_KEY": "a"}, "claude"),
    ({"GEMINI_API_KEY": "g", "PSC_AI_PROVIDER": "claude"}, "claude"),
    ({"GEMINI_API_KEY": "g", "PSC_AI": "off"}, None),
])
def test_provider_choice(monkeypatch, tmp_path, env, expected):
    for k in ["GEMINI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "PSC_AI_PROVIDER", "PSC_AI"]:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(config.Path, "home", lambda: tmp_path)  # no `ant` login profile
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    assert config.ai_provider() == expected


def gemini_response(text=None, calls=None, content="model-turn", finish=types.FinishReason.STOP):
    return SimpleNamespace(text=text, function_calls=calls,
                           candidates=[SimpleNamespace(content=content, finish_reason=finish)], prompt_feedback=None)


class FakeGemini:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []
        self.models = self

    def generate_content(self, model, contents, config):
        self.calls.append((model, list(contents), config))
        return self.responses.pop(0)


def test_gemini_json_call_sends_files_and_schema(monkeypatch):
    fake = FakeGemini([gemini_response(text=json.dumps({"questions": []}))])
    monkeypatch.setattr(ai_gemini, "_get_client", lambda: fake)
    out = ai_gemini.json_call(system="sys", parts=["read this", (b"%PDF", "application/pdf")],
                              schema={"type": "object"}, effort="medium")
    assert out == {"questions": []}
    model, contents, cfg = fake.calls[0]
    assert model == config.GEMINI_MODEL
    assert cfg.response_mime_type == "application/json" and cfg.response_json_schema == {"type": "object"}
    parts = contents[0].parts
    assert parts[0].text == "read this" and parts[1].inline_data.mime_type == "application/pdf"


def test_gemini_mentor_runs_tools_and_keeps_the_model_turn(monkeypatch):
    fake = FakeGemini([
        gemini_response(calls=[SimpleNamespace(name="create_test", args={"type": "daily"})], content="turn-1"),
        gemini_response(text="Here is your daily test.", content="turn-2"),
    ])
    monkeypatch.setattr(ai_gemini, "_get_client", lambda: fake)
    ran = []
    reply = ai_gemini.run_mentor(
        system="be a teacher", history=[{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}],
        user_parts=["<ctx>", "test me"], tools=TOOLS, run_tool=lambda n, a: ran.append((n, a)) or "made it")
    assert reply == "Here is your daily test."
    assert ran == [("create_test", {"type": "daily"})]
    _, second_contents, cfg = fake.calls[1]
    assert [c.role if hasattr(c, "role") else c for c in second_contents[:3]] == ["user", "model", "user"]
    assert second_contents[3] == "turn-1"  # the model's own turn, passed back unchanged
    response_part = second_contents[4].parts[0].function_response
    assert response_part.name == "create_test" and response_part.response == {"result": "made it"}
    assert cfg.automatic_function_calling.disable is True
    assert cfg.tools[0].function_declarations[0].parameters_json_schema == TOOLS[0]["schema"]


def test_gemini_errors_become_friendly_ai_errors(monkeypatch):
    from google.genai import errors

    class Quota:
        models = None

        def __init__(self):
            self.models = self

        def generate_content(self, **kw):
            raise errors.ClientError(429, {"error": {"code": 429, "message": "quota", "status": "RESOURCE_EXHAUSTED"}})

    monkeypatch.setattr(ai_gemini, "_get_client", Quota)
    with pytest.raises(ai.AIError, match="quota"):
        ai_gemini.json_call(system="s", parts=["x"], schema={}, effort="low")
    fake = FakeGemini([gemini_response(text="{}", finish=types.FinishReason.MAX_TOKENS)])
    monkeypatch.setattr(ai_gemini, "_get_client", lambda: fake)
    with pytest.raises(ai.AIError, match="cut off"):
        ai_gemini.json_call(system="s", parts=["x"], schema={}, effort="low")


def test_claude_mentor_runs_tools(monkeypatch):
    replies = [
        SimpleNamespace(stop_reason="tool_use", content=[
            SimpleNamespace(type="tool_use", id="t1", name="create_test", input={"type": "daily"})]),
        SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text="Done.")]),
    ]
    sent = []
    monkeypatch.setattr(ai_claude, "_call", lambda **kw: sent.append(kw) or replies.pop(0))
    reply = ai_claude.run_mentor(system="s", history=[], user_parts=["ctx", "go"], tools=TOOLS,
                                 run_tool=lambda n, a: "ok")
    assert reply == "Done."
    assert sent[0]["tools"][0]["strict"] is True and sent[0]["tools"][0]["input_schema"] == TOOLS[0]["schema"]
    tool_turn = next(m for m in sent[1]["messages"] if m["role"] == "user" and m["content"][0].get("type") == "tool_result")
    assert tool_turn["content"][0] == {"type": "tool_result", "tool_use_id": "t1", "content": "ok"}


def test_shared_functions_use_the_active_provider(monkeypatch):
    monkeypatch.setattr(ai, "ai_provider", lambda: "gemini")
    monkeypatch.setattr(ai_gemini, "json_call", lambda **kw: {"questions": [
        {"number": 1, "stem": "Q?", "options": ["a", "b", "c", "d"], "topic_id": "history.kerala_history",
         "explanation": "e", "answer_letter": "C"}]})
    tags = ai.tag_questions([{"number": 1, "stem": "Q?", "options": list("abcd"), "answer_index": None}], "cat", ["x"])
    assert tags[1]["claude_answer"] == 2 and tags[1]["topic_id"] == "history.kerala_history"
    monkeypatch.setattr(ai, "ai_provider", lambda: None)
    with pytest.raises(ai.AIError, match="GEMINI_API_KEY"):
        ai.tag_questions([], "cat", ["x"])


def test_gemini_retries_then_falls_back_when_overloaded(monkeypatch):
    from google.genai import errors
    monkeypatch.setattr(ai_gemini, "RETRY_DELAY_SECONDS", 0)
    attempts = []

    class Flaky:
        def __init__(self):
            self.models = self

        def generate_content(self, **kw):
            attempts.append(kw["model"])
            if len(attempts) < 3:
                raise errors.ServerError(503, {"error": {"code": 503, "message": "overloaded", "status": "UNAVAILABLE"}})
            return gemini_response(text='{"ok": true}')

    monkeypatch.setattr(ai_gemini, "_get_client", lambda: Flaky())
    assert ai_gemini.json_call(system="s", parts=["x"], schema={}, effort="low") == {"ok": True}
    # main model twice, then the first fallback
    assert attempts == [config.GEMINI_MODEL, config.GEMINI_MODEL, config.GEMINI_FALLBACKS[0]]


def test_mixed_script_malayalam_is_detected():
    assert ai.mixed_script({"stem": "പ്രാർത്ഥനാ সমাজം", "options": []})
    assert ai.mixed_script({"stem": "ചോദ്യം", "options": ["आकाशം", "b", "c", "d"]})
    assert not ai.mixed_script({"stem": "ശരിയായ ജോഡി ഏതാണ്?", "options": ["a", "b", "c", "d"]})
    assert not ai.mixed_script({"stem": "Which is correct?", "options": ["a", "b", "c", "d"]})


def test_extract_paper_rereads_only_mixed_script_questions(monkeypatch):
    def q(n, stem, letter="A"):
        return {"number": n, "stem": stem, "options": ["ഒന്ന്", "രണ്ട്", "മൂന്ന്", "നാല്"],
                "topic_id": "history.kerala_renaissance", "explanation": "x", "answer_letter": letter}
    calls = []

    def fake_json_call(system, parts, schema, effort, task="general"):
        calls.append(parts)
        if len(calls) == 1:
            return {"questions": [q(1, "പ്രാർത്ഥനാ সমাজം"), q(2, "വൈക്കം സത്യഗ്രഹം")]}
        return {"questions": [q(1, "പ്രാർത്ഥനാ സമാജം")]}

    monkeypatch.setattr(ai, "_json_call", fake_json_call)
    out = ai.extract_paper([(b"page-photo", "image/png")], {1: 0, 2: 0}, "cat", ["x"])
    assert [x["stem"] for x in out] == ["പ്രാർത്ഥനാ സമാജം", "വൈക്കം സത്യഗ്രഹം"]
    assert len(calls) == 2 and calls[1][0] == (b"page-photo", "image/png")
    assert '"number": 1' in calls[1][-1] and '"number": 2' not in calls[1][-1]


def test_pdf_pages_render_as_png():
    from psc_mentor_server.pdf_pages import as_page_images
    from .conftest import FIXTURES
    pages = as_page_images([((FIXTURES / "pKey-92-26-M.pdf").read_bytes(), "application/pdf"), (b"jpg", "image/jpeg")])
    assert len(pages) == 2
    assert pages[0][1] == "image/png" and pages[0][0].startswith(b"\x89PNG") and pages[1] == (b"jpg", "image/jpeg")


def test_extract_paper_reads_pages_in_overlapping_batches(monkeypatch):
    from psc_mentor_server import pdf_pages
    pages = [(f"p{i}".encode(), "image/png") for i in range(1, 21)]
    monkeypatch.setattr(pdf_pages, "as_page_images", lambda files: pages if files else [])
    sent = []

    def fake_json_call(system, parts, schema, effort, task="general"):
        images = [p[0].decode() for p in parts if isinstance(p, tuple)]
        sent.append(images)
        first = int(images[0][1:])
        # question 1 of each batch; the batch's overlap page yields a cut-off copy of the next one
        full = {"number": first, "stem": f"Question from page {first}", "options": ["a", "b", "c", "d"],
                "topic_id": "x", "explanation": "e", "answer_letter": "A"}
        return {"questions": [full]}

    monkeypatch.setattr(ai, "_json_call", fake_json_call)
    out = ai.extract_paper([(b"%PDF", "application/pdf")], {1: 0}, "cat", ["x"])
    assert sent == [[f"p{i}" for i in range(1, 10)], [f"p{i}" for i in range(9, 18)], [f"p{i}" for i in range(17, 21)]]
    assert [q["number"] for q in out] == [1, 9, 17]


def test_extract_paper_keeps_the_fuller_copy_of_a_question_split_across_batches(monkeypatch):
    from psc_mentor_server import pdf_pages
    monkeypatch.setattr(pdf_pages, "as_page_images", lambda files: [(b"p", "image/png")] * 9 if files else [])
    replies = [
        {"questions": [{"number": 40, "stem": "Long question text here", "options": ["a1", "b1", "c1", "d1"],
                        "topic_id": "x", "explanation": "e", "answer_letter": "B"}]},
        {"questions": [{"number": 40, "stem": "Long", "options": ["a", "b", "c", "d"],
                        "topic_id": "x", "explanation": "e", "answer_letter": "B"}]},
    ]
    monkeypatch.setattr(ai, "_json_call", lambda *a, **k: replies.pop(0))
    out = ai.extract_paper([(b"%PDF", "application/pdf")], None, "cat", ["x"])
    assert out[0]["stem"] == "Long question text here"


def test_gemini_moves_to_the_next_model_when_one_is_out_of_quota(monkeypatch):
    from google.genai import errors
    tried = []

    class Quota:
        def __init__(self):
            self.models = self

        def generate_content(self, **kw):
            tried.append(kw["model"])
            if kw["model"] != config.GEMINI_FALLBACKS[-1]:
                raise errors.ClientError(429, {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED",
                                                         "message": "quota. Please retry in 22h40m13s."}})
            return gemini_response(text='{"ok": 1}')

    monkeypatch.setattr(ai_gemini, "_get_client", lambda: Quota())
    assert ai_gemini.json_call(system="s", parts=["x"], schema={}, effort="low") == {"ok": 1}
    assert tried == [config.GEMINI_MODEL] + config.GEMINI_FALLBACKS  # main model only once on 429

    class AllOut(Quota):
        def generate_content(self, **kw):
            raise errors.ClientError(429, {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED",
                                                     "message": "quota. Please retry in 22h40m13s."}})

    monkeypatch.setattr(ai_gemini, "_get_client", lambda: AllOut())
    with pytest.raises(ai.AIError, match="resets in about 22 h 40 min"):
        ai_gemini.json_call(system="s", parts=["x"], schema={}, effort="low")


def test_paper_reading_never_uses_lite_models(monkeypatch):
    tried = []

    class Fake:
        def __init__(self):
            self.models = self

        def generate_content(self, **kw):
            tried.append(kw["model"])
            return gemini_response(text='{"questions": []}')

    monkeypatch.setattr(ai_gemini, "_get_client", lambda: Fake())
    ai_gemini.json_call(system="s", parts=["x"], schema={}, effort="low", task="read_paper")
    assert tried == [config.GEMINI_READER_MODELS[0]]
    assert not any("lite" in m for m in config.GEMINI_READER_MODELS)


def test_printed_option_labels_are_removed():
    q = {"number": 1, "stem": "s", "options": ["(A) ബീഹാർ", "B) Gujarat", "C. Maharashtra", "Uttar Pradesh"]}
    assert ai._clean_questions([q], with_answer=False)[0]["options"] == ["ബീഹാർ", "Gujarat", "Maharashtra", "Uttar Pradesh"]
