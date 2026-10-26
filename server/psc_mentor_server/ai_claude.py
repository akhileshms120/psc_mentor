"""Anthropic Claude backend for `ai` (used when ANTHROPIC_API_KEY is set and no Google key is)."""

import base64
import json
from typing import Any, Callable

import anthropic

from .ai import AIError, Part
from .config import CLAUDE_MODEL

# Server-side fallback: if a safety classifier declines, the API retries on a
# recommended model inside the same call instead of returning a refusal.
FALLBACK_BETA = "server-side-fallback-2026-07-01"
MAX_TOOL_ROUNDS = 4

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def _call(*, system: str, messages: list, effort: str, max_tokens: int = 64000,
          schema: dict | None = None, tools: list | None = None):
    output_config: dict[str, Any] = {"effort": effort}
    if schema is not None:
        output_config["format"] = {"type": "json_schema", "schema": schema}
    kwargs: dict[str, Any] = dict(
        model=CLAUDE_MODEL,
        max_tokens=max_tokens,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=messages,
        output_config=output_config,
        betas=[FALLBACK_BETA],
        fallbacks="default",
    )
    if tools:
        kwargs["tools"] = tools
    try:
        with _get_client().beta.messages.stream(**kwargs) as stream:
            message = stream.get_final_message()
    except anthropic.RateLimitError as e:
        raise AIError("Claude is rate limited right now; try again in a minute.") from e
    except anthropic.APIStatusError as e:
        raise AIError(f"Claude API error {e.status_code}: {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise AIError("Could not reach the Claude API.") from e
    if message.stop_reason == "refusal":
        raise AIError("Claude declined this request.")
    if message.stop_reason == "max_tokens":
        raise AIError("Claude's answer was cut off; try a smaller request.")
    return message


def _block(part: Part) -> dict:
    if isinstance(part, str):
        return {"type": "text", "text": part}
    data, media_type = part
    source = {"type": "base64", "media_type": media_type, "data": base64.standard_b64encode(data).decode()}
    return {"type": "document" if media_type == "application/pdf" else "image", "source": source}


def json_call(*, system: str, parts: list[Part], schema: dict, effort: str, task: str = "general") -> dict:
    message = _call(system=system, messages=[{"role": "user", "content": [_block(p) for p in parts]}],
                    effort=effort, schema=schema)
    return json.loads(next(b.text for b in message.content if b.type == "text"))


def run_mentor(*, system: str, history: list[dict], user_parts: list[str], tools: list[dict],
               run_tool: Callable[[str, dict], str]) -> str:
    messages: list[dict] = [{"role": m["role"], "content": m["content"]} for m in history]
    messages.append({"role": "user", "content": [{"type": "text", "text": t} for t in user_parts]})
    claude_tools = [{"name": t["name"], "description": t["description"], "strict": True,
                     "input_schema": t["schema"]} for t in tools]
    for _ in range(MAX_TOOL_ROUNDS):
        message = _call(system=system, messages=messages, effort="medium", max_tokens=16000, tools=claude_tools)
        messages.append({"role": "assistant", "content": message.content})
        if message.stop_reason != "tool_use":
            break
        messages.append({"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": b.id, "content": run_tool(b.name, b.input)}
            for b in message.content if b.type == "tool_use"
        ]})
    return "\n\n".join(b.text for b in message.content if b.type == "text").strip()
