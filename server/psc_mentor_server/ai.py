"""Every AI call goes through here, so the rest of the backend can run (and be tested) without one.

The prompts and JSON shapes are shared; `ai_gemini` (Google) and `ai_claude` (Anthropic)
only know how to send them. The provider comes from `config.ai_provider()`.
"""

import json
import re
from typing import Any, Callable

from .config import ai_provider


class AIError(RuntimeError):
    pass


# A part of a prompt: text, or a file as (bytes, media_type) — a PDF or a photo of a page.
Part = str | tuple[bytes, str]


def _backend():
    provider = ai_provider()
    if provider == "gemini":
        from . import ai_gemini
        return ai_gemini
    if provider == "claude":
        from . import ai_claude
        return ai_claude
    raise AIError("AI is not configured. Set GEMINI_API_KEY (or ANTHROPIC_API_KEY) on the server.")


def _json_call(system: str, parts: list[Part], schema: dict, effort: str) -> dict:
    return _backend().json_call(system=system, parts=parts, schema=schema, effort=effort)


def run_mentor(system: str, history: list[dict], user_parts: list[str], tools: list[dict],
               run_tool: Callable[[str, dict], str]) -> str:
    """Chat turn with tool use. history: [{role: user|assistant, content: text}];
    tools: [{name, description, schema}]; run_tool(name, args) -> result text. Returns the reply."""
    return _backend().run_mentor(system=system, history=history, user_parts=user_parts, tools=tools,
                                 run_tool=run_tool)


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
        # official answer when known, otherwise the model's own; "unknown" if it can't tell
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
        options = [str(o).strip() for o in q.get("options", [])]
        if len(options) != 4 or not all(options) or not str(q.get("stem", "")).strip():
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
    data = _json_call(
        TAGGER_SYSTEM.format(catalog=catalog),
        ["Tag these questions. answer_index is the official answer (0=A, null=not known).\n" + listing],
        _question_schema(topic_ids, with_answer=False),
        effort="medium",
    )
    return {q["number"]: q for q in _clean_questions(data["questions"], with_answer=False)}


_MALAYALAM = re.compile(r"[\u0D00-\u0D7F]")
# Other Indian scripts (Devanagari..Kannada, Sinhala). Vision models sometimes slip one of these
# letters into a Malayalam word, e.g. "সমাজം" for "സമാജം".
_OTHER_INDIC = re.compile(r"[\u0900-\u0CFF\u0D80-\u0DFF]")


def mixed_script(q: dict) -> bool:
    text = " ".join([q.get("stem", ""), *q.get("options", [])])
    return bool(_MALAYALAM.search(text) and _OTHER_INDIC.search(text))


def _repair_scripts(questions: list[dict], files: list[tuple[bytes, str]], schema: dict, system: str,
                    instructions: str) -> list[dict]:
    """Re-read only the questions whose Malayalam text picked up letters from another script."""
    broken = [q for q in questions if mixed_script(q)]
    if not broken:
        return questions
    listing = json.dumps([{k: q[k] for k in ("number", "stem", "options")} for q in broken], ensure_ascii=False)
    parts: list[Part] = list(files) + [
        instructions + "\nOnly these questions were transcribed with letters from Tamil, Kannada, "
        "Bengali, Devanagari or another script inside Malayalam words. Re-read just these from the paper "
        "and return them with every Malayalam word written only in Malayalam Unicode letters:\n" + listing]
    try:
        fixed = _clean_questions(_json_call(system, parts, schema, effort="medium")["questions"], with_answer=False)
    except (AIError, KeyError, TypeError):
        return questions  # keep the first reading rather than lose the paper
    by_number = {q["number"]: q for q in fixed if not mixed_script(q)}
    return [by_number.get(q["number"], q) if mixed_script(q) else q for q in questions]


def extract_paper(files: list[tuple[bytes, str]], answers: dict[int, int | None] | None, catalog: str,
                  topic_ids: list[str], key_files: list[tuple[bytes, str]] | None = None) -> list[dict]:
    """Read a scanned, photographed or legacy-font paper with the model's vision.

    files / key_files: (bytes, media_type) for the question paper pages and an
    answer key the model should read itself (when it couldn't be parsed locally).
    """
    parts: list[Part] = list(files)
    instructions = (
        "This is a Kerala PSC question paper. Transcribe every numbered multiple-choice "
        "question exactly as printed, in its original language, using proper Unicode "
        "(Malayalam in Unicode Malayalam script, never mixing in Tamil, Kannada, Bengali or "
        "Devanagari letters). Keep the four options in order A-D without the letter labels. "
        "Skip instructions pages. "
    )
    if key_files:
        parts.append("The answer key for this paper follows.")
        parts.extend(key_files)
        instructions += "Take each answer_letter from the answer key provided."
    else:
        instructions += _key_text(answers)
    parts.append(instructions)
    system, schema = TAGGER_SYSTEM.format(catalog=catalog), _question_schema(topic_ids, with_answer=False)
    questions = _clean_questions(_json_call(system, parts, schema, effort="medium")["questions"], with_answer=False)
    return _repair_scripts(questions, list(files) + list(key_files or []), schema, system, instructions)


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
    data = _json_call(GENERATOR_SYSTEM.format(catalog=catalog), [prompt],
                      _question_schema(topic_ids, with_answer=True), effort="high")
    return _clean_questions(data["questions"], with_answer=True)
