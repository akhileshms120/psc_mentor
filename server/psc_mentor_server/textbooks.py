"""School textbooks (NCERT, Classes 5-12) behind the Degree Prelims syllabus.

Each chapter in `data/ncert_catalog.json` is mapped to the syllabus topics it teaches. Students
see the chapters to read for a topic, and the AI writes new PSC-style questions from a
chapter's actual text, so every such question carries the chapter it came from.
"""

import json
import re
import time
from datetime import datetime
from io import BytesIO
from pathlib import Path

import httpx
from pypdf import PdfReader
from pypdf.errors import PyPdfError

from . import ai
from .config import ai_enabled
from .db import Database
from .questions import add_question
from .syllabus import TOPIC_DETAILS, all_topic_ids, topic_catalog

CATALOG_PATH = Path(__file__).parent / "data" / "ncert_catalog.json"
NCERT_PDF = "https://ncert.nic.in/textbook/pdf/"
QUESTIONS_PER_CHAPTER = 10
MAX_CHAPTER_CHARS = 40_000  # a long chapter; enough context without paying for appendices
USER_AGENT = "Mozilla/5.0 (PSC Mentor study app)"


def chapter_url(code: str, chapter: int) -> str:
    return f"{NCERT_PDF}{code}{chapter:02d}.pdf"


def load_catalog() -> list[dict]:
    if not CATALOG_PATH.exists():
        return []
    return json.loads(CATALOG_PATH.read_text())


def seed_catalog(db: Database, catalog: list[dict] | None = None) -> None:
    """Upsert the catalog; progress (status, question counts) is kept."""
    rows = []
    for c in catalog if catalog is not None else load_catalog():
        cid = f"ncert:{c['code']}:{c['chapter']}"
        rows.append((cid, "NCERT", c["class"], c["subject"], c["book"], c["chapter"], c["title"],
                     chapter_url(c["code"], c["chapter"]), json.dumps(c["topics"])))
    # A restart mid-way through "Make questions" leaves no task running; let the sync pick it up again.
    db.execute("UPDATE textbook_chapters SET status = 'pending' WHERE status = 'working'")
    if rows:
        db.executemany(
            "INSERT INTO textbook_chapters (id, board, class, subject, book, chapter, title, url, topics_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT (id) DO UPDATE SET title = excluded.title, "
            "topics_json = excluded.topics_json, book = excluded.book, subject = excluded.subject", rows)


def source_ref(row) -> str:
    return f"{row['board']} Class {row['class']} · {row['book']} · Ch {row['chapter']}: {row['title']}"


def chapters_for_topic(db: Database, topic_id: str) -> list[dict]:
    rows = db.query("SELECT * FROM textbook_chapters WHERE topics_json LIKE ? ORDER BY class, book, chapter",
                    (f'%"{topic_id}"%',))
    return [{"id": r["id"], "board": r["board"], "class": r["class"], "book": r["book"], "chapter": r["chapter"],
             "title": r["title"], "url": r["url"], "ref": source_ref(r), "questions": r["question_count"]}
            for r in rows]


def all_chapters(db: Database) -> list[dict]:
    """Every mapped chapter with its topics and progress, for the Textbook Questions screen."""
    names = {r["id"]: r["name"] for r in db.query("SELECT id, name FROM topics")}
    return [{"id": r["id"], "board": r["board"], "class": r["class"], "subject": r["subject"], "book": r["book"],
             "chapter": r["chapter"], "title": r["title"], "url": r["url"], "status": r["status"],
             "error": r["error"], "questions": r["question_count"],
             "topics": [{"topic_id": t, "topic": names.get(t, t)} for t in json.loads(r["topics_json"])]}
            for r in db.query("SELECT * FROM textbook_chapters ORDER BY subject, class, book, chapter")]


def chapter_text(pdf: bytes) -> str:
    text = "\n".join(p.extract_text() or "" for p in PdfReader(BytesIO(pdf)).pages)
    text = re.sub(r"Reprint\s+20\d\d-\d\d", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()[:MAX_CHAPTER_CHARS]


def fetch_chapter(url: str) -> bytes:
    if not url.startswith(NCERT_PDF):
        raise ValueError("Only ncert.nic.in textbook PDFs can be read")
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=120, follow_redirects=True) as client:
        # ncert.nic.in resets about one connection in two (Oct 2026); a second try usually works.
        for attempt in range(3):
            try:
                resp = client.get(url)
                break
            except httpx.TransportError:
                if attempt == 2:
                    raise
                time.sleep(2 * (attempt + 1))
        resp.raise_for_status()
        if not resp.content.startswith(b"%PDF"):
            raise ValueError("Not a PDF")
        return resp.content


def generate_from_chapter(db: Database, chapter_id: str, fetch=None) -> int:
    fetch = fetch or fetch_chapter  # looked up now, so it can be swapped out (tests, other sources)
    row = db.one("SELECT * FROM textbook_chapters WHERE id = ?", (chapter_id,))
    topics = json.loads(row["topics_json"])
    try:
        text = chapter_text(fetch(row["url"]))
        if len(text) < 1500:
            raise ValueError("The chapter PDF has too little readable text.")
        questions = ai.textbook_questions(
            text, source_ref(row), {t: TOPIC_DETAILS.get(t, "") for t in topics}, QUESTIONS_PER_CHAPTER,
            topic_catalog(db), [t for t in all_topic_ids() if not t.startswith("special.")])
        count = 0
        for q in questions:
            if add_question(db, type="original_mock", topic_id=q["topic_id"], stem=q["stem"],
                            options=q["options"], answer_index=q["answer_index"], explanation=q["explanation"],
                            difficulty=q["difficulty"], verification="textbook_ai",
                            source_ref=source_ref(row), source_url=row["url"]):
                count += 1
        db.execute("UPDATE textbook_chapters SET status = 'done', error = NULL, question_count = question_count + ?, "
                   "processed_at = ? WHERE id = ?",
                   (count, datetime.now().isoformat(timespec="seconds"), chapter_id))
        return count
    except (ai.AIError, ValueError, httpx.HTTPError, PyPdfError) as e:
        db.execute("UPDATE textbook_chapters SET status = 'failed', error = ? WHERE id = ?", (str(e)[:500], chapter_id))
        return 0


def next_chapters(db: Database, limit: int) -> list[str]:
    """Chapters for the topics with the fewest questions in the bank go first."""
    bank = {r["topic_id"]: r["n"] for r in db.query("SELECT topic_id, COUNT(*) AS n FROM questions GROUP BY topic_id")}
    rows = db.query("SELECT id, topics_json, class FROM textbook_chapters WHERE status = 'pending'")
    rows = sorted(rows, key=lambda r: (min(bank.get(t, 0) for t in json.loads(r["topics_json"])), -r["class"]))
    return [r["id"] for r in rows[:limit]]


def run_textbooks(db: Database, limit: int, fetch=None) -> int:
    """Write questions from up to `limit` new chapters; returns how many questions were added."""
    if limit <= 0 or not ai_enabled():
        return 0
    return sum(generate_from_chapter(db, cid, fetch) for cid in next_chapters(db, limit))
