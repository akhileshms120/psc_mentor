"""The Qwen adapter, with its HTTP client replaced by a fake, and the shared AI helpers."""

import json

import httpx
import pytest

from psc_mentor_server import ai, ai_qwen, config

TOOLS = [{"name": "create_test", "description": "Make a test",
          "schema": {"type": "object", "properties": {"type": {"type": "string"}},
                     "required": ["type"], "additionalProperties": False}}]


@pytest.mark.parametrize("env,expected", [
    ({}, False),
    ({"PSC_AI_BASE_URL": "https://qwen.test"}, False),
    ({"PSC_AI_API_KEY": "k"}, False),
    ({"PSC_AI_BASE_URL": "https://qwen.test", "PSC_AI_API_KEY": "k"}, True),
    ({"PSC_AI_BASE_URL": "https://qwen.test", "PSC_AI_API_KEY": "k", "PSC_AI": "off"}, False),
])
def test_ai_needs_both_the_address_and_the_key(monkeypatch, env, expected):
    for k in ["PSC_AI_BASE_URL", "PSC_AI_API_KEY", "PSC_AI"]:
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    assert config.ai_enabled() is expected


@pytest.mark.parametrize("url", ["https://qwen.test", "https://qwen.test/", "https://qwen.test/v1", "https://qwen.test/v1/"])
def test_base_url_works_with_or_without_v1(monkeypatch, url):
    monkeypatch.setenv("PSC_AI_BASE_URL", url)
    assert config.ai_base_url() == "https://qwen.test"


def test_shared_functions_use_qwen(monkeypatch):
    monkeypatch.setattr(ai, "ai_enabled", lambda: True)
    monkeypatch.setattr(ai_qwen, "json_call", lambda **kw: {"questions": [
        {"number": 1, "stem": "Q?", "options": ["a", "b", "c", "d"], "topic_id": "history.kerala_history",
         "explanation": "e", "answer_letter": "C"}]})
    tags = ai.tag_questions([{"number": 1, "stem": "Q?", "options": list("abcd"), "answer_index": None}], "cat", ["x"])
    assert tags[1]["ai_answer"] == 2 and tags[1]["topic_id"] == "history.kerala_history"
    monkeypatch.setattr(ai, "ai_enabled", lambda: False)
    with pytest.raises(ai.AIError, match="PSC_AI_API_KEY"):
        ai.tag_questions([], "cat", ["x"])


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

    def fake_json_call(system, parts, schema):
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

    def fake_json_call(system, parts, schema):
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


def test_printed_option_labels_are_removed():
    q = {"number": 1, "stem": "s", "options": ["(A) ബീഹാർ", "B) Gujarat", "C. Maharashtra", "Uttar Pradesh"]}
    assert ai._clean_questions([q], with_answer=False)[0]["options"] == ["ബീഹാർ", "Gujarat", "Maharashtra", "Uttar Pradesh"]


def sse(*chunks):
    return "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"


