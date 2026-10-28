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
# Pinned: in testing (Oct 2026) "gemini-flash-latest" pointed at an overloaded preview that timed
# out, and Pro models had no free-tier quota. gemini-3.5-flash answered reliably in 2-4 s.
GEMINI_MODEL = os.environ.get("PSC_GEMINI_MODEL", "gemini-3.5-flash")
# Tried in order when the main model is overloaded (503/504) or out of quota (429). On the free
# tier each model has its own daily request allowance (20/day for gemini-3.6-flash in testing).
GEMINI_FALLBACKS = [m.strip() for m in os.environ.get(
    "PSC_GEMINI_FALLBACKS", "gemini-3.6-flash,gemini-3.5-flash-lite,gemini-3.1-flash-lite").split(",") if m.strip()]
# Reading question papers needs a full Flash model: in testing, flash-lite models invented options
# and swapped whole questions when transcribing Malayalam pages. No lite models here.
GEMINI_READER_MODELS = [m.strip() for m in os.environ.get(
    "PSC_GEMINI_READER_MODELS", "gemini-3.5-flash,gemini-3-flash-preview,gemini-3.6-flash").split(",") if m.strip()]


# YouTube Data API v3 key for the "most-viewed lesson videos" per topic.
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")


# OpenAI-compatible AI service; APInex (api.apinex.bond) by default. Any provider with the
# OpenAI chat-completions API works: set PSC_AI_BASE_URL, the key and the model names.
AI_BASE_URL = os.environ.get("PSC_AI_BASE_URL", "https://api.apinex.bond/v1").rstrip("/")
AI_MODEL = os.environ.get("PSC_AI_MODEL", "free/kimi-k3")
AI_FALLBACKS = [m.strip() for m in os.environ.get(
    "PSC_AI_FALLBACKS", "free/gemini-3.8-flash,free/deepseek-v4.1-flash").split(",") if m.strip()]
# Reading papers and writing textbook questions need models that read Malayalam page images well.
AI_READER_MODELS = [m.strip() for m in os.environ.get(
    "PSC_AI_READER_MODELS", "free/kimi-k3,free/gemini-3.8-flash").split(",") if m.strip()]


def apinex_api_key() -> str | None:
    return os.environ.get("APINEX_API_KEY") or os.environ.get("PSC_AI_API_KEY")


def google_api_key() -> str | None:
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")


def _anthropic_credentials() -> bool:
    # The SDK also picks up an `ant auth login` profile, so a missing env var
    # alone doesn't mean there are no credentials.
    return bool(
        os.environ.get("ANTHROPIC_API_KEY")
        or os.environ.get("ANTHROPIC_AUTH_TOKEN")
        or (Path.home() / ".config" / "anthropic").exists()
    )


def ai_provider() -> str | None:
    """'apinex', 'gemini', 'claude', or None. PSC_AI_PROVIDER picks one explicitly; otherwise
    the first key found in that order is used."""
    if os.environ.get("PSC_AI", "").lower() == "off":
        return None
    explicit = os.environ.get("PSC_AI_PROVIDER", "").lower()
    if explicit in ("apinex", "gemini", "claude"):
        return explicit
    if apinex_api_key():
        return "apinex"
    if google_api_key():
        return "gemini"
    if _anthropic_credentials():
        return "claude"
    return None


def ai_enabled() -> bool:
    """AI features need a provider; everything else works without one."""
    return ai_provider() is not None
