# Online Examination System

A terminal-based examination management system built in Python that handles the complete lifecycle of an online exam — from question bank management and exam scheduling to auto-grading, proctoring, and result generation.

---

## Problem Statement

Educational institutions conducting online exams face several operational challenges:

- **Question management** — storing, tagging, and reusing questions across exams
- **Timed delivery** — enforcing server-side countdown timers that students cannot manipulate
- **Auto-grading** — instantly scoring objective questions (MCQ, True/False) without examiner involvement
- **Manual review** — queuing descriptive answers for examiner evaluation before publishing results
- **Academic integrity** — detecting and acting on suspicious behavior (tab switching) during the exam
- **Accessibility** — supporting disability accommodations such as extended time
- **Reliability** — preserving student progress during connection drops via auto-save

This system addresses all of the above through a structured, role-based CLI application covering three actors: **Admin**, **Examiner**, and **Student**.

---

## Approach and Logic

### Architecture

The system is split into three layers:

```
cli.py            ← Interactive terminal interface (user input / output)
exam_service.py   ← Business logic (all use-case flows)
models.py         ← Data classes (Question, Exam, ExamAttempt, Student, Result)
```

### Core Classes

| Class | Responsibility |
|---|---|
| `Question` | Stores question text, type, options, correct answer, marks, difficulty |
| `QuestionBank` | Repository of questions; supports tag-based search and random selection |
| `Exam` | Holds exam metadata, question list, enrollment list, and lifecycle status |
| `Student` | Stores student profile, enrolled exams, and attempt history |
| `ExamAttempt` | Tracks one student's live session — answers, timer, violations, score |
| `Result` | Computed after grading — percentage, grade letter, grade point, transcript |
| `ExamService` | Orchestrates all operations across the above classes |

### Key Design Decisions

**Server-side timer**
The deadline is stored as `start_time + duration` on the server object. Every answer submission checks `seconds_remaining()` before accepting the response. If time has expired, the attempt is auto-submitted regardless of client state.

**Auto-grade vs manual review**
After submission, `auto_grade()` scores all MCQ and True/False answers instantly. Descriptive questions skip auto-grading and enter a review queue. If an exam has no descriptive questions, the result is published immediately.

**Auto-save**
`auto_save()` records the current state of all answers server-side every 30 seconds. If a student disconnects and reconnects within the exam window, `start_exam()` detects the existing in-progress attempt and returns it — no data is lost.

**Proctoring**
Every tab-switch event is logged as a `ProctoringViolation`. On the third violation, `log_violation()` calls `force_submit(auto=True)` and triggers auto-grading immediately.

**Grading Table**

| Percentage | Grade | Result | Grade Point |
|---|---|---|---|
| 90 – 100 | O | Outstanding | 10 |
| 80 – 89 | A+ | Excellent | 9 |
| 70 – 79 | A | Very Good | 8 |
| 60 – 69 | B+ | Good | 7 |
| 50 – 59 | B | Average | 6 |
| 40 – 49 | C | Pass | 5 |
| Below 40 | F | Fail | 0 |

### Flow Summary

```
Admin      →  Register students, create exam, set window, enroll students, publish
Examiner   →  Add questions to bank, attach questions to exam (manual or random)
Student    →  Start exam (timer begins), answer / flag / save, submit
System     →  Auto-grade objective answers
Examiner   →  Award marks for descriptive answers, publish result
Admin      →  View performance report
```

### Exception Handling

| Scenario | Behaviour |
|---|---|
| Exam started outside window | `ExamWindowError` — window not open / already closed |
| Student already submitted | `DuplicateAttemptError` — cannot attempt again |
| Mandatory question unanswered | Warning shown; student must confirm or answer first |
| Insufficient questions in bank | `ValueError` before randomisation proceeds |
| 3 tab-switch violations | Exam auto-submitted; proctoring log saved |
| Timer expires mid-answer | `TimerExpiredError`; attempt auto-submitted and graded |

---

## Project Structure

```
Mr_Cooper/
├── models.py         # All data models and enumerations
├── exam_service.py   # Business logic and use-case orchestration
├── cli.py            # Interactive CLI application  ← run this
└── README.md
```

---

## Requirements

- Python 3.10 or higher
- No external packages required — uses only the Python standard library

---

## Steps to Execute

### 1. Open a terminal in the project folder

```
cd path\to\Mr_Cooper
```

### 2. Run the application

```
python cli.py
```

### 3. Follow the menu — recommended first-time order

```
Step 1 — Add questions to the bank
         Main Menu → 2. Examiner Panel → 1. Add Question to Bank
         (repeat for as many questions as needed)

Step 2 — Register students
         Main Menu → 1. Admin Panel → 1. Register Student

Step 3 — Create an exam
         Main Menu → 1. Admin Panel → 2. Create Exam
         (enter title, subject, duration, total marks, window hours)

Step 4 — Attach questions to the exam
         Main Menu → 2. Examiner Panel → 3. Add Specific Question to Exam
         OR
         Main Menu → 2. Examiner Panel → 4. Randomise Questions into Exam

Step 5 — Enroll students
         Main Menu → 1. Admin Panel → 3. Enroll Student in Exam

Step 6 — Publish the exam
         Main Menu → 1. Admin Panel → 4. Publish Exam

Step 7 — Student takes the exam
         Main Menu → 3. Student Panel → 1. Start Exam
         (answer questions, flag for review, auto-save, then submit)

Step 8 — Examiner grades descriptive answers  (skip if exam is MCQ/T-F only)
         Main Menu → 2. Examiner Panel → 5. Grade Descriptive Answer

Step 9 — View results and reports
         Main Menu → 4. Reports → 1. View Student Result
         Main Menu → 4. Reports → 2. Class Performance Report
```

### 4. Main Menu Reference

```
1. Admin Panel     — create exams, register and enroll students, publish
2. Examiner Panel  — manage question bank, add questions, grade descriptive answers
3. Student Panel   — start exam, answer questions, submit, view result
4. Reports         — individual transcript, class performance, grading table
0. Exit
```

---

## Sample Session

```
> python cli.py

  ONLINE EXAMINATION SYSTEM
  ══════════════════════════

  1.  Admin Panel
  2.  Examiner Panel
  3.  Student Panel
  4.  Reports
  0.  Exit

  Choose a panel: 2           ← go to Examiner Panel

  1. Add Question to Bank     ← add MCQ / True-False / Descriptive questions
  2. View Question Bank
  3. Add Specific Question to Exam
  4. Randomise Questions into Exam
  5. Grade Descriptive Answer
  0. Back
```

---

## Notes

- The **timer is server-side** — stored as a Python `datetime` object on the `ExamAttempt`. Students cannot manipulate it from the client.
- **Auto-save** is triggered by pressing `S` inside the exam session (simulates the 30-second background save).
- For a **fully objective exam** (MCQ + True/False only), the result is published automatically the moment the student submits — no examiner step needed.
- For a **mixed exam** (includes Descriptive), the result is published only after the examiner awards marks via *Grade Descriptive Answer*.
- The **proctoring demo** (tab-switch simulation) is available under `Student Panel → 4. Tab-Switch Proctoring Demo` for any in-progress attempt.
