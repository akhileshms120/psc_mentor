"""All Claude calls live here, so the rest of the backend can run (and be tested) without them."""

import base64
import json
from typing import Any

import anthropic

from .config import CLAUDE_MODEL, ai_enabled

# Server-side fallback: if a safety classifier declines, the API retries on a
# recommended model inside the same call instead of returning a refusal.
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AIError(RuntimeError):
    pass


_client: anthropic.Anthropic | None = None


def client() -> anthropic.Anthropic:
    global _client
    if not ai_enabled():
        raise AIError("AI is not configured. Set ANTHROPIC_API_KEY on the server.")
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
        with client().beta.messages.stream(**kwargs) as stream:
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


def _json(message) -> dict:
    text = next(b.text for b in message.content if b.type == "text")
    return json.loads(text)


def _file_block(data: bytes, media_type: str) -> dict:
    """A PDF becomes a document block; a photo of a paper becomes an image block."""
    source = {"type": "base64", "media_type": media_type,
              "data": base64.standard_b64encode(data).decode()}
    return {"type": "document" if media_type == "application/pdf" else "image", "source": source}


def _question_schema(topic_ids: list[str], with_answer: bool) -> dict:
    props: dict[str, Any] = {
        "number": {"type": "integer"},
        "stem": {"type": "string"},
        "options": {"type": "array", "items": {"type": "string"}},
        "topic_id": {"type": "string", "enum": topic_ids},
        "explanation": {"type": "string"},
    }
    if with_answer:
        props["answer_index"] = {"type": "integer", "enum": [0, 1, 2, 3]}
        props["difficulty"] = {"type": "integer", "enum": [1, 2, 3]}
    else:
        # official answer when known, otherwise Claude's own; "unknown" if it can't tell
        props["answer_letter"] = {"type": "string", "enum": ["A", "B", "C", "D", "unknown"]}
    return {
        "type": "object",
        "properties": {
            "questions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": props,
                    "required": list(props),
                    "additionalProperties": False,
                },
            }
        },
        "required": ["questions"],
        "additionalProperties": False,
    }


def _clean_questions(raw: list[dict], with_answer: bool) -> list[dict]:
    """Drop anything that isn't a well-formed four-option question."""
    out = []
    for q in raw:
        options = [o.strip() for o in q.get("options", [])]
        if len(options) != 4 or not all(options) or not q.get("stem", "").strip():
            continue
        q["options"] = options
        q["stem"] = q["stem"].strip()
        if with_answer and q.get("answer_index") not in (0, 1, 2, 3):
            continue
        if not with_answer:
            letter = q.pop("answer_letter", "unknown")
            q["claude_answer"] = "ABCD".index(letter) if letter in ("A", "B", "C", "D") else None
        out.append(q)
    return out


TAGGER_SYSTEM = """You prepare Kerala PSC questions for a study app for the Degree Level
Preliminary exam. Tag every question with the single best topic id from this syllabus.
Current-affairs questions go to the section they are about. Questions from
post-specific technical subjects (laboratory, engineering, trade skills, nursing,
etc.) go to special.technical.

Syllabus topic ids:
{catalog}

For each question give answer_letter: the official answer when one is supplied;
otherwise solve the question yourself, and use "unknown" if you cannot be confident.
Also write a one or two sentence explanation of why that answer is correct, in the
same language as the question."""


def _key_text(answers: dict[int, int | None] | None) -> str:
    if not answers:
        return "No official answer key is available; solve each question."
    return "Official answer key (question:answer): " + ", ".join(
        f"{n}:{'ABCD'[a] if a is not None else 'deleted'}" for n, a in sorted(answers.items()))


def tag_questions(questions: list[dict], catalog: str, topic_ids: list[str]) -> dict[int, dict]:
    """questions: [{number, stem, options, answer_index}] -> {number: {topic_id, explanation, claude_answer}}."""
    listing = json.dumps(questions, ensure_ascii=False)
    message = _call(
        system=TAGGER_SYSTEM.format(catalog=catalog),
        messages=[{"role": "user", "content":
                   "Tag these questions. answer_index is the official answer (0=A, null=not known).\n" + listing}],
        effort="medium",
        schema=_question_schema(topic_ids, with_answer=False),
    )
    return {q["number"]: q for q in _clean_questions(_json(message)["questions"], with_answer=False)}


def extract_paper(files: list[tuple[bytes, str]], answers: dict[int, int | None] | None, catalog: str,
                  topic_ids: list[str], key_files: list[tuple[bytes, str]] | None = None) -> list[dict]:
    """Read a scanned, photographed or legacy-font paper with Claude's vision.

    files / key_files: (bytes, media_type) for the question paper pages and an
    answer key Claude should read itself (when it couldn't be parsed locally).
    """
    content: list[dict] = [_file_block(data, mt) for data, mt in files]
    instructions = (
        "This is a Kerala PSC question paper. Transcribe every numbered multiple-choice "
        "question exactly as printed, in its original language, using proper Unicode "
        "(Malayalam in Unicode Malayalam script). Keep the four options in order A-D "
        "without the letter labels. Skip instructions pages. "
    )
    if key_files:
        content.append({"type": "text", "text": "The answer key for this paper follows."})
        content.extend(_file_block(data, mt) for data, mt in key_files)
        instructions += "Take each answer_letter from the answer key provided."
    else:
        instructions += _key_text(answers)
    content.append({"type": "text", "text": instructions})
    message = _call(
        system=TAGGER_SYSTEM.format(catalog=catalog),
        messages=[{"role": "user", "content": content}],
        effort="medium",
        schema=_question_schema(topic_ids, with_answer=False),
    )
    return _clean_questions(_json(message)["questions"], with_answer=False)


GENERATOR_SYSTEM = """You are an experienced Kerala PSC question setter. Write fresh
multiple-choice questions in the style of recent Kerala PSC preliminary exams:
one clearly correct option, three plausible distractors, no "all of the above"
tricks unless natural, facts that are stable and verifiable. Never invent
statistics or recent events you are unsure of; for current affairs prefer
well-established facts. Arithmetic and mental ability questions must be
solvable in under a minute and the explanation must show the working.

Syllabus topic ids:
{catalog}"""


def generate_questions(requests: list[dict], examples: list[dict], language: str,
                       catalog: str, topic_ids: list[str]) -> list[dict]:
    """requests: [{topic_id, topic, count}]; examples: real PYQs to imitate."""
    lang = "Malayalam (Unicode)" if language == "ml" else "English"
    prompt = (
        f"Write questions in {lang}.\n"
        f"Needed (topic_id, topic, how many): {json.dumps(requests, ensure_ascii=False)}\n"
        "Set number sequentially from 1. difficulty: 1 easy, 2 medium, 3 hard (mix them).\n"
    )
    if examples:
        prompt += ("Real previous-year questions on these topics, for style and level "
                   "(do not copy them):\n" + json.dumps(examples, ensure_ascii=False))
    message = _call(
        system=GENERATOR_SYSTEM.format(catalog=catalog),
        messages=[{"role": "user", "content": prompt}],
        effort="high",
        schema=_question_schema(topic_ids, with_answer=True),
    )
    return _clean_questions(_json(message)["questions"], with_answer=True)


def chat(system: str, messages: list, tools: list):
    return _call(system=system, messages=messages, effort="medium", max_tokens=16000, tools=tools)
