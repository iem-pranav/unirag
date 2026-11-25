# * End-to-end eval: every main question through pipeline.answer(), scored step by step.
# * Real LLM calls. Run: python eval/run_eval.py [ids...] [--cache off|record|replay] [--mlflow]
import sys
from collections import defaultdict

from eval_set import (
    GOLD,
    QUESTIONS,
    cell_to_text,
    fact_in_answer,
    load_jsonl,
    setup_llm,
    short,
    sql_part_ok,
    stop_on_daily_limit,
)
from retrieval_eval import is_hit, retrieval_facts
from tracking import log_run, take_flag

from unirag.pipeline import answer

# * The end status each question must reach.
EXPECTED_STATUS = {"not_answerable": "not_found", "guest_refusal": "refused"}
COLUMNS = ["routing", "sql", "retrieval", "exact", "status"]


def facts_for(q: dict, gold: dict[str, dict]) -> list[str]:
    # * Pure SQL questions: the gold rows are the answer. Joint: hand-checked answer facts.
    if q["question_type"] == "sql":
        g = gold.get(q["id"])
        if g is None or g["gold_sql"] != q["gold_sql"]:
            raise SystemExit(f"{q['id']}: gold.jsonl is stale. Run: python eval/build_gold.py")
        return q["expected_facts"] + g["facts"]
    return q["expected_facts"]


def score(q: dict, a, gold: dict[str, dict]) -> tuple[dict[str, bool | None], list[str]]:
    # * Each check is True, False, or None (does not apply to this question).
    checks: dict[str, bool | None] = dict.fromkeys(COLUMNS)
    notes = []
    checks["routing"] = a.route == q["expected_route"]
    if not checks["routing"]:
        notes.append(f"route {a.route}, expected {q['expected_route']}")

    if q["gold_sql"]:
        got = [[cell_to_text(v) for v in row] for row in a.rows]
        checks["sql"] = a.sql is not None and sql_part_ok(q, gold[q["id"]]["rows"], got)
        if not checks["sql"]:
            notes.append(f"sql: {a.sql or 'no SQL result'} -> {got[:4]}")

    if q["question_type"] == "joint":
        docs = {s for s in q["expected_sources"] if s.endswith(".md")}
        _, rfacts = retrieval_facts(q)
        checks["retrieval"] = any(is_hit(h, docs, rfacts) for h in a.chunks)
        if not checks["retrieval"]:
            notes.append(f"retrieval: no chunk from {sorted(docs)} with {rfacts}")

    facts = facts_for(q, gold)
    if facts:
        missing = [f for f in facts if not fact_in_answer(f, a.text)]
        checks["exact"] = not missing
        if missing:
            notes.append(f"missing facts: {missing}")

    # * A question can override the default status of its type (n02: refused, not not_found).
    expected_status = q.get("expected_status") or EXPECTED_STATUS.get(
        q["question_type"], "answered"
    )
    checks["status"] = a.status == expected_status
    if not checks["status"]:
        notes.append(f"status {a.status}, expected {expected_status}")
    return checks, notes


def cell(results: list[bool | None]) -> str:
    scored = [r for r in results if r is not None]
    return f"{sum(scored)}/{len(scored)}" if scored else "-"


def main(only: set[str], track: bool = False) -> None:
    gold = {g["id"]: g for g in load_jsonl(GOLD)}
    questions = [q for q in load_jsonl(QUESTIONS) if not only or q["id"] in only]
    by_type: dict[str, list[dict]] = defaultdict(list)
    failures, infra = [], []
    tokens: dict[str, list[int]] = defaultdict(list)
    latency: dict[str, list[float]] = defaultdict(list)

    for q in questions:
        a = answer(q["question"], q["role"])
        stop_on_daily_limit(a.infra_detail)
        for step, n in a.tokens.items():
            tokens[step].append(n)
        for step, s in a.latency_s.items():
            latency[step].append(s)
        # ! No LLM reachable: count apart, do not score as a wrong answer.
        if a.infra_error:
            infra.append((q, a))
            by_type[q["question_type"]].append({"infra": True})
            print(f"{q['id']:<5} INFRA")
            continue
        checks, notes = score(q, a, gold)
        by_type[q["question_type"]].append(checks)
        ok = all(v is not False for v in checks.values())
        print(f"{q['id']:<5} {'PASS' if ok else 'FAIL'}  route={a.route:<5} status={a.status}")
        if not ok:
            failures.append((q, a, notes))

    rows = [*by_type.items(), ("ALL", [c for v in by_type.values() for c in v])]
    print(
        f"\n{'question_type':<16}{'n':>3}" + "".join(f"{c:>11}" for c in COLUMNS) + f"{'infra':>8}"
    )
    for qtype, results in rows:
        scored = [r for r in results if "infra" not in r]
        cells = "".join(f"{cell([r[c] for r in scored]):>11}" for c in COLUMNS)
        print(f"{qtype:<16}{len(results):>3}{cells}{len(results) - len(scored):>8}")

    print("\nper step (avg)    tokens   LLM secs")
    for step in ("router", "sql", "docs", "synthesis"):
        t = tokens.get(step, [])
        s = latency.get(step, [])
        avg_t = f"{sum(t) / len(t):.0f}" if t else "-"
        avg_s = f"{sum(s) / len(s):.2f}" if s else "-"
        print(f"  {step:<14}{avg_t:>8}{avg_s:>11}")
    totals = latency.get("total", [])
    p50, p95 = percentile(totals, 50), percentile(totals, 95)
    print(f"\nanswer latency    p50 {p50:.2f}s   p95 {p95:.2f}s")

    print(f"\nFailures ({len(failures)}):")
    for q, a, notes in failures:
        print(f"\n{q['id']} [{q['role']}] {q['question']}")
        print(f"  route: {a.route}   status: {a.status}   missing paths: {a.missing or '-'}")
        for note in notes:
            print(f"  - {note}")
        print(f"  answer: {a.text[:400]}")
    for q, a in infra:
        print(f"\nINFRA {q['id']} [{q['role']}] {q['question']}")
        for detail in a.infra_detail:
            print(f"  - {short(detail)}")

    if track:
        scored = [r for r in rows[-1][1] if "infra" not in r]
        metrics = {"infra": len(infra), "latency_p50_s": p50, "latency_p95_s": p95}
        for c in COLUMNS:
            checks = [r[c] for r in scored if r[c] is not None]
            if checks:
                metrics[c] = sum(checks) / len(checks)
        for step, t in tokens.items():
            metrics[f"tokens_avg_{step}"] = sum(t) / len(t)
        log_run("end_to_end", metrics, {"questions": len(questions)})


def percentile(values: list[float], p: int) -> float:
    # * Nearest-rank percentile; 0 when there is nothing to measure.
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[-(-p * len(ordered) // 100) - 1]


if __name__ == "__main__":
    track, args = take_flag(setup_llm(sys.argv[1:]))
    main(set(args), track)
