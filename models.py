"""
Online Examination System - Data Models
"""

from __future__ import annotations
import uuid
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional



class QuestionType(Enum):
    MCQ = "mcq"
    TRUE_FALSE = "true_false"
    DESCRIPTIVE = "descriptive"


class Difficulty(Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class ExamStatus(Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ONGOING = "ongoing"
    ENDED = "ended"
    RESULTS_PUBLISHED = "results_published"


class AttemptStatus(Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"
    AUTO_SUBMITTED = "auto_submitted"
    GRADED = "graded"



@dataclass
class Question:
    text: str
    question_type: QuestionType
    marks: int
    difficulty: Difficulty
    subject: str
    options: list[str] = field(default_factory=list)        # MCQ choices
    correct_answer: Optional[str] = None                    # None for descriptive
    is_mandatory: bool = False
    question_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def validate(self) -> bool:
        """Ensure question data is consistent before adding to bank."""
        if not self.text.strip():
            return False
        if self.question_type == QuestionType.MCQ and len(self.options) < 2:
            return False
        if self.is_objective() and self.correct_answer is None:
            return False
        if self.marks <= 0:
            return False
        return True

    def get_mark(self, student_answer: str) -> int:
        """Return marks earned for the given answer (objective only)."""
        if not self.is_objective():
            raise ValueError("Use examiner review for descriptive questions.")
        if student_answer is None:
            return 0
        return self.marks if str(student_answer).strip().lower() == str(self.correct_answer).strip().lower() else 0

    def is_objective(self) -> bool:
        return self.question_type in (QuestionType.MCQ, QuestionType.TRUE_FALSE)

    def __repr__(self):
        return f"<Question [{self.question_type.value}] {self.text[:40]!r} ({self.marks}m)>"



class QuestionBank:
    def __init__(self, bank_id: Optional[str] = None):
        self.bank_id: str = bank_id or str(uuid.uuid4())
        self._questions: dict[str, Question] = {}

    def add_question(self, q: Question) -> None:
        if not q.validate():
            raise ValueError(f"Invalid question data: {q}")
        self._questions[q.question_id] = q

    def get(self, question_id: str) -> Question:
        if question_id not in self._questions:
            raise KeyError(f"Question {question_id} not found.")
        return self._questions[question_id]

    def search_by_tag(self, subject: Optional[str] = None,
                      difficulty: Optional[Difficulty] = None,
                      question_type: Optional[QuestionType] = None) -> list[Question]:
        results = list(self._questions.values())
        if subject:
            results = [q for q in results if q.subject.lower() == subject.lower()]
        if difficulty:
            results = [q for q in results if q.difficulty == difficulty]
        if question_type:
            results = [q for q in results if q.question_type == question_type]
        return results

    def random_select(self, count: int, subject: Optional[str] = None,
                      difficulty: Optional[Difficulty] = None) -> list[Question]:
        import random
        pool = self.search_by_tag(subject=subject, difficulty=difficulty)
        if len(pool) < count:
            raise ValueError(
                f"Not enough questions in bank. Needed {count}, found {len(pool)}."
            )
        return random.sample(pool, count)

    @property
    def all_questions(self) -> list[Question]:
        return list(self._questions.values())

    def __len__(self):
        return len(self._questions)

    def __repr__(self):
        return f"<QuestionBank questions={len(self._questions)}>"


# ─────────────────────────── Student ─────────────────────────────────────────

@dataclass
class Student:
    name: str
    roll_no: str
    email: str
    student_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    enrolled_exams: list[str] = field(default_factory=list)     # exam_ids
    attempt_ids: list[str] = field(default_factory=list)
    extra_time_minutes: int = 0                                  # disability accommodation

    def enroll(self, exam_id: str) -> None:
        if exam_id not in self.enrolled_exams:
            self.enrolled_exams.append(exam_id)

    def __repr__(self):
        return f"<Student {self.roll_no} – {self.name}>"


# ─────────────────────────── Exam ────────────────────────────────────────────

@dataclass
class Exam:
    title: str
    subject: str
    duration_minutes: int
    total_marks: int
    window_start: datetime
    window_end: datetime
    created_by: str                                             # admin user id
    exam_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: ExamStatus = ExamStatus.DRAFT
    question_ids: list[str] = field(default_factory=list)
    enrolled_student_ids: list[str] = field(default_factory=list)

    # ── Lifecycle ──────────────────────────────────────────────────────────
    def publish(self) -> None:
        if not self.question_ids:
            raise RuntimeError("Cannot publish exam with no questions.")
        if self.status != ExamStatus.DRAFT:
            raise RuntimeError(f"Exam already in state: {self.status.value}")
        self.status = ExamStatus.PUBLISHED

    def start(self) -> None:
        if self.status != ExamStatus.PUBLISHED:
            raise RuntimeError("Exam must be published before it can start.")
        self.status = ExamStatus.ONGOING

    def end(self) -> None:
        self.status = ExamStatus.ENDED

    def publish_results(self) -> None:
        self.status = ExamStatus.RESULTS_PUBLISHED

    # ── Queries ────────────────────────────────────────────────────────────
    def is_window_open(self, at: Optional[datetime] = None) -> bool:
        now = at or datetime.now()
        return self.window_start <= now <= self.window_end

    def add_question(self, question_id: str) -> None:
        if question_id not in self.question_ids:
            self.question_ids.append(question_id)

    def enroll_student(self, student_id: str) -> None:
        if student_id not in self.enrolled_student_ids:
            self.enrolled_student_ids.append(student_id)

    def __repr__(self):
        return f"<Exam {self.title!r} [{self.status.value}]>"


# ─────────────────────────── Answer ──────────────────────────────────────────

@dataclass
class Answer:
    question_id: str
    response: Optional[str] = None          # None = not answered
    is_flagged: bool = False                 # student flagged for review
    marks_awarded: Optional[int] = None     # set after grading
    saved_at: datetime = field(default_factory=datetime.now)



@dataclass
class ProctoringViolation:
    violation_type: str                     # e.g. "TAB_SWITCH"
    logged_at: datetime = field(default_factory=datetime.now)
    detail: str = ""



class ExamAttempt:
    MAX_TAB_VIOLATIONS = 3

    def __init__(self, student_id: str, exam_id: str,
                 exam_duration_minutes: int, extra_time_minutes: int = 0):
        self.attempt_id: str = str(uuid.uuid4())
        self.student_id = student_id
        self.exam_id = exam_id
        self.status: AttemptStatus = AttemptStatus.NOT_STARTED
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self._duration_minutes = exam_duration_minutes + extra_time_minutes
        self.answers: dict[str, Answer] = {}        # question_id -> Answer
        self.score: int = 0
        self.violations: list[ProctoringViolation] = []
        self._last_save: Optional[datetime] = None

    @property
    def deadline(self) -> Optional[datetime]:
        if self.start_time is None:
            return None
        return self.start_time + timedelta(minutes=self._duration_minutes)

    def seconds_remaining(self, at: Optional[datetime] = None) -> int:
        if self.deadline is None:
            return 0
        now = at or datetime.now()
        delta = (self.deadline - now).total_seconds()
        return max(0, int(delta))

    def is_time_up(self, at: Optional[datetime] = None) -> bool:
        return self.seconds_remaining(at) == 0

    def start(self) -> None:
        if self.status != AttemptStatus.NOT_STARTED:
            raise RuntimeError("Attempt already started or completed.")
        self.status = AttemptStatus.IN_PROGRESS
        self.start_time = datetime.now()

    def submit_answer(self, question_id: str, response: str) -> None:
        self._require_in_progress()
        if question_id not in self.answers:
            self.answers[question_id] = Answer(question_id)
        self.answers[question_id].response = response
        self.answers[question_id].saved_at = datetime.now()

    def flag_question(self, question_id: str, flagged: bool = True) -> None:
        self._require_in_progress()
        if question_id in self.answers:
            self.answers[question_id].is_flagged = flagged

    def auto_save(self) -> datetime:
        """Simulate server-side auto-save; returns save timestamp."""
        self._last_save = datetime.now()
        return self._last_save

    def submit(self, mandatory_ids: Optional[list[str]] = None) -> list[str]:
        """
        Returns list of unanswered mandatory question IDs.
        Caller should warn the student; actual submission must be forced.
        """
        self._require_in_progress()
        unanswered = []
        if mandatory_ids:
            for qid in mandatory_ids:
                ans = self.answers.get(qid)
                if ans is None or ans.response is None:
                    unanswered.append(qid)
        return unanswered

    def force_submit(self, auto: bool = False) -> None:
        self._require_in_progress()
        self.end_time = datetime.now()
        self.status = AttemptStatus.AUTO_SUBMITTED if auto else AttemptStatus.SUBMITTED

    def auto_grade(self, questions: dict[str, Question]) -> int:
        """Grades objective questions. Returns total objective score."""
        total = 0
        # Check ALL exam questions for descriptive, not just answered ones —
        # a student who skips a descriptive question still needs manual review.
        has_descriptive = any(not q.is_objective() for q in questions.values())
        for qid, answer in self.answers.items():
            q = questions.get(qid)
            if q is None:
                continue
            if q.is_objective():
                earned = q.get_mark(answer.response or "")
                answer.marks_awarded = earned
                total += earned
        self.score = total
        if not has_descriptive:
            self.status = AttemptStatus.GRADED
        return total


    def log_violation(self, violation_type: str, detail: str = "") -> bool:
        """
        Logs a proctoring violation.
        Returns True if the attempt should be auto-submitted (3rd tab switch).
        """
        v = ProctoringViolation(violation_type=violation_type, detail=detail)
        self.violations.append(v)
        tab_violations = sum(1 for x in self.violations if x.violation_type == "TAB_SWITCH")
        if tab_violations >= self.MAX_TAB_VIOLATIONS:
            self.force_submit(auto=True)
            return True
        return False

    @property
    def tab_violation_count(self) -> int:
        return sum(1 for v in self.violations if v.violation_type == "TAB_SWITCH")

    # ── Internal ───────────────────────────────────────────────────────────
    def _require_in_progress(self) -> None:
        if self.status != AttemptStatus.IN_PROGRESS:
            raise RuntimeError(f"Attempt is not in progress (status={self.status.value}).")

    def __repr__(self):
        return f"<ExamAttempt student={self.student_id[:8]} status={self.status.value}>"



GRADING_TABLE = [
    (90, 100, "O",  "Outstanding", 10),
    (80,  89, "A+", "Excellent",    9),
    (70,  79, "A",  "Very Good",    8),
    (60,  69, "B+", "Good",         7),
    (50,  59, "B",  "Average",      6),
    (40,  49, "C",  "Pass",         5),
    (0,   39, "F",  "Fail",         0),
]


def compute_grade(percentage: float) -> tuple[str, str, int]:
    """Returns (grade_letter, result_label, grade_point)."""
    for low, high, letter, label, gp in GRADING_TABLE:
        if low <= percentage <= high:
            return letter, label, gp
    return "F", "Fail", 0


@dataclass
class Result:
    attempt_id: str
    student_id: str
    exam_id: str
    total_marks: int
    scored: int
    result_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    is_published: bool = False
    generated_at: Optional[datetime] = None

    # Computed on generate()
    percentage: float = 0.0
    grade: str = ""
    result_label: str = ""
    grade_point: int = 0
    remarks: str = ""

    def generate(self) -> "Result":
        if self.total_marks == 0:
            raise ValueError("total_marks cannot be zero.")
        self.percentage = round((self.scored / self.total_marks) * 100, 2)
        self.grade, self.result_label, self.grade_point = compute_grade(self.percentage)
        self.generated_at = datetime.now()
        return self

    def publish(self) -> None:
        if not self.generated_at:
            raise RuntimeError("Call generate() before publish().")
        self.is_published = True

    def get_transcript(self) -> str:
        lines = [
            "=" * 50,
            "         EXAMINATION RESULT TRANSCRIPT",
            "=" * 50,
            f"  Result ID   : {self.result_id}",
            f"  Student ID  : {self.student_id}",
            f"  Exam ID     : {self.exam_id}",
            f"  Total Marks : {self.total_marks}",
            f"  Marks Scored: {self.scored}",
            f"  Percentage  : {self.percentage:.2f}%",
            f"  Grade       : {self.grade}  ({self.result_label})",
            f"  Grade Point : {self.grade_point}",
            f"  Remarks     : {self.remarks or '—'}",
            f"  Generated   : {self.generated_at}",
            f"  Published   : {'Yes' if self.is_published else 'Pending'}",
            "=" * 50,
        ]
        return "\n".join(lines)

    def __repr__(self):
        return (f"<Result {self.grade} {self.percentage:.1f}% "
                f"({self.scored}/{self.total_marks})>")