def fake_qwen(monkeypatch, replies, models=({"id": "qwen-test"}, {"id": "other"})):
    """Swap the AI HTTP client for one that lists `models`, returns `replies` in order and records requests."""
    sent = []

    def handler(request):
        if request.method == "GET":
            assert request.url.path == "/v1/models"
            sent.append("models")
            return httpx.Response(200, json={"data": list(models)})
        assert request.url.path == "/v1/chat/completions"
        sent.append(json.loads(request.content))
        status, body = replies.pop(0)
        if isinstance(body, str):
            return httpx.Response(status, text=body)
        if status != 200:
            return httpx.Response(status, json=body)
        choice = body["choices"][0]
        delta = {**choice["message"]}
        if "tool_calls" in delta:
            delta["tool_calls"] = [{**c, "index": i} for i, c in enumerate(delta["tool_calls"])]
        return httpx.Response(200, text=sse({"choices": [{"delta": delta, "finish_reason": choice["finish_reason"]}]}))

    monkeypatch.setenv("PSC_AI_BASE_URL", "https://qwen.test")
    monkeypatch.setattr(ai_qwen, "_model_id", None)
    monkeypatch.setattr(ai_qwen, "_get_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    return sent


def chat_reply(content=None, tool_calls=None, finish="stop"):
    msg = {"role": "assistant", "content": content}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    return (200, {"choices": [{"message": msg, "finish_reason": finish}]})


def test_qwen_json_call_sends_schema_images_and_the_listed_model(monkeypatch):
    sent = fake_qwen(monkeypatch, [chat_reply('{"questions": []}')])
    out = ai_qwen.json_call(system="sys", parts=["read", (b"png-bytes", "image/png")], schema={"type": "object"})
    assert out == {"questions": []}
    body = sent[1]
    assert body["model"] == "qwen-test" and body["stream"] is True
    assert body["response_format"]["json_schema"] == {"name": "result", "strict": True, "schema": {"type": "object"}}
    system, user = body["messages"]
    assert system == {"role": "system", "content": "sys"}
    assert user["content"][0] == {"type": "text", "text": "read"}
    assert user["content"][1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_qwen_reads_the_model_list_only_once(monkeypatch):
    sent = fake_qwen(monkeypatch, [chat_reply("{}"), chat_reply("{}")])
    ai_qwen.json_call(system="s", parts=["x"], schema={})
    ai_qwen.json_call(system="s", parts=["x"], schema={})
    assert sent.count("models") == 1 and len(sent) == 3


def test_qwen_without_a_model_is_a_clear_error(monkeypatch):
    fake_qwen(monkeypatch, [], models=())
    with pytest.raises(ai.AIError, match="no model"):
        ai_qwen.json_call(system="s", parts=["x"], schema={})


def test_qwen_mentor_runs_tools(monkeypatch):
    call = {"id": "call_1", "type": "function", "function": {"name": "create_test", "arguments": '{"type": "daily"}'}}
    sent = fake_qwen(monkeypatch, [chat_reply("", [call]), chat_reply("Your daily test is ready.")])
    ran = []
    reply = ai_qwen.run_mentor(system="teach", history=[{"role": "user", "content": "hi"},
                                                        {"role": "assistant", "content": "hello"}],
                               user_parts=["<ctx>", "test me"], tools=TOOLS,
                               run_tool=lambda n, a: ran.append((n, a)) or "made it")
    assert reply == "Your daily test is ready." and ran == [("create_test", {"type": "daily"})]
    second = sent[2]["messages"]
    assert [m["role"] for m in second] == ["system", "user", "assistant", "user", "assistant", "tool"]
    assert second[-1] == {"role": "tool", "tool_call_id": "call_1", "content": "made it"}
    assert sent[1]["tools"][0]["function"]["parameters"] == TOOLS[0]["schema"]
    assert sent[1]["model"] == "qwen-test"
    assert sent[1]["reasoning_effort"] == "none"


@pytest.mark.parametrize("status,body,match", [
    (401, {"error": {"code": 401, "message": "No auth"}}, "rejected the API key"),
    (503, {"error": {"code": 503, "message": "overloaded"}}, "busy"),
    (429, {"error": {"code": 429, "message": "slow down"}}, "busy"),
    (200, {"choices": [{"message": {"content": "{"}, "finish_reason": "length"}]}, "cut off"),
    (400, {"error": {"code": 400, "message": "bad schema"}}, "bad schema"),
    (524, "<html>A timeout occurred</html>", "busy"),
    (200, sse({"error": {"message": "model crashed"}}), "model crashed"),
    (200, "data: {not json\n\n", "garbled"),
    (200, sse({"choices": [{"delta": {"reasoning": "hmm"}, "finish_reason": "stop"}]}), "no answer"),
])
def test_qwen_errors_become_friendly_ai_errors(monkeypatch, status, body, match):
    fake_qwen(monkeypatch, [(status, body)])
    with pytest.raises(ai.AIError, match=match):
        ai_qwen.json_call(system="s", parts=["x"], schema={})


def test_qwen_joins_a_streamed_answer(monkeypatch):
    fake_qwen(monkeypatch, [(200, sse(
        {"choices": [{"delta": {"reasoning": "thinking..."}, "finish_reason": None}]},
        {"choices": [{"delta": {"content": '{"ok"'}, "finish_reason": None}]},
        {"choices": [{"delta": {"content": ': 1}'}, "finish_reason": "stop"}]},
    ))])
    assert ai_qwen.json_call(system="s", parts=["x"], schema={}) == {"ok": 1}


def test_qwen_joins_tool_calls_sent_in_pieces(monkeypatch):
    first = {"index": 0, "id": "call_1", "type": "function", "function": {"name": "create_test", "arguments": '{"ty'}}
    rest = {"index": 0, "function": {"arguments": 'pe": "daily"}'}}
    sent = fake_qwen(monkeypatch, [
        (200, sse({"choices": [{"delta": {"tool_calls": [first]}, "finish_reason": None}]},
                  {"choices": [{"delta": {"tool_calls": [rest]}, "finish_reason": "tool_calls"}]})),
        chat_reply("Done."),
    ])
    ran = []
    assert ai_qwen.run_mentor(system="s", history=[], user_parts=["go"], tools=TOOLS,
                              run_tool=lambda n, a: ran.append((n, a)) or "ok") == "Done."
    assert ran == [("create_test", {"type": "daily"})]
    assert sent[2]["messages"][-2]["tool_calls"][0]["function"]["arguments"] == '{"type": "daily"}'


def test_qwen_timeout_is_a_clear_error(monkeypatch):
    def handler(request):
        raise httpx.ReadTimeout("slow")

    monkeypatch.setenv("PSC_AI_BASE_URL", "https://qwen.test")
    monkeypatch.setattr(ai_qwen, "_model_id", "qwen-test")
    monkeypatch.setattr(ai_qwen, "_get_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(ai.AIError, match="too long"):
        ai_qwen.json_call(system="s", parts=["x"], schema={})


def test_foreign_letters_in_malayalam_are_flagged():
    assert ai.mixed_script({"stem": "മലയാള കലാമണ്ഡലം സ്ഥാപകന്‍?", "options": ["മッカー", "b", "c", "d"]})
    assert ai.mixed_script({"stem": "i, ii 모두", "options": ["ചോദ്യം"]})
    assert ai.mixed_script({"stem": "ചോദ്യം", "options": ["Griechenland", "Ελλάδα", "c", "d"]})
    assert not ai.mixed_script({"stem": "ഇന്ത്യയുടെ GDP വളർച്ച?", "options": ["RBI", "SEBI", "c", "d"]})


@pytest.mark.parametrize("content", [
    '{"questions": [{"n": 1}]}',
    '[{"n": 1}]',
    'Here you go:\n```json\n{"questions": [{"n": 1}]}\n```',
    'Sure! [{"n": 1}]',
])
def test_qwen_accepts_loosely_formatted_json(monkeypatch, content):
    fake_qwen(monkeypatch, [chat_reply(content)])
    schema = {"type": "object", "properties": {"questions": {"type": "array"}}, "required": ["questions"]}
    assert ai_qwen.json_call(system="s", parts=["x"], schema=schema) == {"questions": [{"n": 1}]}
