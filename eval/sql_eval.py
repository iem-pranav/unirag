# * SQL execution accuracy: run text-to-SQL on every gold_sql question, compare rows with gold.
# * Calls the real LLM, so it is not part of pytest. Run: python eval/sql_eval.py
import sys
import time
from collections import defaultdict

from eval_set import GOLD, QUESTIONS, cell_to_text, load_jsonl, rows_match

from unirag.config.settings import get_settings
from unirag.db import connect
from unirag.structured.text_to_sql import answer_sql


def main(only: set[str]) -> None:
    tolerance = get_settings().number_tolerance
    gold = {g["id"]: g for g in load_jsonl(GOLD)}
    questions = [q for q in load_jsonl(QUESTIONS) if q["gold_sql"]]
    # * Optional ids on the command line run just those, e.g. python eval/sql_eval.py s06
    questions = [q for q in questions if not only or q["id"] in only]
    by_type: dict[str, list[bool]] = defaultdict(list)
    failures = []

    print(f"{'id':<5}{'type':<7}{'result':<7}{'tries':<7}{'secs':<7}{'tokens':<8}model")
    with connect() as conn:
        for i, q in enumerate(questions):
            if i:
                time.sleep(get_settings().eval_pause_s)
            result = answer_sql(conn, q["question"], q["role"])
            got = [[cell_to_text(v) for v in row] for row in result.rows]
            passed = result.ok and rows_match(gold[q["id"]]["rows"], got, tolerance)
            by_type[q["question_type"]].append(passed)

            calls = result.llm_calls
            secs = sum(c.latency_s for c in calls)
            tokens = sum(c.prompt_tokens + c.completion_tokens for c in calls)
            models = ", ".join(sorted({c.model.split("/", 1)[0] for c in calls})) or "-"
            verdict = "PASS" if passed else "FAIL"
            print(f"{q['id']:<5}{q['question_type']:<7}{verdict:<7}{result.attempts:<7}"
                  f"{secs:<7.1f}{tokens:<8}{models}")  # fmt: skip
            for c in calls:
                if c.fallback_reason:
                    print(f"     fallback: {c.fallback_reason}")
            if not passed:
                why = result.error if not result.ok else f"rows differ: got {got[:5]}"
                failures.append((q, result.sql, why, gold[q["id"]]["rows"]))

    print(f"\n{'question_type':<16}SQL execution accuracy")
    for qtype, results in [*by_type.items(), ("ALL", [r for v in by_type.values() for r in v])]:
        print(f"{qtype:<16}{sum(results)}/{len(results)} ({sum(results) / len(results):.0%})")

    print(f"\nFailures ({len(failures)}):")
    for q, sql, why, expected in failures:
        print(f"\n{q['id']} [{q['role']}] {q['question']}")
        print(f"  SQL:      {sql}")
        print(f"  why:      {why}")
        print(f"  expected: {expected}")


if __name__ == "__main__":
    main(set(sys.argv[1:]))
