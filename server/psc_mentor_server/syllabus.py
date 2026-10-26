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


# What each topic covers, from the official 2024 Degree Level Common Preliminary syllabus.
# Shown to students and given to the AI when it writes or tags questions.
TOPIC_DETAILS: dict[str, str] = {
    "history.kerala_history": "Arrival of Europeans and their contributions; Travancore from Marthanda Varma to "
                              "Sree Chithira Thirunal; national movement in Kerala; literary sources of Kerala history.",
    "history.kerala_renaissance": "Social and religious reform movements in Kerala: reformers, organisations, "
                                  "satyagrahas and their leaders.",
    "history.kerala_post_1956": "United Kerala movement; political and social history of Kerala after 1956.",
    "history.medieval_india": "Medieval India: political history, administrative reforms and contributions; "
                              "establishment of British rule.",
    "history.freedom_struggle": "First War of Independence; formation of the INC; Swadeshi movement; social reform "
                                "movements; newspapers, literature and art of the freedom struggle; Gandhi and the "
                                "national movement; extremist movement; independence.",
    "history.post_independence": "Post-independence India: state reorganisation; development in science, education "
                                 "and technology; foreign policy; political history after 1951.",
    "history.world_history": "Glorious Revolution in England; American War of Independence; French, Russian and "
                             "Chinese revolutions; political history after the Second World War; UNO and other "
                             "international organisations.",
    "geography.world_physical": "Earth's structure, atmosphere, rocks, landforms; pressure belts and winds; "
                                "temperature and seasons; global warming and pollution; maps, topographic maps and "
                                "signs; remote sensing and GIS; oceans and their movements; continents and nations.",
    "geography.india": "India: physiography, states, northern mountains, rivers, northern plains, peninsular "
                       "plateau, coastal plains; climate, natural vegetation, agriculture, minerals and industries, "
                       "energy sources; road, water, rail and air transport.",
    "geography.kerala": "Kerala: physiography, districts, rivers, climate, natural vegetation, wildlife, agriculture "
                        "and research centres, minerals and industries, energy sources, transport.",
    "economics.planning": "National income and per capita income; factors of production; economic sectors; Indian "
                          "economic planning, Five Year Plans, NITI Aayog.",
    "economics.finance": "Types and functions of economic institutions; Reserve Bank and its functions; public "
                         "revenue, tax and non-tax revenue; public expenditure; budget; fiscal policy; consumer "
                         "protection and rights.",
    "civics.public_admin": "Public administration; bureaucracy; Indian and State civil services; e-governance; "
                           "Information Commission and RTI Act; Lokpal and Lokayukta.",
    "civics.government": "Government: executive, judiciary, legislature; elections; political parties.",
    "civics.welfare_laws": "Human rights and human rights organisations; consumer protection; watershed "
                           "management; labour and employment; national rural employment policies; land reforms; "
                           "protection of women, children and the elderly; social welfare and social security; "
                           "socio-economic statistics.",
    "constitution.making_preamble": "Constituent Assembly; the Preamble.",
    "constitution.rights_duties": "Fundamental Rights; Directive Principles; Fundamental Duties; citizenship.",
    "constitution.institutions": "Constitutional amendments; Panchayati Raj; constitutional institutions and their "
                                 "functions; emergency; Union, State and Concurrent Lists.",
    "culture.arts": "Kerala's major visual and performing arts: origin, spread, practice; famous places, "
                    "institutions, people and artists.",
    "culture.literature": "Malayalam literary movements, first works and authors; major works; pen names; "
                          "characters; famous lines; beginnings of Malayalam journalism; awards and honours; "
                          "Malayali Jnanpith winners; Malayalam cinema's origin, milestones and national awards.",
    "culture.sports": "Sportspersons of Kerala, India and the world and their honours; major awards and trophies; "
                      "number of players and terms in major games; Olympics, Paralympics and Winter Olympics; "
                      "Asian, Afro-Asian, Commonwealth and SAF Games; National Games; national games of countries.",
    "culture.festivals": "Kerala's major festivals and the places linked to them; cultural centres, places of "
                         "worship, cultural leaders and their contributions.",
    "computer.hardware_software": "Input, output and memory devices; system and application software; operating "
                                  "systems; word processors, spreadsheets, databases, presentations, image editors; "
                                  "basics of programming (instruction types).",
    "computer.networks_internet": "LAN, WAN, MAN; network devices (media, switch, hub, router, bridge, gateway); "
                                  "WWW, e-mail, search engines; social media; browsers and HTML basics.",
    "computer.cyber_law": "Types of cyber crimes; the IT Act and other laws (awareness level).",
    "science.everyday": "Nature and scope of science and technology; national policy on S&T and innovation; basics "
                        "of everyday science.",
    "science.health": "Human body; public health and community medicine; food and nutrition; health care.",
    "science.space_defence": "Indian space programme, ISRO and its satellite programmes; DRDO; S&T institutions in "
                             "India; prominent Indian scientists.",
    "science.energy_environment": "India's energy needs, resources and policy; renewable and non-renewable energy; "
                                  "nuclear policy; environmental issues, laws, policies and treaties; biodiversity; "
                                  "climate change; Western Ghats; forest and wildlife laws; pollution and global "
                                  "warming; biotechnology, green technology and nanotechnology.",
    "arithmetic.numbers": "Numbers and basic operations; fractions and decimals; laws of exponents.",
    "arithmetic.percentage": "Percentage; profit and loss.",
    "arithmetic.interest": "Simple and compound interest.",
    "arithmetic.ratio_average": "Ratio and proportion; average.",
    "arithmetic.time_work_distance": "Time and distance; time and work.",
    "arithmetic.mensuration_progressions": "Perimeter, area and volume of geometric figures; progressions.",
    "mental_ability.series_analogy": "Number and letter series; word, letter and number analogies; odd man out.",
    "mental_ability.coding_signs": "Coding and decoding; problems with mathematical signs; number observation.",
    "mental_ability.relations_direction": "Family relations; sense of direction; position and ranking tests.",
    "mental_ability.clock_calendar": "Clock: time and angles, mirror images; date and calendar; clerical ability.",
    "english.grammar_basics": "Parts of speech; agreement of subject and verb; articles; prepositions; correlatives; "
                              "degrees of comparison.",
    "english.verbs_tenses": "Primary and modal auxiliaries; question tags; infinitives and gerunds; tenses; tenses in "
                            "conditional sentences.",
    "english.transformation": "Types and interchange of sentences; direct and indirect speech; active and passive "
                              "voice; correction of sentences.",
    "english.vocabulary": "Synonyms; antonyms; one-word substitutes; singular and plural; gender; collective nouns.",
    "english.words_idioms": "Word formation with prefixes and suffixes; compound words; phrasal verbs; foreign "
                            "words and phrases; words often confused; spelling; idioms; common abbreviations.",
    "malayalam.correct_usage": "പദശുദ്ധി, വാക്യശുദ്ധി.",
    "malayalam.word_meaning": "പര്യായം, വിപരീതപദം, ഒറ്റപ്പദം, സമാനപദം.",
    "malayalam.idioms_proverbs": "ശൈലികൾ, പഴഞ്ചൊല്ലുകൾ.",
    "malayalam.grammar": "സ്ത്രീലിംഗം, പുല്ലിംഗം; വചനം; ചേർത്തെഴുതുക; പിരിച്ചെഴുതുക; ഘടകപദം.",
    "malayalam.translation": "പരിഭാഷ (ഇംഗ്ലീഷ് വാക്യങ്ങൾ മലയാളത്തിലേക്ക്).",
    "special.technical": "Questions from post-specific technical papers.",
}


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
    """`id: Subject / Topic (covers ...)` list used in AI prompts."""
    rows = db.query(
        "SELECT t.id, s.name AS subject, t.name AS topic FROM topics t "
        "JOIN subjects s ON s.id = t.subject_id ORDER BY s.position, t.position"
    )
    return "\n".join(f"{r['id']}: {r['subject']} / {r['topic']} (covers: {TOPIC_DETAILS.get(r['id'], '')})"
                     for r in rows)
