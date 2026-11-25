# * Routing eval: score the semantic and LLM routers on the main and routing-only questions.
# * The LLM router makes real calls, so it is not part of pytest.
# * Run: python eval/routing_eval.py [semantic|llm] [ids...] [--cache MODE] [--mlflow] [--gate]
# * --gate: exit 1 if accuracy is below eval.ci_min_routing_accuracy (CI, semantic router).
# * No router named = both. No ids = all questions.
import sys
import time
from collections import Counter

from eval_set import QUESTIONS, ROUTING_QUESTIONS, load_jsonl, setup_llm, short, stop_on_daily_limit
from tracking import log_run, take_flag

from unirag.config.settings import get_settings
from unirag.router.llm_router import route_llm
from unirag.router.semantic import route_semantic

ROUTERS = {"semantic": route_semantic, "llm": route_llm}
ORDER = ["sql", "docs", "both", "none"]


def pct(hits: int, total: int) -> str:
    return f"{hits}/{total} ({hits / total:.0%})" if total else "n/a"


def evaluate(name: str, questions: list[dict]) -> dict[str, float]:
    router = ROUTERS[name]
    if name == "semantic":
        router("warm up the embedding model", "guest")

    results = []
    for q in questions:
        start = time.perf_counter()
        decision = router(q["question"], q["role"])
        stop_on_daily_limit([decision.reason] if decision.infra_error else [])
        # * LLM router reports its own LLM time, so eval pacing is not counted as latency.
        secs = decision.latency_s if name == "llm" else time.perf_counter() - start
        results.append((q, decision, secs))

    # ! Infra errors (no LLM reachable) are counted apart, not as wrong routes.
    infra = [(q, d) for q, d, _ in results if d.infra_error]
    scored = [(q, d, s) for q, d, s in results if not d.infra_error]
    ok = [d.route == q["expected_route"] for q, d, _ in scored]
    guest = [o for o, (q, _, _) in zip(ok, scored, strict=True) if q["role"] == "guest"]
    student = [o for o, (q, _, _) in zip(ok, scored, strict=True) if q["role"] != "guest"]
    secs = [s for *_, s in scored] or [0.0]
    tokens = [d.tokens for _, d, _ in scored] or [0]

    print(f"\n===== {name} router =====")
    print(f"accuracy  {pct(sum(ok), len(ok))}")
    print(f"guest     {pct(sum(guest), len(guest))}")
    print(f"student   {pct(sum(student), len(student))}")
    print(f"infra     {len(infra)} (not scored)")
    print(f"latency   avg {sum(secs) / len(secs):.2f}s, max {max(secs):.2f}s")
    print(f"tokens    avg {sum(tokens) / len(tokens):.0f} per question")

    counts = Counter((q["expected_route"], d.route) for q, d, _ in scored)
    print("\nconfusion (rows = expected, columns = got)")
    print(f"{'':<8}" + "".join(f"{r:>7}" for r in ORDER))
    for expected in ORDER:
        print(f"{expected:<8}" + "".join(f"{counts[(expected, got)]:>7}" for got in ORDER))

    wrong = [(q, d) for (q, d, _), o in zip(scored, ok, strict=True) if not o]
    print(f"\nwrong routes ({len(wrong)}):")
    for q, d in wrong:
        print(f"  {q['id']:<4} [{q['role']}] {q['question']}")
        print(f"       expected {q['expected_route']}, got {d.route}: {d.reason}")
    for q, d in infra:
        print(f"  INFRA {q['id']}: {short(d.reason)}")
    return {
        f"{name}_accuracy": sum(ok) / len(ok) if ok else 0.0,
        f"{name}_guest_accuracy": sum(guest) / len(guest) if guest else 0.0,
        f"{name}_student_accuracy": sum(student) / len(student) if student else 0.0,
        f"{name}_infra": len(infra),
        f"{name}_latency_avg_s": sum(secs) / len(secs),
        f"{name}_tokens_avg": sum(tokens) / len(tokens),
    }


def gate(accuracy: float, minimum: float) -> None:
    # ! CI fails here when a change makes routing worse than the agreed floor.
    if accuracy < minimum:
        print(f"GATE FAILED: routing accuracy {accuracy:.1%} is below {minimum:.0%}")
        raise SystemExit(1)
    print(f"GATE OK: routing accuracy {accuracy:.1%} (minimum {minimum:.0%})")


def main(args: list[str]) -> None:
    track, args = take_flag(args)
    check = "--gate" in args
    args = [a for a in args if a != "--gate"]
    names = [a for a in args if a in ROUTERS] or list(ROUTERS)
    ids = {a for a in args if a not in ROUTERS}
    keys = ("id", "question", "role", "expected_route")
    questions = [{k: q[k] for k in keys} for q in load_jsonl(QUESTIONS)]
    questions += load_jsonl(ROUTING_QUESTIONS)
    questions = [q for q in questions if not ids or q["id"] in ids]
    print(f"{len(questions)} questions")
    metrics: dict[str, float] = {}
    for name in names:
        metrics |= evaluate(name, questions)
    if track:
        log_run("routing", metrics, {"routers": ",".join(names), "questions": len(questions)})
    if check:
        minimum = get_settings().ci_min_routing_accuracy
        for name in names:
            gate(metrics[f"{name}_accuracy"], minimum)


if __name__ == "__main__":
    main(setup_llm(sys.argv[1:]))
