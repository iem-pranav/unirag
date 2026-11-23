-- * Database schema for UniRAG (PostgreSQL 16).
-- * Table and column comments are used by the schema retriever, so keep them clear.
-- ! The app connects with a read-only user. Only the tables below are allowlisted.

CREATE TABLE students (
    student_id        TEXT PRIMARY KEY,
    full_name         TEXT NOT NULL,
    gender            CHAR(1) NOT NULL CHECK (gender IN ('M','F')),
    branch            TEXT NOT NULL CHECK (branch IN ('CE','IT','ENTC')),
    admission_year    INT NOT NULL,
    year_of_study     INT NOT NULL CHECK (year_of_study BETWEEN 1 AND 4),
    current_semester  INT NOT NULL,
    cgpa              NUMERIC(4,2),
    active_backlogs   INT NOT NULL DEFAULT 0,
    hostel_resident   BOOLEAN NOT NULL,
    admission_quota   TEXT NOT NULL
);
COMMENT ON TABLE students IS 'One row per current B.Tech student of the fictional institute (AIT).';
COMMENT ON COLUMN students.student_id IS 'Unique ID like 24IT007: admission year (2 digits) + branch + serial number.';
COMMENT ON COLUMN students.branch IS 'CE = Computer Engineering, IT = Information Technology, ENTC = Electronics and Telecommunication.';
COMMENT ON COLUMN students.year_of_study IS 'Current year: 1 = first year, 2 = second, 3 = third, 4 = final year.';
COMMENT ON COLUMN students.current_semester IS 'Semester in progress (odd, 1/3/5/7), as of 2026-11-23.';
COMMENT ON COLUMN students.cgpa IS 'CGPA on a 10-point scale from completed semesters. NULL for first-year students.';
COMMENT ON COLUMN students.active_backlogs IS 'Number of courses with grade F that are not cleared.';
COMMENT ON COLUMN students.admission_quota IS 'merit, institute, management or nri.';

CREATE TABLE courses (
    course_code  TEXT PRIMARY KEY,
    title        TEXT NOT NULL,
    branch       TEXT NOT NULL,
    semester     INT NOT NULL,
    credits      INT NOT NULL,
    course_type  TEXT NOT NULL CHECK (course_type IN ('theory','lab'))
);
COMMENT ON TABLE courses IS 'Course catalogue. First-year courses (semesters 1-2) are shared by all branches.';
COMMENT ON COLUMN courses.branch IS 'CE, IT, ENTC, or COMMON for first-year courses.';

CREATE TABLE enrollments (
    enrollment_id   INT PRIMARY KEY,
    student_id      TEXT NOT NULL REFERENCES students(student_id),
    course_code     TEXT NOT NULL REFERENCES courses(course_code),
    academic_year   TEXT NOT NULL,
    semester        INT NOT NULL,
    attendance_pct  INT,
    ise_marks       INT,
    grade_letter    TEXT,
    grade_point     INT,
    total_marks     INT,
    status          TEXT NOT NULL CHECK (status IN ('passed','backlog','ongoing'))
);
COMMENT ON TABLE enrollments IS 'One row per student per course per semester: attendance, marks and grades.';
COMMENT ON COLUMN enrollments.attendance_pct IS 'Attendance percentage in that course. For ongoing courses it is the value so far.';
COMMENT ON COLUMN enrollments.ise_marks IS 'In-Semester Exam marks out of 15. Only for ongoing theory courses.';
COMMENT ON COLUMN enrollments.grade_letter IS 'O, A+, A, B+, B, C, P or F. NULL while ongoing.';
COMMENT ON COLUMN enrollments.grade_point IS 'Grade point 0-10. NULL while ongoing.';
COMMENT ON COLUMN enrollments.total_marks IS 'Final marks out of 100. NULL while ongoing.';
COMMENT ON COLUMN enrollments.status IS 'passed, backlog (grade F, not cleared) or ongoing.';

