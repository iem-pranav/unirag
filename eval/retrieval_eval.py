# * Retrieval eval: recall@3 and recall@5 for vector, keyword and hybrid search, plus every miss.
# * Run after ingest: python eval/retrieval_eval.py
from eval_set import QUESTIONS, fact_in_answer, load_jsonl

from unirag.db import connect
from unirag.unstructured.search import Hit, search

MODES = ["vector", "keyword", "hybrid"]
KS = [3, 5]


def retrieval_facts(q: dict) -> tuple[str, list[str]]:
    # * retrieval_facts is only for search scoring. Without it, use the answer facts.
    if "retrieval_facts" in q:
        return "retrieval_facts", q["retrieval_facts"]
    return "expected_facts", q["expected_facts"]


def is_hit(hit: Hit, docs: set[str], facts: list[str]) -> bool:
    # * Strip Markdown bold, so a fact like "8.0 or above" matches "**8.0 or above**".
    text = hit.content.replace("**", "")
    return hit.document in docs and any(fact_in_answer(f, text) for f in facts)


def main() -> None:
    questions = []
    for q in load_jsonl(QUESTIONS):
        docs = {s for s in q["expected_sources"] if s.endswith(".md")}
        if q["expected_route"] in {"docs", "both"} and docs:
            questions.append((q, docs, *retrieval_facts(q)))

    recall = {(m, k): 0 for m in MODES for k in KS}
    misses = []
    with connect() as conn:
        for q, docs, rule, facts in questions:
            for mode in MODES:
                hits = search(conn, q["question"], mode=mode, k=max(KS))
                first = next((i for i, h in enumerate(hits) if is_hit(h, docs, facts)), None)
                for k in KS:
                    recall[(mode, k)] += first is not None and first < k
                if first is None or first >= min(KS):
                    misses.append((mode, q, rule, facts, docs, hits, first))

    print(f"Scored {len(questions)} questions (route docs/both with a document source)\n")
    print(f"{'mode':<10}" + "".join(f"recall@{k:<6}" for k in KS))
    for mode in MODES:
        cells = "".join(f"{recall[(mode, k)]}/{len(questions):<10}" for k in KS)
        print(f"{mode:<10}{cells}")

    print("\nFact rule per question:")
    for q, _, rule, facts in questions:
        print(f"  {q['id']}  {rule:<16} {facts}")

    print(f"\nMisses at k={min(KS)} ({len(misses)}):")
    for mode, q, rule, facts, docs, hits, first in misses:
        found = "not in top 5" if first is None else f"found at rank {first + 1}"
        print(f"\n[{mode}] {q['id']}: {q['question']}  ({found})")
        print(f"  wants: {sorted(docs)} with one of {facts}  ({rule})")
        for i, h in enumerate(hits, 1):
            mark = "*" if is_hit(h, docs, facts) else " "
            print(f"  {mark}{i}. {h.document} | {h.heading.split(' > ', 1)[-1]}")


if __name__ == "__main__":
    main()
