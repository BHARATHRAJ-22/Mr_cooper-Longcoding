"""
Online Examination System — Interactive CLI
Run: python cli.py
"""

import os
import sys
from datetime import datetime, timedelta
from models import (
    Question, QuestionType, Difficulty, QuestionBank, compute_grade
)
from exam_service import (
    ExamService, ExamWindowError, DuplicateAttemptError, TimerExpiredError
)


def clear():
    os.system("cls" if os.name == "nt" else "clear")

def line(char="─", width=60):
    print(char * width)

def header(title):
    clear()
    line("═")
    print(f"  {title}")
    line("═")
    print()

def pause():
    input("\n  Press Enter to continue...")

def ask(prompt, required=True):
    while True:
        val = input(f"  {prompt}: ").strip()
        if val or not required:
            return val
        print("  [!] This field cannot be empty.")

def ask_int(prompt, min_val=1, max_val=9999):
    while True:
        try:
            val = int(ask(prompt))
            if min_val <= val <= max_val:
                return val
            print(f"  [!] Enter a number between {min_val} and {max_val}.")
        except ValueError:
            print("  [!] Please enter a valid number.")

def pick(label, options):
    """Show numbered list, return chosen index (0-based)."""
    print(f"\n  {label}")
    for i, opt in enumerate(options, 1):
        print(f"    {i}. {opt}")
    while True:
        try:
            choice = int(ask("Your choice"))
            if 1 <= choice <= len(options):
                return choice - 1
        except ValueError:
            pass
        print(f"  [!] Enter a number between 1 and {len(options)}.")

def pick_from_dict(label, items: dict):
    """items = {display_label: key}. Returns the key."""
    labels = list(items.keys())
    keys   = list(items.values())
    idx    = pick(label, labels)
    return keys[idx]

def confirm(prompt):
    ans = ask(f"{prompt} (y/n)", required=False).lower()
    return ans == "y"

def short_id(uid):
    return uid[:8] + "..."


bank    = QuestionBank()
service = ExamService(bank)

# Registry for display  (id -> label)
_exams    = {}   # exam_id    -> title
_students = {}   # student_id -> "Name (RollNo)"
_attempts = {}   # attempt_id -> "StudentName @ ExamTitle"

# ── Picker helpers: invert the dicts so pick_from_dict shows labels, returns ids ──
def _pick_exam(prompt):
    return pick_from_dict(prompt, {title: eid for eid, title in _exams.items()})

def _pick_student(prompt):
    return pick_from_dict(prompt, {label: sid for sid, label in _students.items()})

def _pick_attempt(prompt, attempts_dict):
    """attempts_dict must be {attempt_id: label}"""
    return pick_from_dict(prompt, {label: aid for aid, label in attempts_dict.items()})

# ─────────────────────── Question Bank ───────────────────────────────────────

def menu_add_question():
    header("ADD QUESTION TO BANK")

    q_type_map = {
        "MCQ  (Multiple Choice)": QuestionType.MCQ,
        "T/F  (True / False)":    QuestionType.TRUE_FALSE,
        "DESC (Descriptive)":     QuestionType.DESCRIPTIVE,
    }
    q_type = pick_from_dict("Select question type:", q_type_map)

    diff_map = {
        "Easy":   Difficulty.EASY,
        "Medium": Difficulty.MEDIUM,
        "Hard":   Difficulty.HARD,
    }
    diff    = pick_from_dict("Select difficulty:", diff_map)
    subject = ask("Subject")
    text    = ask("Question text")
    marks   = ask_int("Marks for this question", 1, 100)

    options        = []
    correct_answer = None

    if q_type == QuestionType.MCQ:
        print("\n  Enter 4 options (one per line):")
        for i in range(1, 5):
            options.append(ask(f"  Option {i}"))
        print("\n  Which option is correct?")
        for i, o in enumerate(options, 1):
            print(f"    {i}. {o}")
        ci = ask_int("Correct option number", 1, 4)
        correct_answer = options[ci - 1]

    elif q_type == QuestionType.TRUE_FALSE:
        options = ["true", "false"]
        ans_map = {"True": "true", "False": "false"}
        correct_answer = pick_from_dict("Correct answer:", ans_map)

    is_mandatory = False
    if q_type == QuestionType.DESCRIPTIVE:
        is_mandatory = confirm("Mark as mandatory?")

    q = Question(
        text=text, question_type=q_type, marks=marks,
        difficulty=diff, subject=subject, options=options,
        correct_answer=correct_answer, is_mandatory=is_mandatory
    )
    bank.add_question(q)
    print(f"\n  [✓] Question added!  ID: {short_id(q.question_id)}")
    pause()


