# * Runs every gold_sql on the DB and saves the result rows and facts to eval/gold.jsonl.
# * Run after loading data: python eval/build_gold.py
import json

from eval_set import GOLD, QUESTIONS, cell_to_text, load_jsonl, rows_to_facts, run_gold

from unirag.db import connect


def main() -> None:
    gold = []
    with connect() as conn:
        for q in load_jsonl(QUESTIONS):
            if not q["gold_sql"]:
                continue
            rows = run_gold(conn, q)
            if not rows:
                raise SystemExit(f"{q['id']}: gold_sql returned no rows")
            gold.append(
                {
                    "id": q["id"],
                    "gold_sql": q["gold_sql"],
                    "rows": [[cell_to_text(v) for v in row] for row in rows],
                    "facts": rows_to_facts(rows),
                }
            )
    GOLD.write_text("".join(json.dumps(g) + "\n" for g in gold), encoding="utf-8")
    print(f"Wrote {len(gold)} gold results to {GOLD.name}")


if __name__ == "__main__":
    main()
