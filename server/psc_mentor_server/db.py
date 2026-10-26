import re
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

import psycopg
from psycopg_pool import ConnectionPool

SCHEMA_VERSION = 2

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    login TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS profiles (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    target_exam TEXT NOT NULL DEFAULT 'degree_prelims',
    daily_minutes INTEGER NOT NULL DEFAULT 120,
    exam_date TEXT,
    language TEXT NOT NULL DEFAULT 'en',
    diagnostic_test_id INTEGER
);

CREATE TABLE IF NOT EXISTS subjects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    weight INTEGER NOT NULL,
    position INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS topics (
    id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL REFERENCES subjects(id),
    name TEXT NOT NULL,
    position INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS papers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    paper_code TEXT,
    category_code TEXT,
    medium TEXT,
    test_date TEXT,
    uploaded_on TEXT,
    level TEXT NOT NULL DEFAULT 'general',
    source TEXT NOT NULL DEFAULT 'psc' CHECK (source IN ('psc', 'upload')),
    owner_user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    answer_source TEXT,
    question_url TEXT,
    key_url TEXT NOT NULL UNIQUE,
    key_type TEXT,
    status TEXT NOT NULL DEFAULT 'queued',
    error TEXT,
    question_count INTEGER NOT NULL DEFAULT 0,
    imported_at TEXT
);

CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL CHECK (type IN ('verified_pyq', 'pyq_derived', 'original_mock', 'uploaded')),
    topic_id TEXT NOT NULL REFERENCES topics(id),
    stem TEXT NOT NULL,
    options_json TEXT NOT NULL,
    answer_index INTEGER,
    explanation TEXT,
    difficulty INTEGER NOT NULL DEFAULT 2,
    lang TEXT NOT NULL DEFAULT 'en',
    source_paper_id INTEGER REFERENCES papers(id),
    source_qno INTEGER,
    verification TEXT NOT NULL DEFAULT 'unverified',
    stem_key TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_questions_topic ON questions(topic_id);
CREATE INDEX IF NOT EXISTS idx_questions_paper ON questions(source_paper_id);

-- Which questions make up each paper, in paper order (a question already in the
-- bank from another paper is linked rather than duplicated).
CREATE TABLE IF NOT EXISTS paper_questions (
    paper_id INTEGER NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    qno INTEGER NOT NULL,
    question_id INTEGER NOT NULL REFERENCES questions(id),
    PRIMARY KEY (paper_id, qno)
);

CREATE TABLE IF NOT EXISTS tests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type TEXT NOT NULL,
    title TEXT NOT NULL,
    topic_id TEXT,
    paper_id INTEGER,
    question_ids_json TEXT NOT NULL,
    duration_minutes INTEGER NOT NULL,
    negative_mark REAL NOT NULL,
    created_at TEXT NOT NULL,
    submitted_at TEXT,
    score REAL,
    max_score REAL,
    correct INTEGER,
    wrong INTEGER,
    skipped INTEGER
);
CREATE INDEX IF NOT EXISTS idx_tests_user ON tests(user_id);

CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    test_id INTEGER NOT NULL REFERENCES tests(id) ON DELETE CASCADE,
    question_id INTEGER NOT NULL REFERENCES questions(id),
    selected_index INTEGER,
    is_correct INTEGER,
    time_ms INTEGER,
    answered_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_attempts_user_question ON attempts(user_id, question_id);

CREATE TABLE IF NOT EXISTS revision (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    question_id INTEGER NOT NULL REFERENCES questions(id),
    due_on TEXT NOT NULL,
    stage INTEGER NOT NULL,
    PRIMARY KEY (user_id, question_id)
);

CREATE TABLE IF NOT EXISTS plan_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    week_start TEXT NOT NULL,
    day TEXT NOT NULL,
    kind TEXT NOT NULL,
    topic_id TEXT,
    minutes INTEGER NOT NULL,
    done INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_plan_user_week ON plan_items(user_id, week_start);

-- Most-viewed YouTube lessons per topic, cached because each search costs YouTube API quota.
CREATE TABLE IF NOT EXISTS topic_videos (
    topic_id TEXT NOT NULL REFERENCES topics(id),
    rank INTEGER NOT NULL,
    video_id TEXT NOT NULL,
    title TEXT NOT NULL,
    channel TEXT NOT NULL,
    views INTEGER NOT NULL,
    duration_seconds INTEGER NOT NULL,
    thumbnail TEXT,
    published_at TEXT,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (topic_id, rank)
);

