"""Tests for document extraction and chunk processing."""

import hashlib

from pathlib import Path

import pytest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.app.db.base import Base
from backend.app.db.models import Document, DocumentChunk

from backend.app.services.document_processing import (
    DocumentProcessingError,
    ExtractedPage,
    normalize_text,
    process_document,
    split_pages_into_chunks,
)


@pytest.fixture
def db_session():
    """Create an isolated in-memory SQLite database."""

    engine = create_engine("sqlite:///:memory:")

    Base.metadata.create_all(engine)

    with Session(engine) as session:
        yield session

    engine.dispose()


def test_normalize_text() -> None:
    """Normalize whitespace while preserving paragraphs."""

    source = (
        "  First   sentence.  \r\n"
        "\r\n"
        "Second\u00a0sentence.\x00"
    )

    result = normalize_text(source)

    assert result == (
        "First sentence.\n\n"
        "Second sentence."
    )


def test_split_text_creates_overlapping_chunks() -> None:
    """Adjacent chunks should share the configured overlap."""

    pages = [
        ExtractedPage(
            page_number=None,
            text="ABCDEFGHIJKLMNOPQRSTUVWXYZ",
        )
    ]

    chunks = split_pages_into_chunks(
        pages,
        chunk_size=10,
        overlap=3,
    )

    assert len(chunks) > 1

    first = chunks[0].content
    second = chunks[1].content

    assert first[-3:] == second[:3]


def test_split_pages_preserves_page_numbers() -> None:
    """Chunks retain the source PDF page number."""

    pages = [
        ExtractedPage(
            page_number=2,
            text="Content from page two.",
        ),
        ExtractedPage(
            page_number=3,
            text="Content from page three.",
        ),
    ]

    chunks = split_pages_into_chunks(
        pages,
        chunk_size=100,
        overlap=10,
    )

    assert [chunk.page_number for chunk in chunks] == [
        2,
        3,
    ]

    assert [chunk.chunk_index for chunk in chunks] == [
        0,
        1,
    ]


def test_split_text_rejects_invalid_overlap() -> None:
    """Overlap must be smaller than chunk size."""

    with pytest.raises(ValueError):
        split_pages_into_chunks(
            [
                ExtractedPage(
                    page_number=None,
                    text="Some text.",
                )
            ],
            chunk_size=100,
            overlap=100,
        )


def test_process_document_saves_chunks(
    db_session: Session,
    tmp_path: Path,
) -> None:
    """A TXT document should be extracted and saved as chunks."""

    data_dir = tmp_path / "data"
    document_dir = data_dir / "raw" / "documents"
    document_dir.mkdir(parents=True)

    file_path = document_dir / "toeic-notes.txt"

    content = (
        "The present perfect describes an action "
        "that connects the past with the present.\n\n"
        "Since is used with a starting point in time."
    )

    file_path.write_text(
        content,
        encoding="utf-8",
    )

    file_hash = hashlib.sha256(
        file_path.read_bytes()
    ).hexdigest()

    document = Document(
        title="TOEIC Grammar Notes",
        original_filename="toeic-notes.txt",
        document_type="txt",
        storage_path="raw/documents/toeic-notes.txt",
        content_hash=file_hash,
    )

    db_session.add(document)
    db_session.commit()
    db_session.refresh(document)

    chunk_count = process_document(
        session=db_session,
        document_id=document.id,
        chunk_size=60,
        overlap=10,
        data_dir=data_dir,
    )

    saved_document = db_session.get(
        Document,
        document.id,
    )

    saved_chunks = db_session.scalars(
        select(DocumentChunk)
        .where(
            DocumentChunk.document_id == document.id
        )
        .order_by(DocumentChunk.chunk_index)
    ).all()

    assert saved_document is not None
    assert saved_document.processing_status == "pending"
    assert saved_document.processing_error is None

    assert chunk_count == len(saved_chunks)
    assert chunk_count >= 1

    assert saved_chunks[0].chunk_index == 0
    assert saved_chunks[0].page_number is None
    assert saved_chunks[0].content_hash
    assert saved_chunks[0].vector_id
    assert saved_chunks[0].token_count is None


def test_process_document_rejects_file_hash_mismatch(
    db_session: Session,
    tmp_path: Path,
) -> None:
    """A modified file must not be processed silently."""

    data_dir = tmp_path / "data"
    document_dir = data_dir / "raw" / "documents"
    document_dir.mkdir(parents=True)

    file_path = document_dir / "notes.txt"

    file_path.write_text(
        "Modified content.",
        encoding="utf-8",
    )

    expected_hash = hashlib.sha256(
        b"Original content."
    ).hexdigest()

    document = Document(
        title="Test document",
        original_filename="notes.txt",
        document_type="txt",
        storage_path="raw/documents/notes.txt",
        content_hash=expected_hash,
    )

    db_session.add(document)
    db_session.commit()
    db_session.refresh(document)

    with pytest.raises(DocumentProcessingError):
        process_document(
            session=db_session,
            document_id=document.id,
            data_dir=data_dir,
        )

    db_session.refresh(document)

    assert document.processing_status == "failed"
    assert "hash" in (document.processing_error or "").lower()


def test_process_document_rejects_path_traversal(
    db_session: Session,
    tmp_path: Path,
) -> None:
    """A document cannot be read outside the data directory."""

    outside_file = tmp_path / "outside.txt"

    outside_file.write_text(
        "This file must not be read.",
        encoding="utf-8",
    )

    file_hash = hashlib.sha256(
        outside_file.read_bytes()
    ).hexdigest()

    document = Document(
        title="Unsafe document",
        original_filename="outside.txt",
        document_type="txt",
        storage_path="../outside.txt",
        content_hash=file_hash,
    )

    db_session.add(document)
    db_session.commit()
    db_session.refresh(document)

    data_dir = tmp_path / "data"
    data_dir.mkdir()

    with pytest.raises(DocumentProcessingError):
        process_document(
            session=db_session,
            document_id=document.id,
            data_dir=data_dir,
        )

    db_session.refresh(document)

    assert document.processing_status == "failed"