"""Google Gemini backend for `ai` (used when GEMINI_API_KEY or GOOGLE_API_KEY is set)."""

import json
import re
import time
from typing import Callable

from google import genai
from google.genai import errors, types

from .ai import AIError, Part
from .config import GEMINI_FALLBACKS, GEMINI_MODEL, GEMINI_READER_MODELS, google_api_key

MAX_TOOL_ROUNDS = 4
# Reading a 100-question paper can take a few minutes; a chat reply should not.
TIMEOUT_MS = 10 * 60 * 1000
CHAT_TIMEOUT_MS = 90 * 1000
MAX_OUTPUT_TOKENS = 65536
RETRY_DELAY_SECONDS = 3

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=google_api_key(), http_options=types.HttpOptions(timeout=TIMEOUT_MS))
    return _client


def _part(part: Part) -> types.Part:
    if isinstance(part, str):
        return types.Part.from_text(text=part)
    data, media_type = part
    return types.Part.from_bytes(data=data, mime_type=media_type)


def _generate_with_fallback(contents: list, config: types.GenerateContentConfig, models: list[str] | None = None):
    """Overloaded (503/504): retry once, then try the fallback models. Out of quota (429):
    each model has its own free-tier daily allowance, so go straight to the next model."""
    chain = models or [GEMINI_MODEL] + GEMINI_FALLBACKS
    attempts = [chain[0]] + list(dict.fromkeys(chain))
    quota_hit: set[str] = set()
    last_error: errors.APIError | None = None
    for i, model in enumerate(attempts):
        if model in quota_hit:
            continue
        try:
            return _get_client().models.generate_content(model=model, contents=contents, config=config)
        except errors.ServerError as e:
            last_error = e
            if i == 0:
                time.sleep(RETRY_DELAY_SECONDS)
        except errors.ClientError as e:
            if e.code != 429:
                raise
            quota_hit.add(model)
            last_error = e
    raise last_error


def _quota_message(e: errors.APIError) -> str:
    m = re.search(r"retry in (?:(\d+)h)?(?:(\d+)m)?", str(e))
    if m and (m.group(1) or m.group(2)):
        wait = " ".join(x for x in (f"{m.group(1)} h" if m.group(1) else "", f"{m.group(2)} min" if m.group(2) else "") if x)
        return f"Today's free Gemini quota is used up; it resets in about {wait}."
    return "The Gemini API quota is used up for now; try again later."


def _generate(contents: list, config: types.GenerateContentConfig, models: list[str] | None = None):
    try:
        response = _generate_with_fallback(contents, config, models)
    except errors.ClientError as e:
        if e.code == 429:
            raise AIError(_quota_message(e)) from e
        raise AIError(f"Gemini API error {e.code}: {e.message}") from e
    except errors.ServerError as e:
        raise AIError(f"Gemini is having trouble (error {e.code}); try again shortly.") from e
    except errors.APIError as e:
        raise AIError(f"Gemini API error {e.code}: {e.message}") from e
    if not response.candidates:
        reason = response.prompt_feedback.block_reason if response.prompt_feedback else "no answer"
        raise AIError(f"Gemini returned no answer ({reason}).")
    finish = response.candidates[0].finish_reason
    if finish == types.FinishReason.MAX_TOKENS:
        raise AIError("Gemini's answer was cut off; try a smaller request.")
    if finish in (types.FinishReason.SAFETY, types.FinishReason.PROHIBITED_CONTENT, types.FinishReason.BLOCKLIST):
        raise AIError("Gemini declined this request.")
    return response


def json_call(*, system: str, parts: list[Part], schema: dict, effort: str, task: str = "general") -> dict:
    response = _generate(
        [types.Content(role="user", parts=[_part(p) for p in parts])],
        types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_json_schema=schema,
            max_output_tokens=MAX_OUTPUT_TOKENS,
        ),
        GEMINI_READER_MODELS if task == "read_paper" else None,
    )
    try:
        return json.loads(response.text)
    except (TypeError, json.JSONDecodeError) as e:
        raise AIError("Gemini returned malformed JSON; try again.") from e


def run_mentor(*, system: str, history: list[dict], user_parts: list[str], tools: list[dict],
               run_tool: Callable[[str, dict], str]) -> str:
    contents = [types.Content(role="model" if m["role"] == "assistant" else "user",
                              parts=[types.Part.from_text(text=m["content"])]) for m in history]
    contents.append(types.Content(role="user", parts=[types.Part.from_text(text=t) for t in user_parts]))
    config = types.GenerateContentConfig(
        system_instruction=system,
        tools=[types.Tool(function_declarations=[
            types.FunctionDeclaration(name=t["name"], description=t["description"],
                                      parameters_json_schema=t["schema"]) for t in tools])],
        # We run the tools ourselves so they act on this student's data.
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        http_options=types.HttpOptions(timeout=CHAT_TIMEOUT_MS),
    )
    text = ""
    for _ in range(MAX_TOOL_ROUNDS):
        response = _generate(contents, config)
        # Keep the model's turn exactly as returned: it carries the thought signatures Gemini
        # needs to continue a tool-calling turn.
        contents.append(response.candidates[0].content)
        text = response.text or text
        calls = response.function_calls or []
        if not calls:
            break
        contents.append(types.Content(role="user", parts=[
            types.Part.from_function_response(name=c.name, response={"result": run_tool(c.name, dict(c.args or {}))})
            for c in calls
        ]))
    return (text or "").strip()
