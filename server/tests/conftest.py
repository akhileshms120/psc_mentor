import os
from datetime import date
from pathlib import Path

os.environ["PSC_DB_PATH"] = ":memory:"
os.environ["PSC_AI"] = "off"
os.environ["PSC_AUTO_SYNC"] = "off"

import pytest  # noqa: E402

from psc_mentor_server import auth  # noqa: E402
from psc_mentor_server.db import Database, PostgresDatabase  # noqa: E402
from psc_mentor_server.seed_questions import seed_questions  # noqa: E402
from psc_mentor_server.syllabus import seed_syllabus  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
# A Wednesday, so the week has study days before and after it.
TODAY = date(2026, 10, 28)


# Set TEST_DATABASE_URL=postgresql://... to run every test against Postgres instead of SQLite.
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


@pytest.fixture
def db():
    if TEST_DATABASE_URL:
        import psycopg
        with psycopg.connect(TEST_DATABASE_URL, autocommit=True) as conn:
            conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        database = PostgresDatabase(TEST_DATABASE_URL)
    else:
        database = Database(":memory:")
    seed_syllabus(database)
    seed_questions(database)
    yield database
    if TEST_DATABASE_URL:
        database.close()


@pytest.fixture
def user(db):
    _, user_id = auth.signup(db, "Anu", "9876543210", "secret123", daily_minutes=120)
    return user_id


@pytest.fixture
def fixture_text():
    return lambda name: (FIXTURES / name).read_text()
