
"""Document indexing service for the global TOEIC RAG pipeline."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from backend.app.db.models import Document
from backend.app.services.embedding_service import EmbeddingService
from backend.app.services.vector_store import (
    ChromaVectorStore,
    ChunkVectorRecord,
)


class DocumentIndexingError(RuntimeError):
    """Raised when document indexing fails."""


class DocumentIndexingPermissionError(DocumentIndexingError):
    """Raised when a document is not authorized for indexing."""


class DocumentNotFoundError(DocumentIndexingError):
    """Raised when the requested document does not exist."""


@dataclass(frozen=True)
class IndexingResult:
    """Summary of a successfully indexed document."""

    document_id: int
    chunks_indexed: int
    batches_processed: int
    embedding_model: str


class DocumentIndexingService:
    """Generate embeddings and index document chunks in ChromaDB."""

    def __init__(
        self,
        embedding_service: EmbeddingService | None = None,
        vector_store: ChromaVectorStore | None = None,
        batch_size: int = 32,
    ) -> None:
        if (
            not isinstance(batch_size, int)
            or isinstance(batch_size, bool)
            or batch_size <= 0
        ):
            raise ValueError(
                "batch_size must be a positive integer."
            )

        self.embedding_service = (
            embedding_service or EmbeddingService()
        )
        self.vector_store = (
            vector_store or ChromaVectorStore()
        )
        self.batch_size = batch_size

    @staticmethod
    def _validate_document_id(document_id: int) -> None:
        if (
            not isinstance(document_id, int)
            or isinstance(document_id, bool)
            or document_id <= 0
        ):
            raise ValueError(
                "document_id must be a positive integer."
            )

    def _build_records(
        self,
        document: Document,
    ) -> list[ChunkVectorRecord]:
        """Convert database chunks into vector records."""

        return [
            ChunkVectorRecord(
                vector_id=chunk.vector_id,
                document_id=str(document.id),
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                page_number=chunk.page_number,
                content_hash=chunk.content_hash,
            )
            for chunk in document.chunks
        ]

    def _mark_failed(
        self,
        db: Session,
        document_id: int,
        error_message: str,
    ) -> None:
        """Mark a document as failed after rolling back pending changes."""

        db.rollback()

        document = db.get(Document, document_id)

        if document is None:
            return

        document.processing_status = "failed"
        document.processing_error = error_message[:2000]

        db.commit()

    def index_document(
        self,
        db: Session,
        document_id: int,
    ) -> IndexingResult:
        """Index all chunks belonging to one authorized document.

        The method owns its database commits. Use a dedicated
        SQLAlchemy session for this operation.

        Re-indexing is supported. Existing vectors belonging
        to this document are removed before new vectors are written.

        Args:
            db: Active SQLAlchemy session.
            document_id: ID of the document to index.

        Returns:
            IndexingResult containing indexing statistics.

        Raises:
            ValueError: Invalid document ID.
            DocumentNotFoundError: Document does not exist.
            DocumentIndexingPermissionError: Permission is not granted.
            DocumentIndexingError: Indexing or cleanup fails.
        """

        self._validate_document_id(document_id)

        document = db.get(Document, document_id)

        if document is None:
            raise DocumentNotFoundError(
                f"Document {document_id} was not found."
            )

        if document.processing_status == "archived":
            raise DocumentIndexingError(
                "Archived documents cannot be indexed."
            )

        if document.processing_status == "processing":
            raise DocumentIndexingError(
                "Document is currently being processed."
            )

        if document.usage_permission_status != "granted":
            # Remove any previously indexed vectors.
            # Retrieval also checks permission in SQLite.
            try:
                self.vector_store.delete_document(
                    str(document_id)
                )
            except Exception as exc:
                raise DocumentIndexingError(
                    "Could not remove vectors from a document "
                    "without indexing permission."
                ) from exc

            document.processing_status = "pending"
            document.embedding_model = None
            document.processing_error = (
                "Indexing skipped: usage permission is not granted."
            )
            db.commit()

            raise DocumentIndexingPermissionError(
                "Document usage permission must be granted before indexing."
            )

        # Snapshot chunk information before committing the status.
        records = self._build_records(document)

        if not records:
            try:
                self.vector_store.delete_document(
                    str(document_id)
                )
            except Exception as exc:
                raise DocumentIndexingError(
                    "Could not clean up vectors for an empty document."
                ) from exc

            document.processing_status = "failed"
            document.processing_error = (
                "Document has no chunks available for indexing."
            )
            db.commit()

            raise DocumentIndexingError(
                "Document has no chunks available for indexing."
            )

        # Mark as processing first. RetrievalService only returns
        # documents whose status is indexed.
        document.processing_status = "processing"
        document.processing_error = None
        db.commit()

        try:
            # Remove stale vectors from previous indexing runs.
            self.vector_store.delete_document(
                str(document_id)
            )

            batches_processed = 0
            chunks_indexed = 0

            for start in range(
                0,
                len(records),
                self.batch_size,
            ):
                batch_records = records[
                    start : start + self.batch_size
                ]

                batch_texts = [
                    record.content
                    for record in batch_records
                ]

                embeddings = (
                    self.embedding_service.embed_passages(
                        batch_texts
                    )
                )

                if len(embeddings) != len(batch_records):
                    raise DocumentIndexingError(
                        "Embedding count does not match chunk count."
                    )

                saved_count = self.vector_store.upsert_chunks(
                    chunks=batch_records,
                    embeddings=embeddings,
                )

                if saved_count != len(batch_records):
                    raise DocumentIndexingError(
                        "ChromaDB did not save the expected number of chunks."
                    )

                chunks_indexed += saved_count
                batches_processed += 1

            # Only mark indexed after every batch has been saved.
            document = db.get(Document, document_id)

            if document is None:
                raise DocumentIndexingError(
                    "Document disappeared during indexing."
                )

            document.embedding_model = (
                self.embedding_service.model_name
            )
            document.processing_status = "indexed"
            document.processing_error = None

            db.commit()

            return IndexingResult(
                document_id=document_id,
                chunks_indexed=chunks_indexed,
                batches_processed=batches_processed,
                embedding_model=self.embedding_service.model_name,
            )

        except Exception as exc:
            cleanup_error = None

            # Remove partial vectors so a retry starts cleanly.
            try:
                self.vector_store.delete_document(
                    str(document_id)
                )
            except Exception as cleanup_exc:
                cleanup_error = cleanup_exc

            error_message = str(exc)

            if cleanup_error is not None:
                error_message += (
                    f" | Vector cleanup failed: {cleanup_error}"
                )

            try:
                self._mark_failed(
                    db=db,
                    document_id=document_id,
                    error_message=error_message,
                )
            except Exception as status_exc:
                db.rollback()
                raise DocumentIndexingError(
                    "Indexing failed and the document status "
                    "could not be updated."
                ) from status_exc

            raise DocumentIndexingError(
                "Could not index document "
                f"{document_id}: {exc}"
            ) from exc