def menu_view_bank():
    header("QUESTION BANK")
    all_q = bank.all_questions
    if not all_q:
        print("  No questions in the bank yet.")
    else:
        print(f"  Total: {len(all_q)} questions\n")
        line()
        for i, q in enumerate(all_q, 1):
            mand = " [MANDATORY]" if q.is_mandatory else ""
            print(f"  {i:>3}. [{q.question_type.value.upper():<12}] "
                  f"[{q.difficulty.value.upper():<6}] "
                  f"{q.marks}m  {q.text[:45]}{mand}")
    pause()



def menu_register_student():
    header("REGISTER STUDENT")
    name   = ask("Full name")
    roll   = ask("Roll number")
    email  = ask("Email")
    s      = service.register_student(name, roll, email)
    label  = f"{name} ({roll})"
    _students[s.student_id] = label
    print(f"\n  [✓] Student registered!")
    print(f"      Name   : {name}")
    print(f"      Roll No: {roll}")
    print(f"      ID     : {short_id(s.student_id)}")
    pause()


def menu_create_exam():
    header("CREATE EXAM")
    title   = ask("Exam title")
    subject = ask("Subject")
    dur     = ask_int("Duration (minutes)", 10, 300)
    marks   = ask_int("Total marks", 1, 1000)

    print("\n  Exam window — when can students start?")
    print("  1. Opens NOW  (window starts immediately)")
    print("  2. Set custom start time")
    choice = ask_int("Choice", 1, 2)

    if choice == 1:
        w_start = datetime.now()
    else:
        hrs = ask_int("Hours from now until window opens", 0, 72)
        w_start = datetime.now() + timedelta(hours=hrs)

    w_end_hrs = ask_int("Window stays open for how many hours?", 1, 72)
    w_end = w_start + timedelta(hours=w_end_hrs)

    exam = service.create_exam(
        title=title, subject=subject,
        duration_minutes=dur, total_marks=marks,
        window_start=w_start, window_end=w_end,
        admin_id="admin-001"
    )
    _exams[exam.exam_id] = title
    print(f"\n  [✓] Exam created!")
    print(f"      Title   : {title}")
    print(f"      Duration: {dur} min")
    print(f"      Marks   : {marks}")
    print(f"      Window  : {w_start.strftime('%d-%b %H:%M')} → {w_end.strftime('%d-%b %H:%M')}")
    print(f"      ID      : {short_id(exam.exam_id)}")
    pause()


def menu_add_question_to_exam():
    header("ADD QUESTION TO EXAM")
    if not _exams:
        print("  No exams created yet."); pause(); return
    if not bank.all_questions:
        print("  No questions in bank yet."); pause(); return

    exam_id = _pick_exam("Select exam:")
    exam    = service._get_exam(exam_id)

    print(f"\n  Questions in bank ({len(bank.all_questions)} total):")
    line()
    all_q = bank.all_questions
    for i, q in enumerate(all_q, 1):
        already = " [already added]" if q.question_id in exam.question_ids else ""
        print(f"  {i:>3}. [{q.question_type.value.upper():<12}] {q.marks}m  {q.text[:45]}{already}")

    while True:
        num = ask_int(f"Add question number (1-{len(all_q)}), 0 to finish", 0, len(all_q))
        if num == 0:
            break
        q = all_q[num - 1]
        if q.question_id in exam.question_ids:
            print("  [!] Already added.")
        else:
            service.add_question_to_exam(exam_id, q.question_id)
            print(f"  [✓] Added: {q.text[:50]}")

    # Recalculate total marks
    total = sum(bank.get(qid).marks for qid in exam.question_ids)
    exam.total_marks = total
    print(f"\n  Questions in exam: {len(exam.question_ids)}  |  Total marks: {total}")
    pause()


