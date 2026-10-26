import json
import logging

import pytest

from psc_mentor_server import ai, importer, psc_source, psc_thriller, sync

from .conftest import FIXTURES

logging.getLogger("pypdf").setLevel(logging.ERROR)
PDF = (FIXTURES / "pscthriller_54_2026.pdf").read_bytes()
POST_URL = "https://www.pscthriller.com/2026/07/2026-degree-prelims-question-paper-with_02059127312.html"


def test_feed_lists_question_paper_posts_with_codes_and_levels():
    posts = psc_thriller.parse_feed(json.loads((FIXTURES / "pscthriller_feed.json").read_text()))
    titles = [p.title for p in posts]
    assert not any("Practice Test" in t for t in titles)  # not a question paper
    degree = next(p for p in posts if "Degree Prelims" in p.title)
    assert degree.paper_code == "72/2025" and degree.level == "degree"
    assert all(p.url.startswith(psc_thriller.BASE) for p in posts)


@pytest.mark.parametrize("title,code", [
    ("2026 Degree Prelims  Question Paper with Answer Key (54/2026) || Stage 3", "54/2026"),
    ("2025 Degree Prelims Stage 2(72-2025) Question paper wth Answer Key", "72/2025"),
    ("Village Field Assistant Question Paper with Answer Key (85/26)", "85/2026"),
    ("Traffic Superintendent/Junior Assistant Question Paper with Answer Key  (126/2026/OL)", "126/2026"),
    ("Some post without a code", None),
])
def test_paper_codes(title, code):
    assert psc_thriller.paper_code(title) == code


def test_post_page_gives_the_drive_pdf():
    html = (FIXTURES / "pscthriller_post_54_2026.html").read_text()
    assert psc_thriller.drive_file_id(html) == "1N7EFor_wGb_ZCR8JMoUM8y-XHQmYGWfe"


def test_pdf_splits_into_english_questions_and_the_official_key():
    sp = psc_thriller.split_pdf(PDF)
    assert sp.booklet == "A" and sp.final_key
    answers = psc_source.parse_answer_key(sp.key_text, sp.booklet)
    assert len(answers) == 100 and answers[1] == 0 and answers[3] is None  # Q3 was deleted by PSC
    questions = psc_source.parse_question_paper(sp.question_text)
    assert [q.number for q in questions] == list(range(1, 88))  # 88-100 are the Malayalam section
    assert "pscthriller" not in " ".join(o for q in questions for o in q.options).lower()
    assert sp.unreadable_tail and max(sp.unreadable_tail) == max(sp.question_pages)


@pytest.fixture
def thriller_paper(db, monkeypatch, tmp_path):
    monkeypatch.setattr(importer, "PAPERS_DIR", tmp_path)
    monkeypatch.setattr(psc_thriller, "fetch_paper_pdf", lambda url: (PDF, "https://drive.google.com/uc?id=x"))
    return importer.queue_thriller(db, {"title": "2026 Degree Prelims Question Paper (54/2026)", "url": POST_URL,
                                        "published": "2026-07-16", "paper_code": "54/2026", "level": "degree"})


def test_import_without_ai_keeps_the_english_questions_with_official_answers(db, thriller_paper):
    importer.import_thriller(db, thriller_paper)
    paper = db.one("SELECT * FROM papers WHERE id = ?", (thriller_paper,))
    assert paper["status"] == "done", paper["error"]
    assert paper["origin"] == "PSC Thriller" and paper["origin_url"] == POST_URL
    assert paper["key_type"] == "Final Answer Key" and paper["level"] == "degree" and paper["uploaded_on"] == "16-07-2026"
    q1 = db.one("SELECT q.* FROM paper_questions pq JOIN questions q ON q.id = pq.question_id "
                "WHERE pq.paper_id = ? AND pq.qno = 1", (thriller_paper,))
    assert q1["stem"].startswith("Which of the following is/are correct regarding the Dutch power")
    assert q1["answer_index"] == 0 and q1["type"] == "verified_pyq" and q1["verification"] == "final_key"
    assert paper["question_count"] == 87


def test_import_with_ai_tags_and_reads_the_malayalam_section(db, thriller_paper, monkeypatch):
    monkeypatch.setattr(importer, "ai_enabled", lambda: True)
    monkeypatch.setattr(ai, "tag_questions", lambda qs, c, t: {
        q["number"]: {"topic_id": "history.kerala_history", "explanation": "e"} for q in qs})
    asked = {}

    def fake_extract(files, answers, catalog, topic_ids, key_files=None):
        asked.update(pages=len(files), numbers=sorted(answers))
        return [{"number": n, "stem": f"മലയാളം ചോദ്യം {n}", "options": ["ഒന്ന്", "രണ്ട്", "മൂന്ന്", "നാല്"],
                 "topic_id": "malayalam.word_meaning", "explanation": "", "claude_answer": 0} for n in answers]

    monkeypatch.setattr(ai, "extract_paper", fake_extract)
    importer.import_thriller(db, thriller_paper)
    paper = db.one("SELECT * FROM papers WHERE id = ?", (thriller_paper,))
    assert paper["status"] == "done" and paper["question_count"] == 100
    assert asked["numbers"] == list(range(88, 101)) and asked["pages"] == 2
    topics = {r["topic_id"] for r in db.query(
        "SELECT q.topic_id FROM paper_questions pq JOIN questions q ON q.id = pq.question_id WHERE pq.paper_id = ?",
        (thriller_paper,))}
    assert topics == {"history.kerala_history", "malayalam.word_meaning"}


def test_same_paper_from_psc_site_is_not_imported_twice(db):
    db.execute("INSERT INTO papers (title, paper_code, key_url, status) VALUES ('x', '054-2026 M', 'k', 'done')")
    assert importer.already_have_paper(db, "54/2026")
    assert not importer.already_have_paper(db, "55/2026")
    posts = [psc_thriller.ThrillerPost("Degree Prelims (54/2026)", POST_URL, "2026-07-16", "54/2026", "degree"),
             psc_thriller.ThrillerPost("LGS (80/2026)", psc_thriller.BASE + "/a.html", "2026-09-22", "80/2026", "general"),
             psc_thriller.ThrillerPost("Degree Prelims (48/2026)", psc_thriller.BASE + "/b.html", "2026-07-07", "48/2026", "degree"),
             psc_thriller.ThrillerPost("Lab Assistant (90/2026)", psc_thriller.BASE + "/c.html", "2026-10-01", "90/2026", "technical")]
    picked = sync.select_thriller(posts, set(), db, limit=5)
    assert [p.paper_code for p in picked] == ["48/2026", "80/2026"]  # degree first; no duplicate; no technical
