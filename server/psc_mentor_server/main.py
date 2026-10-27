"""HTTP API for the PSC Mentor app. Run: uvicorn psc_mentor_server.main:app --host 0.0.0.0"""

import os
import time
from datetime import date
from typing import Annotated, Callable

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import (ai, analysis, auth, curriculum, engine, importer, mentor, planner, progress, psc_source, psc_thriller,
               sync, textbooks, videos)
from .config import DATABASE_URL, DATABASE_URL_UNPOOLED, DB_PATH, ai_enabled, ai_provider
from .db import Database, open_database
from .seed_questions import seed_questions
from .syllabus import EXAM_MINUTES, EXAM_NAME, EXAM_QUESTIONS, TOPIC_DETAILS, seed_syllabus

LISTING_CACHE_SECONDS = 30 * 60
MAX_UPLOAD_BYTES = 30 * 1024 * 1024  # Claude accepts up to 32 MB per request
MAX_UPLOAD_FILES = 20


class SignupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    login: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=1, max_length=200)
    daily_minutes: int | None = Field(default=None, ge=30, le=600)
    exam_date: str | None = None
    language: str | None = Field(default=None, pattern="^(en|ml)$")


class LoginRequest(BaseModel):
    login: str
    password: str


class PasswordConfirm(BaseModel):
    password: str


class ProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    daily_minutes: int | None = Field(default=None, ge=30, le=600)
    exam_date: str | None = None
    language: str | None = Field(default=None, pattern="^(en|ml)$")


class TestRequest(BaseModel):
    type: str
    topic_id: str | None = None
    paper_id: int | None = None
    chapter_id: str | None = None


class Answer(BaseModel):
    question_id: int
    selected: int | None = None
    time_ms: int | None = None


class Submission(BaseModel):
    answers: list[Answer]


class ImportRequest(BaseModel):
    title: str
    key_url: str
    question_url: str | None = None
    paper_code: str | None = None
    category_code: str | None = None
    medium: str | None = None
    test_date: str | None = None
    uploaded_on: str | None = None
    key_type: str | None = None


class ThrillerImport(BaseModel):
    url: str


class ChatRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


def _check_date(value: str | None) -> None:
    if value:
        try:
            date.fromisoformat(value)
        except ValueError:
            raise HTTPException(400, "exam_date must be YYYY-MM-DD")