def menu_randomise_questions():
    header("RANDOMISE QUESTIONS FROM BANK")
    if not _exams:
        print("  No exams created yet."); pause(); return

    exam_id = _pick_exam("Select exam:")
    count   = ask_int("How many random questions to add?", 1, len(bank))

    subject  = ask("Filter by subject? (leave blank for all)", required=False) or None
    diff_map = {"Any": None, "Easy": Difficulty.EASY, "Medium": Difficulty.MEDIUM, "Hard": Difficulty.HARD}
    diff     = pick_from_dict("Filter by difficulty:", diff_map)

    try:
        selected = service.randomise_questions(exam_id, count, subject=subject, difficulty=diff)
        exam = service._get_exam(exam_id)
        exam.total_marks = sum(bank.get(qid).marks for qid in exam.question_ids)
        print(f"\n  [✓] {len(selected)} random questions added:")
        for q in selected:
            print(f"      - [{q.question_type.value.upper()}] {q.text[:50]}")
        print(f"\n  Total marks now: {exam.total_marks}")
    except ValueError as e:
        print(f"\n  [!] {e}")
    pause()


def menu_enroll_student():
    header("ENROLL STUDENT IN EXAM")
    if not _exams or not _students:
        print("  Need at least one exam and one student first."); pause(); return

    exam_id    = _pick_exam("Select exam:")
    student_id = _pick_student("Select student:")
    service.enroll_student(exam_id, student_id)
    print(f"\n  [✓] {_students[student_id]} enrolled in '{_exams[exam_id]}'")

    if confirm("Grant extra time for this student?"):
        mins = ask_int("Extra minutes", 1, 120)
        service.grant_extra_time(exam_id, student_id, extra_minutes=mins)
        print(f"  [✓] +{mins} minutes granted.")
    pause()


def menu_publish_exam():
    header("PUBLISH EXAM")
    if not _exams:
        print("  No exams created yet."); pause(); return

    exam_id = _pick_exam("Select exam to publish:")
    exam    = service._get_exam(exam_id)

    if not exam.question_ids:
        print("  [!] Cannot publish — no questions added yet.")
        pause(); return

    try:
        service.publish_exam(exam_id)
        print(f"\n  [✓] '{_exams[exam_id]}' is now PUBLISHED.")
        print(f"      Questions: {len(exam.question_ids)}")
        print(f"      Marks    : {exam.total_marks}")
        enrolled = len(exam.enrolled_student_ids)
        print(f"      Students : {enrolled} enrolled")
    except RuntimeError as e:
        print(f"  [!] {e}")
    pause()


# ─────────────────────── Student Panel ───────────────────────────────────────

def menu_start_exam():
    header("START EXAM")
    if not _exams or not _students:
        print("  Need at least one published exam and one student."); pause(); return

    student_id = _pick_student("Who is taking the exam?")
    exam_id    = _pick_exam("Select exam:")

    try:
        attempt = service.start_exam(exam_id, student_id)
        _attempts[attempt.attempt_id] = f"{_students[student_id]} @ {_exams[exam_id]}"
        exam    = service._get_exam(exam_id)

        print(f"\n  [✓] Exam started!")
        print(f"      Student  : {_students[student_id]}")
        print(f"      Exam     : {_exams[exam_id]}")
        print(f"      Started  : {attempt.start_time.strftime('%H:%M:%S')}")
        print(f"      Deadline : {attempt.deadline.strftime('%H:%M:%S')}  "
              f"({attempt.seconds_remaining() // 60} min remaining)")
        print(f"      Attempt  : {short_id(attempt.attempt_id)}")

        if confirm("\n  Begin answering questions now?"):
            _answer_session(attempt, exam)
        else:
            pause()
    except (ExamWindowError, DuplicateAttemptError, PermissionError) as e:
        print(f"\n  [!] {e}")
        pause()


