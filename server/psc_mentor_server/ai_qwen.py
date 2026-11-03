"""The Qwen backend for `ai`: a server with the OpenAI-style API at PSC_AI_BASE_URL.

The model is read from the server's /v1/models list. JSON answers use `response_format:
json_schema`, the mentor uses OpenAI-style tools, and page images go as data URLs.
"""

import base64
import json
import re
from contextlib import contextmanager
from typing import Callable

import httpx

from .ai import AIError, Part
from .config import ai_api_key, ai_base_url

MAX_TOOL_ROUNDS = 4
# How long to wait for the next piece of an answer, not for the whole answer.
TIMEOUT_SECONDS = 600
CHAT_TIMEOUT_SECONDS = 300
MODELS_TIMEOUT_SECONDS = 30
MAX_TOKENS = 32768

_client: httpx.Client | None = None
_model_id: str | None = None


def _get_client() -> httpx.Client:
    global _client
    if _client is None:
        _client = httpx.Client(timeout=TIMEOUT_SECONDS, headers={"Authorization": f"Bearer {ai_api_key()}"})
    return _client


def _content(part: Part) -> dict:
    if isinstance(part, str):
        return {"type": "text", "text": part}
    data, media_type = part
    url = f"data:{media_type};base64,{base64.standard_b64encode(data).decode()}"
    if media_type == "application/pdf":
        return {"type": "file", "file": {"filename": "paper.pdf", "file_data": url}}
    return {"type": "image_url", "image_url": {"url": url}}


@contextmanager
def _friendly_network_errors():
    try:
        yield
    except httpx.TimeoutException as e:
        raise AIError("The AI took too long to answer; try again.") from e
    except httpx.HTTPError as e:
        raise AIError("Could not reach the AI service.") from e


def _check(status: int, data, text: str = "") -> None:
    """Turn an error answer from the server into a friendly AIError."""
    error = data.get("error") if isinstance(data, dict) else None
    if status == 200 and not error:
        return
    message = error.get("message") if isinstance(error, dict) else error
    code = status if status != 200 else (error.get("code") if isinstance(error, dict) else None)
    if code == 401:
        raise AIError("The AI service rejected the API key.")
    if code == 429 or (isinstance(code, int) and code >= 500):
        raise AIError(f"The AI service is busy (error {code}); try again in a minute.")
    raise AIError(f"AI service error {code}: {message or text[:200]}")


def _checked_json(resp: httpx.Response) -> dict:
    try:
        data = resp.json()
    except ValueError:
        data = {}
    _check(resp.status_code, data, resp.text)
    return data


def _model() -> str:
    """The first model the server lists, remembered once it has been read."""
    global _model_id
    if _model_id is None:
        with _friendly_network_errors():
            resp = _get_client().get(f"{ai_base_url()}/v1/models", timeout=MODELS_TIMEOUT_SECONDS)
        models = _checked_json(resp).get("data")
        if not models:
            raise AIError("The AI service has no model available.")
        _model_id = models[0]["id"]
    return _model_id


def _post(body: dict, timeout: float) -> dict:
    """Send a chat request and return the whole assistant message. It is streamed even so: a
    Cloudflare tunnel drops a request after about 100 s without data (error 524)."""
    model = _model()
    text, calls, finish = "", {}, None
    with _friendly_network_errors():
        with _get_client().stream("POST", f"{ai_base_url()}/v1/chat/completions",
                                  json={**body, "model": model, "stream": True}, timeout=timeout) as resp:
            if resp.status_code != 200:
                resp.read()
                _checked_json(resp)
            for line in resp.iter_lines():
                if not line.startswith("data:"):
                    continue
                chunk = line[len("data:"):].strip()
                if chunk == "[DONE]":
                    break
                try:
                    data = json.loads(chunk)
                except json.JSONDecodeError as e:
                    raise AIError("The AI returned a garbled answer; try again.") from e
                _check(200, data)
                for choice in data.get("choices") or []:
                    delta = choice.get("delta") or {}
                    text += delta.get("content") or ""
                    for call in delta.get("tool_calls") or []:
                        slot = calls.setdefault(call.get("index", 0), {
                            "id": None, "type": "function", "function": {"name": "", "arguments": ""}})
                        slot["id"] = call.get("id") or slot["id"]
                        function = call.get("function") or {}
                        slot["function"]["name"] += function.get("name") or ""
                        slot["function"]["arguments"] += function.get("arguments") or ""
                    finish = choice.get("finish_reason") or finish
    if finish == "length":
        raise AIError("The AI's answer was cut off; try a smaller request.")
    if finish == "content_filter":
        raise AIError("The AI declined this request.")
    if not text and not calls:
        raise AIError("The AI returned no answer; try again.")
    message = {"role": "assistant", "content": text}
    if calls:
        message["tool_calls"] = [calls[i] for i in sorted(calls)]
    return message


def json_call(*, system: str, parts: list[Part], schema: dict) -> dict:
    message = _post({
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": [_content(p) for p in parts]}],
        "response_format": {"type": "json_schema",
                            "json_schema": {"name": "result", "strict": True, "schema": schema}},
        "max_tokens": MAX_TOKENS,
        "temperature": 0.2,
    }, TIMEOUT_SECONDS)
    return _parse_json(message.get("content") or "", schema)


def _parse_json(text: str, schema: dict):
    """Not every model honours `json_schema` exactly: accept JSON in
    ```json fences or after some prose, and a bare list where the schema wraps one list field."""
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = min((i for i in (text.find("{"), text.find("[")) if i >= 0), default=-1)
        try:
            data = json.loads(text[start:]) if start >= 0 else None
        except json.JSONDecodeError:
            data = None
        if data is None:
            raise AIError("The AI returned malformed JSON; try again.")
    props = schema.get("properties") or {}
    if isinstance(data, list) and len(props) == 1:
        (key, spec), = props.items()
        if spec.get("type") == "array":
            data = {key: data}
    return data


def run_mentor(*, system: str, history: list[dict], user_parts: list[str], tools: list[dict],
               run_tool: Callable[[str, dict], str]) -> str:
    messages: list[dict] = [{"role": "system", "content": system}]
    messages += [{"role": m["role"], "content": m["content"]} for m in history]
    messages.append({"role": "user", "content": [{"type": "text", "text": t} for t in user_parts]})
    chat_tools = [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                                  "parameters": t["schema"], "strict": True}} for t in tools]
    text = ""
    for _ in range(MAX_TOOL_ROUNDS):
        # No thinking first: a student is waiting, and in testing it took 51 s against 4 s for a one-word answer.
        message = _post({"messages": messages, "tools": chat_tools, "max_tokens": 8192, "reasoning_effort": "none"},
                        CHAT_TIMEOUT_SECONDS)
        messages.append(message)
        text = message.get("content") or text
        calls = message.get("tool_calls") or []
        if not calls:
            break
        for call in calls:
            try:
                args = json.loads(call["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                result = "Error: the tool arguments were not valid JSON."
            else:
                result = run_tool(call["function"]["name"], args)
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": result})
    return (text or "").strip()