def create_app(db: Database | None = None, today: Callable[[], date] = date.today,
               fetch_listing: Callable[[int], list] = psc_source.fetch_answer_key_listing,
               run_import: Callable[[Database, int], None] = importer.import_paper,
               run_upload: Callable[..., None] = importer.import_upload,
               fetch_thriller: Callable[[], list] = psc_thriller.fetch_posts,
               run_thriller_import: Callable[[Database, int], None] = importer.import_thriller,
               auto_sync: bool | None = None) -> FastAPI:
    db = db or open_database(DATABASE_URL or DB_PATH, schema_url=DATABASE_URL_UNPOOLED)
    seed_syllabus(db)
    seed_questions(db)
    textbooks.seed_catalog(db)
    if auto_sync is None:
        auto_sync = os.environ.get("PSC_AUTO_SYNC", "on").lower() != "off"
    if auto_sync:
        sync.start_background_sync(db)
    listing_cache: dict[int, tuple[float, list]] = {}

    app = FastAPI(title="PSC Mentor API")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    def current_user(authorization: Annotated[str | None, Header()] = None) -> int:
        if not authorization or not authorization.lower().startswith("bearer "):
            raise HTTPException(401, "Please log in.")
        user_id = auth.user_for_token(db, authorization[7:].strip())
        if user_id is None:
            raise HTTPException(401, "Your session has expired. Please log in again.")
        return user_id

    User = Annotated[int, Depends(current_user)]

    def test_error(e: engine.TestError) -> HTTPException:
        return HTTPException(404 if "not found" in str(e).lower() else 400, str(e))

    def me_view(user_id: int) -> dict:
        row = db.one("SELECT u.id, u.name, u.login, p.* FROM users u JOIN profiles p ON p.user_id = u.id "
                     "WHERE u.id = ?", (user_id,))
        data = dict(row)
        data.pop("user_id", None)
        data["exam"] = {"name": EXAM_NAME, "questions": EXAM_QUESTIONS, "minutes": EXAM_MINUTES}
        data["diagnostic_done"] = row["diagnostic_test_id"] is not None
        return data

    @app.get("/health")
    def health():
        return {"ok": True, "ai_enabled": ai_enabled(), "ai_provider": ai_provider()}

    # --- accounts -----------------------------------------------------------

    @app.post("/auth/signup")
    def signup(req: SignupRequest):
        _check_date(req.exam_date)
        try:
            token, user_id = auth.signup(db, req.name, req.login, req.password, daily_minutes=req.daily_minutes,
                                         exam_date=req.exam_date, language=req.language)
        except auth.AuthError as e:
            raise HTTPException(400, str(e))
        return {"token": token, "user": me_view(user_id)}

    @app.post("/auth/login")
    def login(req: LoginRequest):
        try:
            token, user_id = auth.login(db, req.login, req.password)
        except auth.AuthError as e:
            raise HTTPException(401, str(e))
        return {"token": token, "user": me_view(user_id)}

    @app.post("/auth/logout")
    def logout(user_id: User, authorization: Annotated[str, Header()]):
        auth.logout(db, authorization[7:].strip())
        return {"ok": True}

    @app.post("/me/delete")
    def delete_me(req: PasswordConfirm, user_id: User):
        try:
            auth.delete_account(db, user_id, req.password)
        except auth.AuthError as e:
            raise HTTPException(403, str(e))
        return {"ok": True}

    @app.get("/me")
    def me(user_id: User):
        return me_view(user_id)

    @app.put("/me")
    def update_me(user_id: User, update: ProfileUpdate):
        fields = update.model_dump(exclude_unset=True)
        _check_date(fields.get("exam_date"))
        if "name" in fields:
            db.execute("UPDATE users SET name = ? WHERE id = ?", (fields.pop("name").strip(), user_id))
        for key, value in fields.items():
            db.execute(f"UPDATE profiles SET {key} = ? WHERE user_id = ?", (value, user_id))
        if "daily_minutes" in fields or "exam_date" in fields:
            curriculum.ensure_course(db, user_id, today(), rebuild=True)
            planner.ensure_week(db, user_id, today(), regenerate=True)
        return me_view(user_id)

    # --- study --------------------------------------------------------------

    @app.get("/syllabus")
    def syllabus(user_id: User):
        stats = progress.topic_stats(db, user_id)
        subjects = {s["subject_id"]: s for s in progress.subject_stats(stats)}
        for s in subjects.values():
            s["topics"] = []
        for t in stats:
            subjects[t["subject_id"]]["topics"].append({**t, "details": TOPIC_DETAILS.get(t["topic_id"], "")})
        return list(subjects.values())

    @app.get("/today")
    def today_view(user_id: User):
        day = today()
        plan = planner.week_plan(db, user_id, day)
        return {
            "date": day.isoformat(),
            "plan": [p for p in plan if p["day"] == day.isoformat()],
            "summary": progress.summary(db, user_id, day),
            "ai_enabled": ai_enabled(),
        }

    @app.get("/analysis")
    def strength_report(user_id: User):
        return analysis.report(db, user_id, today())

    @app.get("/topics/{topic_id}/textbooks")
    def topic_textbooks(topic_id: str, user_id: User):
        return textbooks.chapters_for_topic(db, topic_id)

    @app.get("/textbooks/chapters")
    def textbook_chapters(user_id: User):
        return textbooks.all_chapters(db)

    @app.post("/textbooks/chapters/{chapter_id}/generate")
    def make_textbook_questions(chapter_id: str, user_id: User, background: BackgroundTasks):
        if not db.one("SELECT 1 FROM textbook_chapters WHERE id = ?", (chapter_id,)):
            raise HTTPException(404, "Chapter not found")
        if not ai_enabled():
            raise HTTPException(503, "The AI is off on the server, so it can't write questions yet.")
        db.execute("UPDATE textbook_chapters SET status = 'working', error = NULL WHERE id = ?", (chapter_id,))
        background.add_task(textbooks.generate_from_chapter, db, chapter_id)
        return {"ok": True, "status": "working"}

    @app.get("/textbooks")
    def textbook_progress(user_id: User):
        rows = db.query("SELECT status, COUNT(*) AS n, COALESCE(SUM(question_count), 0) AS q "
                        "FROM textbook_chapters GROUP BY status")
        return {"chapters": {r["status"]: r["n"] for r in rows}, "questions": sum(r["q"] for r in rows)}

    @app.get("/topics/{topic_id}/videos")
    def topic_videos(topic_id: str, user_id: User):
        try:
            return videos.topic_videos(db, topic_id)
        except videos.VideoError as e:
            raise HTTPException(404 if "Unknown topic" in str(e) else 503, str(e))

    @app.get("/course")
    def course(user_id: User):
        return curriculum.course_view(db, user_id, today())

    @app.get("/plan/week")
    def week(user_id: User):
        return planner.week_plan(db, user_id, today())

    @app.post("/plan/regenerate")
    def regenerate(user_id: User):
        planner.ensure_week(db, user_id, today(), regenerate=True)
        return planner.week_plan(db, user_id, today())

    @app.post("/plan/items/{item_id}/toggle")
    def toggle(item_id: int, user_id: User):
        if not db.one("SELECT 1 FROM plan_items WHERE id = ? AND user_id = ?", (item_id, user_id)):
            raise HTTPException(404, "Plan item not found")
        db.execute("UPDATE plan_items SET done = 1 - done WHERE id = ?", (item_id,))
        return planner.week_plan(db, user_id, today())

    # --- tests --------------------------------------------------------------

    @app.post("/tests")
    def create_test(req: TestRequest, user_id: User):
        try:
            test_id = engine.create_test(db, user_id, req.type, today(), topic_id=req.topic_id,
                                         paper_id=req.paper_id, chapter_id=req.chapter_id)
            return engine.get_test(db, user_id, test_id)
        except engine.TestError as e:
            raise test_error(e)

    @app.get("/tests")
    def list_tests(user_id: User):
        return engine.list_tests(db, user_id)

    @app.get("/tests/{test_id}")
    def get_test(test_id: int, user_id: User):
        try:
            return engine.get_test(db, user_id, test_id)
        except engine.TestError as e:
            raise test_error(e)

    @app.post("/tests/{test_id}/submit")
    def submit(test_id: int, submission: Submission, user_id: User):
        answers = {a.question_id: {"selected": a.selected, "time_ms": a.time_ms} for a in submission.answers}
        try:
            return engine.submit_test(db, user_id, test_id, answers, today())
        except engine.TestError as e:
            raise test_error(e)

    @app.get("/tests/{test_id}/result")
    def result(test_id: int, user_id: User):
        try:
            return engine.get_result(db, user_id, test_id)
        except engine.TestError as e:
            raise test_error(e)

    @app.get("/progress/summary")
    def progress_summary(user_id: User):
        return progress.summary(db, user_id, today())

    @app.get("/progress/topics")
    def progress_topics(user_id: User):
        return progress.topic_stats(db, user_id)

    # --- papers -------------------------------------------------------------

    @app.get("/psc/papers")
    def psc_papers(user_id: User, page: int = 0):
        cached = listing_cache.get(page)
        if cached and time.time() - cached[0] < LISTING_CACHE_SECONDS:
            listings = cached[1]
        else:
            try:
                listings = psc_source.attach_question_links(fetch_listing(page))
            except Exception as e:
                raise HTTPException(502, f"Could not reach keralapsc.gov.in: {e}")
            listing_cache[page] = (time.time(), listings)
        imported = {r["key_url"]: r for r in db.query("SELECT id, key_url, status FROM papers")}
        out = []
        for p in listings:
            d = p.to_dict()
            row = imported.get(p.key_url)
            d["paper_id"] = row["id"] if row else None
            d["status"] = row["status"] if row else None
            d["level"] = psc_source.paper_level(p.title)
            out.append(d)
        return out

    @app.post("/papers/import")
    def import_paper(req: ImportRequest, background: BackgroundTasks, user_id: User):
        if not req.key_url.startswith(psc_source.PSC_BASE_URL + "/"):
            raise HTTPException(400, "Only official keralapsc.gov.in papers can be imported")
        paper_id = importer.queue_paper(db, req.model_dump())
        row = db.one("SELECT * FROM papers WHERE id = ?", (paper_id,))
        if row["status"] == "queued":
            background.add_task(run_import, db, paper_id)
        return dict(row)

    thriller_cache: dict[str, tuple[float, list]] = {}

    @app.get("/thriller/papers")
    def thriller_papers(user_id: User):
        cached = thriller_cache.get("posts")
        if cached and time.time() - cached[0] < LISTING_CACHE_SECONDS:
            posts = cached[1]
        else:
            try:
                posts = fetch_thriller()
            except Exception as e:
                raise HTTPException(502, f"Could not reach pscthriller.com: {e}")
            thriller_cache["posts"] = (time.time(), posts)
        imported = {r["key_url"]: r for r in db.query("SELECT id, key_url, status FROM papers")}
        out = []
        for p in posts:
            d = p.to_dict()
            row = imported.get(p.url)
            d["paper_id"] = row["id"] if row else None
            d["status"] = row["status"] if row else None
            out.append(d)
        return out

    @app.post("/papers/import-thriller")
    def import_thriller(req: ThrillerImport, background: BackgroundTasks, user_id: User):
        if not req.url.startswith(psc_thriller.BASE + "/"):
            raise HTTPException(400, "Only pscthriller.com posts can be imported here")
        post = next((p for p in thriller_cache.get("posts", (0, []))[1] if p.url == req.url), None)
        listing = post.to_dict() if post else {"title": req.url.rsplit("/", 1)[-1], "url": req.url}
        paper_id = importer.queue_thriller(db, listing)
        row = db.one("SELECT * FROM papers WHERE id = ?", (paper_id,))
        if row["status"] == "queued":
            background.add_task(run_thriller_import, db, paper_id)
        return dict(row)

    @app.post("/papers/upload")
    async def upload_paper(
        user_id: User,
        background: BackgroundTasks,
        title: Annotated[str, Form(min_length=1, max_length=200)],
        paper: Annotated[list[UploadFile], File(description="Question paper: one PDF or photos of the pages")],
        key: Annotated[list[UploadFile] | None, File(description="Answer key: PDF or photos (optional)")] = None,
        booklet: Annotated[str, Form(pattern="^[ABCD]$")] = "A",
    ):
        async def read(files: list[UploadFile]) -> list[tuple[bytes, str]]:
            out = []
            for f in files:
                data = await f.read()
                media_type = "application/pdf" if data.startswith(b"%PDF") else (f.content_type or "")
                if media_type != "application/pdf" and media_type not in importer.IMAGE_TYPES:
                    raise HTTPException(400, f"{f.filename}: upload a PDF or JPG/PNG photo")
                out.append((data, media_type))
            return out

        files = await read(paper)
        key_files = await read(key or [])
        if len(files) + len(key_files) > MAX_UPLOAD_FILES:
            raise HTTPException(400, f"Upload at most {MAX_UPLOAD_FILES} files")
        if sum(len(d) for d, _ in files + key_files) > MAX_UPLOAD_BYTES:
            raise HTTPException(400, "Files are too large (30 MB total at most)")
        if sum(mt == "application/pdf" for _, mt in files) > 1:
            raise HTTPException(400, "Upload the question paper as one PDF, or as photos")
        paper_id = importer.queue_upload(db, user_id, title.strip())
        background.add_task(run_upload, db, paper_id, files, key_files, booklet)
        return dict(db.one("SELECT * FROM papers WHERE id = ?", (paper_id,)))

    @app.get("/papers")
    def papers(user_id: User):
        rows = db.query("SELECT * FROM papers WHERE owner_user_id IS NULL OR owner_user_id = ? "
                        "ORDER BY id DESC", (user_id,))
        return [dict(r) for r in rows]

    @app.post("/papers/sync")
    def sync_now(user_id: User, background: BackgroundTasks):
        if not sync.state["running"]:
            background.add_task(sync.run_sync, db, fetch_listing, run_import,
                                thriller_fetch=fetch_thriller, thriller_import=run_thriller_import)
        return sync.state

    @app.get("/papers/sync")
    def sync_status(user_id: User):
        return sync.state

    @app.get("/papers/{paper_id}")
    def paper(paper_id: int, user_id: User):
        row = db.one("SELECT * FROM papers WHERE id = ? AND (owner_user_id IS NULL OR owner_user_id = ?)",
                     (paper_id, user_id))
        if not row:
            raise HTTPException(404, "Paper not found")
        data = dict(row)
        data["attempts"] = [engine.test_summary(t) for t in db.query(
            "SELECT * FROM tests WHERE user_id = ? AND paper_id = ? ORDER BY id DESC", (user_id, paper_id))]
        return data

    # --- mentor -------------------------------------------------------------

    @app.post("/mentor/chat")
    def chat(req: ChatRequest, user_id: User):
        try:
            return mentor.chat(db, user_id, req.text, today())
        except ai.AIError as e:
            raise HTTPException(503, str(e))

    @app.get("/mentor/history")
    def chat_history(user_id: User):
        return mentor.history(db, user_id)

    return app


app = create_app()
