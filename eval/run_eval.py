# * Runs every eval question through answer() and prints routing accuracy and numeric exactness.
# * Run: python eval/run_eval.py   (needs eval/gold.jsonl from build_gold.py)
from collections import defaultdict
from dataclasses import dataclass

from eval_set import GOLD, QUESTIONS, fact_in_answer, load_jsonl


@dataclass
class Answer:
    route: str | None
    text: str


def answer(question: str, role: str) -> Answer:
    # TODO: swap in the real pipeline (Phases 5-6). The stub only lets the harness run end to end.
    return Answer(route=None, text="")


def facts_for(q: dict, gold: dict[str, dict]) -> list[str]:
    if not q["gold_sql"]:
        return q["expected_facts"]
    g = gold.get(q["id"])
    # ! Gold rows must come from the current gold_sql, never from an old run.
    if g is None or g["gold_sql"] != q["gold_sql"]:
        raise SystemExit(f"{q['id']}: gold.jsonl is stale. Run: python eval/build_gold.py")
    return q["expected_facts"] + g["facts"]


def pct(hits: int, total: int) -> str:
    return f"{hits}/{total} ({hits / total:.0%})" if total else "n/a"


def main() -> None:
    gold = {g["id"]: g for g in load_jsonl(GOLD)}
    results: dict[str, list[tuple[bool, bool | None]]] = defaultdict(list)

    for q in load_jsonl(QUESTIONS):
        facts = facts_for(q, gold)
        result = answer(q["question"], q["role"])
        route_ok = result.route == q["expected_route"]
        # TODO: not_answerable and guest_refusal have no facts. Score "says no" once answers exist.
        exact = all(fact_in_answer(f, result.text) for f in facts) if facts else None
        results[q["question_type"]].append((route_ok, exact))

    results["ALL"] = [r for rows in list(results.values()) for r in rows]
    print(f"{'question_type':<16}{'n':>3}  {'routing':<14}numeric exact")
    for qtype, rows in results.items():
        routing = pct(sum(ok for ok, _ in rows), len(rows))
        scored = [e for _, e in rows if e is not None]
        print(f"{qtype:<16}{len(rows):>3}  {routing:<14}{pct(sum(scored), len(scored))}")


if __name__ == "__main__":
    main()
