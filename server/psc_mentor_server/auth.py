"""Accounts: sign-up, login and bearer-token sessions."""

import hashlib
import hmac
import re
import secrets
import threading
import time

from .db import Database, IntegrityError

MIN_PASSWORD = 6
# Once the server is on the internet, slow down password guessing on any one account.
MAX_FAILED_LOGINS = 10
FAILED_LOGIN_WINDOW = 15 * 60
_failed: dict[str, list[float]] = {}
_failed_lock = threading.Lock()
_SCRYPT = {"n": 2**14, "r": 8, "p": 1}


class AuthError(ValueError):
    pass


def normalise_login(login: str) -> str:
    """Accept an email address or a phone number; phones keep only their digits."""
    login = login.strip().lower()
    if "@" in login:
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", login):
            raise AuthError("Enter a valid email address.")
        return login
    digits = re.sub(r"\D", "", login)
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    if len(digits) != 10:
        raise AuthError("Enter a 10-digit mobile number or an email address.")
    return digits


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return f"scrypt${salt.hex()}${digest.hex()}"


def check_password(password: str, stored: str) -> bool:
    _, salt, digest = stored.split("$")
    candidate = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), **_SCRYPT)
    return hmac.compare_digest(candidate.hex(), digest)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _new_session(db: Database, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    db.execute("INSERT INTO sessions (token_hash, user_id) VALUES (?, ?)", (_token_hash(token), user_id))
    return token


def signup(db: Database, name: str, login: str, password: str, **profile) -> tuple[str, int]:
    name = name.strip()
    if not name:
        raise AuthError("Enter your name.")
    if len(password) < MIN_PASSWORD:
        raise AuthError(f"Password must be at least {MIN_PASSWORD} characters.")
    login = normalise_login(login)
    try:
        user_id = db.execute("INSERT INTO users (name, login, password_hash) VALUES (?, ?, ?)",
                             (name, login, hash_password(password)))
    except IntegrityError:
        raise AuthError("An account with this phone/email already exists. Log in instead.")
    fields = {k: v for k, v in profile.items() if v is not None}
    db.execute("INSERT INTO profiles (user_id) VALUES (?)", (user_id,))
    for key, value in fields.items():
        db.execute(f"UPDATE profiles SET {key} = ? WHERE user_id = ?", (value, user_id))
    return _new_session(db, user_id), user_id


def _recent_failures(login: str, now: float) -> list[float]:
    times = [t for t in _failed.get(login, []) if now - t < FAILED_LOGIN_WINDOW]
    _failed[login] = times
    return times


def login(db: Database, login: str, password: str) -> tuple[str, int]:
    try:
        login = normalise_login(login)
    except AuthError:
        raise AuthError("Wrong phone/email or password.")
    now = time.time()
    with _failed_lock:
        if len(_recent_failures(login, now)) >= MAX_FAILED_LOGINS:
            raise AuthError("Too many wrong passwords. Try again in 15 minutes.")
    row = db.one("SELECT id, password_hash FROM users WHERE login = ?", (login,))
    if not row or not check_password(password, row["password_hash"]):
        with _failed_lock:
            _failed.setdefault(login, []).append(now)
        raise AuthError("Wrong phone/email or password.")
    with _failed_lock:
        _failed.pop(login, None)
    return _new_session(db, row["id"]), row["id"]


def user_for_token(db: Database, token: str) -> int | None:
    row = db.one("SELECT user_id FROM sessions WHERE token_hash = ?", (_token_hash(token),))
    return row["user_id"] if row else None


def delete_account(db: Database, user_id: int, password: str) -> None:
    """Remove a student and everything they created, including their private uploads."""
    row = db.one("SELECT password_hash FROM users WHERE id = ?", (user_id,))
    if not row or not check_password(password, row["password_hash"]):
        raise AuthError("Wrong password.")
    uploads = [r["id"] for r in db.query("SELECT id FROM papers WHERE owner_user_id = ?", (user_id,))]
    db.execute("DELETE FROM attempts WHERE user_id = ?", (user_id,))
    db.execute("DELETE FROM revision WHERE user_id = ?", (user_id,))
    for paper_id in uploads:
        db.execute("DELETE FROM paper_questions WHERE paper_id = ?", (paper_id,))
        # A question that another paper also contains stays in the bank, detached from the upload.
        db.execute("UPDATE questions SET source_paper_id = NULL WHERE source_paper_id = ? "
                   "AND id IN (SELECT question_id FROM paper_questions)", (paper_id,))
        db.execute("DELETE FROM questions WHERE source_paper_id = ?", (paper_id,))
    db.execute("DELETE FROM users WHERE id = ?", (user_id,))  # cascades to sessions, tests, plan, chat, papers


def logout(db: Database, token: str) -> None:
    db.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))
