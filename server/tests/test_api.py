import pytest
from fastapi.testclient import TestClient

from psc_mentor_server import psc_source
from psc_mentor_server.main import create_app

from .conftest import FIXTURES, TODAY


@pytest.fixture
def app_client(db, fixture_text):
    imports, uploads = [], []
    listing = lambda page: psc_source.parse_answer_key_listing(fixture_text("answerkey_listing.html"))
    app = create_app(db, today=lambda: TODAY, fetch_listing=listing,
                     run_import=lambda db, pid: imports.append(pid),
                     run_upload=lambda db, pid, files, keys, booklet: uploads.append((pid, files, keys, booklet)),
                     auto_sync=False)
    c = TestClient(app)
    c.imports, c.uploads = imports, uploads
    return c


def signup(client, login="9876543210", name="Anu"):
    resp = client.post("/auth/signup", json={"name": name, "login": login, "password": "secret123",
                                             "daily_minutes": 120, "exam_date": "2027-03-01"})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['token']}"}


@pytest.fixture
def client(app_client):
    app_client.headers.update(signup(app_client))
    return app_client


def test_health_is_public(app_client):
    assert app_client.get("/health").json() == {"ok": True, "ai_enabled": False, "ai_provider": None}


def test_everything_else_needs_login(app_client):
    for path in ["/me", "/today", "/tests", "/analysis", "/papers", "/mentor/history"]:
        assert app_client.get(path).status_code == 401
    assert app_client.get("/today", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_signup_login_logout(app_client):
    headers = signup(app_client)
    me = app_client.get("/me", headers=headers).json()
    assert me["name"] == "Anu" and me["login"] == "9876543210"
    assert me["diagnostic_done"] is False and me["exam"]["questions"] == 100
    assert app_client.post("/auth/signup", json={"name": "X", "login": "+91 98765 43210",
                                                 "password": "secret123"}).status_code == 400  # same phone
    assert app_client.post("/auth/login", json={"login": "9876543210", "password": "wrong"}).status_code == 401
    token = app_client.post("/auth/login", json={"login": "+91-9876543210", "password": "secret123"}).json()["token"]
    h2 = {"Authorization": f"Bearer {token}"}
    assert app_client.post("/auth/logout", headers=h2).status_code == 200
    assert app_client.get("/me", headers=h2).status_code == 401
    assert app_client.get("/me", headers=headers).status_code == 200  # other sessions stay


def test_signup_validation(app_client):
    bad = [{"name": "A", "login": "12345", "password": "secret123"},
           {"name": "A", "login": "a@b.co", "password": "123"},
           {"name": "A", "login": "not-an-email@", "password": "secret123"}]
    for body in bad:
        assert app_client.post("/auth/signup", json=body).status_code == 400


def test_onboarding_flow_diagnostic_then_report(client):
    test = client.post("/tests", json={"type": "diagnostic"}).json()
    assert test["duration_minutes"] == 75
    answers = [{"question_id": q["id"], "selected": 0} for q in test["questions"]]
    result = client.post(f"/tests/{test['id']}/submit", json={"answers": answers}).json()
    assert result["correct"] + result["wrong"] == len(answers)
    assert client.get("/me").json()["diagnostic_done"] is True
    report = client.get("/analysis").json()
    assert report["assessed"] and report["diagnostic"]["id"] == test["id"]
    assert {s["status"] for s in report["sections"]} <= {"strong", "average", "weak"}


def test_users_see_only_their_own_data(client, app_client):
    test = client.post("/tests", json={"type": "daily"}).json()
    other = signup(app_client, login="binu@example.com", name="Binu")
    assert app_client.get(f"/tests/{test['id']}", headers=other).status_code == 404
    assert app_client.get("/tests", headers=other).json() == []


def test_bad_requests(client):
    assert client.post("/tests", json={"type": "nope"}).status_code == 400
    assert client.post("/tests", json={"type": "topic", "topic_id": "x.y"}).status_code == 400
    assert client.get("/tests/999").status_code == 404
    assert client.put("/me", json={"exam_date": "soon"}).status_code == 400


def test_profile_update(client):
    data = client.put("/me", json={"daily_minutes": 180, "language": "ml", "name": "Anu K"}).json()
    assert data["daily_minutes"] == 180 and data["language"] == "ml" and data["name"] == "Anu K"


def test_psc_listing_and_import_queue(client):
    papers = client.get("/psc/papers").json()
    assert len(papers) == 20
    target = next(p for p in papers if p["question_url"])
    queued = client.post("/papers/import", json=target).json()
    assert queued["status"] == "queued" and client.imports == [queued["id"]]
    assert client.post("/papers/import", json={"title": "x", "key_url": "https://evil.example/k.pdf"}).status_code == 400


def test_upload_question_paper_with_key(client):
    paper = (FIXTURES / "pKey-92-26-M.pdf").read_bytes()  # any PDF will do for the endpoint
    resp = client.post("/papers/upload", data={"title": "My coaching mock", "booklet": "B"},
                       files=[("paper", ("paper.pdf", paper, "application/pdf")),
                              ("key", ("key.jpg", b"\xff\xd8 photo", "image/jpeg"))])
    assert resp.status_code == 200, resp.text
    row = resp.json()
    assert row["source"] == "upload" and row["status"] == "queued"
    pid, files, keys, booklet = client.uploads[0]
    assert pid == row["id"] and files[0][1] == "application/pdf" and keys[0][1] == "image/jpeg" and booklet == "B"
    assert any(p["id"] == row["id"] for p in client.get("/papers").json())


def test_upload_rejects_other_files(client):
    resp = client.post("/papers/upload", data={"title": "x"},
                       files=[("paper", ("notes.docx", b"PK\x03\x04", "application/msword"))])
    assert resp.status_code == 400


def test_uploads_are_hidden_from_other_users(client, app_client):
    client.post("/papers/upload", data={"title": "Mine"},
                files=[("paper", ("p.pdf", b"%PDF-1.4 x", "application/pdf"))])
    other = signup(app_client, login="binu@example.com", name="Binu")
    assert app_client.get("/papers", headers=other).json() == []


def test_mentor_without_ai_is_a_clear_error(client):
    resp = client.post("/mentor/chat", json={"text": "What should I study today?"})
    assert resp.status_code == 503 and "GEMINI_API_KEY" in resp.json()["detail"]


def test_syllabus_matches_degree_prelims(client):
    subjects = client.get("/syllabus").json()
    marks = {s["subject_id"]: s["weight"] for s in subjects}
    assert sum(marks.values()) == 100 and marks["english"] == 20


def test_sync_status_route_is_not_swallowed_by_paper_ids(client):
    state = client.get("/papers/sync").json()
    assert set(state) >= {"running", "imported", "queued", "last_run"}


def test_too_many_wrong_passwords_locks_the_account_for_a_while(app_client):
    signup(app_client, login="lock@example.com")
    for _ in range(10):
        assert app_client.post("/auth/login", json={"login": "lock@example.com", "password": "nope"}).status_code == 401
    resp = app_client.post("/auth/login", json={"login": "lock@example.com", "password": "secret123"})
    assert resp.status_code == 401 and "Too many" in resp.json()["detail"]


def test_delete_account_removes_the_student_and_private_uploads(client, app_client, db):
    test = client.post("/tests", json={"type": "daily"}).json()
    client.post(f"/tests/{test['id']}/submit",
                json={"answers": [{"question_id": q["id"], "selected": 0} for q in test["questions"]]})
    paper = db.execute("INSERT INTO papers (title, key_url, status, source, owner_user_id) VALUES "
                       "('Mine', 'upload://del', 'done', 'upload', (SELECT id FROM users WHERE login = '9876543210'))")
    from psc_mentor_server.questions import add_question
    qid = add_question(db, type="uploaded", topic_id="computer.cyber_law", stem="Upload-only question",
                       options=["a", "b", "c", "d"], answer_index=0, source_paper_id=paper)
    db.execute("INSERT INTO paper_questions (paper_id, qno, question_id) VALUES (?, 1, ?)", (paper, qid))
    bank = db.one("SELECT COUNT(*) AS n FROM questions")["n"]

    assert client.post("/me/delete", json={"password": "wrong"}).status_code == 403
    assert client.post("/me/delete", json={"password": "secret123"}).json() == {"ok": True}
    assert client.get("/me").status_code == 401
    for table in ["users", "tests", "attempts", "revision", "plan_items", "papers", "sessions"]:
        assert db.one(f"SELECT COUNT(*) AS n FROM {table}")["n"] == 0, table
    assert db.one("SELECT COUNT(*) AS n FROM questions")["n"] == bank - 1  # only the private upload went
    signup(app_client)  # the phone number can be used again
