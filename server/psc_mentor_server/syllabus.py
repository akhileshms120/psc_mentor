"""Kerala PSC Degree Level Common Preliminary syllabus (2024 notification).

Subject weights are the official marks out of 100; a full mock and the
diagnostic test use them as question counts. Current affairs has no separate
marks: the syllabus asks for it inside every section, so current-affairs
questions are tagged to the section they belong to.
"""

from .db import Database

EXAM_NAME = "Degree Level Preliminary"
EXAM_QUESTIONS = 100
EXAM_MINUTES = 75
NEGATIVE_MARK = 1 / 3

# (subject_id, name, marks, [(topic_suffix, topic_name), ...])
SYLLABUS: list[tuple[str, str, int, list[tuple[str, str]]]] = [
    ("history", "History", 10, [
        ("kerala_history", "Kerala: Europeans to Travancore & national movement"),
        ("kerala_renaissance", "Kerala: Social & religious reform movements"),
        ("kerala_post_1956", "Kerala: United Kerala & after 1956"),
        ("medieval_india", "India: Medieval India & arrival of the British"),
        ("freedom_struggle", "India: Freedom struggle & Gandhi"),
        ("post_independence", "India: After independence"),
        ("world_history", "World: Revolutions, World Wars & UNO"),
    ]),
    ("geography", "Geography", 5, [
        ("world_physical", "Basics of geography & the world"),
        ("india", "Indian geography"),
        ("kerala", "Kerala geography"),
    ]),
    ("economics", "Economics", 5, [
        ("planning", "National income, sectors & planning"),
        ("finance", "RBI, budget, taxes & fiscal policy"),
    ]),
    ("civics", "Civics", 5, [
        ("public_admin", "Public administration, RTI, Lokpal & e-governance"),
        ("government", "Executive, legislature, judiciary & elections"),
        ("welfare_laws", "Human rights, welfare & social legislation"),
    ]),
    ("constitution", "Indian Constitution", 5, [
        ("making_preamble", "Constituent Assembly & Preamble"),
        ("rights_duties", "Fundamental Rights, DPSP, Duties & Citizenship"),
        ("institutions", "Amendments, Panchayat Raj, bodies, emergency & lists"),
    ]),
    ("culture", "Arts, Literature, Culture & Sports", 10, [
        ("arts", "Kerala arts & art forms"),
        ("literature", "Malayalam literature, writers & awards"),
        ("sports", "Sports, games & sports awards"),
        ("festivals", "Festivals, cultural centres & cinema"),
    ]),
    ("computer", "Basics of Computer", 5, [
        ("hardware_software", "Hardware, software & operating systems"),
        ("networks_internet", "Networks, internet & social media"),
        ("cyber_law", "Cyber crimes & IT Act"),
    ]),
    ("science", "Science & Technology", 5, [
        ("everyday", "Everyday science"),
        ("health", "Human body, health & nutrition"),
        ("space_defence", "Space, defence & Indian scientists"),
        ("energy_environment", "Energy, environment & biotechnology"),
    ]),
    ("arithmetic", "Simple Arithmetic", 10, [
        ("numbers", "Numbers, fractions, decimals & exponents"),
        ("percentage", "Percentage, profit & loss"),
        ("interest", "Simple & compound interest"),
        ("ratio_average", "Ratio, proportion & average"),
        ("time_work_distance", "Time & work, time & distance"),
        ("mensuration_progressions", "Mensuration & progressions"),
    ]),
    ("mental_ability", "Mental Ability & Reasoning", 10, [
        ("series_analogy", "Series, analogy & odd man out"),
        ("coding_signs", "Coding-decoding & mathematical signs"),
        ("relations_direction", "Family relations, direction & ranking"),
        ("clock_calendar", "Clock, calendar & clerical ability"),
    ]),
    ("english", "General English", 20, [
        ("grammar_basics", "Parts of speech, articles, agreement & prepositions"),
        ("verbs_tenses", "Tenses, auxiliaries, question tags & conditionals"),
        ("transformation", "Voice, speech, sentence types & correction"),
        ("vocabulary", "Synonyms, antonyms & one-word substitutes"),
        ("words_idioms", "Idioms, phrasal verbs, spelling & word forms"),
    ]),
    ("malayalam", "Malayalam", 10, [
        ("correct_usage", "പദശുദ്ധി, വാക്യശുദ്ധി"),
        ("word_meaning", "പര്യായം, വിപരീതം, ഒറ്റപ്പദം"),
        ("idioms_proverbs", "ശൈലികൾ, പഴഞ്ചൊല്ലുകൾ"),
        ("grammar", "ലിംഗം, വചനം, ചേർത്തെഴുതുക, പിരിച്ചെഴുതുക"),
        ("translation", "പരിഭാഷ"),
    ]),
    # Questions from post-specific technical papers (lab technician, engineering...).
    # They stay available as full papers but never appear in prelims mocks.
    ("special", "Post-specific / Technical", 0, [
        ("technical", "Technical subject"),
    ]),
]


def topic_id(subject_id: str, suffix: str) -> str:
    return f"{subject_id}.{suffix}"


def all_topic_ids() -> list[str]:
    return [topic_id(s, t) for s, _, _, topics in SYLLABUS for t, _ in topics]


def seed_syllabus(db: Database) -> None:
    for s_pos, (subject_id, name, weight, topics) in enumerate(SYLLABUS):
        db.execute(
            "INSERT INTO subjects (id, name, weight, position) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET name = excluded.name, weight = excluded.weight, "
            "position = excluded.position",
            (subject_id, name, weight, s_pos),
        )
        for t_pos, (suffix, topic_name) in enumerate(topics):
            db.execute(
                "INSERT INTO topics (id, subject_id, name, position) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET name = excluded.name, position = excluded.position",
                (topic_id(subject_id, suffix), subject_id, topic_name, t_pos),
            )


def topic_catalog(db: Database) -> str:
    """Compact `id: Subject / Topic` list used in Claude prompts."""
    rows = db.query(
        "SELECT t.id, s.name AS subject, t.name AS topic FROM topics t "
        "JOIN subjects s ON s.id = t.subject_id ORDER BY s.position, t.position"
    )
    return "\n".join(f"{r['id']}: {r['subject']} / {r['topic']}" for r in rows)
