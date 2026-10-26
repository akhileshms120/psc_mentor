import json
import re

from .db import Database, IntegrityError


def stem_key(stem: str, options: list[str]) -> str:
    """Normalised fingerprint so the same question imported twice is stored once."""
    text = (stem + "|" + "|".join(sorted(options))).lower()
    return re.sub(r"[\W_]+", "", text)


def detect_lang(stem: str) -> str:
    return "ml" if re.search(r"[\u0D00-\u0D7F]", stem) else "en"


def add_question(db: Database, *, type: str, topic_id: str, stem: str, options: list[str],
                 answer_index: int | None, explanation: str | None = None, difficulty: int = 2,
                 source_paper_id: int | None = None, source_qno: int | None = None,
                 verification: str = "unverified", source_ref: str | None = None,
                 source_url: str | None = None) -> int | None:
    """Insert a question; returns its id, or the existing id if it is a duplicate."""
    key = stem_key(stem, options)
    try:
        return db.execute(
            "INSERT INTO questions (type, topic_id, stem, options_json, answer_index, explanation, "
            "difficulty, lang, source_paper_id, source_qno, verification, stem_key, source_ref, source_url) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (type, topic_id, stem, json.dumps(options, ensure_ascii=False), answer_index,
             explanation, difficulty, detect_lang(stem), source_paper_id, source_qno, verification, key,
             source_ref, source_url),
        )
    except IntegrityError:
        row = db.one("SELECT id FROM questions WHERE stem_key = ?", (key,))
        return row["id"] if row else None


def question_dict(row, reveal: bool) -> dict:
    q = {
        "id": row["id"],
        "type": row["type"],
        "topic_id": row["topic_id"],
        "stem": row["stem"],
        "options": json.loads(row["options_json"]),
        "difficulty": row["difficulty"],
        "lang": row["lang"],
        "verification": row["verification"],
        "source_paper_id": row["source_paper_id"],
        "source_qno": row["source_qno"],
        "source_ref": row["source_ref"],
        "source_url": row["source_url"],
    }
    if reveal:
        q["answer_index"] = row["answer_index"]
        q["explanation"] = row["explanation"]
    return q


def get_questions(db: Database, ids: list[int]) -> list:
    """Rows in the same order as `ids`."""
    if not ids:
        return []
    rows = db.query(f"SELECT * FROM questions WHERE id IN ({','.join('?' * len(ids))})", ids)
    by_id = {r["id"]: r for r in rows}
    return [by_id[i] for i in ids if i in by_id]
