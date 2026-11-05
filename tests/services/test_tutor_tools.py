
"""Tests for the extensible TOEIC Tutor Tool Registry."""

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.db.base import Base
from backend.app.db.models import (
    Attempt,
    Question,
    QuestionOption,
    QuestionSkill,
    QuizItem,
    QuizSession,
    Skill,
    StudentProfile,
    User,
)
from backend.app.services.tutor_tools import (
    ToolDefinition,
    ToolInputError,
    ToolRegistry,
    ToolExecutionError,
    TUTOR_TOOL_REGISTRY,
    UnknownToolError,
)
from types import SimpleNamespace

from backend.app.services.retrieval_service import (
    RetrievalServiceError,
)
from backend.app.services import tutor_tools

@pytest.fixture
def db() -> Iterator[Session]:
    """Create an isolated in-memory SQLite database."""

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    Base.metadata.create_all(engine)

    with Session(engine) as session:
        yield session

    engine.dispose()


def create_user(
    db: Session,
    email: str,
) -> User:
    user = User(
        email=email,
        password_hash="test-only-password-hash",
    )
    db.add(user)
    db.flush()
    return user


def create_question(
    db: Session,
    user_id: int,
    skill: Skill,
    question_number: int,
    correct: bool,
) -> None:
    """Create one question, quiz item, and first attempt."""

    question = Question(
        part=5,
        content=f"Test question {question_number}",
        correct_option_key="A",
        content_hash=f"{question_number:064d}",
    )
    db.add(question)
    db.flush()

    db.add(
        QuestionSkill(
            question_id=question.id,
            skill_id=skill.id,
        )
    )

    quiz_session = QuizSession(user_id=user_id)
    db.add(quiz_session)
    db.flush()

    quiz_item = QuizItem(
        quiz_session_id=quiz_session.id,
        question_id=question.id,
        position=1,
        question_snapshot={
            "content": f"Test question {question_number}",
        },
        answer_key_snapshot="A",
    )
    db.add(quiz_item)
    db.flush()

    db.add(
        Attempt(
            user_id=user_id,
            quiz_item_id=quiz_item.id,
            attempt_number=1,
            selected_option_key="A" if correct else "B",
            is_correct=correct,
            is_retry=False,
        )
    )

    db.flush()

def create_recommendation_candidate(
    db: Session,
    skill: Skill,
    question_number: int,
    part: int = 5,
) -> Question:
    """Create an approved question eligible for recommendation."""

    question = Question(
        part=part,
        content=f"Recommendation candidate {question_number}",
        correct_option_key="A",
        explanation="Test explanation.",
        review_status="approved",
        usage_permission_status="granted",
        visibility="public",
        content_hash=f"{question_number:064d}",
    )

    db.add(question)
    db.flush()

    db.add(
        QuestionSkill(
            question_id=question.id,
            skill_id=skill.id,
        )
    )

    db.flush()

    return question

def test_registry_contains_initial_tools() -> None:
    names = {
        definition.name
        for definition in TUTOR_TOOL_REGISTRY.get_all()
    }

    assert names == {
        "get_student_profile",
        "get_weak_skills",
        "get_learning_progress",
        "search_question",
        "recommend_questions",
        "retrieve_global_knowledge",
    }


def test_get_student_profile_returns_learning_preferences(
    db: Session,
) -> None:
    user = create_user(db, "student@example.test")

    db.add(
        StudentProfile(
            user_id=user.id,
            target_score=750,
            timezone="Asia/Ho_Chi_Minh",
        )
    )
    db.commit()

    result = TUTOR_TOOL_REGISTRY.execute(
        name="get_student_profile",
        arguments={},
        db=db,
        student_id=user.id,
    )

    assert result == {
        "profile_found": True,
        "target_score": 750,
        "timezone": "Asia/Ho_Chi_Minh",
    }

    assert "email" not in result
    assert "password_hash" not in result


def test_get_student_profile_handles_missing_profile(
    db: Session,
) -> None:
    user = create_user(db, "student@example.test")
    db.commit()

    result = TUTOR_TOOL_REGISTRY.execute(
        name="get_student_profile",
        arguments={},
        db=db,
        student_id=user.id,
    )

    assert result["profile_found"] is False
    assert result["target_score"] is None


