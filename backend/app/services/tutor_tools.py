
"""Extensible, provider-independent tools for the TOEIC Tutor Agent."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from backend.app.db.models import (
    Attempt,
    QuestionSkill,
    QuizItem,
    QuizSession,
    Skill,
    StudentProfile,
    User,
)

logger = logging.getLogger(__name__)


class ToolError(RuntimeError):
    """Base exception for Tutor Tool errors."""


class ToolInputError(ToolError):
    """Raised when a tool name or its arguments are invalid."""


class UnknownToolError(ToolInputError):
    """Raised when the requested tool is not registered."""


class ToolExecutionError(ToolError):
    """Raised when a registered tool fails during execution."""


ToolHandler = Callable[
    [Session, int, dict[str, Any]],
    dict[str, Any],
]


@dataclass(frozen=True)
class ToolDefinition:
    """Provider-independent definition of one callable tool."""

    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler


class ToolRegistry:
    """Register, validate, and execute Tutor tools."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, definition: ToolDefinition) -> None:
        """Register a new tool without allowing duplicate names."""

        if not definition.name.strip():
            raise ValueError("Tool name must not be empty.")

        if definition.name in self._tools:
            raise ValueError(
                f"Tool '{definition.name}' is already registered."
            )

        self._tools[definition.name] = definition

    def get(self, name: str) -> ToolDefinition:
        """Return a registered tool definition."""

        definition = self._tools.get(name)

        if definition is None:
            raise UnknownToolError(
                f"Unknown Tutor tool: '{name}'."
            )

        return definition

    def get_all(self) -> tuple[ToolDefinition, ...]:
        """Return all registered tool definitions."""

        return tuple(self._tools.values())

    @staticmethod
    def _validate_arguments(
        definition: ToolDefinition,
        arguments: dict[str, Any],
    ) -> None:
        """Validate arguments against the supported JSON Schema subset."""

        if not isinstance(arguments, dict):
            raise ToolInputError(
                "Tool arguments must be a JSON object."
            )

        schema = definition.parameters

        if schema.get("type") != "object":
            raise ToolInputError(
                "Tool parameter schema must define an object."
            )

        properties = schema.get("properties", {})
        required = schema.get("required", [])

        if not isinstance(properties, dict):
            raise ToolInputError(
                "Invalid tool parameter properties."
            )

        if not isinstance(required, list):
            raise ToolInputError(
                "Invalid tool required parameters."
            )

        unknown_keys = set(arguments) - set(properties)

        if (
            unknown_keys
            and schema.get("additionalProperties", False) is False
        ):
            raise ToolInputError(
                "Unexpected tool arguments: "
                + ", ".join(sorted(unknown_keys))
            )

        missing_keys = set(required) - set(arguments)

        if missing_keys:
            raise ToolInputError(
                "Missing required tool arguments: "
                + ", ".join(sorted(missing_keys))
            )

        for key, value in arguments.items():
            property_schema = properties[key]
            expected_type = property_schema.get("type")

            if expected_type == "integer":
                if (
                    not isinstance(value, int)
                    or isinstance(value, bool)
                ):
                    raise ToolInputError(
                        f"Argument '{key}' must be an integer."
                    )

            elif expected_type == "string":
                if not isinstance(value, str):
                    raise ToolInputError(
                        f"Argument '{key}' must be a string."
                    )

            elif expected_type == "boolean":
                if not isinstance(value, bool):
                    raise ToolInputError(
                        f"Argument '{key}' must be a boolean."
                    )

            minimum = property_schema.get("minimum")
            maximum = property_schema.get("maximum")

            if minimum is not None and value < minimum:
                raise ToolInputError(
                    f"Argument '{key}' must be at least {minimum}."
                )

            if maximum is not None and value > maximum:
                raise ToolInputError(
                    f"Argument '{key}' must not exceed {maximum}."
                )

    def execute(
        self,
        name: str,
        arguments: dict[str, Any],
        db: Session,
        student_id: int,
    ) -> dict[str, Any]:
        """Validate and execute a tool for the authenticated student."""

        if (
            not isinstance(student_id, int)
            or isinstance(student_id, bool)
            or student_id <= 0
        ):
            raise ToolInputError(
                "Authenticated student ID is invalid."
            )

        definition = self.get(name)

        self._validate_arguments(
            definition=definition,
            arguments=arguments,
        )

        try:
            return definition.handler(
                db,
                student_id,
                arguments,
            )

        except ToolError:
            raise

        except Exception as exc:
            logger.exception(
                "Tutor tool execution failed: tool=%s",
                name,
            )

            raise ToolExecutionError(
                f"Tool '{name}' could not be executed."
            ) from exc


