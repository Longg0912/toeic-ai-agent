
"""Response schemas for TOEIC question APIs."""

from pydantic import BaseModel


class Part5OptionPublic(BaseModel):
    """One answer choice shown during practice."""

    option_key: str
    content: str


class Part5QuestionPublic(BaseModel):
    """A question that is safe to display during practice."""

    id: int
    content: str
    difficulty: int | None
    options: list[Part5OptionPublic]
    skill_codes: list[str]


class Part5QuestionListResponse(BaseModel):
    """Paginated response containing TOEIC Part 5 questions."""

    items: list[Part5QuestionPublic]
    total: int
    limit: int
    offset: int
