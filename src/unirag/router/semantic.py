# * Baseline router: nearest example question by embedding similarity. No LLM. Route only.
from functools import lru_cache

from unirag.router.base import RouteDecision, other_student_check
from unirag.unstructured.embeddings import embed

# * (route, personal, example). personal=True means it reads the asker's own records,
# * so for a guest it becomes "none".
# ! Must not repeat any eval question (tests/test_router.py checks this).
EXAMPLES: list[tuple[str, bool, str]] = [
    # ---- sql: the asker's own records ----
    ("sql", True, "What grades did I get in semester 3?"),
    ("sql", True, "How much tuition have I paid this year?"),
    ("sql", True, "Which of my courses are still ongoing?"),
    ("sql", True, "What is my ISE score in Computer Networks?"),
    ("sql", True, "Is my development fee cleared?"),
    ("sql", True, "What was my total in Data Structures?"),
    ("sql", True, "Which semester am I in right now?"),
    # ---- sql: public tables ----
    ("sql", False, "Which companies offered more than 10 LPA in 2021-22?"),
    ("sql", False, "List the holidays in October."),
    ("sql", False, "When does the Embedded and Wireless grant open?"),
    ("sql", False, "How many credits is the Data Science course?"),
    ("sql", False, "Which courses are taught in semester 6 for CE?"),
    ("sql", False, "Total offers across all branches in 2020-21?"),
    ("sql", False, "When does semester II begin?"),
    # ---- docs: rules and procedures ----
    ("docs", False, "What is the passing mark for a theory course?"),
    ("docs", False, "What is the re-exam fee?"),
    ("docs", False, "Are visitors allowed inside hostel rooms?"),
    ("docs", False, "What is the dress code for placement interviews?"),
    ("docs", False, "How do I get a duplicate ID card?"),
    ("docs", False, "What does ATKT mean?"),
    ("docs", False, "How are hostel seats allotted?"),
    ("docs", False, "How are grant proposals scored by the committee?"),
    ("docs", False, "Who can join the Model UN club?"),
    ("docs", False, "Is there a plagiarism check for project reports?"),
    # ---- both: own records checked against a rule ----
    ("both", True, "Can I register for semester 5 with the credits I have?"),
    ("both", True, "Is my CGPA good enough for a distinction?"),
    ("both", True, "Do my backlogs block me from research grants?"),
    ("both", True, "Can I get the need-based fund with my pending dues?"),
    ("both", True, "Am I eligible for the Final-Year Project Funding?"),
    ("both", True, "Will my attendance let me get the merit scholarship?"),
    # ---- both: public data checked against a rule ----
    ("both", False, "Which open grants accept second-year students?"),
    ("both", False, "Which Group I companies came in 2023-24 and what are the Group I rules?"),
    # ---- none: off-topic or other students' records ----
    ("none", False, "Tell me a joke."),
    ("none", False, "What is the capital of France?"),
    ("none", False, "Recommend a good movie for tonight."),
    ("none", False, "List every student who failed a course."),
    ("none", False, "Who has the highest CGPA in IT?"),
    ("none", False, "What are my friend's marks in Physics?"),
]


@lru_cache
def _example_vectors() -> list[list[float]]:
    return embed([example for _, _, example in EXAMPLES])


def route_semantic(question: str, role: str) -> RouteDecision:
    if blocked := other_student_check(question, role):
        return blocked
    query = embed([question])[0]
    # * fastembed returns unit vectors, so the dot product is the cosine similarity.
    sims = [sum(a * b for a, b in zip(query, v, strict=True)) for v in _example_vectors()]
    best = max(range(len(sims)), key=sims.__getitem__)
    route, personal, example = EXAMPLES[best]
    if personal and role == "guest":
        return RouteDecision("none", reason=f"guest asks for personal records (like: {example})")
    return RouteDecision(route, reason=f"closest example {sims[best]:.2f}: {example}")
