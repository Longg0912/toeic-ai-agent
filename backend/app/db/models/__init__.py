"""Import ORM models into the shared SQLAlchemy metadata."""

from backend.app.db.models.core import (
    Question,
    QuestionOption,
    QuestionSkill,
    Skill,
    StudentProfile,
    User,
)

from backend.app.db.models.quiz import (
    Attempt,
    QuizItem,
    QuizSession,
)

__all__ = [
    "User",
    "StudentProfile",
    "Skill",
    "Question",
    "QuestionOption",
    "QuestionSkill",
    "QuizSession",
    "QuizItem",
    "Attempt",
]