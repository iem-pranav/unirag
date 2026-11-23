# * The router's output type, plus the one safety check both routers share.
import re
from dataclasses import dataclass
from typing import Literal

Route = Literal["sql", "docs", "both", "none"]
ROUTES: set[str] = {"sql", "docs", "both", "none"}

STUDENT_ID = re.compile(r"\b\d{2}(?:CE|IT|ENTC)\d{3}\b", re.IGNORECASE)


@dataclass(frozen=True)
class RouteDecision:
    route: Route
    # * Short standalone sub-questions. Empty when that source is not used.
    sql_question: str = ""
    docs_question: str = ""
    reason: str = ""
    tokens: int = 0


def other_student_check(question: str, role: str) -> RouteDecision | None:
    # ! A student ID that is not the asker's own means someone else's records: always "none".
    # * Cheap and certain, so it runs before any model.
    for found in STUDENT_ID.findall(question):
        if found.upper() != role.upper():
            return RouteDecision("none", reason=f"asks about another student ({found})")
    return None
