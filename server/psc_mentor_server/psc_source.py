"""Reading the official Kerala PSC website: answer-key listings, answer keys and papers.

Everything here is pure parsing so it can be tested with saved fixtures; the
network calls live in `fetch_*` helpers.
"""

import re
from dataclasses import dataclass, asdict
from io import BytesIO
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from pypdf import PdfReader

from .config import PSC_ANSWER_KEY_LIST, PSC_BASE_URL

USER_AGENT = "Mozilla/5.0 (PSC Mentor study app)"
LETTERS = "ABCD"


@dataclass
class PaperListing:
    title: str
    paper_code: str | None
    category_code: str | None
    medium: str | None
    test_date: str | None
    key_type: str | None
    question_url: str | None
    key_url: str
    uploaded_on: str | None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ParsedQuestion:
    number: int
    stem: str
    options: list[str]


def _search(pattern: str, text: str) -> str | None:
    m = re.search(pattern, text, re.IGNORECASE)
    return m.group(1).strip() if m else None


def parse_listing_details(details: str) -> dict:
    """Pull paper code, medium, category and date out of the free-text details cell."""
    return {
        "paper_code": _search(
            r"Question\s*Paper\s*Code\s*:?\s*(.+?)(?=\s+(?:Question|Cat|Category|Name|Date)\b|$)",
            details,
        ),
        "medium": _search(r"Medium\s*:\s*([A-Za-z]+)", details)
        or _search(r"([A-Za-z]+)\s+Medium", details),
        "category_code": _search(r"Cat(?:egory)?\.?\s*Code\s*:?\s*([\d/]+)", details),
        "test_date": _search(r"Date\s*Of\s*Test\s*:?\s*([\w-]+)", details),
    }


def parse_answer_key_listing(html: str) -> list[PaperListing]:
    soup = BeautifulSoup(html, "html.parser")
    papers: list[PaperListing] = []
    for row in soup.select("tbody tr"):
        title_cell = row.select_one("td.views-field-title")
        key_cell = row.select_one("td.views-field-field-file")
        if not title_cell or not key_cell or not key_cell.find("a"):
            continue
        details_cell = row.select_one("td.views-field-body")
        type_cell = row.select_one("td.views-field-term-node-tid")
        question_cell = row.select_one("td.views-field-field-omr-question-paper")
        date_cell = row.select_one("td.views-field-created")
        details = " ".join(details_cell.get_text(" ").split()) if details_cell else ""
        question_link = question_cell.find("a") if question_cell else None
        papers.append(
            PaperListing(
                title=" ".join(title_cell.get_text(" ").split()),
                key_type=type_cell.get_text(strip=True) if type_cell else None,
                question_url=urljoin(PSC_BASE_URL, question_link["href"]) if question_link else None,
                key_url=urljoin(PSC_BASE_URL, key_cell.find("a")["href"]),
                uploaded_on=date_cell.get_text(strip=True) if date_cell else None,
                **parse_listing_details(details),
            )
        )
    return papers


# Posts recruited through the Degree Level Common Preliminary exam.
DEGREE_POSTS = ("DEGREE LEVEL", "DEGREE PRELIM", "UNIVERSITIES", "KAS ", "SECRETARIAT", "SUB INSPECTOR", "SI OF POLICE",
                "EXCISE INSPECTOR", "ASSISTANT JAILOR", "SPECIAL BRANCH", "AUDITOR", "PSC ASSISTANT",
                "ASSISTANT INFORMATION OFFICER", "COMMON PRELIMINARY")
# Other general-studies papers (10th/12th level) whose GK, maths and English still help.
GENERAL_POSTS = ("PRELIMINARY", "CLERK", "LAST GRADE", "VILLAGE FIELD ASSISTANT", "POLICE CONSTABLE",
                 "CIVIL EXCISE", "BEAT FOREST", "FIRE AND RESCUE", "PEON", "WATCHMAN", "ATTENDER",
                 "SALESMAN", "SERGEANT", "STOREMAN", "STORE MAN", "OFFICE ATTENDANT", "TYPIST",
                 "ASSISTANT SALESMAN", "FIELD OFFICER", "PRISON OFFICER", "WARDER", "FOREST GUARD",
                 "JUNIOR ASSISTANT", "VEO", "10TH LEVEL", "PLUS TWO", "12TH LEVEL", "PRELIMS")


def paper_level(title: str) -> str:
    """'degree', 'general' or 'technical', from the post name."""
    t = title.upper()
    if any(k in t for k in DEGREE_POSTS):
        return "degree"
    if any(k in t for k in GENERAL_POSTS):
        return "general"
    return "technical"


def _code_key(code: str | None) -> str | None:
    """'092/2026-M', '92-26 M' and '092/26 - M' all name the same booklet."""
    if not code:
        return None
    m = re.match(r"\s*0*(\d+)\s*[/-]\s*(?:20)?(\d{2})\s*(?:-?\s*([A-Z]))?", code.upper())
    return "-".join(p for p in m.groups() if p) if m else code.upper()