def _answer_session(attempt, exam):
    """Interactive answering loop for one attempt."""
    questions = [bank.get(qid) for qid in exam.question_ids]

    while True:
        # Exit loop if exam was auto-submitted (timer / proctoring) mid-session
        if attempt.status.value not in ("in_progress",):
            header(f"EXAM: {exam.title}")
            print(f"  Your exam has ended.")
            print(f"  Status : {attempt.status.value.upper()}")
            has_desc = any(not bank.get(qid).is_objective() for qid in exam.question_ids)
            if has_desc:
                print("  Descriptive answers are queued for examiner review.")
            else:
                print("  Result has been published. Check Reports > View Result.")
            pause()
            break

        header(f"EXAM: {exam.title}")
        print(f"  Time remaining : {attempt.seconds_remaining() // 60} min "
              f"{attempt.seconds_remaining() % 60} sec")
        print(f"  Status         : {attempt.status.value.upper()}\n")
        line()

        # Show question list with answered / flagged state
        print(f"  {'#':<4} {'Type':<14} {'Marks':<6} {'Status':<12} Question")
        line()
        for i, q in enumerate(questions, 1):
            ans  = attempt.answers.get(q.question_id)
            flag = " 🔖" if (ans and ans.is_flagged) else ""
            if ans and ans.response is not None:
                status = "Answered"
            else:
                status = "Not answered"
            mandatory = "*" if q.is_mandatory else " "
            print(f"  {mandatory}{i:<3} [{q.question_type.value.upper():<12}] "
                  f"{q.marks:<6} {status:<12} {q.text[:35]}{flag}")

        line()
        print("\n  Options:")
        print("    A  - Answer a question")
        print("    F  - Flag / unflag a question")
        print("    S  - Auto-save progress")
        print("    V  - View my answers so far")
        print("    X  - Submit exam")

        action = ask("Action").upper()

        if action == "A":
            _do_answer(attempt, questions)
        elif action == "F":
            _do_flag(attempt, questions)
        elif action == "S":
            saved = service.auto_save(attempt.attempt_id)
            print(f"\n  [✓] Progress auto-saved at {saved.strftime('%H:%M:%S')}")
            pause()
        elif action == "V":
            _view_my_answers(attempt, questions)
        elif action == "X":
            if _do_submit(attempt, exam):
                break
        else:
            print("  [!] Invalid option.")


def _do_answer(attempt, questions):
    header("ANSWER QUESTION")
    print(f"  {'#':<4} Question")
    line()
    for i, q in enumerate(questions, 1):
        ans = attempt.answers.get(q.question_id)
        status = f"  [answered: {str(ans.response)[:20]}]" if (ans and ans.response) else ""
        print(f"  {i}. {q.text[:55]}{status}")

    num = ask_int(f"Question number to answer (1-{len(questions)})", 1, len(questions))
    q   = questions[num - 1]

    print(f"\n  Question {num}: {q.text}")
    print(f"  Type: {q.question_type.value.upper()}  |  Marks: {q.marks}")
    line()

    if q.question_type == QuestionType.MCQ:
        for i, opt in enumerate(q.options, 1):
            print(f"    {i}. {opt}")
        ci = ask_int("Your answer (option number)", 1, len(q.options))
        response = q.options[ci - 1]

    elif q.question_type == QuestionType.TRUE_FALSE:
        choice = pick("Your answer:", ["True", "False"])
        response = ["true", "false"][choice]

    else:  # Descriptive
        print("  Write your answer (press Enter twice to finish):")
        lines = []
        while True:
            ln = input("  ")
            if ln == "" and lines and lines[-1] == "":
                break
            lines.append(ln)
        response = " ".join(l for l in lines if l)

    try:
        service.submit_answer(attempt.attempt_id, q.question_id, response)
        print(f"\n  [✓] Answer saved: {str(response)[:60]}")
    except (TimerExpiredError, RuntimeError) as e:
        print(f"\n  [!] {e}")
    pause()


