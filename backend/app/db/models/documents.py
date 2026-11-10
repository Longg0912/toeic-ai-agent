
"""ORM models for global and personal TOEIC RAG documents."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base


class Document(Base):
    """A global or user-owned source document for TOEIC RAG."""

    __tablename__ = "documents"

    __table_args__ = (
        CheckConstraint(
            "length(trim(title)) > 0",
            name="ck_documents_title_not_empty",
        ),
        CheckConstraint(
            "length(trim(original_filename)) > 0",
            name="ck_documents_filename_not_empty",
        ),
        CheckConstraint(
            "document_type IN ('pdf', 'docx', 'txt', 'md', 'html')",
            name="ck_documents_document_type",
        ),
        CheckConstraint(
            "usage_permission_status IN "
            "('unknown', 'granted', 'restricted')",
            name="ck_documents_usage_permission",
        ),
        CheckConstraint(
            "processing_status IN "
            "('pending', 'processing', 'indexed', "
            "'failed', 'archived')",
            name="ck_documents_processing_status",
        ),
        CheckConstraint(
            "length(content_hash) = 64",
            name="ck_documents_content_hash_length",
        ),
        CheckConstraint(
            "length(trim(storage_path)) > 0",
            name="ck_documents_storage_path_not_empty",
        ),

        # Global documents: content_hash must be unique.
        Index(
            "uq_documents_global_content_hash",
            "content_hash",
            unique=True,
            sqlite_where=text("owner_user_id IS NULL"),
        ),

        # Personal documents: uniqueness is scoped to one owner.
        Index(
            "uq_documents_personal_owner_hash",
            "owner_user_id",
            "content_hash",
            unique=True,
            sqlite_where=text("owner_user_id IS NOT NULL"),
        ),

        Index(
            "ix_documents_status_permission",
            "processing_status",
            "usage_permission_status",
        ),
        Index(
            "ix_documents_owner_status",
            "owner_user_id",
            "processing_status",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    # NULL means Global RAG.
    # A user ID means Personal RAG.
    owner_user_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        nullable=True,
    )

    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    original_filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    document_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    # Relative path under the project's data directory.
    # Do not store absolute paths or file bytes in this column.
    storage_path: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    content_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
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

    processing_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'pending'"),
    )

    embedding_model: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
    )

    processing_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.current_timestamp(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    chunks: Mapped[list[DocumentChunk]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="DocumentChunk.chunk_index",
    )


class DocumentChunk(Base):
    """A text chunk extracted from a source document."""

    __tablename__ = "document_chunks"

    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "chunk_index",
            name="uq_document_chunks_document_index",
        ),
        UniqueConstraint(
            "vector_id",
            name="uq_document_chunks_vector_id",
        ),
        CheckConstraint(
            "chunk_index >= 0",
            name="ck_document_chunks_chunk_index",
        ),
        CheckConstraint(
            "length(trim(content)) > 0",
            name="ck_document_chunks_content_not_empty",
        ),
        CheckConstraint(
            "length(content_hash) = 64",
            name="ck_document_chunks_content_hash_length",
        ),
        CheckConstraint(
            "vector_id IS NOT NULL AND length(trim(vector_id)) > 0",
            name="ck_document_chunks_vector_id_not_empty",
        ),
        CheckConstraint(
            "token_count IS NULL OR token_count >= 0",
            name="ck_document_chunks_token_count",
        ),
        CheckConstraint(
            "page_number IS NULL OR page_number >= 1",
            name="ck_document_chunks_page_number",
        ),
        Index(
            "ix_document_chunks_document_id",
            "document_id",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    document_id: Mapped[int] = mapped_column(
        ForeignKey(
            "documents.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    chunk_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    page_number: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    content_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    token_count: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    # This ID will be used to find/delete the corresponding
    # embedding in ChromaDB.
    vector_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.current_timestamp(),
    )

    document: Mapped[Document] = relationship(
        back_populates="chunks",
    )
