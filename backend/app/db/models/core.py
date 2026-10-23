"""Core ORM models for the TOEIC Tutor Agent."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base


class User(Base):
    """Account information for a system user."""

    __tablename__ = "users"

    __table_args__ = (
        CheckConstraint(
            "role IN ('student', 'admin')",
            name="ck_users_role",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    email: Mapped[str] = mapped_column(
        String(320, collation="NOCASE"),
        nullable=False,
        unique=True,
    )

    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'student'"),
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("1"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.current_timestamp(),
    )

    profile: Mapped[StudentProfile | None] = relationship(
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )

    questions: Mapped[list[Question]] = relationship(
        back_populates="owner",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class StudentProfile(Base):
    """Learning preferences separated from authentication data."""

    __tablename__ = "student_profiles"

    __table_args__ = (
        CheckConstraint(
            "target_score IS NULL OR "
            "(target_score BETWEEN 0 AND 990)",
            name="ck_student_profiles_target_score",
        ),
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )

    target_score: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    timezone: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        server_default=text("'Asia/Ho_Chi_Minh'"),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    user: Mapped[User] = relationship(
        back_populates="profile",
    )


class Skill(Base):
    """Grammar, vocabulary, or reading skill."""

    __tablename__ = "skills"

    __table_args__ = (
        CheckConstraint(
            "category IN "
            "('grammar', 'vocabulary', 'reading', 'other')",
            name="ck_skills_category",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    code: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
    )

    name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    category: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    question_links: Mapped[list[QuestionSkill]] = relationship(
        back_populates="skill",
        cascade="all, delete-orphan",
    )


class Question(Base):
    """TOEIC question with a reviewed official answer key."""

    __tablename__ = "questions"

    __table_args__ = (
        CheckConstraint(
            "part IN (5, 6, 7)",
            name="ck_questions_part",
        ),
        CheckConstraint(
            "correct_option_key IN ('A', 'B', 'C', 'D')",
            name="ck_questions_correct_option_key",
        ),
        CheckConstraint(
            "difficulty IS NULL OR "
            "(difficulty BETWEEN 1 AND 5)",
            name="ck_questions_difficulty",
        ),
        CheckConstraint(
            "review_status IN "
            "('draft', 'pending_review', 'approved', 'rejected')",
            name="ck_questions_review_status",
        ),
        CheckConstraint(
            "source_type IN "
            "('original', 'licensed', 'ai_generated', "
            "'user_uploaded', 'third_party')",
            name="ck_questions_source_type",
        ),
        CheckConstraint(
            "usage_permission_status IN "
            "('unknown', 'granted', 'restricted')",
            name="ck_questions_permission",
        ),
        CheckConstraint(
            "visibility IN ('public', 'private')",
            name="ck_questions_visibility",
        ),
        CheckConstraint(
            "visibility = 'public' OR owner_user_id IS NOT NULL",
            name="ck_questions_private_owner",
        ),
        CheckConstraint(
            "length(trim(content)) > 0",
            name="ck_questions_content_not_empty",
        ),
        Index(
            "ix_questions_part_review_status",
            "part",
            "review_status",
        ),
        Index(
            "ix_questions_owner_user_id",
            "owner_user_id",
        ),
        Index(
            "ix_questions_content_hash",
            "content_hash",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    owner_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )

    part: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("5"),
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    
    explanation: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    correct_option_key: Mapped[str] = mapped_column(
        String(1),
        nullable=False,
    )

    difficulty: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    review_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'draft'"),
    )

    source_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=text("'original'"),
    )

    source_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    source_reference: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    source_license: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    usage_permission_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'unknown'"),
    )

    visibility: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        server_default=text("'public'"),
    )

    content_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.current_timestamp(),
    )

    owner: Mapped[User | None] = relationship(
        back_populates="questions",
    )

    options: Mapped[list[QuestionOption]] = relationship(
        back_populates="question",
        cascade="all, delete-orphan",
    )

    skill_links: Mapped[list[QuestionSkill]] = relationship(
        back_populates="question",
        cascade="all, delete-orphan",
    )


class QuestionOption(Base):
    """One multiple-choice option belonging to a question."""

    __tablename__ = "question_options"

    __table_args__ = (
        UniqueConstraint(
            "question_id",
            "option_key",
            name="uq_question_options_question_key",
        ),
        CheckConstraint(
            "option_key IN ('A', 'B', 'C', 'D')",
            name="ck_question_options_key",
        ),
        CheckConstraint(
            "length(trim(content)) > 0",
            name="ck_question_options_content_not_empty",
        ),
        Index(
            "ix_question_options_question_id",
            "question_id",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"),
        nullable=False,
    )

    option_key: Mapped[str] = mapped_column(
        String(1),
        nullable=False,
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    question: Mapped[Question] = relationship(
        back_populates="options",
    )


class QuestionSkill(Base):
    """Many-to-many association between questions and skills."""

    __tablename__ = "question_skills"

    __table_args__ = (
        Index(
            "ix_question_skills_skill_id",
            "skill_id",
        ),
    )

    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"),
        primary_key=True,
    )

    skill_id: Mapped[int] = mapped_column(
        ForeignKey("skills.id", ondelete="CASCADE"),
        primary_key=True,
    )

    question: Mapped[Question] = relationship(
        back_populates="skill_links",
    )

    skill: Mapped[Skill] = relationship(
        back_populates="question_links",
    )