def test_get_weak_skills_ranks_high_error_rate_first(
    db: Session,
) -> None:
    user = create_user(db, "student@example.test")

    grammar = Skill(
        code="GRAMMAR_TEST",
        name="Grammar test",
        category="grammar",
    )

    vocabulary = Skill(
        code="VOCAB_TEST",
        name="Vocabulary test",
        category="vocabulary",
    )

    db.add_all([grammar, vocabulary])
    db.flush()

    # Grammar: 2 incorrect out of 2 attempts.
    create_question(db, user.id, grammar, 1, False)
    create_question(db, user.id, grammar, 2, False)

    # Vocabulary: 1 incorrect out of 2 attempts.
    create_question(db, user.id, vocabulary, 3, False)
    create_question(db, user.id, vocabulary, 4, True)

    db.commit()

    result = TUTOR_TOOL_REGISTRY.execute(
        name="get_weak_skills",
        arguments={"limit": 5},
        db=db,
        student_id=user.id,
    )

    skills = result["weak_skills"]

    assert len(skills) == 2

    assert skills[0]["skill_code"] == "GRAMMAR_TEST"
    assert skills[0]["attempt_count"] == 2
    assert skills[0]["incorrect_count"] == 2
    assert skills[0]["accuracy_percent"] == 0.0

    assert skills[1]["skill_code"] == "VOCAB_TEST"
    assert skills[1]["accuracy_percent"] == 50.0



def test_get_weak_skills_ignores_retry_attempts(
    db: Session,
) -> None:
    user = create_user(db, "student@example.test")

    skill = Skill(
        code="RETRY_TEST",
        name="Retry test",
        category="grammar",
    )
    db.add(skill)
    db.flush()

    create_question(db, user.id, skill, 10, False)
    create_question(db, user.id, skill, 11, False)

    # Get the first quiz item using the actual question ID.
    first_question = (
        db.query(Question)
        .filter(Question.content == "Test question 10")
        .one()
    )

    first_item = (
        db.query(QuizItem)
        .filter(QuizItem.question_id == first_question.id)
        .one()
    )

    # Add a retry that is correct.
    db.add(
        Attempt(
            user_id=user.id,
            quiz_item_id=first_item.id,
            attempt_number=2,
            selected_option_key="A",
            is_correct=True,
            is_retry=True,
        )
    )

    db.commit()

    result = TUTOR_TOOL_REGISTRY.execute(
        name="get_weak_skills",
        arguments={},
        db=db,
        student_id=user.id,
    )

    skill_result = result["weak_skills"][0]

    assert skill_result["attempt_count"] == 2
    assert skill_result["incorrect_count"] == 2
    assert skill_result["accuracy_percent"] == 0.0


def test_get_weak_skills_does_not_read_another_student(
    db: Session,
) -> None:
    student_one = create_user(db, "one@example.test")
    student_two = create_user(db, "two@example.test")

    skill = Skill(
        code="PRIVATE_TEST",
        name="Private test",
        category="grammar",
    )
    db.add(skill)
    db.flush()

    create_question(db, student_one.id, skill, 20, False)
    create_question(db, student_one.id, skill, 21, False)

    db.commit()

    result = TUTOR_TOOL_REGISTRY.execute(
        name="get_weak_skills",
        arguments={},
        db=db,
        student_id=student_two.id,
    )

    assert result["has_data"] is False
    assert result["weak_skills"] == []


def test_get_weak_skills_requires_two_first_attempts(
    db: Session,
) -> None:
    user = create_user(db, "student@example.test")

    skill = Skill(
        code="LOW_DATA",
        name="Low data skill",
        category="grammar",
    )
    db.add(skill)
    db.flush()

    create_question(db, user.id, skill, 30, False)
    db.commit()

    result = TUTOR_TOOL_REGISTRY.execute(
        name="get_weak_skills",
        arguments={},
        db=db,
        student_id=user.id,
    )

    assert result["has_data"] is False
    assert result["weak_skills"] == []


@pytest.mark.parametrize(
    "arguments",
    [
        {"limit": 0},
        {"limit": 11},
        {"limit": True},
        {"unexpected": "value"},
    ],
)
def test_get_weak_skills_rejects_invalid_arguments(
    db: Session,
    arguments: dict,
) -> None:
    user = create_user(db, "student@example.test")

    with pytest.raises(ToolInputError):
        TUTOR_TOOL_REGISTRY.execute(
            name="get_weak_skills",
            arguments=arguments,
            db=db,
            student_id=user.id,
        )


