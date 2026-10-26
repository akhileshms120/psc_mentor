# PSC Mentor

A personal mentor for the **Kerala PSC Degree Level Common Preliminary** exam (2024 syllabus:
100 questions, 75 minutes, −1/3 per wrong answer).

Two parts:

- `lib/` – Flutter app (Android, iOS, macOS, Windows)
- `server/` – Python backend: accounts, question bank, PSC paper sync & uploads, test engine, strength report, AI mentor

## How a student uses it

1. **Create an account** with a mobile number or email and a password, plus daily study time, exam date and language.
2. **Take the diagnostic mock:** 100 questions laid out like the real exam (History 10, Geography 5, Economics 5,
   Civics 5, Constitution 5, Arts/Literature/Sports 10, Computer 5, Science & Tech 5, Arithmetic 10,
   Mental Ability 10, English 20, Malayalam 10), drawn from the newest official PSC papers first.
3. **Strength report:** each section is rated Strong (≥70%), Average (50–69%) or Weak (<50%), with an
   estimated score, the marks it could gain, and weak/strong topics.
4. **Time plan:** the weekly study time is shared out in proportion to *marks × (1 − accuracy + 0.15)*,
   so weak, high-mark sections get the most time and strong sections still get some practice.
   The weekly plan is built from that: ~30-minute topic blocks Mon–Sat (weakest topics first,
   one block per section per day), a daily test, revision, a weekly test on Sunday and a full
   mock on the last Sunday of the month. It updates as the student takes more tests.
5. **Upload your own paper:** a PDF or photos of a PSC or coaching paper, with or without an answer key.
   It becomes a timed test, and every attempt can be reviewed question by question. Without a key,
   the AI works out the answers (labelled "AI-answered"). Uploads are private to the student.
6. **Mentor chat:** the AI mentor (Gemini) sees the strength report and plan, and can create tests, show real PYQs and re-plan.
7. **Top YouTube lessons:** every topic (Study tab, and each study block on Home) lists the 3 most-viewed
   Kerala PSC lessons on YouTube, at least 3 minutes long and mentioning PSC, with view counts.
   Needs `YOUTUBE_API_KEY` (Google Cloud → enable *YouTube Data API v3* → Credentials → API key).
   Results are cached for 7 days per topic: a search costs 100 of YouTube's free 10,000 daily units.

### Latest questions from the internet
The server checks keralapsc.gov.in at startup and every 12 hours. It imports the newest
general-studies papers with their answer keys, degree-level posts first (University Assistant, SI/Excise Inspector,
Secretariat Assistant…), and skips technical posts. Tests prefer real PYQs from the newest degree-level papers.
Most of these papers are Malayalam-medium with legacy fonts, so **the AI (Gemini) is required to read them**:
without an API key the sync finds nothing to import, and the starter bank of 86 questions is all there is.

## Run the backend

The app needs the server running first, or it shows "Cannot reach the PSC Mentor server".
Easiest way (keep this terminal open while you use the app):

```bash
./scripts/run_server.sh
```

Or step by step:

```bash
cd server
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
export GEMINI_API_KEY=...                  # optional, enables the AI features (Google AI Studio key)
.venv/bin/uvicorn psc_mentor_server.main:app --host 0.0.0.0 --port 8000
```

Data is stored in `server/data/` (SQLite database + downloaded PDFs). Tests: `.venv/bin/python -m pytest`.

AI provider: **Google Gemini** when `GEMINI_API_KEY` (or `GOOGLE_API_KEY`) is set — model
`PSC_GEMINI_MODEL` (default `gemini-3.5-flash`), backups `PSC_GEMINI_FALLBACKS`
(default `gemini-3.6-flash,gemini-3.5-flash-lite`) used when Google says a model is overloaded.
Anthropic Claude is used instead when only `ANTHROPIC_API_KEY` is set (`PSC_CLAUDE_MODEL`, default
`claude-opus-5-5`); `PSC_AI_PROVIDER=gemini|claude` forces one.

Settings (environment variables): `PSC_DATA_DIR`, `PSC_DB_PATH`, `PSC_AI=off` to disable AI, `PSC_AUTO_SYNC=off` to stop automatic paper
import, `PSC_SYNC_PAGES` (listing pages to scan, default 6) and `PSC_SYNC_PAPERS` (papers per run, default 8).

A database from the earlier single-student version is renamed to `*.bak` on first start and a fresh one is created.

## Host the backend on Render (free)

Render's free plan wipes the server's disk on every restart and puts it to sleep after 15 idle
minutes (the first request then takes up to a minute). Render's own free Postgres is deleted after
30 days. So keep the data in a free **Neon** Postgres database and run the code on **Render**:

1. **Database:** a Neon project is linked (`neon.ts`, `.neon`). `neon deploy` writes its two connection
   strings into `.env.local` (git-ignored, contains the password): `DATABASE_URL` (pooled, host has
   `-pooler`, used for queries) and `DATABASE_URL_UNPOOLED` (direct, used only to create tables).
2. **Code on GitHub:** create an empty GitHub repository and push this folder to it.
3. **Render:** dashboard → **New → Blueprint** → choose the repository. `render.yaml` sets everything up.
   When asked, paste the two values from `.env.local` into `DATABASE_URL` and `DATABASE_URL_UNPOOLED`,
   and (optionally) your Google Gemini key into `GEMINI_API_KEY`. Deploy.
4. **Check:** open `https://<your-service>.onrender.com/health`. It should show `{"ok":true,...}`.
5. **Point the app at it:** either enter that URL in the app under *Server settings*, or build it in:

   ```bash
   flutter build apk --dart-define=PSC_API_URL=https://<your-service>.onrender.com
   ```

Some networks block Postgres's port 5432 (this happens on many home and office connections), so the
server may not reach Neon from your computer even though it works from Render. Locally, just leave
`DATABASE_URL` unset to use SQLite.

The server works with both databases: `DATABASE_URL` set → Postgres, not set → the local SQLite file.
To run the tests against Postgres: `TEST_DATABASE_URL=postgresql://... .venv/bin/python -m pytest`.

Anyone with the URL can create an account. With `GEMINI_API_KEY` set, every account uses your
Gemini quota, so watch your usage in Google AI Studio.

## Run the app

```bash
flutter pub get
flutter run            # pick a device
```

The app talks to `http://localhost:8000` (Android emulator: `http://10.0.2.2:8000`). On a real
phone, set the server address in Home → settings to `http://<your-computer-ip>:8000`.
Plain HTTP is allowed for local development; put the server behind HTTPS before publishing.

Tests: `flutter test`.

## Build commands

```bash
flutter build apk            # Android (or: flutter build appbundle)
flutter build ios            # requires macOS + Xcode
flutter build macos          # requires macOS + Xcode
flutter build windows        # requires Windows + Visual Studio C++ tools
```

## Important

- AI keys (Gemini or Anthropic) stay on the server. Never put them in the Flutter app.
- Only official `keralapsc.gov.in` files can be imported.
- Answer keys marked "provisional" can still change. Re-import after PSC publishes the final key.
- Subject weights for the monthly mock live in `server/psc_mentor_server/syllabus.py`. They
  approximate the common preliminary pattern, so adjust them to your exam's notified syllabus.

See `docs/ARCHITECTURE.md` for the design.
