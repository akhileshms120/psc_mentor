"""Turning a question paper (official PSC, or uploaded by a student) into bank questions."""

import uuid
from datetime import datetime

from . import ai, psc_source
from .config import PAPERS_DIR, ai_enabled
from .db import Database
from .questions import add_question
from .syllabus import all_topic_ids, topic_catalog

MIN_PARSED_SHARE = 0.6  # below this, local parsing failed and Claude reads the paper instead
UNTAGGED_TOPIC = "special.technical"
PDF = "application/pdf"
IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


class PaperImportError(RuntimeError):
    pass


def queue_paper(db: Database, listing: dict) -> int:
    existing = db.one("SELECT id, status FROM papers WHERE key_url = ?", (listing["key_url"],))
    if existing:
        if existing["status"] == "failed":
            db.execute("UPDATE papers SET status = 'queued', error = NULL WHERE id = ?", (existing["id"],))
        return existing["id"]
    return db.execute(
        "INSERT INTO papers (title, paper_code, category_code, medium, test_date, uploaded_on, level, "
        "question_url, key_url, key_type) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (listing["title"], listing.get("paper_code"), listing.get("category_code"), listing.get("medium"),
         listing.get("test_date"), listing.get("uploaded_on"), psc_source.paper_level(listing["title"]),
         listing.get("question_url"), listing["key_url"], listing.get("key_type")),
    )


def queue_upload(db: Database, user_id: int, title: str) -> int:
    return db.execute(
        "INSERT INTO papers (title, source, owner_user_id, key_url, level) VALUES (?, 'upload', ?, ?, 'general')",
        (title, user_id, f"upload://{uuid.uuid4().hex}"),
    )


def _save(paper_id: int, name: str, data: bytes) -> None:
    folder = PAPERS_DIR / str(paper_id)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_bytes(data)


def _status(db: Database, paper_id: int, status: str, error: str | None = None) -> None:
    db.execute("UPDATE papers SET status = ?, error = ? WHERE id = ?", (status, error, paper_id))


def build_questions(paper_text: str, answers: dict[int, int | None], tagger=None) -> list[dict] | None:
    """Locally parse a readable paper and merge in the key. None = needs Claude to read the paper."""
    if not psc_source.looks_readable(paper_text):
        return None
    parsed = psc_source.parse_question_paper(paper_text, expected=max(answers) if answers else 150)
    if not parsed or len(parsed) < MIN_PARSED_SHARE * max(len(answers), 1):
        return None
    questions = [{"number": q.number, "stem": q.stem, "options": q.options,
                  "answer_index": answers.get(q.number)} for q in parsed]
    tags = tagger(questions) if tagger else {}
    for q in questions:
        tag = tags.get(q["number"], {})
        q["topic_id"] = tag.get("topic_id", UNTAGGED_TOPIC)
        q["explanation"] = tag.get("explanation")
        q["claude_answer"] = tag.get("claude_answer")
    return questions


def _read_questions(db: Database, files: list[tuple[bytes, str]], answers: dict[int, int | None],
                    key_files: list[tuple[bytes, str]] | None) -> list[dict]:
    catalog, topic_ids = topic_catalog(db), all_topic_ids()
    tagger = (lambda qs: ai.tag_questions(qs, catalog, topic_ids)) if ai_enabled() else None
    questions = None
    if len(files) == 1 and files[0][1] == PDF and not key_files:
        questions = build_questions(psc_source.pdf_text(files[0][0]), answers, tagger)
    if questions is None:
        if not ai_enabled():
            raise PaperImportError("This paper is scanned, a photo, or uses a legacy Malayalam font; "
                                   "set up Claude on the server to read it.")
        questions = ai.extract_paper(files, answers, catalog, topic_ids, key_files)
    return questions


def _store(db: Database, paper_id: int, questions: list[dict], answer_for, qtype: str,
           verification: str) -> int:
    count = 0
    for q in questions:
        answer = answer_for(q)
        if answer is False:
            continue
        qid = add_question(db, type=qtype, topic_id=q["topic_id"], stem=q["stem"], options=q["options"],
                           answer_index=answer, explanation=q.get("explanation"), source_paper_id=paper_id,
                           source_qno=q["number"], verification=verification)
        if qid:
            db.execute("INSERT INTO paper_questions (paper_id, qno, question_id) VALUES (?, ?, ?) "
                       "ON CONFLICT (paper_id, qno) DO UPDATE SET question_id = excluded.question_id",
                       (paper_id, q["number"], qid))
            count += 1
    if not count:
        raise PaperImportError("No questions could be read from this paper.")
    return count