-- When each topic was last searched, even if the search found nothing worth showing.
CREATE TABLE IF NOT EXISTS topic_video_fetches (
    topic_id TEXT PRIMARY KEY REFERENCES topics(id),
    fetched_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    test_id INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


IntegrityError = (sqlite3.IntegrityError, psycopg.IntegrityError)

# Tables whose INSERTs should report the new row's id.
_ID_TABLES = {"users", "papers", "questions", "tests", "attempts", "plan_items", "chat_messages"}


def open_database(target: str | Path, schema_url: str | None = None) -> "Database | PostgresDatabase":
    """A postgres:// URL opens Postgres; anything else is a SQLite file path (or ':memory:')."""
    if str(target).startswith(("postgres://", "postgresql://")):
        return PostgresDatabase(str(target), schema_url=schema_url)
    return Database(target)


class Database:
    """SQLite: one connection shared across threads, serialised with a lock."""

    def __init__(self, path: Path | str):
        if str(path) != ":memory:":
            path = Path(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            _set_aside_old_schema(path)
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.lock = threading.RLock()
        with self.lock:
            self.conn.executescript(SCHEMA)
            self.conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            self.conn.commit()

    def query(self, sql: str, params=()) -> list[sqlite3.Row]:
        with self.lock:
            return self.conn.execute(sql, params).fetchall()

    def one(self, sql: str, params=()) -> sqlite3.Row | None:
        with self.lock:
            return self.conn.execute(sql, params).fetchone()

    def execute(self, sql: str, params=()) -> int:
        """Run a write and return lastrowid."""
        with self.lock:
            cur = self.conn.execute(sql, params)
            self.conn.commit()
            return cur.lastrowid

    def executemany(self, sql: str, rows) -> None:
        with self.lock:
            self.conn.executemany(sql, rows)
            self.conn.commit()


class Row(dict):
    """A result row readable by column name or position, like sqlite3.Row."""

    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


def _row_factory(cursor):
    names = [c.name for c in cursor.description or []]
    return lambda values: Row(zip(names, values))


def _pg_sql(sql: str) -> str:
    """The app writes SQLite-style `?` placeholders; psycopg wants `%s` (and literal `%%`)."""
    return sql.replace("%", "%%").replace("?", "%s")


def _pg_schema() -> str:
    return (SCHEMA
            .replace("INTEGER PRIMARY KEY AUTOINCREMENT", "INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY")
            .replace("DEFAULT (datetime('now'))",
                     "DEFAULT (to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS'))"))


class PostgresDatabase:
    """Postgres (e.g. a free Neon database) for hosting, where the local disk doesn't last."""

    def __init__(self, url: str, schema_url: str | None = None):
        # Creating tables is a migration: Neon recommends the direct (unpooled) URL for it,
        # and the pooled one for everyday queries.
        with psycopg.connect(schema_url or url, autocommit=True) as conn:
            conn.execute(_pg_schema())
        self.pool = ConnectionPool(
            url, min_size=1, max_size=4, open=True,
            # prepare_threshold=None: Neon's pooled (PgBouncer) URLs can't keep prepared statements
            kwargs={"autocommit": True, "row_factory": _row_factory, "prepare_threshold": None},
            check=ConnectionPool.check_connection,  # hosted databases drop idle connections
        )

    def query(self, sql: str, params=()) -> list[Row]:
        with self.pool.connection() as conn:
            return conn.execute(_pg_sql(sql), params).fetchall()

    def one(self, sql: str, params=()) -> Row | None:
        with self.pool.connection() as conn:
            return conn.execute(_pg_sql(sql), params).fetchone()

    def execute(self, sql: str, params=()) -> int | None:
        """Run a write; for INSERTs into tables with an id, return the new id."""
        m = re.match(r"\s*INSERT\s+INTO\s+(\w+)", sql, re.IGNORECASE)
        returning = bool(m and m.group(1) in _ID_TABLES and "RETURNING" not in sql.upper())
        with self.pool.connection() as conn:
            cur = conn.execute(_pg_sql(sql) + (" RETURNING id" if returning else ""), params)
            if returning:
                row = cur.fetchone()
                return row["id"] if row else None
            return None

    def executemany(self, sql: str, rows) -> None:
        with self.pool.connection() as conn:
            conn.cursor().executemany(_pg_sql(sql), list(rows))

    def close(self) -> None:
        self.pool.close()


def _set_aside_old_schema(path: Path) -> None:
    """The single-student prototype database can't be upgraded in place; keep it as a backup."""
    if not path.exists():
        return
    conn = sqlite3.connect(str(path))
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        has_tables = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type = 'table'").fetchone()[0]
    finally:
        conn.close()
    if has_tables and version < SCHEMA_VERSION:
        stamp = datetime.now().strftime("%Y%m%d%H%M%S")
        path.rename(path.with_name(f"{path.stem}.v{version}-{stamp}.bak"))