def test_profile_tool_rejects_unexpected_student_id(
    db: Session,
) -> None:
    user = create_user(db, "student@example.test")

    with pytest.raises(ToolInputError):
        TUTOR_TOOL_REGISTRY.execute(
            name="get_student_profile",
            arguments={"student_id": user.id},
            db=db,
            student_id=user.id,
        )


def test_registry_rejects_unknown_tool(
    db: Session,
) -> None:
    user = create_user(db, "student@example.test")

    with pytest.raises(UnknownToolError):
        TUTOR_TOOL_REGISTRY.execute(
            name="delete_all_data",
            arguments={},
            db=db,
            student_id=user.id,
        )


def test_registry_rejects_invalid_student_id(
    db: Session,
) -> None:
    with pytest.raises(ToolInputError):
        TUTOR_TOOL_REGISTRY.execute(
            name="get_student_profile",
            arguments={},
            db=db,
            student_id=True,
        )


def test_registry_rejects_duplicate_tool_names() -> None:
    registry = ToolRegistry()

    definition = ToolDefinition(
        name="sample_tool",
        description="A test tool.",
        parameters={
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
        handler=lambda db, student_id, arguments: {},
    )

    registry.register(definition)

    with pytest.raises(ValueError):
        registry.register(definition)


def test_get_learning_progress_returns_first_attempt_statistics(
    db: Session,
) -> None:
    user = create_user(db, "progress@example.test")

    skill = Skill(
        code="PROGRESS_TEST",
        name="Progress test",
        category="grammar",
    )
    db.add(skill)
    db.flush()

    create_question(db, user.id, skill, 101, True)
    create_question(db, user.id, skill, 102, False)

    # Add a correct retry. It must not change first-attempt accuracy.
    first_item = (
        db.query(QuizItem)
        .join(Question)
        .filter(Question.content == "Test question 102")
        .one()
    )

    db.add(
        Attempt(
            user_id=user.id,
            quiz_item_id=first_item.id,
            attempt_number=2,
            selected_option_key="A",
            is_correct=True,
            is_retry=True,
        )
    )

    db.commit()

    result = TUTOR_TOOL_REGISTRY.execute(
        name="get_learning_progress",
        arguments={},
        db=db,
        student_id=user.id,
    )

    assert result["has_data"] is True
    assert result["quiz_session_count"] == 2
    assert result["first_attempt_count"] == 2
    assert result["correct_count"] == 1
    assert result["incorrect_count"] == 1
    assert result["accuracy_percent"] == 50.0
    assert result["analysis_basis"] == "first_attempt_only"


def test_get_learning_progress_handles_no_data(
    db: Session,
) -> None:
    user = create_user(db, "empty-progress@example.test")
    db.commit()

    result = TUTOR_TOOL_REGISTRY.execute(
        name="get_learning_progress",
        arguments={},
        db=db,
        student_id=user.id,
    )

    assert result["has_data"] is False
    assert result["first_attempt_count"] == 0
    assert result["accuracy_percent"] == 0.0


def test_search_question_by_id(
    db: Session,
) -> None:
    user = create_user(db, "search@example.test")

    question = Question(
        part=5,
        content="The manager _____ the report.",
        correct_option_key="A",
        explanation="Use the present simple form.",
        review_status="approved",
        usage_permission_status="granted",
        visibility="public",
        content_hash="a" * 64,
    )
    db.add(question)
    db.flush()

    db.add_all(
        [
            QuestionOption(
                question_id=question.id,
                option_key="A",
                content="reviews",
            ),
            QuestionOption(
                question_id=question.id,
                option_key="B",
                content="review",
            ),
        ]
    )
    db.commit()

    result = TUTOR_TOOL_REGISTRY.execute(
        name="search_question",
        arguments={"question_id": question.id},
        db=db,
        student_id=user.id,
    )

    assert result["has_results"] is True
    assert result["result_count"] == 1

    found = result["results"][0]

    assert found["question_id"] == question.id
    assert found["correct_option_key"] == "A"
    assert len(found["options"]) == 2


def test_search_question_by_text(
    db: Session,
) -> None:
    user = create_user(db, "text-search@example.test")

    question = Question(
        part=5,
        content="The employees _____ hard every day.",
        correct_option_key="B",
        review_status="approved",
        usage_permission_status="granted",
        visibility="public",
        content_hash="b" * 64,
    )
    db.add(question)
    db.commit()

    result = TUTOR_TOOL_REGISTRY.execute(
        name="search_question",
        arguments={"query": "employees"},
        db=db,
        student_id=user.id,
    )

    assert result["has_results"] is True
    assert result["result_count"] == 1


def test_search_question_excludes_unapproved_questions(
    db: Session,
) -> None:
    user = create_user(db, "approval@example.test")

    question = Question(
        part=5,
        content="Unapproved test question.",
        correct_option_key="A",
        review_status="draft",
        usage_permission_status="granted",
        visibility="public",
        content_hash="c" * 64,
    )
    db.add(question)
    db.commit()

    result = TUTOR_TOOL_REGISTRY.execute(
        name="search_question",
        arguments={"query": "Unapproved"},
        db=db,
        student_id=user.id,
    )

    assert result["has_results"] is False
    assert result["results"] == []


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"question_id": 1, "query": "test"},
        {"question_id": 0},
        {"query": "   "},
        {"unexpected": "value"},
    ],
)
def test_search_question_rejects_invalid_arguments(
    db: Session,
    arguments: dict,
) -> None:
    user = create_user(db, "invalid-search@example.test")

    with pytest.raises(ToolInputError):
        TUTOR_TOOL_REGISTRY.execute(
            name="search_question",
            arguments=arguments,
            db=db,
            student_id=user.id,
        )

