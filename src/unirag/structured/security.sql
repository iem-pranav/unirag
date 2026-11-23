-- * Database-side safety for the app user (unirag_ro). Applied by load_data after every load.
-- ! This is the real boundary. The SQL guard is a first check; these rules hold even if it fails.

-- * Row-level security: on student tables the app user sees only the current student's rows.
-- * The app sets app.student_id per transaction (SET LOCAL). Not set or empty (guest) = no rows.
ALTER TABLE students ENABLE ROW LEVEL SECURITY;
ALTER TABLE enrollments ENABLE ROW LEVEL SECURITY;
ALTER TABLE fee_ledger ENABLE ROW LEVEL SECURITY;

CREATE POLICY own_rows ON students FOR SELECT TO unirag_ro
    USING (student_id = current_setting('app.student_id', true));
CREATE POLICY own_rows ON enrollments FOR SELECT TO unirag_ro
    USING (student_id = current_setting('app.student_id', true));
CREATE POLICY own_rows ON fee_ledger FOR SELECT TO unirag_ro
    USING (student_id = current_setting('app.student_id', true));

-- ! Without this, a query could call set_config() and switch itself to another student.
REVOKE EXECUTE ON FUNCTION set_config(text, text, boolean) FROM PUBLIC;

-- * Own rank in the branch, for the Merit Scholarship ("top 5 students of each branch by CGPA").
-- * The view runs as its owner (admin, not bound by RLS), so the rank is over the whole branch,
-- * but the outer WHERE returns only the current student's row.
-- ! security_barrier stops a caller's WHERE from being pushed inside the view, which could leak
-- ! other students' rows through a function with side effects.
CREATE VIEW student_branch_rank WITH (security_barrier = true) AS
SELECT student_id, branch, cgpa, branch_rank
FROM (
    SELECT student_id, branch, cgpa,
           RANK() OVER (PARTITION BY branch ORDER BY cgpa DESC) AS branch_rank
    FROM students
    WHERE year_of_study BETWEEN 2 AND 4 AND cgpa IS NOT NULL
) ranked
WHERE student_id = current_setting('app.student_id', true);

COMMENT ON VIEW student_branch_rank IS 'The current student''s CGPA rank within their branch, among students in years 2-4 with a CGPA. Rank 1 = highest CGPA. Only the asking student''s own row is visible.';
GRANT SELECT ON student_branch_rank TO unirag_ro;
