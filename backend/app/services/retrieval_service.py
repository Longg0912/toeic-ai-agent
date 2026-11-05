
"""Global RAG retrieval service for TOEIC documents."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models import Document, DocumentChunk
from backend.app.services.embedding_service import EmbeddingService
from backend.app.services.vector_store import (
    ChromaVectorStore,
    VectorSearchResult,
)


class RetrievalServiceError(RuntimeError):
    """Raised when global RAG retrieval cannot be completed."""


@dataclass(frozen=True)
class RetrievedChunk:
    """A relevant document chunk with its source information."""

    document_id: int
    document_title: str
    original_filename: str
    chunk_index: int
    content: str
    page_number: int | None
    source_name: str | None
    source_reference: str | None
    source_license: str | None
    distance: float | None


class RetrievalService:
    """Retrieve relevant, approved TOEIC document chunks.

    The service combines:
    - EmbeddingService for query embeddings.
    - ChromaVectorStore for semantic vector search.
    - SQLAlchemy for authoritative document metadata.

    A result is returned only when its document is indexed
    and its usage permission has been granted.
    """

    def __init__(
        self,
        embedding_service: EmbeddingService | None = None,
        vector_store: ChromaVectorStore | None = None,
        candidate_multiplier: int = 5,
    ) -> None:
        if (
            not isinstance(candidate_multiplier, int)
            or isinstance(candidate_multiplier, bool)
            or candidate_multiplier < 1
        ):
            raise ValueError(
                "candidate_multiplier must be a positive integer."
            )

        self.embedding_service = (
            embedding_service or EmbeddingService()
        )
        self.vector_store = (
            vector_store or ChromaVectorStore()
        )
        self.candidate_multiplier = candidate_multiplier

    @staticmethod
    def _validate_query(query: str) -> str:
        """Validate and normalize the search query."""

        if not isinstance(query, str):
            raise ValueError("query must be a string.")

        normalized_query = query.strip()

        if not normalized_query:
            raise ValueError("query must not be empty.")

        return normalized_query

    @staticmethod
    def _validate_top_k(top_k: int) -> None:
        """Validate the requested number of results."""

        if (
            not isinstance(top_k, int)
            or isinstance(top_k, bool)
            or top_k <= 0
        ):
            raise ValueError(
                "top_k must be a positive integer."
            )

    @staticmethod
    def _load_approved_chunks(
        db: Session,
        vector_results: list[VectorSearchResult],
    ) -> dict[str, tuple[DocumentChunk, Document]]:
        """Load matching chunks and approved document metadata."""

        vector_ids = [
            result.vector_id
            for result in vector_results
        ]

        if not vector_ids:
            return {}

        statement = (
            select(DocumentChunk, Document)
            .join(
                Document,
                Document.id == DocumentChunk.document_id,
            )
            .where(
                DocumentChunk.vector_id.in_(vector_ids),
                Document.processing_status == "indexed",
                Document.usage_permission_status == "granted",
            )
        )

        rows = db.execute(statement).all()

        return {
            chunk.vector_id: (chunk, document)
            for chunk, document in rows
        }

    def retrieve(
        self,
        db: Session,
        query: str,
        top_k: int = 5,
        document_id: int | None = None,
    ) -> list[RetrievedChunk]:
        """Retrieve the most relevant approved document chunks.

        Args:
            db: An active SQLAlchemy database session.
            query: The learner's question or search query.
            top_k: Maximum number of chunks to return.
            document_id: Optional document ID restriction.

        Returns:
            Relevant chunks ordered by ChromaDB distance.
            An empty list is returned when no approved chunks match.

        Raises:
            ValueError: If the input arguments are invalid.
            RetrievalServiceError: If embedding, vector search,
                or database retrieval fails.
        """

        normalized_query = self._validate_query(query)
        self._validate_top_k(top_k)

        if document_id is not None:
            if (
                not isinstance(document_id, int)
                or isinstance(document_id, bool)
                or document_id <= 0
            ):
                raise ValueError(
                    "document_id must be a positive integer."
                )

        try:
            query_embeddings = (
                self.embedding_service.embed_queries(
                    [normalized_query]
                )
            )

            if len(query_embeddings) != 1:
                raise RetrievalServiceError(
                    "Embedding service returned an invalid result count."
                )

            query_embedding = query_embeddings[0]

            candidate_k = (
                top_k * self.candidate_multiplier
            )

            vector_results = self.vector_store.search(
                query_embedding=query_embedding,
                top_k=candidate_k,
                document_id=(
                    str(document_id)
                    if document_id is not None
                    else None
                ),
            )

            if not vector_results:
                return []

            approved_chunks = self._load_approved_chunks(
                db=db,
                vector_results=vector_results,
            )

            retrieved: list[RetrievedChunk] = []

            # Preserve ChromaDB's semantic ranking.
            for vector_result in vector_results:
                matched = approved_chunks.get(
                    vector_result.vector_id
                )

                if matched is None:
                    continue

                chunk, document = matched

                retrieved.append(
                    RetrievedChunk(
                        document_id=document.id,
                        document_title=document.title,
                        original_filename=document.original_filename,
                        chunk_index=chunk.chunk_index,
                        content=chunk.content,
                        page_number=chunk.page_number,
                        source_name=document.source_name,
                        source_reference=document.source_reference,
                        source_license=document.source_license,
                        distance=vector_result.distance,
                    )
                )

                if len(retrieved) >= top_k:
                    break

            return retrieved

        except ValueError:
            raise

        except RetrievalServiceError:
            raise

        except Exception as exc:
            raise RetrievalServiceError(
                "Could not retrieve relevant TOEIC document chunks."
            ) from exc