def attach_question_links(papers: list[PaperListing]) -> list[PaperListing]:
    """Final keys are often listed without the paper; borrow it from the provisional row."""
    links = {_code_key(p.paper_code): p.question_url for p in papers if p.question_url and p.paper_code}
    for p in papers:
        if not p.question_url:
            p.question_url = links.get(_code_key(p.paper_code))
    return papers


def booklet_code(question_url: str | None) -> str:
    """Question booklets are named like `qn-092-2026-M-A.pdf` or `090-2026-A.pdf`."""
    if question_url:
        m = re.search(r"[-_ ]([A-D])\.pdf$", question_url, re.IGNORECASE)
        if m:
            return m.group(1).upper()
    return "A"


def parse_answer_key(text: str, booklet: str = "A") -> dict[int, int | None]:
    """Map question number -> answer index (0-3) for one booklet; None means deleted (X)."""
    column = LETTERS.index(booklet)
    answers: dict[int, int | None] = {}
    for m in re.finditer(r"(?m)^\s*(\d{1,3})((?:\s+[A-DX]){1,4})\s*$", text):
        letters = m.group(2).split()
        if column >= len(letters):
            continue
        letter = letters[column]
        answers[int(m.group(1))] = None if letter == "X" else LETTERS.index(letter)
    return answers


_NOISE_LINE = re.compile(
    r"^\s*(\[?P\.?T\.?O\.?\]?|\d{1,3}|\d{2,3}[/-]\d{2,4}(?:-[A-Z])?\s*[A-D]?|"
    r"Maximum\s*:.*|Time\s*:.*|SPACE FOR ROUGH WORK.*)\s*$",
    re.IGNORECASE,
)


def clean_paper_text(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if not _NOISE_LINE.match(line))


def looks_readable(text: str) -> bool:
    """Malayalam papers use legacy non-Unicode fonts that extract as gibberish."""
    words = re.findall(r"[A-Za-z]{3,}|[ഀ-ൿ]{2,}", text)
    junk = re.findall(r"[À-ÿŒ-Ÿ]", text)
    return len(words) > 200 and len(junk) < len(words) * 0.05


def _tidy(fragment: str) -> str:
    return re.sub(r"[\s_–—-]{3,}$", "", " ".join(fragment.split())).strip()


def _parse_from(text: str, pos: int, expected: int) -> list[ParsedQuestion]:
    starts: list[tuple[int, int]] = []
    for n in range(1, expected + 1):
        m = re.compile(rf"(?:^|\n)\s*{n}\.\s").search(text, pos)
        if not m:
            break
        starts.append((n, m.start()))
        pos = m.end()

    questions: list[ParsedQuestion] = []
    for i, (n, start) in enumerate(starts):
        end = starts[i + 1][1] if i + 1 < len(starts) else len(text)
        block = re.sub(rf"^\s*{n}\.\s", "", text[start:end].strip())
        split = _split_options(block)
        if split:
            questions.append(ParsedQuestion(n, *split))
    return questions


def _split_options(block: str) -> tuple[str, list[str]] | None:
    """Find (A)..(D) in order, so "Both (A) and (B)" inside option D stays intact."""
    marks, pos = [], 0
    for letter in LETTERS:
        i = block.find(f"({letter})", pos)
        if i == -1:
            return None
        marks.append(i)
        pos = i + 3
    stem = _tidy(block[: marks[0]])
    bounds = marks + [len(block)]
    options = [_tidy(block[bounds[k] + 3 : bounds[k + 1]]) for k in range(4)]
    if not stem or not all(options):
        return None
    return stem, options


def parse_question_paper(text: str, expected: int = 100) -> list[ParsedQuestion]:
    """Split extracted English paper text into numbered four-option questions.

    The instructions page is also a numbered list, so every "1." is tried as
    the start of the paper and the reading that yields most questions wins.
    """
    text = clean_paper_text(text)
    candidates = [m.start() for m in re.finditer(r"(?:^|\n)\s*1\.\s", text)]
    best: list[ParsedQuestion] = []
    for pos in candidates:
        parsed = _parse_from(text, pos, expected)
        if len(parsed) > len(best):
            best = parsed
    return best


def pdf_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _client() -> httpx.Client:
    return httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=60, follow_redirects=True)


def fetch_answer_key_listing(page: int = 0) -> list[PaperListing]:
    with _client() as client:
        resp = client.get(PSC_ANSWER_KEY_LIST, params={"tid": "All", "page": page})
        resp.raise_for_status()
        return parse_answer_key_listing(resp.text)


def fetch_pdf(url: str) -> bytes:
    if not url.startswith(PSC_BASE_URL + "/"):
        raise ValueError("Only official keralapsc.gov.in files can be imported")
    with _client() as client:
        resp = client.get(url)
        resp.raise_for_status()
        if not resp.content.startswith(b"%PDF"):
            raise ValueError("Downloaded file is not a PDF")
        return resp.content