def _done(db: Database, paper_id: int, count: int, answer_source: str) -> None:
    db.execute("UPDATE papers SET status = 'done', error = NULL, question_count = ?, answer_source = ?, "
               "imported_at = ? WHERE id = ?",
               (count, answer_source, datetime.now().isoformat(timespec="seconds"), paper_id))


def import_paper(db: Database, paper_id: int) -> None:
    """Official PSC paper + answer key from keralapsc.gov.in."""
    paper = db.one("SELECT * FROM papers WHERE id = ?", (paper_id,))
    try:
        _status(db, paper_id, "downloading")
        key_pdf = psc_source.fetch_pdf(paper["key_url"])
        _save(paper_id, "key.pdf", key_pdf)
        answers = psc_source.parse_answer_key(psc_source.pdf_text(key_pdf),
                                              psc_source.booklet_code(paper["question_url"]))
        if not answers:
            raise PaperImportError("Could not read the answer key.")
        if not paper["question_url"]:
            raise PaperImportError("PSC has not published the question paper for this answer key.")
        paper_pdf = psc_source.fetch_pdf(paper["question_url"])
        _save(paper_id, "paper.pdf", paper_pdf)

        _status(db, paper_id, "extracting")
        questions = _read_questions(db, [(paper_pdf, PDF)], answers, None)
        verification = "final_key" if "final" in (paper["key_type"] or "").lower() else "provisional_key"
        # Only the official key counts; questions PSC deleted keep no answer.
        count = _store(db, paper_id, questions,
                       lambda q: answers[q["number"]] if q["number"] in answers else False,
                       "verified_pyq", verification)
        _done(db, paper_id, count, "official_key")
    except (PaperImportError, ai.AIError, ValueError) as e:
        _status(db, paper_id, "failed", str(e))
    except Exception as e:  # network errors, malformed PDFs
        _status(db, paper_id, "failed", f"{type(e).__name__}: {e}")


def import_upload(db: Database, paper_id: int, files: list[tuple[bytes, str]],
                  key_files: list[tuple[bytes, str]], booklet: str = "A") -> None:
    """A paper the student uploaded: PDF or photos, with or without an answer key."""
    try:
        _status(db, paper_id, "extracting")
        for i, (data, media_type) in enumerate(files):
            _save(paper_id, f"paper-{i}{'.pdf' if media_type == PDF else '.img'}", data)
        for i, (data, media_type) in enumerate(key_files):
            _save(paper_id, f"key-{i}{'.pdf' if media_type == PDF else '.img'}", data)

        answers: dict[int, int | None] = {}
        if key_files and all(mt == PDF for _, mt in key_files):
            answers = psc_source.parse_answer_key(
                "\n".join(psc_source.pdf_text(d) for d, _ in key_files), booklet)
        unread_key = key_files if key_files and not answers else None
        if unread_key and not ai_enabled():
            raise PaperImportError("Couldn't read this answer key; set up Claude on the server, "
                                   "or upload the key as a text PDF.")
        if not key_files and not ai_enabled():
            raise PaperImportError("Upload the answer key too, or set up Claude on the server "
                                   "so it can work out the answers.")

        questions = _read_questions(db, files, answers, unread_key)
        if answers:
            source = "uploaded_key"
        elif unread_key:
            source = "ai_read_key"
        else:
            source = "ai_solved"

        def answer_for(q):
            if answers:
                return answers.get(q["number"])
            return q.get("claude_answer")

        count = _store(db, paper_id, questions, answer_for, "uploaded", source)
        _done(db, paper_id, count, source)
    except (PaperImportError, ai.AIError, ValueError) as e:
        _status(db, paper_id, "failed", str(e))
    except Exception as e:
        _status(db, paper_id, "failed", f"{type(e).__name__}: {e}")
