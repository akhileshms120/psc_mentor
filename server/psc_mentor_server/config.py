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

CLAUDE_MODEL = os.environ.get("PSC_CLAUDE_MODEL", "claude-opus-5-5")


def ai_enabled() -> bool:
    """Claude features need credentials; everything else works without them.

    The SDK also picks up an `ant auth login` profile, so a missing env var
    alone doesn't mean there are no credentials.
    """
    if os.environ.get("PSC_AI", "").lower() == "off":
        return False
    return bool(
        os.environ.get("ANTHROPIC_API_KEY")
        or os.environ.get("ANTHROPIC_AUTH_TOKEN")
        or (Path.home() / ".config" / "anthropic").exists()
    )
