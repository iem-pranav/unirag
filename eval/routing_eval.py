# * Routing eval: score the semantic and LLM routers on all 70 questions (30 main + 40 routing).
# * The LLM router makes real calls, so it is not part of pytest.
# * Run: python eval/routing_eval.py [semantic|llm]   (no argument = both)
import sys
import time
from collections import Counter

from eval_set import QUESTIONS, ROUTING_QUESTIONS, load_jsonl

from unirag.config.settings import get_settings
from unirag.router.llm_router import route_llm
from unirag.router.semantic import route_semantic

ROUTERS = {"semantic": route_semantic, "llm": route_llm}
ORDER = ["sql", "docs", "both", "none"]


def pct(hits: int, total: int) -> str:
    return f"{hits}/{total} ({hits / total:.0%})" if total else "n/a"


def evaluate(name: str, questions: list[dict]) -> None:
    router = ROUTERS[name]
    # * Only the LLM router needs pacing for the Groq free tier.
    pause = get_settings().eval_pause_s if name == "llm" else 0
    if name == "semantic":
        router("warm up the embedding model", "guest")

    results = []
    for i, q in enumerate(questions):
        if pause and i:
            time.sleep(pause)
        start = time.perf_counter()
        decision = router(q["question"], q["role"])
        results.append((q, decision, time.perf_counter() - start))

    ok = [d.route == q["expected_route"] for q, d, _ in results]
    guest = [o for o, (q, _, _) in zip(ok, results, strict=True) if q["role"] == "guest"]
    student = [o for o, (q, _, _) in zip(ok, results, strict=True) if q["role"] != "guest"]
    secs = [s for *_, s in results]
    tokens = [d.tokens for _, d, _ in results]

    print(f"\n===== {name} router =====")
    print(f"accuracy  {pct(sum(ok), len(ok))}")
    print(f"guest     {pct(sum(guest), len(guest))}")
    print(f"student   {pct(sum(student), len(student))}")
    print(f"latency   avg {sum(secs) / len(secs):.2f}s, max {max(secs):.2f}s")
    print(f"tokens    avg {sum(tokens) / len(tokens):.0f} per question")

    counts = Counter((q["expected_route"], d.route) for q, d, _ in results)
    print("\nconfusion (rows = expected, columns = got)")
    print(f"{'':<8}" + "".join(f"{r:>7}" for r in ORDER))
    for expected in ORDER:
        print(f"{expected:<8}" + "".join(f"{counts[(expected, got)]:>7}" for got in ORDER))

    wrong = [(q, d) for (q, d, _), o in zip(results, ok, strict=True) if not o]
    print(f"\nwrong routes ({len(wrong)}):")
    for q, d in wrong:
        print(f"  {q['id']:<4} [{q['role']}] {q['question']}")
        print(f"       expected {q['expected_route']}, got {d.route}: {d.reason}")


def main(names: list[str]) -> None:
    keys = ("id", "question", "role", "expected_route")
    questions = [{k: q[k] for k in keys} for q in load_jsonl(QUESTIONS)]
    questions += load_jsonl(ROUTING_QUESTIONS)
    print(f"{len(questions)} questions")
    for name in names:
        evaluate(name, questions)


if __name__ == "__main__":
    main(sys.argv[1:] or list(ROUTERS))