def test_recommend_questions_prioritizes_weak_skills(
    db: Session,
) -> None:
    user = create_user(db, "recommend@example.test")

    grammar = Skill(
        code="RECOMMEND_GRAMMAR",
        name="Grammar",
        category="grammar",
    )

    vocabulary = Skill(
        code="RECOMMEND_VOCAB",
        name="Vocabulary",
        category="vocabulary",
    )

    db.add_all([grammar, vocabulary])
    db.flush()

    # Two incorrect first attempts make Grammar a weak skill.
    create_question(db, user.id, grammar, 201, False)
    create_question(db, user.id, grammar, 202, False)

    grammar_candidate = create_recommendation_candidate(
        db,
        grammar,
        203,
    )

    vocabulary_candidate = create_recommendation_candidate(
        db,
        vocabulary,
        204,
    )

    db.commit()

    result = TUTOR_TOOL_REGISTRY.execute(
        name="recommend_questions",
        arguments={},
        db=db,
        student_id=user.id,
    )

    assert result["has_recommendations"] is True
    assert result["recommendation_basis"] == "weak_skills"
    assert "RECOMMEND_GRAMMAR" in result["target_weak_skills"]

    recommended_ids = {
        item["question_id"]
        for item in result["recommendations"]
    }

    assert grammar_candidate.id in recommended_ids
    assert vocabulary_candidate.id not in recommended_ids

    # The tool must not reveal answers or explanations.
    for item in result["recommendations"]:
        assert "correct_option_key" not in item
        assert "explanation" not in item


def test_recommend_questions_uses_general_practice_without_weak_skills(
    db: Session,
) -> None:
    user = create_user(db, "general-recommend@example.test")

    skill = Skill(
        code="GENERAL_RECOMMEND",
        name="General practice",
        category="grammar",
    )

    db.add(skill)
    db.flush()

    candidate = create_recommendation_candidate(
        db,
        skill,
        205,
    )

    db.commit()

    result = TUTOR_TOOL_REGISTRY.execute(
        name="recommend_questions",
        arguments={},
        db=db,
        student_id=user.id,
    )

    assert result["has_recommendations"] is True

    assert (
        result["recommendation_basis"]
        == "general_practice_no_identified_weak_skills"
    )

    assert result["target_weak_skills"] == []

    assert (
        result["recommendations"][0]["question_id"]
        == candidate.id
    )


def test_recommend_questions_filters_by_part(
    db: Session,
) -> None:
    user = create_user(db, "part-recommend@example.test")

    skill = Skill(
        code="PART_FILTER",
        name="Part filter",
        category="grammar",
    )

    db.add(skill)
    db.flush()

    create_recommendation_candidate(
        db,
        skill,
        206,
        part=5,
    )

    part_six_candidate = create_recommendation_candidate(
        db,
        skill,
        207,
        part=6,
    )

    db.commit()

    result = TUTOR_TOOL_REGISTRY.execute(
        name="recommend_questions",
        arguments={"part": 6},
        db=db,
        student_id=user.id,
    )

    assert result["has_recommendations"] is True

    assert all(
        item["part"] == 6
        for item in result["recommendations"]
    )

    assert (
        result["recommendations"][0]["question_id"]
        == part_six_candidate.id
    )


