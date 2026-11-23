# CLAUDE.md

Rules for working on UniRAG. Read `README.md` first. It is the plan.

## How to work

- **Phase by phase.** Follow the roadmap in `README.md`. Do one phase, then stop and show what was done. Do not start the next phase until I say so.
- **Eval comes first.** Do not skip Phase 2. Every later phase must be measured with the eval set.
- **Ask before big choices.** If something is unclear or the README does not cover it, ask a short question instead of guessing.
- **Do not commit or push** unless I ask.
- When a phase is done, tick its box in the README roadmap.

## Keep the code simple

- Write only the code that is really needed. No extra features, no "just in case" code, no unused helpers.
- Do not add a library if a few lines of plain Python do the job.
- Do not build abstractions until there are two real uses for them.
- Small files, small functions, clear names. One function does one thing.
- Do not add anything that is not in the README. If you think something is missing, suggest it and wait.
- Config values (model names, top-k, chunk size) go in the config file, not in the code.
- Never hardcode API keys. Use `.env`.

## Comments: simple, human, Better Comments style

Write comments like you are explaining to a friend. Short and plain. Explain **why**, not what the code already says.

Use these tags:

```python
# * Important idea or main step of the file
# ! Warning: something that can break or must not be changed
# ? Open question or something I should decide
# TODO: work that is still pending
# // old code kept only for a moment (delete it before finishing the phase)
```

Good:

```python
# ! Only SELECT is allowed. The LLM can write anything, so we check it before running.
# * Run SQL first, because the GPA is needed to check the grant rules.
```

Bad:

```python
# This function gets the user.   <- the code already says this
```

Rules:
- One short line is better than a paragraph.
- No comment on obvious lines.
- Each file starts with one `# *` line saying what the file is for.

## Data rules

- The data and documents in `data/` are **provided**. Do not regenerate or rewrite them unless I ask. If you find an error in them, tell me first.
- The university is **fictional (AIT)**. Never add a real college name, real people or real student data anywhere in the repo.
- Read `data/README.md` before Phase 1. It explains why some facts are only in tables and some only in documents. Do not duplicate them.
- Users have a **role**: a `student_id` or `guest`. Guests must never reach student tables (`students`, `enrollments`, `fee_ledger`).
- "Today" in the fake world is 2026-11-23. Use it for questions about deadlines and "upcoming" events.

## Safety rules (never break)

- SQL runs only through the SQL guard, with the read-only DB user.
- Only `SELECT`, only allowlisted tables, always a `LIMIT` and a timeout.
- Student-specific queries are always scoped to the asking student's ID.
- All data in this repo is synthetic. Never add real student data.

## Testing

- Write tests only for logic that can break: the SQL guard, the router output format, the number matching in eval.
- Do not write tests for trivial code.
- Before saying a phase is done, run it and show the result (test output or eval numbers).

## Style

- Python 3.11, type hints on function signatures.
- Format and lint with `ruff`.
- Plain Python modules. No LangChain or LlamaIndex.
