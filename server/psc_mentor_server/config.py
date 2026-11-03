import os
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("PSC_DATA_DIR", SERVER_ROOT / "data"))
DB_PATH = Path(os.environ.get("PSC_DB_PATH", DATA_DIR / "psc_mentor.db"))
# When set (e.g. a Neon Postgres URL), it is used instead of the SQLite file.
DATABASE_URL = os.environ.get("DATABASE_URL")
# Neon's direct connection, used only to create tables (falls back to DATABASE_URL).
DATABASE_URL_UNPOOLED = os.environ.get("DATABASE_URL_UNPOOLED")
PAPERS_DIR = DATA_DIR / "papers"

PSC_BASE_URL = "https://www.keralapsc.gov.in"
PSC_ANSWER_KEY_LIST = PSC_BASE_URL + "/answerkey_omrexams"

# YouTube Data API v3 key for the "most-viewed lesson videos" per topic.
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")


def ai_base_url() -> str | None:
    """The Qwen server's address, without the /v1 that the OpenAI-style paths add."""
    url = os.environ.get("PSC_AI_BASE_URL", "").rstrip("/").removesuffix("/v1")
    return url or None


def ai_api_key() -> str | None:
    return os.environ.get("PSC_AI_API_KEY") or None


def ai_enabled() -> bool:
    """AI features need the server's address and key; everything else works without them."""
    if os.environ.get("PSC_AI", "").lower() == "off":
        return False
    return bool(ai_base_url() and ai_api_key())
