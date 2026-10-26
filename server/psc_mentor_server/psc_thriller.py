"""Question papers from PSC Thriller (pscthriller.com), a Blogger site that posts Kerala PSC papers.

Each post embeds one Google Drive PDF: the official PSC question paper (for bilingual papers,
an English page then its Malayalam page) with PSC's official answer key appended at the end.
So the questions and answers are PSC's own; we credit and link the post they came from.

Crawling is polite: the Blogger feed lists posts (robots.txt allows everything but /search),
requests are spaced out, and only question-paper posts are opened.
"""

import re
import time
from dataclasses import dataclass, asdict
from io import BytesIO

import httpx
from pypdf import PdfReader

from . import psc_source

BASE = "https://www.pscthriller.com"
FEED = BASE + "/feeds/posts/summary"
USER_AGENT = "Mozilla/5.0 (PSC Mentor study app; credits and links PSC Thriller posts)"
REQUEST_DELAY_SECONDS = 1.5
ORIGIN = "PSC Thriller"


@dataclass
class ThrillerPost:
    title: str
    url: str
    published: str
    paper_code: str | None
    level: str

    def to_dict(self) -> dict:
        return asdict(self)


def is_question_paper(title: str) -> bool:
    return bool(re.search(r"question\s*paper", title, re.IGNORECASE))


def paper_code(title: str) -> str | None:
    """'(54/2026)', 'Stage 1(56-2025)', '(85/26)', '(126/2026/OL)' -> '54/2026', '56/2025', '85/2026', ..."""
    m = re.search(r"\(\s*(\d{1,3})\s*[-/]\s*(\d{4}|\d{2})\b", title)
    if not m:
        return None
    year = m.group(2) if len(m.group(2)) == 4 else "20" + m.group(2)
    return f"{int(m.group(1))}/{year}"


def parse_feed(data: dict) -> list[ThrillerPost]:
    posts = []
    for e in data.get("feed", {}).get("entry", []):
        title = " ".join(e["title"]["$t"].split())
        if not is_question_paper(title):
            continue
        url = next((l["href"] for l in e.get("link", []) if l.get("rel") == "alternate"), None)
        if url:
            posts.append(ThrillerPost(title=title, url=url, published=e["published"]["$t"][:10],
                                      paper_code=paper_code(title), level=psc_source.paper_level(title)))
    return posts


def drive_file_id(post_html: str) -> str | None:
    m = re.search(r"drive\.google\.com/file/d/([\w-]{20,})", post_html)
    return m.group(1) if m else None


def drive_download_url(file_id: str) -> str:
    return f"https://drive.google.com/uc?export=download&id={file_id}"


@dataclass
class SplitPaper:
    question_text: str              # readable (English / Unicode) question pages only
    question_pages: list[int]       # 0-based indexes of all question pages
    unreadable_tail: list[int]      # legacy-font pages after the last readable one (e.g. the Malayalam section)
    key_text: str                   # the appended PSC answer key
    booklet: str
    final_key: bool


_WATERMARK = re.compile(r"^.*(?:www\.pscthriller\.com|t\.me/PSC_Thriller).*$", re.IGNORECASE | re.MULTILINE)


def _page_readable(text: str) -> bool:
    """English pages extract cleanly; legacy-font Malayalam pages come out as private-use glyphs."""
    words = re.findall(r"[A-Za-z]{3,}|[ഀ-ൿ]{2,}", text)
    junk = re.findall(r"[-À-ÿ]", text)
    return len(words) > 25 and len(junk) < len(words) * 0.2


def split_pdf(pdf: bytes) -> SplitPaper:
    pages = [_WATERMARK.sub("", p.extract_text() or "") for p in PdfReader(BytesIO(pdf)).pages]
    key_start = next((i for i, t in enumerate(pages) if re.search(r"(FINAL|PROVISIONAL)?\s*ANSWER\s*KEY", t)
                      and re.search(r"QUESTION\s*BOOKLET|Q\s*No", t, re.IGNORECASE)), len(pages))
    # The key often starts part-way down the last question page.
    question_pages, key_parts = list(range(key_start)), []
    if key_start < len(pages):
        head, _, tail = pages[key_start].partition("ANSWER KEY")
        before = re.split(r"(?:FINAL|PROVISIONAL)\s*$", head.rstrip())[0]
        if re.search(r"\(A\)", before):
            question_pages.append(key_start)
            pages[key_start] = before
        key_parts = ["ANSWER KEY" + tail] + pages[key_start + 1:]
    key_text = "\n".join(key_parts)
    readable_idx = [i for i in question_pages if _page_readable(pages[i])]
    readable = [pages[i] for i in readable_idx]
    last = readable_idx[-1] if readable_idx else -1
    tail_pages = [i for i in question_pages if i > last]
    header = pages[0] if pages else ""
    m = re.search(r"^\s*\d{1,3}/\d{4}\S*\s*\n\s*([A-D])\s*$", header, re.MULTILINE)
    return SplitPaper(question_text="\n".join(readable), question_pages=question_pages,
                      unreadable_tail=tail_pages, key_text=key_text,
                      booklet=m.group(1) if m else "A",
                      final_key="FINAL ANSWER KEY" in "\n".join(pages).upper())


def _client() -> httpx.Client:
    return httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=60, follow_redirects=True)


def fetch_posts(max_posts: int = 450) -> list[ThrillerPost]:
    posts: list[ThrillerPost] = []
    with _client() as client:
        start = 1
        while start <= max_posts:
            resp = client.get(FEED, params={"alt": "json", "max-results": 150, "start-index": start})
            resp.raise_for_status()
            data = resp.json()
            entries = data.get("feed", {}).get("entry", [])
            posts.extend(parse_feed(data))
            if len(entries) < 150:
                break
            start += 150
            time.sleep(REQUEST_DELAY_SECONDS)
    return posts


def fetch_paper_pdf(post_url: str) -> tuple[bytes, str]:
    """The post's PDF and its Drive download URL."""
    if not post_url.startswith(BASE + "/"):
        raise ValueError("Not a PSC Thriller post")
    with _client() as client:
        page = client.get(post_url)
        page.raise_for_status()
        file_id = drive_file_id(page.text)
        if not file_id:
            raise ValueError("This post has no question paper PDF.")
        time.sleep(REQUEST_DELAY_SECONDS)
        url = drive_download_url(file_id)
        resp = client.get(url)
        resp.raise_for_status()
        if not resp.content.startswith(b"%PDF"):
            raise ValueError("The post's Google Drive file is not a downloadable PDF.")
        return resp.content, url
