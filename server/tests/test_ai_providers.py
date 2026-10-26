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

    def fake_json_call(system, parts, schema, effort):
        calls.append(parts)
        if len(calls) == 1:
            return {"questions": [q(1, "പ്രാർത്ഥനാ সমাজം"), q(2, "വൈക്കം സത്യഗ്രഹം")]}
        return {"questions": [q(1, "പ്രാർത്ഥനാ സമാജം")]}

    monkeypatch.setattr(ai, "_json_call", fake_json_call)
    out = ai.extract_paper([(b"%PDF", "application/pdf")], {1: 0, 2: 0}, "cat", ["x"])
    assert [x["stem"] for x in out] == ["പ്രാർത്ഥനാ സമാജം", "വൈക്കം സത്യഗ്രഹം"]
    assert len(calls) == 2 and calls[1][0] == (b"%PDF", "application/pdf")
    assert '"number": 1' in calls[1][-1] and '"number": 2' not in calls[1][-1]
