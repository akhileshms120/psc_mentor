"""OpenRouter backend for `ai` (used when OPENROUTER_API_KEY is set).

OpenRouter is OpenAI-compatible and routes one request to many providers' models. We send
`models` (a fallback list OpenRouter tries in order) and `provider.require_parameters`, so a
request only goes to providers that support JSON schemas / tools.
"""

import base64
import json
from typing import Callable

import httpx

from .ai import AIError, Part
from .config import (OPENROUTER_FALLBACKS, OPENROUTER_FREE_MODELS, OPENROUTER_MODEL, OPENROUTER_READER_MODELS,
                     openrouter_api_key)

API = "https://openrouter.ai/api/v1/chat/completions"
MAX_TOOL_ROUNDS = 4
TIMEOUT_SECONDS = 600       # reading a batch of paper pages can take minutes
CHAT_TIMEOUT_SECONDS = 90
MAX_TOKENS = 32768

_client: httpx.Client | None = None


def _get_client() -> httpx.Client:
    global _client
    if _client is None:
        _client = httpx.Client(timeout=TIMEOUT_SECONDS, headers={
            "Authorization": f"Bearer {openrouter_api_key()}",
            "X-Title": "PSC Mentor",
            "HTTP-Referer": "https://github.com/akhileshms120/psc_mentor",
        })
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
    chain = OPENROUTER_READER_MODELS if task == "read_paper" else [OPENROUTER_MODEL] + OPENROUTER_FALLBACKS
    return list(dict.fromkeys(chain))


class _NoCredits(AIError):
    pass


def _post_with_free_fallback(body: dict, timeout: float, task: str) -> dict:
    """With no credits, chat and tagging still work on free models; reading papers does not."""
    try:
        return _post(body, timeout)
    except _NoCredits:
        if task == "read_paper" or not OPENROUTER_FREE_MODELS:
            raise
        return _post({**body, "models": OPENROUTER_FREE_MODELS}, timeout)


def _post(body: dict, timeout: float) -> dict:
    try:
        resp = _get_client().post(API, json=body, timeout=timeout)
    except httpx.TimeoutException as e:
        raise AIError("The AI took too long to answer; try again.") from e
    except httpx.HTTPError as e:
        raise AIError("Could not reach OpenRouter.") from e
    try:
        data = resp.json()
    except ValueError:
        data = {}
    error = data.get("error") if isinstance(data, dict) else None
    if resp.status_code != 200 or error:
        message = (error or {}).get("message") if isinstance(error, dict) else None
        code = resp.status_code if resp.status_code != 200 else (error or {}).get("code")
        if code == 401:
            raise AIError("The OpenRouter API key is not valid.")
        if code == 402:
            raise _NoCredits("The OpenRouter account has no credits; add credits at openrouter.ai to read "
                             "papers and write textbook questions.")
        if code == 429:
            raise AIError("OpenRouter is rate limiting requests right now; try again in a minute.")
        raise AIError(f"OpenRouter error {code}: {message or resp.text[:200]}")
    if not data.get("choices"):
        raise AIError("OpenRouter returned no answer.")
    choice = data["choices"][0]
    if choice.get("finish_reason") == "length":
        raise AIError("The AI's answer was cut off; try a smaller request.")
    if choice.get("finish_reason") == "content_filter":
        raise AIError("The AI declined this request.")
    return choice["message"]


def json_call(*, system: str, parts: list[Part], schema: dict, effort: str, task: str = "general") -> dict:
    message = _post_with_free_fallback({
        "models": _models(task),
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": [_content(p) for p in parts]}],
        "response_format": {"type": "json_schema",
                            "json_schema": {"name": "result", "strict": True, "schema": schema}},
        "provider": {"require_parameters": True},
        "max_tokens": MAX_TOKENS,
    }, TIMEOUT_SECONDS, task)
    try:
        return json.loads(message.get("content") or "")
    except json.JSONDecodeError as e:
        raise AIError("The AI returned malformed JSON; try again.") from e


def run_mentor(*, system: str, history: list[dict], user_parts: list[str], tools: list[dict],
               run_tool: Callable[[str, dict], str]) -> str:
    messages: list[dict] = [{"role": "system", "content": system}]
    messages += [{"role": m["role"], "content": m["content"]} for m in history]
    messages.append({"role": "user", "content": [{"type": "text", "text": t} for t in user_parts]})
    or_tools = [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                                  "parameters": t["schema"], "strict": True}} for t in tools]
    text = ""
    for _ in range(MAX_TOOL_ROUNDS):
        # Free models are slow (tens of seconds), so the chat allows them more time.
        message = _post_with_free_fallback({"models": _models("general"), "messages": messages, "tools": or_tools,
                                            "provider": {"require_parameters": True}, "max_tokens": 8192},
                                           CHAT_TIMEOUT_SECONDS * 3, "general")
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
