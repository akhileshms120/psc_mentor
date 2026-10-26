from psc_mentor_server import psc_source
from psc_mentor_server.importer import build_questions

from .conftest import FIXTURES


def test_listing_rows_are_parsed(fixture_text):
    papers = psc_source.parse_answer_key_listing(fixture_text("answerkey_listing.html"))
    assert len(papers) == 20
    vfa = next(p for p in papers if p.paper_code == "092/2026-M")
    assert vfa.medium == "Malayalam"
    assert vfa.category_code == "571/2025"
    assert vfa.test_date == "17-Oct-2026"
    assert vfa.key_type == "Provisional Answer Key"
    assert vfa.question_url.endswith("/2026-10/qn-092-2026-M-A.pdf")
    assert vfa.key_url.startswith("https://www.keralapsc.gov.in/sites/default/files/")


def test_final_keys_borrow_the_question_paper_from_provisional_rows():
    rows = [
        psc_source.PaperListing("X", "092/2026-M", None, None, None, "Provisional", "https://q/A.pdf",
                                "https://k1.pdf", None),
        psc_source.PaperListing("X", "92-26 M", None, None, None, "Final", None, "https://k2.pdf", None),
    ]
    psc_source.attach_question_links(rows)
    assert rows[1].question_url == "https://q/A.pdf"


def test_answer_key_pdf_for_booklet_a():
    text = psc_source.pdf_text((FIXTURES / "pKey-92-26-M.pdf").read_bytes())
    answers = psc_source.parse_answer_key(text, "A")
    assert len(answers) == 100
    assert answers[1] == 1   # B
    assert answers[2] == 0   # A
    assert answers[3] == 3   # D
    assert psc_source.parse_answer_key(text, "B")[1] == 3  # booklet B column: D


def test_deleted_questions_are_none():
    assert psc_source.parse_answer_key("53 B D C A\n54 X A D D\n", "A") == {53: 1, 54: None}


def test_booklet_code_from_url():
    assert psc_source.booklet_code("https://x/qn-092-2026-M-A.pdf") == "A"
    assert psc_source.booklet_code("https://x/090-2026-C.pdf") == "C"
    assert psc_source.booklet_code(None) == "A"


def test_english_paper_parses_all_100_questions(fixture_text):
    questions = psc_source.parse_question_paper(fixture_text("paper_090_2026_A.txt"))
    assert [q.number for q in questions] == list(range(1, 101))
    assert questions[0].stem.startswith("Human Anatomical wastes")
    assert questions[0].options == ["Green", "Yellow", "Blue", "Red"]
    # "(A)" and "(B)" inside an option must not split it
    assert questions[97].options[3] == "Both (A) and (B)"
    assert questions[99].options[3] == "Flame cells"


def test_legacy_font_malayalam_paper_is_detected_as_unreadable(fixture_text):
    assert not psc_source.looks_readable(fixture_text("paper_092_2026_M.txt"))
    assert psc_source.looks_readable(fixture_text("paper_090_2026_A.txt"))


def test_build_questions_merges_key_and_tags(fixture_text):
    answers = {n: n % 4 for n in range(1, 101)}
    answers[5] = None
    tagger = lambda qs: {q["number"]: {"topic_id": "science.health", "explanation": "why"} for q in qs}
    questions = build_questions(fixture_text("paper_090_2026_A.txt"), answers, tagger)
    assert len(questions) == 100
    assert questions[0]["answer_index"] == 1
    assert questions[4]["answer_index"] is None
    assert questions[0]["topic_id"] == "science.health"


def test_build_questions_without_ai_tags_as_technical(fixture_text):
    questions = build_questions(fixture_text("paper_090_2026_A.txt"), {n: 0 for n in range(1, 101)})
    assert {q["topic_id"] for q in questions} == {"special.technical"}


def test_build_questions_asks_for_claude_on_unreadable_paper(fixture_text):
    assert build_questions(fixture_text("paper_092_2026_M.txt"), {1: 0}) is None


def test_paper_levels():
    assert psc_source.paper_level("ASSISTANT (Universities in Kerala)") == "degree"
    assert psc_source.paper_level("Special Branch Asst, Excise Inspector, SI of Police, Assista") == "degree"
    assert psc_source.paper_level("LAST GRADE SERVANTS, STOREMAN, LOWER DIVISION CLERK") == "general"
    assert psc_source.paper_level("JUNIOR LAB ASSISTANT - Medical Education") == "technical"


def test_sync_picks_degree_papers_first_and_skips_technical(fixture_text):
    from psc_mentor_server.sync import select_candidates
    listings = psc_source.attach_question_links(
        psc_source.parse_answer_key_listing(fixture_text("answerkey_listing.html")))
    with_ai = select_candidates(listings, set(), with_ai=True, limit=5)
    assert with_ai[0].title.startswith("ASSISTANT (Universities")
    assert all(psc_source.paper_level(p.title) != "technical" for p in with_ai)
    assert all(p.medium in ("English", "Malayalam") and p.question_url for p in with_ai)
    # Without Claude only English papers can be read, and this page has no general English ones.
    assert select_candidates(listings, set(), with_ai=False) == []
    known = {p.key_url for p in with_ai}
    assert not set(p.key_url for p in select_candidates(listings, known, True, limit=5)) & known


def test_sync_imports_the_chosen_papers(db, fixture_text):
    from psc_mentor_server import sync
    listing = psc_source.parse_answer_key_listing(fixture_text("answerkey_listing.html"))
    ran = []

    def fake_import(db, pid):
        ran.append(pid)
        db.execute("UPDATE papers SET status = 'done' WHERE id = ?", (pid,))

    sync.ai_enabled = lambda: True
    try:
        state = sync.run_sync(db, fetch=lambda page: listing if page == 0 else [], run_import=fake_import,
                              pages=2, limit=3)
    finally:
        from psc_mentor_server.config import ai_enabled
        sync.ai_enabled = ai_enabled
    assert state["imported"] == 3 and len(ran) == 3 and not state["running"]
    assert {r["level"] for r in db.query("SELECT level FROM papers")} <= {"degree", "general"}


def test_sync_skips_the_provisional_copy_of_a_paper_with_a_final_key():
    from psc_mentor_server.sync import select_candidates
    mk = lambda key, kind: psc_source.PaperListing("SI of Police", "1/26", None, "Malayalam", None, kind,
                                                   "https://q/si.pdf", key, "06-07-2026")
    picked = select_candidates([mk("https://k/p.pdf", "Provisional Answer Key"),
                                mk("https://k/f.pdf", "Final Answer Key")], set(), with_ai=True)
    assert [p.key_url for p in picked] == ["https://k/f.pdf"]
