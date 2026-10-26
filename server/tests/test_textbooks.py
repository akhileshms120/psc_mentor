import json
import logging

import pytest

from psc_mentor_server import ai, config, engine, textbooks

from .conftest import FIXTURES, TODAY

logging.getLogger("pypdf").setLevel(logging.ERROR)
CATALOG = [
    {"code": "keps2", "class": 11, "subject": "Political Science", "book": "Indian Constitution at Work",
     "chapter": 2, "title": "Rights in the Indian Constitution", "topics": ["constitution.rights_duties"]},
    {"code": "jess2", "class": 10, "subject": "Economics", "book": "Understanding Economic Development",
     "chapter": 3, "title": "Money and Credit", "topics": ["economics.finance"]},
]
TEXT_PDF = (FIXTURES / "pscthriller_54_2026.pdf").read_bytes()  # any PDF with plenty of English text


@pytest.fixture
def catalog(db):
    textbooks.seed_catalog(db, CATALOG)
    return db


def test_catalog_and_reading_list(catalog):
    chapters = textbooks.chapters_for_topic(catalog, "constitution.rights_duties")
    assert [c["title"] for c in chapters] == ["Rights in the Indian Constitution"]
    assert chapters[0]["url"] == "https://ncert.nic.in/textbook/pdf/keps202.pdf"
    assert chapters[0]["ref"] == "NCERT Class 11 · Indian Constitution at Work · Ch 2: Rights in the Indian Constitution"
    textbooks.seed_catalog(catalog, CATALOG)  # re-seeding keeps one row per chapter
    assert catalog.one("SELECT COUNT(*) AS n FROM textbook_chapters")["n"] == 2


def test_the_shipped_catalog_only_uses_real_topics_and_ncert_codes():
    from psc_mentor_server.syllabus import all_topic_ids
    shipped = textbooks.load_catalog()
    assert shipped, "data/ncert_catalog.json is missing"
    ids = set(all_topic_ids())
    for c in shipped:
        assert c["topics"] and set(c["topics"]) <= ids, c
        assert c["class"] in range(5, 13) and c["chapter"] >= 1 and c["code"][1] == "e"


def test_questions_are_written_from_the_chapter_and_keep_their_source(catalog, monkeypatch):
    monkeypatch.setattr(config, "ai_provider", lambda: "gemini")
    monkeypatch.setattr(textbooks, "ai_enabled", lambda: True)
    seen = {}

    def fake(text, source, topics, count, cat, topic_ids):
        seen.update(chars=len(text), source=source, topics=topics)
        return [{"number": i, "stem": f"Which Article guarantees right {i}?", "options": ["14", "19", "21", "32"],
                 "answer_index": 3, "topic_id": "constitution.rights_duties", "explanation": "The chapter says so.",
                 "difficulty": 2} for i in range(1, 4)]

    monkeypatch.setattr(ai, "textbook_questions", fake)
    fetched = []
    added = textbooks.run_textbooks(catalog, 1, fetch=lambda url: fetched.append(url) or TEXT_PDF)
    assert added == 3 and fetched == ["https://ncert.nic.in/textbook/pdf/jess203.pdf"]  # thinnest topic first
    assert seen["chars"] > 1500 and "NCERT Class" in seen["source"]
    row = catalog.one("SELECT * FROM questions WHERE verification = 'textbook_ai' LIMIT 1")
    assert row["source_ref"].startswith("NCERT Class") and row["source_url"].startswith("https://ncert.nic.in/")
    done = catalog.one("SELECT status, question_count FROM textbook_chapters WHERE status = 'done'")
    assert done["question_count"] == 3
    assert textbooks.run_textbooks(catalog, 5, fetch=lambda url: TEXT_PDF) == 3  # only the other chapter is left
    assert textbooks.run_textbooks(catalog, 5, fetch=lambda url: TEXT_PDF) == 0


def test_chapters_for_the_thinnest_topics_go_first(catalog, user):
    # economics.finance has 2 starter questions, rights_duties has more: finance goes first
    assert textbooks.next_chapters(catalog, 2)[0] == "ncert:jess2:3"


def test_a_bad_chapter_is_marked_failed_not_fatal(catalog, monkeypatch):
    monkeypatch.setattr(textbooks, "ai_enabled", lambda: True)
    assert textbooks.run_textbooks(catalog, 1, fetch=lambda url: b"%PDF-1.4 no text") == 0
    assert catalog.one("SELECT COUNT(*) AS n FROM textbook_chapters WHERE status = 'failed'")["n"] == 1


def test_no_ai_means_no_textbook_generation(catalog):
    assert textbooks.run_textbooks(catalog, 3, fetch=lambda url: TEXT_PDF) == 0


def test_textbook_questions_show_their_source_in_review(catalog, user):
    from psc_mentor_server.questions import add_question
    qid = add_question(catalog, type="original_mock", topic_id="economics.finance", stem="Who regulates banks in India?",
                       options=["RBI", "SEBI", "NITI Aayog", "Finance Commission"], answer_index=0,
                       verification="textbook_ai", source_ref="NCERT Class 10 · Understanding Economic Development · Ch 3: Money and Credit",
                       source_url="https://ncert.nic.in/textbook/pdf/jess203.pdf")
    test_id = engine.create_test(catalog, user, "topic", TODAY, topic_id="economics.finance")
    result = engine.submit_test(catalog, user, test_id, {}, TODAY)
    q = next(q for q in result["questions"] if q["id"] == qid)
    assert q["source_ref"].endswith("Money and Credit")