def _do_flag(attempt, questions):
    header("FLAG / UNFLAG QUESTION")
    for i, q in enumerate(questions, 1):
        ans    = attempt.answers.get(q.question_id)
        flagged = ans and ans.is_flagged
        tag    = " [FLAGGED]" if flagged else ""
        print(f"  {i}. {q.text[:55]}{tag}")

    num     = ask_int(f"Question number (1-{len(questions)})", 1, len(questions))
    q       = questions[num - 1]
    ans     = attempt.answers.get(q.question_id)
    flagged = bool(ans and ans.is_flagged)

    new_state = not flagged
    service.flag_question(attempt.attempt_id, q.question_id, flagged=new_state)
    state_label = "FLAGGED for review" if new_state else "UNFLAGGED"
    print(f"\n  [✓] Question {num} is now {state_label}.")
    pause()


def _view_my_answers(attempt, questions):
    header("MY ANSWERS SO FAR")
    for i, q in enumerate(questions, 1):
        ans  = attempt.answers.get(q.question_id)
        flag = " [FLAGGED]" if (ans and ans.is_flagged) else ""
        mand = " *" if q.is_mandatory else ""
        print(f"  Q{i}{mand}: {q.text}")
        if ans and ans.response is not None:
            print(f"       Answer : {str(ans.response)[:70]}{flag}")
        else:
            print(f"       Answer : — (not answered){flag}")
        print()
    pause()


def _do_submit(attempt, exam) -> bool:
    header("SUBMIT EXAM")
    # Guard: exam may have been auto-submitted already (timer / proctoring)
    if attempt.status.value not in ("in_progress",):
        print(f"  Your exam was already submitted (status: {attempt.status.value}).")
        pause()
        return True
    mandatory_ids = [qid for qid in exam.question_ids if bank.get(qid).is_mandatory]
    unanswered    = attempt.submit(mandatory_ids)

    if unanswered:
        print(f"  [!] You have {len(unanswered)} unanswered mandatory question(s):")
        for qid in unanswered:
            print(f"      - {bank.get(qid).text}")
        if not confirm("\n  Submit anyway? (you will receive 0 for these)"):
            return False

    if not confirm("  Are you sure you want to submit the exam?"):
        return False

    service.submit_exam(attempt.attempt_id, force=True)
    print(f"\n  [✓] Exam submitted at {attempt.end_time.strftime('%H:%M:%S')}")
    print(f"  Objective questions have been auto-graded.")

    # Check if fully objective → result auto-published
    has_desc = any(not bank.get(qid).is_objective() for qid in exam.question_ids)
    if has_desc:
        print("  Descriptive answers are queued for examiner review.")
    else:
        print("  No descriptive questions — result published immediately!")
    pause()
    return True



def menu_grade_descriptive():
    header("GRADE DESCRIPTIVE ANSWERS")

    # Find all submitted / auto-submitted attempts
    submitted = {
        aid: label for aid, label in _attempts.items()
        if service._attempts[aid].status.value in ("submitted", "auto_submitted")
    }
    if not submitted:
        print("  No submitted attempts waiting for grading."); pause(); return

    attempt_id = _pick_attempt("Select attempt to grade:", submitted)
    attempt    = service._attempts[attempt_id]
    exam       = service._get_exam(attempt.exam_id)

    desc_ids = [qid for qid in exam.question_ids
                if not bank.get(qid).is_objective()]

    if not desc_ids:
        print("  No descriptive questions in this exam."); pause(); return

    print(f"\n  Student  : {_students.get(attempt.student_id, attempt.student_id[:8])}")
    print(f"  Exam     : {exam.title}\n")

    all_graded = True
    for qid in desc_ids:
        q   = bank.get(qid)
        ans = attempt.answers.get(qid)
        line()
        print(f"  Question : {q.text}")
        print(f"  Max marks: {q.marks}")
        if ans and ans.response:
            print(f"\n  Student's answer:\n")
            # Wrap answer for readability
            words = ans.response.split()
            line_buf, output_lines = [], []
            for w in words:
                line_buf.append(w)
                if len(" ".join(line_buf)) > 65:
                    output_lines.append("    " + " ".join(line_buf[:-1]))
                    line_buf = [w]
            if line_buf:
                output_lines.append("    " + " ".join(line_buf))
            print("\n".join(output_lines))
        else:
            print("  [No answer provided]")
            all_graded = False

        if ans and ans.response:
            awarded = ask_int(f"\n  Marks to award (0 - {q.marks})", 0, q.marks)
            service.award_descriptive_marks(attempt_id, qid, marks=awarded)
            print(f"  [✓] Awarded {awarded}/{q.marks}")
        print()

    remarks = ask("Overall remarks for this student (leave blank to skip)", required=False)
    result  = service.finalize_and_publish_result(attempt_id, remarks=remarks)
    print(f"\n  [✓] Result published!")
    print(f"      Score     : {result.scored} / {result.total_marks}")
    print(f"      Percentage: {result.percentage:.2f}%")
    print(f"      Grade     : {result.grade}  —  {result.result_label}")
    pause()