def _get_student_profile(
    db: Session,
    student_id: int,
    _arguments: dict[str, Any],
) -> dict[str, Any]:
    """Return the authenticated student's learning profile."""

    user = db.get(User, student_id)

    if user is None:
        raise ToolExecutionError(
            "Authenticated student does not exist."
        )

    profile = db.get(StudentProfile, student_id)

    if profile is None:
        return {
            "profile_found": False,
            "target_score": None,
            "timezone": None,
            "message": "Student has not created a learning profile.",
        }

    return {
        "profile_found": True,
        "target_score": profile.target_score,
        "timezone": profile.timezone,
    }


def _get_weak_skills(
    db: Session,
    student_id: int,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Identify skills with the highest first-attempt error rates."""

    user = db.get(User, student_id)

    if user is None:
        raise ToolExecutionError(
            "Authenticated student does not exist."
        )

    limit = arguments.get("limit", 5)

    incorrect_count = func.sum(
        case(
            (Attempt.is_correct.is_(False), 1),
            else_=0,
        )
    )

    attempt_count = func.count(Attempt.id)

    error_rate = (
        incorrect_count * 1.0 / attempt_count
    )

    statement = (
        select(
            Skill.code.label("skill_code"),
            Skill.name.label("skill_name"),
            Skill.category.label("category"),
            attempt_count.label("attempt_count"),
            incorrect_count.label("incorrect_count"),
        )
        .select_from(Attempt)
        .join(
            QuizItem,
            QuizItem.id == Attempt.quiz_item_id,
        )
        .join(
            QuizSession,
            QuizSession.id == QuizItem.quiz_session_id,
        )
        .join(
            QuestionSkill,
            QuestionSkill.question_id == QuizItem.question_id,
        )
        .join(
            Skill,
            Skill.id == QuestionSkill.skill_id,
        )
        .where(
            Attempt.user_id == student_id,
            QuizSession.user_id == student_id,
            Attempt.attempt_number == 1,
        )
        .group_by(
            Skill.id,
            Skill.code,
            Skill.name,
            Skill.category,
        )
        .having(attempt_count >= 2)
        .order_by(
            error_rate.desc(),
            attempt_count.desc(),
            Skill.name.asc(),
        )
        .limit(limit)
    )

    rows = db.execute(statement).all()

    weak_skills = []

    for row in rows:
        total = int(row.attempt_count)
        incorrect = int(row.incorrect_count or 0)
        correct = total - incorrect

        weak_skills.append(
            {
                "skill_code": row.skill_code,
                "skill_name": row.skill_name,
                "category": row.category,
                "attempt_count": total,
                "incorrect_count": incorrect,
                "correct_count": correct,
                "accuracy_percent": round(
                    correct / total * 100,
                    1,
                ),
            }
        )

    return {
        "has_data": bool(weak_skills),
        "analysis_basis": "first_attempt_only",
        "minimum_attempts_per_skill": 2,
        "weak_skills": weak_skills,
        "message": (
            "Weak skills were identified from the student's "
            "first attempts."
            if weak_skills
            else (
                "Not enough practice data to identify weak skills. "
                "The student needs at least two first attempts "
                "for a skill."
            )
        ),
    }


# -------------------------------------------------------------------
# Initial Tutor Tool Registry
# -------------------------------------------------------------------

TUTOR_TOOL_REGISTRY = ToolRegistry()


TUTOR_TOOL_REGISTRY.register(
    ToolDefinition(
        name="get_student_profile",
        description=(
            "Get the authenticated student's TOEIC learning profile, "
            "including target score and timezone. "
            "This tool does not accept a student ID."
        ),
        parameters={
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
        handler=_get_student_profile,
    )
)


TUTOR_TOOL_REGISTRY.register(
    ToolDefinition(
        name="get_weak_skills",
        description=(
            "Identify the student's weakest TOEIC skills using "
            "first-attempt quiz results. "
            "Returns attempt counts, incorrect counts, and accuracy. "
            "This tool does not accept a student ID."
        ),
        parameters={
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 10,
                    "description": (
                        "Maximum number of weak skills to return. "
                        "Default is 5."
                    ),
                }
            },
            "required": [],
            "additionalProperties": False,
        },
        handler=_get_weak_skills,
    )
)
