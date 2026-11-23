# * Builds the synthetic tables for the fictional Aravali Institute of Technology (AIT).
# * Run: python data/seed/generate_tables.py   (same seed = same data every time)
# ! "Today" in this fake world is 2026-11-23 (middle of semester I of 2026-27).
# ! The placements CSVs are NOT made here. They are shipped as-is (see data/README.md).

import csv
import random
from datetime import date, timedelta
from pathlib import Path

random.seed(42)
OUT = Path(__file__).parent
TODAY = date(2026, 11, 23)
CURRENT_AY = "2026-27"
BRANCHES = ["CE", "IT", "ENTC"]
PER_GROUP = 20  # students per branch per year

# ---------- names (made up combinations) ----------
FIRST_M = ["Aarav", "Vihaan", "Arjun", "Rohan", "Kabir", "Aditya", "Ishaan", "Yash", "Omkar", "Soham",
           "Tanmay", "Harsh", "Pratik", "Siddharth", "Nikhil", "Varun", "Rahul", "Karan", "Atharv", "Shreyas"]
FIRST_F = ["Ananya", "Diya", "Isha", "Meera", "Kavya", "Riya", "Sneha", "Pooja", "Tanvi", "Aditi",
           "Neha", "Shruti", "Priya", "Aarohi", "Sakshi", "Mansi", "Rutuja", "Vaidehi", "Janhavi", "Gauri"]
LAST = ["Patil", "Deshmukh", "Kulkarni", "Joshi", "Shinde", "Pawar", "More", "Jadhav", "Kale", "Bhosale",
        "Gaikwad", "Thakur", "Mehta", "Iyer", "Nair", "Reddy", "Sharma", "Verma", "Gupta", "Chavan"]

# ---------- courses ----------
COMMON = {
    1: (["Engineering Mathematics I", "Engineering Physics", "Basic Electrical and Electronics", "Programming Fundamentals"],
        ["Physics Lab", "Programming Lab"]),
    2: (["Engineering Mathematics II", "Engineering Chemistry", "Engineering Mechanics", "Communication Skills"],
        ["Chemistry Lab", "Workshop Practice"]),
}
BRANCH_COURSES = {
    "CE": {
        3: (["Discrete Mathematics", "Data Structures", "Computer Organization", "Object Oriented Programming"], ["Data Structures Lab", "OOP Lab"]),
        4: (["Database Management Systems", "Operating Systems", "Design and Analysis of Algorithms", "Microprocessors"], ["DBMS Lab", "Operating Systems Lab"]),
        5: (["Computer Networks", "Theory of Computation", "Software Engineering", "Machine Learning"], ["Networks Lab", "Machine Learning Lab"]),
        6: (["Compiler Design", "Distributed Systems", "Cloud Computing", "Deep Learning"], ["Compiler Lab", "Mini Project"]),
        7: (["Information Security", "Big Data Analytics", "Computer Vision", "Natural Language Processing"], ["Security Lab", "Project Stage I"]),
        8: (["Reinforcement Learning", "MLOps Practices", "Professional Ethics", "Startup Management"], ["Major Project", "Industry Internship"]),
    },
    "IT": {
        3: (["Discrete Mathematics", "Data Structures", "Digital Logic", "Object Oriented Programming"], ["Data Structures Lab", "OOP Lab"]),
        4: (["Database Management Systems", "Operating Systems", "Design and Analysis of Algorithms", "Web Technologies"], ["DBMS Lab", "Web Technologies Lab"]),
        5: (["Computer Networks", "Software Engineering", "Data Science", "Information Systems Design"], ["Networks Lab", "Data Science Lab"]),
        6: (["Cloud Computing", "Information Security", "Mobile Application Development", "Deep Learning"], ["Cloud Lab", "Mini Project"]),
        7: (["DevOps and Site Reliability", "Big Data Analytics", "Natural Language Processing", "Blockchain Technology"], ["DevOps Lab", "Project Stage I"]),
        8: (["Reinforcement Learning", "Scalable AI Systems", "Professional Ethics", "Startup Management"], ["Major Project", "Industry Internship"]),
    },
    "ENTC": {
        3: (["Signals and Systems", "Analog Circuits", "Digital Electronics", "Network Theory"], ["Analog Circuits Lab", "Digital Electronics Lab"]),
        4: (["Control Systems", "Electromagnetics", "Microcontrollers", "Communication Theory"], ["Microcontrollers Lab", "Communication Lab"]),
        5: (["Digital Signal Processing", "Digital Communication", "Embedded Systems", "Antenna Theory"], ["DSP Lab", "Embedded Systems Lab"]),
        6: (["VLSI Design", "Wireless Communication", "Internet of Things", "Image Processing"], ["VLSI Lab", "Mini Project"]),
        7: (["Optical Communication", "Radar Systems", "Satellite Communication", "Machine Learning for Signals"], ["Wireless Lab", "Project Stage I"]),
        8: (["Mobile Communication", "Robotics and Automation", "Professional Ethics", "Startup Management"], ["Major Project", "Industry Internship"]),
    },
}


