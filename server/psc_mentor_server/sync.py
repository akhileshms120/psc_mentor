"""Keeping the question bank fresh with the latest official PSC papers.

Scans the newest pages of the answer-key listing and imports general-studies
papers, degree-level posts first. Malayalam-medium papers need Claude to read
them, so without AI only English papers are taken.
"""

import os
import threading
import time
from datetime import datetime

from . import importer, psc_source
from .config import ai_enabled
from .db import Database

SYNC_PAGES = int(os.environ.get("PSC_SYNC_PAGES", "6"))
SYNC_LIMIT = int(os.environ.get("PSC_SYNC_PAPERS", "8"))
SYNC_INTERVAL_HOURS = 12

state = {"running": False, "last_run": None, "imported": 0, "failed": 0, "queued": 0, "error": None}
_lock = threading.Lock()


def _uploaded(listing: psc_source.PaperListing) -> datetime:
    try:
        return datetime.strptime(listing.uploaded_on or "", "%d-%m-%Y")
    except ValueError:
        return datetime.min


def select_candidates(listings: list[psc_source.PaperListing], known_keys: set[str], with_ai: bool,
                      limit: int = SYNC_LIMIT) -> list[psc_source.PaperListing]:
    mediums = {"English", "Malayalam"} if with_ai else {"English"}
    picked = [
        p for p in listings
        if p.question_url and p.key_url not in known_keys and p.medium in mediums
        and psc_source.paper_level(p.title) != "technical"
    ]
    # Prefer degree-level, then final keys over provisional, then newest.
    picked.sort(key=lambda p: (psc_source.paper_level(p.title) != "degree",
                               "final" not in (p.key_type or "").lower(),
                               -_uploaded(p).toordinal()))
    # The same booklet is often listed twice (provisional and final key); keep the first, i.e. final.
    seen: set[str] = set()
    unique = []
    for p in picked:
        if p.question_url not in seen:
            seen.add(p.question_url)
            unique.append(p)
    return unique[:limit]


def run_sync(db: Database, fetch=psc_source.fetch_answer_key_listing, run_import=importer.import_paper,
             pages: int = SYNC_PAGES, limit: int = SYNC_LIMIT) -> dict:
    if not _lock.acquire(blocking=False):
        return state
    try:
        state.update(running=True, error=None, imported=0, failed=0, queued=0)
        listings: list[psc_source.PaperListing] = []
        for page in range(pages):
            try:
                listings.extend(fetch(page))
            except Exception as e:
                state["error"] = f"Could not read PSC listing page {page}: {e}"
                break
        psc_source.attach_question_links(listings)
        known = {r["key_url"] for r in db.query("SELECT key_url FROM papers WHERE status != 'failed'")}
        chosen = select_candidates(listings, known, ai_enabled(), limit)
        state["queued"] = len(chosen)
        for listing in chosen:
            paper_id = importer.queue_paper(db, listing.to_dict())
            run_import(db, paper_id)
            status = db.one("SELECT status FROM papers WHERE id = ?", (paper_id,))["status"]
            state["imported" if status == "done" else "failed"] += 1
        state["last_run"] = datetime.now().isoformat(timespec="seconds")
        return state
    finally:
        state["running"] = False
        _lock.release()


def start_background_sync(db: Database) -> None:
    def loop():
        while True:
            try:
                run_sync(db)
            except Exception as e:  # keep the loop alive
                state["error"] = f"{type(e).__name__}: {e}"
            time.sleep(SYNC_INTERVAL_HOURS * 3600)

    threading.Thread(target=loop, daemon=True, name="psc-sync").start()
