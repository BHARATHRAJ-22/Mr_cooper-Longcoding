
from __future__ import annotations
from datetime import datetime
from typing import Optional

from models import (
    Exam, ExamStatus, ExamAttempt, AttemptStatus,
    Question, QuestionBank, Student, Result, Difficulty, QuestionType
)


class ExamService:
    def __init__(self, question_bank: QuestionBank):
        self._bank = question_bank
        self._exams: dict[str, Exam] = {}
        self._students: dict[str, Student] = {}
        self._attempts: dict[str, ExamAttempt] = {}        
        self._student_attempts: dict[tuple, str] = {}       
        self._results: dict[str, Result] = {}              

    def register_student(self, name: str, roll_no: str, email: str) -> Student:
        student = Student(name=name, roll_no=roll_no, email=email)
        self._students[student.student_id] = student
        return student

    def create_exam(self, title: str, subject: str, duration_minutes: int,
                    total_marks: int, window_start: datetime,
                    window_end: datetime, admin_id: str) -> Exam:
        exam = Exam(
            title=title, subject=subject,
            duration_minutes=duration_minutes, total_marks=total_marks,
            window_start=window_start, window_end=window_end,
            created_by=admin_id
        )
        self._exams[exam.exam_id] = exam
        return exam

    def enroll_student(self, exam_id: str, student_id: str) -> None:
        exam = self._get_exam(exam_id)
        student = self._get_student(student_id)
        exam.enroll_student(student_id)
        student.enroll(exam_id)

    def grant_extra_time(self, exam_id: str, student_id: str, extra_minutes: int) -> None:
        """Disability / accommodation: extend this student's timer for this exam."""
        student = self._get_student(student_id)
        student.extra_time_minutes = extra_minutes

        # If the attempt is already running, adjust its deadline in-place.
        key = (student_id, exam_id)
        if key in self._student_attempts:
            attempt = self._attempts[self._student_attempts[key]]
            if attempt.status == AttemptStatus.IN_PROGRESS:
                attempt._duration_minutes += extra_minutes

    def publish_exam(self, exam_id: str) -> None:
        self._get_exam(exam_id).publish()


    def add_question_to_exam(self, exam_id: str, question_id: str) -> None:
        self._get_exam(exam_id).add_question(question_id)

    def randomise_questions(self, exam_id: str, count: int,
                            subject: Optional[str] = None,
                            difficulty: Optional[Difficulty] = None) -> list[Question]:
        """
        Selects `count` random questions from the bank and attaches them to the exam.
        Raises ValueError if the bank doesn't have enough questions.
        """
        selected = self._bank.random_select(count, subject=subject, difficulty=difficulty)
        exam = self._get_exam(exam_id)
        for q in selected:
            exam.add_question(q.question_id)
        return selected

    def start_exam(self, exam_id: str, student_id: str) -> ExamAttempt:
        """
        Exception flows handled:
          - Outside window → ExamWindowError
          - Duplicate attempt → DuplicateAttemptError
          - Student not enrolled → PermissionError
        """
        exam = self._get_exam(exam_id)
        student = self._get_student(student_id)

        # Enrollment check
        if student_id not in exam.enrolled_student_ids:
            raise PermissionError(f"Student {student_id} is not enrolled in exam {exam_id}.")

        # Window check
        now = datetime.now()
        if now < exam.window_start:
            raise ExamWindowError("Exam window has not opened yet.")
        if now > exam.window_end:
            raise ExamWindowError("Exam window has closed.")

        # Duplicate attempt check
        key = (student_id, exam_id)
        if key in self._student_attempts:
            existing = self._attempts[self._student_attempts[key]]
            if existing.status in (AttemptStatus.SUBMITTED, AttemptStatus.AUTO_SUBMITTED,
                                   AttemptStatus.GRADED):
                raise DuplicateAttemptError("You have already submitted this exam.")
            # Reconnect: return existing in-progress attempt (auto-save already running)
            return existing

        # First attempt
        if exam.status == ExamStatus.PUBLISHED:
            exam.start()

        attempt = ExamAttempt(
            student_id=student_id,
            exam_id=exam_id,
            exam_duration_minutes=exam.duration_minutes,
            extra_time_minutes=student.extra_time_minutes
        )
        attempt.start()
        self._attempts[attempt.attempt_id] = attempt
        self._student_attempts[key] = attempt.attempt_id
        student.attempt_ids.append(attempt.attempt_id)
        return attempt

    def submit_answer(self, attempt_id: str, question_id: str, response: str) -> None:
        attempt = self._get_attempt(attempt_id)
        self._check_timer(attempt)
        attempt.submit_answer(question_id, response)

    def flag_question(self, attempt_id: str, question_id: str, flagged: bool = True) -> None:
        attempt = self._get_attempt(attempt_id)
        attempt.flag_question(question_id, flagged)

    def auto_save(self, attempt_id: str) -> datetime:
        """Called every 30 seconds by the client; persists current answers server-side."""
        return self._get_attempt(attempt_id).auto_save()

    def submit_exam(self, attempt_id: str, force: bool = False) -> list[str]:
        """
        Returns unanswered mandatory question IDs as a warning.
        If `force=True` or no mandatory questions remain unanswered, submits.
        """
        attempt = self._get_attempt(attempt_id)
        exam = self._get_exam(attempt.exam_id)
        mandatory_ids = self._mandatory_ids(exam)

        unanswered = attempt.submit(mandatory_ids)
        if unanswered and not force:
            return unanswered   # caller should warn student

        attempt.force_submit(auto=False)
        self._run_auto_grade(attempt, exam)
        return []

    def auto_submit_on_timeout(self, attempt_id: str) -> None:
        """Called by the server-side timer when deadline is reached."""
        attempt = self._get_attempt(attempt_id)
        if attempt.status == AttemptStatus.IN_PROGRESS and attempt.is_time_up():
            attempt.force_submit(auto=True)
            exam = self._get_exam(attempt.exam_id)
            self._run_auto_grade(attempt, exam)

    def report_tab_switch(self, attempt_id: str) -> dict:
        """
        Logs a TAB_SWITCH violation.
        Returns dict with 'auto_submitted' bool and 'violation_count' int.
        """
        attempt = self._get_attempt(attempt_id)
        auto_submitted = attempt.log_violation("TAB_SWITCH")
        if auto_submitted:
            exam = self._get_exam(attempt.exam_id)
            self._run_auto_grade(attempt, exam)
        return {
            "auto_submitted": auto_submitted,
            "violation_count": attempt.tab_violation_count,
            "warnings_remaining": max(0, ExamAttempt.MAX_TAB_VIOLATIONS - attempt.tab_violation_count)
        }

    def award_descriptive_marks(self, attempt_id: str,
                                question_id: str, marks: int) -> None:
        """Examiner manually grades a descriptive answer (0 marks if not answered)."""
        from models import Answer
        attempt = self._get_attempt(attempt_id)
        if question_id not in attempt.answers:
            attempt.answers[question_id] = Answer(question_id)   # student left it blank
        attempt.answers[question_id].marks_awarded = marks
        attempt.score += marks

    def finalize_and_publish_result(self, attempt_id: str,
                                    remarks: str = "") -> Result:
        """
        Called by examiner after all manual grading is done.
        Also called immediately for fully-objective exams.
        """
        attempt = self._get_attempt(attempt_id)
        exam = self._get_exam(attempt.exam_id)

        result = Result(
            attempt_id=attempt_id,
            student_id=attempt.student_id,
            exam_id=attempt.exam_id,
            total_marks=exam.total_marks,
            scored=attempt.score,
        )
        result.remarks = remarks
        result.generate()
        result.publish()
        self._results[attempt_id] = result

        attempt.status = AttemptStatus.GRADED

        # If all attempts for this exam are graded → publish exam results
        all_graded = all(
            self._attempts[aid].status == AttemptStatus.GRADED
            for aid in self._student_attempts.values()
            if self._attempts[aid].exam_id == exam.exam_id
        )
        if all_graded:
            exam.publish_results()

        return result

    def view_result(self, student_id: str, exam_id: str) -> Result:
        key = (student_id, exam_id)
        if key not in self._student_attempts:
            raise KeyError("No attempt found for this student/exam combination.")
        attempt_id = self._student_attempts[key]
        result = self._results.get(attempt_id)
        if result is None or not result.is_published:
            raise RuntimeError("Result is not yet published.")
        return result

    def generate_performance_report(self, exam_id: str) -> str:
        """Admin / examiner: per-student performance report for an exam."""
        exam = self._get_exam(exam_id)
        lines = [
            "=" * 70,
            f"  PERFORMANCE REPORT  — {exam.title} ({exam.subject})",
            "=" * 70,
            f"  {'Roll No':<12} {'Name':<25} {'Score':>7} {'%':>7} {'Grade':>6} {'GP':>4}",
            "-" * 70,
        ]
        for (sid, eid), aid in self._student_attempts.items():
            if eid != exam_id:
                continue
            attempt = self._attempts[aid]
            student = self._students.get(sid, None)
            result = self._results.get(aid)
            roll = student.roll_no if student else sid[:8]
            name = student.name if student else "Unknown"
            if result and result.is_published:
                lines.append(
                    f"  {roll:<12} {name:<25} {result.scored:>4}/{exam.total_marks:<3}"
                    f" {result.percentage:>6.1f}%  {result.grade:>4}  {result.grade_point:>3}"
                )
            else:
                lines.append(f"  {roll:<12} {name:<25} {'Pending':>12}")
        lines.append("=" * 70)
        return "\n".join(lines)

  
    def _get_exam(self, exam_id: str) -> Exam:
        if exam_id not in self._exams:
            raise KeyError(f"Exam {exam_id} not found.")
        return self._exams[exam_id]

    def _get_student(self, student_id: str) -> Student:
        if student_id not in self._students:
            raise KeyError(f"Student {student_id} not found.")
        return self._students[student_id]

    def _get_attempt(self, attempt_id: str) -> ExamAttempt:
        if attempt_id not in self._attempts:
            raise KeyError(f"Attempt {attempt_id} not found.")
        return self._attempts[attempt_id]

    def _mandatory_ids(self, exam: Exam) -> list[str]:
        return [
            qid for qid in exam.question_ids
            if self._bank.get(qid).is_mandatory
        ]

    def _run_auto_grade(self, attempt: ExamAttempt, exam: Exam) -> None:
        questions = {qid: self._bank.get(qid) for qid in exam.question_ids}
        attempt.auto_grade(questions)

        has_descriptive = any(
            not self._bank.get(qid).is_objective() for qid in exam.question_ids
        )
        if not has_descriptive:
            self.finalize_and_publish_result(attempt.attempt_id)

    def _check_timer(self, attempt: ExamAttempt) -> None:
        if attempt.is_time_up():
            attempt.force_submit(auto=True)
            exam = self._get_exam(attempt.exam_id)
            self._run_auto_grade(attempt, exam)
            raise TimerExpiredError("Time is up. Your exam has been auto-submitted.")




class ExamWindowError(Exception):
    """Raised when a student tries to start/access an exam outside its window."""


class DuplicateAttemptError(Exception):
    """Raised when a student tries to submit an already-submitted exam."""


class TimerExpiredError(Exception):
    """Raised when a student tries to answer after time has expired."""
