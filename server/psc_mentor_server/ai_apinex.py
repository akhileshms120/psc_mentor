"""OpenAI-compatible chat-completions backend for `ai` (APInex by default).

Any service with the OpenAI `/v1/chat/completions` API works: set PSC_AI_BASE_URL and the key.
JSON answers use `response_format: json_schema`, the mentor uses OpenAI-style tools, and page
images go as data URLs. If a model fails (overloaded, timed out), the next in the list is tried.
"""

import base64
import json
import re
from typing import Callable

import httpx

from .ai import AIError, Part
from .config import AI_BASE_URL, AI_FALLBACKS, AI_MODEL, AI_READER_MODELS, apinex_api_key

MAX_TOOL_ROUNDS = 4
TIMEOUT_SECONDS = 600       # reading a batch of paper pages can take minutes
CHAT_TIMEOUT_SECONDS = 120
MAX_TOKENS = 32768

_client: httpx.Client | None = None


def _get_client() -> httpx.Client:
    global _client
    if _client is None:
        _client = httpx.Client(timeout=TIMEOUT_SECONDS, headers={"Authorization": f"Bearer {apinex_api_key()}"})
    return _client


def _content(part: Part) -> dict:
    if isinstance(part, str):
        return {"type": "text", "text": part}
    data, media_type = part
    url = f"data:{media_type};base64,{base64.standard_b64encode(data).decode()}"
    if media_type == "application/pdf":
        return {"type": "file", "file": {"filename": "paper.pdf", "file_data": url}}
    return {"type": "image_url", "image_url": {"url": url}}


def _models(task: str) -> list[str]:
    chain = AI_READER_MODELS if task == "read_paper" else [AI_MODEL] + AI_FALLBACKS
    return list(dict.fromkeys(chain))


class _TryNext(AIError):
    """This model failed in a way another model might not (overloaded, timed out, server error)."""


def _post_one(body: dict, timeout: float) -> dict:
    try:
        resp = _get_client().post(f"{AI_BASE_URL}/chat/completions", json=body, timeout=timeout)
    except httpx.TimeoutException as e:
        raise _TryNext("The AI took too long to answer; try again.") from e
    except httpx.HTTPError as e:
        raise AIError("Could not reach the AI service.") from e
    try:
        data = resp.json()
    except ValueError:
        data = {}
    error = data.get("error") if isinstance(data, dict) else None
    if resp.status_code != 200 or error:
        message = (error or {}).get("message") if isinstance(error, dict) else None
        code = resp.status_code if resp.status_code != 200 else (error or {}).get("code")
        if code == 401:
            raise AIError("The AI service rejected the API key.")
        if code == 402:
            raise AIError("The AI account is out of credits.")
        if code in (429, 500, 502, 503, 504) or (isinstance(code, int) and code >= 500):
            raise _TryNext(f"The AI service is busy (error {code}); try again in a minute.")
        raise AIError(f"AI service error {code}: {message or resp.text[:200]}")
    if not data.get("choices"):
        raise _TryNext("The AI returned no answer.")
    choice = data["choices"][0]
    if choice.get("finish_reason") == "length":
        raise AIError("The AI's answer was cut off; try a smaller request.")
    if choice.get("finish_reason") == "content_filter":
        raise AIError("The AI declined this request.")
    return choice["message"]


def _post(body: dict, timeout: float, task: str) -> dict:
    last: AIError | None = None
    for model in _models(task):
        try:
            return _post_one({**body, "model": model}, timeout)
        except _TryNext as e:
            last = e
    raise last or AIError("No AI model is configured.")


def json_call(*, system: str, parts: list[Part], schema: dict, effort: str, task: str = "general") -> dict:
    message = _post({
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": [_content(p) for p in parts]}],
        "response_format": {"type": "json_schema",
                            "json_schema": {"name": "result", "strict": True, "schema": schema}},
        "max_tokens": MAX_TOKENS,
        "temperature": 0.2,
    }, TIMEOUT_SECONDS, task)
    return _parse_json(message.get("content") or "", schema)


def _parse_json(text: str, schema: dict):
    """Not every model behind an OpenAI-style API honours `json_schema` exactly: accept JSON in
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
        message = _post({"messages": messages, "tools": chat_tools, "max_tokens": 8192},
                        CHAT_TIMEOUT_SECONDS, "general")
        # Pass the assistant turn back as returned: it may carry reasoning details the model needs.
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