def build_courses():
    rows = []
    n = 100
    for sem, (theory, labs) in COMMON.items():
        for t in theory:
            n += 1
            rows.append(["COM%03d" % n, t, "COMMON", sem, 4, "theory"])
        for lab in labs:
            n += 1
            rows.append(["COM%03d" % n, lab, "COMMON", sem, 2, "lab"])
    for b, sems in BRANCH_COURSES.items():
        for sem, (theory, labs) in sems.items():
            for t in theory:
                n += 1
                rows.append(["%s%03d" % (b, n), t, b, sem, 4, "theory"])
            for lab in labs:
                n += 1
                rows.append(["%s%03d" % (b, n), lab, b, sem, 2, "lab"])
    return rows


GRADES = [(10, "O", 90, 100), (9, "A+", 80, 89), (8, "A", 70, 79), (7, "B+", 60, 69),
          (6, "B", 55, 59), (5, "C", 50, 54), (4, "P", 40, 49), (0, "F", 10, 39)]


def grade_from_gp(gp):
    for p, letter, lo, hi in GRADES:
        if p == gp:
            return letter, random.randint(lo, hi)


def write(name, header, rows):
    with open(OUT / name, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(f"{name}: {len(rows)} rows")


def main():
    courses = build_courses()
    by_branch_sem = {}
    for c in courses:
        by_branch_sem.setdefault((c[2], c[3]), []).append(c)

    students, enrollments, fees = [], [], []
    enr_id = 0
    fee_id = 0
    for adm_year in (2023, 2024, 2025, 2026):
        year_of_study = 2026 - adm_year + 1  # 2026 -> 1 ... 2023 -> 4
        cur_sem = 2 * year_of_study - 1
        for b in BRANCHES:
            for i in range(1, PER_GROUP + 1):
                female = random.random() < 0.3
                name = random.choice(FIRST_F if female else FIRST_M) + " " + random.choice(LAST)
                sid = f"{adm_year % 100}{b}{i:03d}"
                hostel = random.random() < 0.28
                quota = random.choices(["merit", "institute", "management", "nri"], [70, 20, 8, 2])[0]
                ability = random.gauss(7.4, 1.0)
                tot_pts = tot_cred = backlogs = 0
                # past semesters (finished) + current semester (ongoing)
                for sem in range(1, cur_sem + 1):
                    key = ("COMMON", sem) if sem <= 2 else (b, sem)
                    ay_start = adm_year + (sem - 1) // 2
                    ay = f"{ay_start}-{str(ay_start + 1)[2:]}"
                    for c in by_branch_sem[key]:
                        enr_id += 1
                        if sem < cur_sem:
                            gp = 0 if random.random() < 0.02 else max(4, min(10, round(random.gauss(ability, 1.1))))
                            letter, marks = grade_from_gp(gp)
                            att = max(76, min(100, round(random.gauss(86, 6))))
                            status = "backlog" if gp == 0 else "passed"
                            backlogs += gp == 0
                            tot_pts += gp * c[4]
                            tot_cred += c[4]
                            enrollments.append([enr_id, sid, c[0], ay, sem, att, "", letter, gp, marks, status])
                        else:
                            att = max(55, min(100, round(random.gauss(83, 9))))
                            # ISE (out of 15) is only for theory courses
                            ise = "" if c[5] == "lab" else max(3, min(15, round(random.gauss(ability * 1.4, 2))))
                            enrollments.append([enr_id, sid, c[0], ay, sem, att, ise, "", "", "", "ongoing"])
                cgpa = round(tot_pts / tot_cred, 2) if tot_cred else ""
                students.append([sid, name, "F" if female else "M", b, adm_year, year_of_study, cur_sem,
                                 cgpa, backlogs, hostel, quota])

                # fees: one block per academic year attended
                for k in range(year_of_study):
                    ay_start = adm_year + k
                    ay = f"{ay_start}-{str(ay_start + 1)[2:]}"
                    due = date(ay_start, 8, 31)
                    lines = [("tuition_fee", 102000), ("development_fee", 15000)]
                    if k == 0 and quota in ("management", "nri"):
                        lines.append(("quota_fee", 180000))
                    if k == 0:
                        lines.append(("caution_deposit", 5000))
                    if hostel:
                        lines.append(("hostel_fee", 120000))
                    current = ay == CURRENT_AY
                    roll = random.random()
                    for ftype, amt in lines:
                        fee_id += 1
                        if not current or roll < 0.85:
                            paid, pdate, st = amt, due - timedelta(days=random.randint(0, 25)), "paid"
                        elif roll < 0.93:
                            paid, pdate, st = amt // 2, due + timedelta(days=random.randint(5, 40)), "partial"
                        else:
                            paid, pdate, st = 0, "", "overdue"
                        fees.append([fee_id, sid, ay, ftype, amt, paid, due.isoformat(),
                                     pdate.isoformat() if pdate else "", st])

    write("courses.csv", ["course_code", "title", "branch", "semester", "credits", "course_type"], courses)
    write("students.csv", ["student_id", "full_name", "gender", "branch", "admission_year", "year_of_study",
                           "current_semester", "cgpa", "active_backlogs", "hostel_resident", "admission_quota"], students)
    write("enrollments.csv", ["enrollment_id", "student_id", "course_code", "academic_year", "semester",
                              "attendance_pct", "ise_marks", "grade_letter", "grade_point", "total_marks", "status"], enrollments)
    write("fee_ledger.csv", ["entry_id", "student_id", "academic_year", "fee_type", "amount_due", "amount_paid",
                             "due_date", "paid_date", "status"], fees)

    # ---------- grants (eligibility rules live ONLY in the documents) ----------
    grants = [
        [1, "Undergraduate Research Seed Grant", "AIT R&D Cell", 50000, "research"],
        [2, "Student Innovation Project Grant", "AIT Entrepreneurship Cell", 75000, "project"],
        [3, "Conference Travel Grant", "AIT R&D Cell", 40000, "travel"],
        [4, "AI and Data Research Fellowship", "Nimbus Labs (industry sponsor)", 120000, "research"],
        [5, "Women in Tech Research Grant", "AIT Alumni Association", 60000, "research"],
        [6, "Embedded and Wireless Research Grant", "AIT Electronics Department", 60000, "research"],
        [7, "Final-Year Project Funding", "AIT Academic Office", 30000, "project"],
        [8, "Summer Research Internship Stipend", "AIT R&D Cell", 25000, "internship"],
    ]
    write("grants.csv", ["grant_id", "grant_name", "sponsor", "max_amount_inr", "grant_type"], grants)
    deadlines = [
        [1, "2026-27", "2026-10-15", "2026-12-10", "2027-01-10", ""],
        [2, "2026-27", "2026-12-01", "2027-01-15", "2027-02-10", ""],
        [3, "2026-27", "2026-08-01", "2027-03-31", "", "Rolling: each application is reviewed within 3 weeks"],
        [4, "2026-27", "2026-11-01", "2026-11-20", "2026-12-05", ""],
        [5, "2026-27", "2026-11-10", "2026-12-20", "2027-01-15", ""],
        [6, "2026-27", "2026-11-15", "2027-01-05", "2027-01-30", ""],
        [7, "2026-27", "2026-08-10", "2026-09-30", "2026-10-15", ""],
        [8, "2026-27", "2027-02-01", "2027-03-01", "2027-03-25", ""],
    ]
    write("grant_deadlines.csv", ["grant_id", "cycle", "opens_on", "closes_on", "results_on", "notes"], deadlines)

    # ---------- academic calendar, semester I 2026-27 ----------
    cal = [
        ("Commencement of instruction", "2026-07-06", "2026-07-06", "BE"),
        ("Commencement of instruction", "2026-07-13", "2026-07-13", "SE,TE,PG"),
        ("Commencement of instruction", "2026-08-03", "2026-08-03", "FE"),
        ("Blood donation camp", "2026-08-14", "2026-08-14", "ALL"),
        ("Independence Day (holiday)", "2026-08-15", "2026-08-15", "ALL"),
        ("In-semester examination (ISE)", "2026-08-24", "2026-08-28", "TE"),
        ("ISE answer-book assessment and marks entry", "2026-08-26", "2026-09-03", "TE"),
        ("Mid-semester feedback collection", "2026-08-31", "2026-09-04", "SE,TE,PG,BE"),
        ("Open house for ISE answer books", "2026-09-07", "2026-09-07", "TE"),
        ("ISE result declaration", "2026-09-11", "2026-09-11", "TE"),
        ("Annual faculty gathering", "2026-09-12", "2026-09-12", "ALL"),
        ("Ganesh Chaturthi (holiday)", "2026-09-14", "2026-09-14", "ALL"),
        ("Anant Chaturdashi (holiday)", "2026-09-25", "2026-09-25", "ALL"),
        ("Gandhi Jayanti (holiday)", "2026-10-02", "2026-10-02", "ALL"),
        ("Debate society event", "2026-10-09", "2026-10-10", "ALL"),
        ("Academic council meeting", "2026-10-10", "2026-10-10", "STAFF"),
        ("In-semester examination (ISE)", "2026-10-12", "2026-10-16", "SE,PG"),
        ("ISE answer-book assessment and marks entry", "2026-10-14", "2026-10-24", "SE,PG"),
        ("End-semester feedback and course exit survey", "2026-10-19", "2026-10-23", "SE,TE,PG,BE"),
        ("Dasara (holiday)", "2026-10-20", "2026-10-20", "ALL"),
        ("Entrepreneurship fest", "2026-10-22", "2026-10-24", "ALL"),
        ("Parent meet", "2026-10-24", "2026-10-24", "SE,TE,PG,BE"),
        ("Open house for ISE answer books", "2026-10-29", "2026-10-29", "SE,PG"),
        ("Model UN conclave", "2026-10-30", "2026-10-31", "ALL"),
        ("Continuous internal evaluation marks compilation", "2026-10-26", "2026-11-03", "SE,TE,PG"),
        ("Term work compilation", "2026-11-04", "2026-11-05", "SE,TE,PG,BE"),
        ("Conclusion of instruction", "2026-11-05", "2026-11-05", "SE,TE,PG"),
        ("Conclusion of instruction", "2026-11-07", "2026-11-07", "BE"),
        ("Diwali holidays", "2026-11-09", "2026-11-11", "ALL"),
        ("Practical, oral, seminar and dissertation examinations", "2026-11-16", "2026-11-28", "SE,TE,PG"),
        ("Internal marks display", "2026-11-21", "2026-11-21", "SE,TE,PG"),
        ("Guru Nanak Jayanti (holiday)", "2026-11-24", "2026-11-24", "ALL"),
        ("End-semester examination (ESE)", "2026-12-02", "2026-12-12", "TE"),
        ("End-semester examination (ESE)", "2026-12-03", "2026-12-18", "SE,PG"),
        ("ESE answer-book assessment", "2026-12-04", "2026-12-19", "TE"),
        ("ESE answer-book assessment", "2026-12-07", "2026-12-24", "SE,PG"),
        ("Christmas (holiday)", "2026-12-25", "2026-12-25", "ALL"),
        ("Open house for ESE answer books", "2026-12-30", "2026-12-30", "SE,TE,PG"),
        ("Winter vacation and internship window", "2026-12-14", "2027-01-09", "SE,TE,PG"),
        ("ESE result declaration", "2027-01-15", "2027-01-15", "SE,TE,PG"),
        ("Commencement of semester II", "2027-01-11", "2027-01-11", "SE,TE,PG"),
    ]
    cal = sorted(cal, key=lambda r: (r[1], r[0]))
    write("academic_calendar.csv", ["event_id", "semester_term", "event", "start_date", "end_date", "applies_to"],
          [[i + 1, "2026-27 Semester I", *r] for i, r in enumerate(cal)])


if __name__ == "__main__":
    main()