def menu_view_result():
    header("VIEW RESULT")
    if not _students or not _exams:
        print("  No data yet."); pause(); return

    student_id = _pick_student("Select student:")
    exam_id    = _pick_exam("Select exam:")

    try:
        result = service.view_result(student_id, exam_id)
        print()
        print(result.get_transcript())
    except (KeyError, RuntimeError) as e:
        print(f"\n  [!] {e}")
    pause()


def menu_performance_report():
    header("PERFORMANCE REPORT")
    if not _exams:
        print("  No exams yet."); pause(); return

    exam_id = _pick_exam("Select exam:")
    print()
    print(service.generate_performance_report(exam_id))
    pause()


def menu_proctoring_demo():
    header("PROCTORING — TAB SWITCH DEMO")
    if not _attempts:
        print("  No active attempts."); pause(); return

    in_prog = {
        aid: label for aid, label in _attempts.items()
        if service._attempts[aid].status.value == "in_progress"
    }
    if not in_prog:
        print("  No in-progress attempts to test proctoring on."); pause(); return

    attempt_id = _pick_attempt("Select attempt:", in_prog)
    attempt    = service._attempts[attempt_id]

    print(f"\n  Simulating tab-switch for: {_attempts[attempt_id]}")
    print(f"  (3 tab switches = auto-submit)\n")

    info = service.report_tab_switch(attempt_id)
    print(f"  Tab switch logged!")
    print(f"  Violation count   : {info['violation_count']}")
    print(f"  Warnings remaining: {info['warnings_remaining']}")

    if info["auto_submitted"]:
        print(f"\n  [!] 3rd violation — exam AUTO-SUBMITTED!")
        exam = service._get_exam(attempt.exam_id)
        has_desc = any(not bank.get(qid).is_objective() for qid in exam.question_ids)
        if not has_desc:
            print("  Result published immediately (fully objective).")
        else:
            print("  Awaiting examiner review for descriptive answers.")
    pause()


def menu_grading_table():
    header("GRADING TABLE")
    print(f"  {'Percentage Range':<20} {'Grade':<6} {'Result':<14} {'Grade Point'}")
    line()
    from models import GRADING_TABLE
    for low, high, letter, label, gp in GRADING_TABLE:
        rng = f"{low} – {high}%"
        print(f"  {rng:<20} {letter:<6} {label:<14} {gp}")
    pause()


def menu_system_summary():
    header("SYSTEM SUMMARY")
    print(f"  Questions in bank : {len(bank)}")
    print(f"  Exams created     : {len(_exams)}")
    print(f"  Students registered: {len(_students)}")
    print(f"  Attempts taken    : {len(_attempts)}")
    if _exams:
        print(f"\n  Exams:")
        for eid, title in _exams.items():
            exam = service._get_exam(eid)
            print(f"    - {title:<30} [{exam.status.value.upper()}]  "
                  f"Q:{len(exam.question_ids)}  Marks:{exam.total_marks}")
    if _students:
        print(f"\n  Students:")
        for sid, label in _students.items():
            print(f"    - {label}")
    pause()


