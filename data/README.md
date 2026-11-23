# Data

Everything here is **synthetic**. It describes a fictional university, the **Aravali Institute of Technology (AIT)**. No real student, staff or institute data is used.

"Today" in this fake world is **2026-11-23** (middle of semester I of 2026-27).

## Tables (`data/seed/*.csv`)

| File | Rows | What it holds |
|---|---|---|
| `students.csv` | 240 | 20 students per branch (CE, IT, ENTC) per year, with CGPA and backlogs |
| `courses.csv` | 120 | Course catalogue for 8 semesters |
| `enrollments.csv` | 5,760 | Attendance, marks and grades per student per course |
| `fee_ledger.csv` | 1,650 | Fee items, amounts, due dates and payment status |
| `grants.csv` | 8 | Research and project grants |
| `grant_deadlines.csv` | 8 | Application windows for the 2026-27 cycle |
| `academic_calendar.csv` | 41 | Dated events of semester I 2026-27 |
| `placement_drives.csv` | 526 | Company drives, 5 years |
| `placement_offers_by_branch.csv` | 955 | Offers per drive split by branch (CE, IT, ENTC, PG) |

`schema.sql` has the PostgreSQL schema with a comment on every table and important column.

How they were made:
- `generate_tables.py` builds the first seven tables. It uses a fixed random seed, so the output is always the same. Run it with `python data/seed/generate_tables.py`.
- The two **placement tables** were generated once, using the *overall shape* of real yearly placement reports as a guide (company mix, branch split, package spread), then **randomly changed**: offer counts by about 20%, packages by about 7% (20% for very high packages). Treat them as realistic-looking, not as real statistics. The years are 2020-21, 2021-22, 2022-23, 2023-24 and 2025-26. There is no 2024-25.

### Deliberate design choices (they make the joint questions work)
- **Grant eligibility rules are only in the document** (`documents/09_research_grants_handbook.md`). **Deadlines are only in the table** (`grant_deadlines`). **Student CGPA, year, backlogs, attendance and fee status are only in the tables.** A question like "which grants can I apply for and when do they close?" needs all three.
- The AI and Data Research Fellowship rule mentions an ISE score. That needs a join from `students` to `enrollments` to `courses`.
- Overdue fees block hall tickets and grants. The rule is in the documents, the fee status is in `fee_ledger`.

## Documents (`data/documents/*.md`)

15 original documents for the fictional AIT, written in plain Markdown:

| File | Topic |
|---|---|
| 01 | Academic regulations: attendance, evaluation, grading, ATKT, degree |
| 02 | Examination rules: hall ticket, conduct, revaluation, grace marks |
| 03 | Admissions guide |
| 04 | Fee structure and refund policy |
| 05 | Hostel guide |
| 06 | Library guide |
| 07 | Co-curricular activities and activity points |
| 08 | Extra-curricular activities |
| 09 | Research and project grants handbook |
| 10 | Scholarships and financial aid |
| 11 | Placement policy |
| 12 | Placement highlights (numbers match the placement tables) |
| 13 | Campus IT and network services |
| 14 | Institute-industry partnership cell |
| 15 | How to read the academic calendar |

The documents were written in original words. They follow the topics and structure that real university rule books cover, but the rules, numbers, names and amounts are made up.