CREATE TABLE fee_ledger (
    entry_id     INT PRIMARY KEY,
    student_id   TEXT NOT NULL REFERENCES students(student_id),
    academic_year TEXT NOT NULL,
    fee_type     TEXT NOT NULL,
    amount_due   INT NOT NULL,
    amount_paid  INT NOT NULL,
    due_date     DATE NOT NULL,
    paid_date    DATE,
    status       TEXT NOT NULL CHECK (status IN ('paid','partial','overdue'))
);
COMMENT ON TABLE fee_ledger IS 'Fee ledger: one row per fee item per student per academic year, amounts in rupees.';
COMMENT ON COLUMN fee_ledger.fee_type IS 'tuition_fee, development_fee, hostel_fee, caution_deposit or quota_fee.';
COMMENT ON COLUMN fee_ledger.status IS 'paid, partial (part payment made) or overdue (unpaid after due date).';

CREATE TABLE grants (
    grant_id        INT PRIMARY KEY,
    grant_name      TEXT NOT NULL,
    sponsor         TEXT NOT NULL,
    max_amount_inr  INT NOT NULL,
    grant_type      TEXT NOT NULL
);
COMMENT ON TABLE grants IS 'Research and project grants students can apply for. Eligibility rules are in the Research Grants Handbook document, not here.';

CREATE TABLE grant_deadlines (
    grant_id    INT NOT NULL REFERENCES grants(grant_id),
    cycle       TEXT NOT NULL,
    opens_on    DATE NOT NULL,
    closes_on   DATE NOT NULL,
    results_on  DATE,
    notes       TEXT,
    PRIMARY KEY (grant_id, cycle)
);
COMMENT ON TABLE grant_deadlines IS 'Application window for each grant in the 2026-27 cycle.';
COMMENT ON COLUMN grant_deadlines.closes_on IS 'Last date to apply.';

CREATE TABLE academic_calendar (
    event_id       INT PRIMARY KEY,
    semester_term  TEXT NOT NULL,
    event          TEXT NOT NULL,
    start_date     DATE NOT NULL,
    end_date       DATE NOT NULL,
    applies_to     TEXT NOT NULL
);
COMMENT ON TABLE academic_calendar IS 'Dated events of semester I 2026-27: exams, holidays, result dates.';
COMMENT ON COLUMN academic_calendar.event IS 'Event name. The exams themselves: end-semester exam rows contain "(ESE)", in-semester exam rows contain "(ISE)". Rows like "ESE answer-book assessment", "Open house for ISE answer books" or "ESE result declaration" are related activities, not exams.';
COMMENT ON COLUMN academic_calendar.applies_to IS 'Comma-separated year groups: FE, SE, TE, BE, PG, STAFF or ALL.';

CREATE TABLE placement_drives (
    drive_id         INT PRIMARY KEY,
    academic_year    TEXT NOT NULL,
    company          TEXT NOT NULL,
    package_lpa      NUMERIC(6,2) NOT NULL,
    recruiter_group  TEXT NOT NULL CHECK (recruiter_group IN ('I','II')),
    total_offers     INT NOT NULL,
    male_offers      INT NOT NULL,
    female_offers    INT NOT NULL
);
COMMENT ON TABLE placement_drives IS 'One row per company recruiting drive per year. Years available: 2020-21, 2021-22, 2022-23, 2023-24, 2025-26.';
COMMENT ON COLUMN placement_drives.package_lpa IS 'Package in lakhs of rupees per annum.';
COMMENT ON COLUMN placement_drives.recruiter_group IS 'I = 5 LPA or more, II = below 5 LPA.';

CREATE TABLE placement_offers_by_branch (
    drive_id  INT NOT NULL REFERENCES placement_drives(drive_id),
    branch    TEXT NOT NULL CHECK (branch IN ('CE','IT','ENTC','PG')),
    offers    INT NOT NULL,
    PRIMARY KEY (drive_id, branch)
);
COMMENT ON TABLE placement_offers_by_branch IS 'Offers per drive split by branch. PG means M.Tech students.';