# ─────────────────────── Sub-menus ───────────────────────────────────────────

def admin_menu():
    while True:
        header("ADMIN PANEL")
        print("  1. Register Student")
        print("  2. Create Exam")
        print("  3. Enroll Student in Exam")
        print("  4. Publish Exam")
        print("  5. System Summary")
        print("  0. Back")
        ch = ask_int("Choice", 0, 5)
        if   ch == 1: menu_register_student()
        elif ch == 2: menu_create_exam()
        elif ch == 3: menu_enroll_student()
        elif ch == 4: menu_publish_exam()
        elif ch == 5: menu_system_summary()
        elif ch == 0: break


def examiner_menu():
    while True:
        header("EXAMINER PANEL")
        print("  1. Add Question to Bank")
        print("  2. View Question Bank")
        print("  3. Add Specific Question to Exam")
        print("  4. Randomise Questions into Exam")
        print("  5. Grade Descriptive Answer")
        print("  0. Back")
        ch = ask_int("Choice", 0, 5)
        if   ch == 1: menu_add_question()
        elif ch == 2: menu_view_bank()
        elif ch == 3: menu_add_question_to_exam()
        elif ch == 4: menu_randomise_questions()
        elif ch == 5: menu_grade_descriptive()
        elif ch == 0: break


def student_menu():
    while True:
        header("STUDENT PANEL")
        print("  1. Start Exam")
        print("  2. Continue In-Progress Exam")
        print("  3. View My Result")
        print("  4. Tab-Switch Proctoring Demo")
        print("  0. Back")
        ch = ask_int("Choice", 0, 4)
        if   ch == 1: menu_start_exam()
        elif ch == 2: _continue_exam()
        elif ch == 3: menu_view_result()
        elif ch == 4: menu_proctoring_demo()
        elif ch == 0: break


def _continue_exam():
    header("CONTINUE EXAM")
    in_prog = {
        aid: label for aid, label in _attempts.items()
        if service._attempts[aid].status.value == "in_progress"
    }
    if not in_prog:
        print("  No in-progress attempts found."); pause(); return

    attempt_id = _pick_attempt("Select your attempt:", in_prog)
    attempt    = service._attempts[attempt_id]
    exam       = service._get_exam(attempt.exam_id)

    if attempt.is_time_up():
        print("  [!] Time is up. Exam will be auto-submitted.")
        service.auto_submit_on_timeout(attempt_id)
        pause()
        return

    print(f"\n  Reconnected!  Time remaining: "
          f"{attempt.seconds_remaining() // 60} min {attempt.seconds_remaining() % 60} sec")
    pause()
    _answer_session(attempt, exam)


def reports_menu():
    while True:
        header("REPORTS & REFERENCE")
        print("  1. View Student Result / Transcript")
        print("  2. Class Performance Report")
        print("  3. Grading Table")
        print("  0. Back")
        ch = ask_int("Choice", 0, 3)
        if   ch == 1: menu_view_result()
        elif ch == 2: menu_performance_report()
        elif ch == 3: menu_grading_table()
        elif ch == 0: break


# ─────────────────────── Main Menu ───────────────────────────────────────────

def main():
    while True:
        header("ONLINE EXAMINATION SYSTEM")
        print("  1.  Admin Panel       — create exams, register students")
        print("  2.  Examiner Panel    — add questions, grade answers")
        print("  3.  Student Panel     — take exam, view result")
        print("  4.  Reports           — transcripts, performance, grading table")
        print("  0.  Exit")
        line()
        ch = ask_int("Choose a panel", 0, 4)
        if   ch == 1: admin_menu()
        elif ch == 2: examiner_menu()
        elif ch == 3: student_menu()
        elif ch == 4: reports_menu()
        elif ch == 0:
            clear()
            print("  Goodbye!\n")
            sys.exit(0)


if __name__ == "__main__":
    main()