@pytest.mark.parametrize(
    "arguments",
    [
        {"part": 4},
        {"part": 8},
        {"limit": 0},
        {"limit": 11},
        {"unexpected": "value"},
    ],
)
def test_recommend_questions_rejects_invalid_arguments(
    db: Session,
    arguments: dict,
) -> None:
    user = create_user(db, "invalid-recommend@example.test")

    with pytest.raises(ToolInputError):
        TUTOR_TOOL_REGISTRY.execute(
            name="recommend_questions",
            arguments=arguments,
            db=db,
            student_id=user.id,
        )

def create_fake_retrieved_chunk():
    return SimpleNamespace(
        document_id=10,
        document_title="TOEIC Grammar Guide",
        original_filename="toeic_grammar.pdf",
        chunk_index=2,
        content="The present simple is used for habits and facts.",
        page_number=5,
        source_name="TOEIC Study Materials",
        source_reference="https://example.test/toeic-grammar",
        source_license="CC BY 4.0",
        distance=0.15,
    )

def test_retrieve_global_knowledge_returns_sources(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = create_user(db, "rag-tool@example.test")

    fake_chunk = create_fake_retrieved_chunk()

    class FakeRetrievalService:
        def retrieve(self, db, query, top_k):
            assert query == "Present simple tense"
            assert top_k == 3
            return [fake_chunk]

    monkeypatch.setattr(
        tutor_tools,
        "_get_retrieval_service",
        lambda: FakeRetrievalService(),
    )

    result = TUTOR_TOOL_REGISTRY.execute(
        name="retrieve_global_knowledge",
        arguments={
            "query": "Present simple tense",
            "top_k": 3,
        },
        db=db,
        student_id=user.id,
    )

    assert result["has_results"] is True
    assert result["result_count"] == 1

    source = result["sources"][0]

    assert source["document_id"] == 10
    assert source["document_title"] == "TOEIC Grammar Guide"
    assert source["page_number"] == 5
    assert source["source_reference"] == (
        "https://example.test/toeic-grammar"
    )

    assert "content_trust_notice" in result

def test_retrieve_global_knowledge_handles_empty_results(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = create_user(db, "empty-rag@example.test")

    class FakeRetrievalService:
        def retrieve(self, db, query, top_k):
            return []

    monkeypatch.setattr(
        tutor_tools,
        "_get_retrieval_service",
        lambda: FakeRetrievalService(),
    )

    result = TUTOR_TOOL_REGISTRY.execute(
        name="retrieve_global_knowledge",
        arguments={"query": "Unknown TOEIC topic"},
        db=db,
        student_id=user.id,
    )

    assert result["has_results"] is False
    assert result["result_count"] == 0
    assert result["sources"] == []

def test_retrieve_global_knowledge_handles_service_error(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = create_user(db, "error-rag@example.test")

    class FakeRetrievalService:
        def retrieve(self, db, query, top_k):
            raise RetrievalServiceError("Simulated retrieval failure")

    monkeypatch.setattr(
        tutor_tools,
        "_get_retrieval_service",
        lambda: FakeRetrievalService(),
    )

    with pytest.raises(ToolExecutionError):
        TUTOR_TOOL_REGISTRY.execute(
            name="retrieve_global_knowledge",
            arguments={"query": "TOEIC grammar"},
            db=db,
            student_id=user.id,
        )

@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"query": ""},
        {"query": "   "},
        {"query": "x" * 1001},
        {"query": "TOEIC", "top_k": 0},
        {"query": "TOEIC", "top_k": 6},
        {"query": "TOEIC", "top_k": True},
        {"query": "TOEIC", "student_id": 123},
    ],
)
def test_retrieve_global_knowledge_rejects_invalid_arguments(
    db: Session,
    arguments: dict,
) -> None:
    user = create_user(db, "invalid-rag@example.test")

    with pytest.raises(ToolInputError):
        TUTOR_TOOL_REGISTRY.execute(
            name="retrieve_global_knowledge",
            arguments=arguments,
            db=db,
            student_id=user.id,
        )