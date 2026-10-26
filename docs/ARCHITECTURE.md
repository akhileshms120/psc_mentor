# PSC Mentor architecture

## Frontend (`lib/`)
- Flutter / Dart, one codebase for Android, iOS, macOS and Windows
- Adaptive navigation: bottom bar on phones, navigation rail on wide screens
- Tabs: Home (today's plan, stats, week), Study (syllabus + mastery), Tests, PYQ, Mentor, Progress; Profile from Home
- `core/api.dart` – HTTP client; `Api.changes` notifies open screens to reload after a test, import or chat
- `core/models.dart` – typed views of the backend JSON
- `features/tests/test_runner.dart` – timed test screen and answer review

## Backend (`server/psc_mentor_server/`)
Python + FastAPI + SQLite. Single student for now. Add accounts before hosting it for many users.

| Module | Responsibility |
|---|---|
| `syllabus.py` | Subjects, topics, mock weights, negative mark |
| `seed_questions.py` | Starter bank of static-fact questions |
| `psc_source.py` | Parse the keralapsc.gov.in answer-key listing, answer-key PDFs and English question papers |
| `importer.py` | Download → read key → parse paper locally or with Claude → tag topics → store |
| `engine.py` | Build tests per type, fill gaps with generated questions, score with negative marking |
| `progress.py` | Topic accuracy, weak topics, streak, spaced-revision queue |
| `planner.py` | Weekly plan generation and completion tracking |
| `ai.py` | All Claude calls: tagging, PDF extraction, question generation, chat |
| `mentor.py` | Mentor agent: system prompt, student context, tools (create_test, pyq_examples, replan_week) |
| `main.py` | HTTP API |

## API
- `GET /health`, `GET|PUT /student`, `GET /syllabus`, `GET /today`
- `GET /plan/week`, `POST /plan/regenerate`, `POST /plan/items/{id}/toggle`
- `POST /tests` `{type: topic|daily|weekly|monthly|mistakes|paper, topic_id?, paper_id?}`
- `GET /tests`, `GET /tests/{id}` (answers hidden until submitted), `POST /tests/{id}/submit`, `GET /tests/{id}/result`
- `GET /progress/summary`, `GET /progress/topics`
- `GET /psc/papers?page=N` (live official listing), `POST /papers/import`, `GET /papers`, `GET /papers/{id}`
- `POST /mentor/chat`, `GET /mentor/history`

## Question types
- `verified_pyq` – from an official paper; `verification` is `final_key` or `provisional_key`
- `pyq_derived` – Claude-written in the style of real PYQs on that topic
- `original_mock` – seed questions, or Claude-written when no PYQs exist for the topic

## AI
Claude (`claude-opus-5-5` by default) is called server-side only, with structured JSON output
for extraction/generation, prompt caching on the system prompt, and server-side refusal fallback.
English papers are parsed without AI; Malayalam papers use legacy non-Unicode fonts, so the
PDF is sent to Claude to read.

## Next steps
- Accounts + auth (JWT) and PostgreSQL when hosting for many students
- Scheduled import of new answer keys, and re-import when a provisional key becomes final
- The older `/previous-question-papers` archive (papers without answer keys)
- Current-affairs feed, push reminders for daily/weekly tests
