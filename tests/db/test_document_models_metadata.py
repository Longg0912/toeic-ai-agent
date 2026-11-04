"""Metadata tests for global RAG document models."""

from sqlalchemy import CheckConstraint
from sqlalchemy.orm import configure_mappers

from backend.app.db.base import Base
from backend.app.db.models import Document, DocumentChunk


def test_document_tables_registered() -> None:
    """Both document tables must be registered."""

    expected = {
        "documents",
        "document_chunks",
    }

    actual = set(Base.metadata.tables.keys())

    assert expected.issubset(actual)


def test_document_relationships_configured() -> None:
    """SQLAlchemy must configure document relationships."""

    configure_mappers()

    assert Document.__tablename__ == "documents"
    assert DocumentChunk.__tablename__ == "document_chunks"

    assert Document.chunks.property.back_populates == "document"

    assert DocumentChunk.document.property.back_populates == "chunks"


def test_document_chunk_foreign_key() -> None:
    """Every chunk must reference its source document."""

    column = Base.metadata.tables[
        "document_chunks"
    ].c["document_id"]

    targets = {
        foreign_key.target_fullname
        for foreign_key in column.foreign_keys
    }

    assert "documents.id" in targets


def test_document_check_constraints_registered() -> None:
    """Document metadata must contain its validation constraints."""

    table = Base.metadata.tables["documents"]

    constraint_names = {
        constraint.name
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }

    assert "ck_documents_document_type" in constraint_names
    assert "ck_documents_usage_permission" in constraint_names
    assert "ck_documents_processing_status" in constraint_names
    assert "ck_documents_content_hash_length" in constraint_names


def test_document_chunk_check_constraints_registered() -> None:
    """Chunk metadata must contain its validation constraints."""

    table = Base.metadata.tables["document_chunks"]

    constraint_names = {
        constraint.name
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }

    assert "ck_document_chunks_chunk_index" in constraint_names
    assert "ck_document_chunks_content_not_empty" in constraint_names
    assert "ck_document_chunks_token_count" in constraint_names
    assert "ck_document_chunks_vector_id_not_empty" in constraint_names
    assert "ck_document_chunks_page_number" in constraint_names


def test_document_indexes_registered() -> None:
    """Document tables must have indexes for common queries."""

    document_indexes = {
        index.name
        for index in Document.__table__.indexes
    }

    chunk_indexes = {
        index.name
        for index in DocumentChunk.__table__.indexes
    }

    assert "ix_documents_status_permission" in document_indexes
    assert "ix_document_chunks_document_id" in chunk_indexes

def test_document_chunk_page_number_column_registered() -> None:
    """Chunks must retain their source page when available."""

    table = Base.metadata.tables["document_chunks"]

    assert "page_number" in table.c
    assert table.c["page_number"].nullable is True