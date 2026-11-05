
"""Tests for the global RAG retrieval service."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from backend.app.services.retrieval_service import (
    RetrievalService,
    RetrievalServiceError,
)
from backend.app.services.vector_store import VectorSearchResult


class FakeEmbeddingService:
    def __init__(self):
        self.received_queries = None

    def embed_queries(self, texts):
        self.received_queries = texts
        return [[0.1, 0.2, 0.3]]


class FakeVectorStore:
    def __init__(self, results=None):
        self.results = results or []
        self.received_arguments = None

    def search(self, **kwargs):
        self.received_arguments = kwargs
        return self.results


def make_vector_result(vector_id, distance):
    return VectorSearchResult(
        vector_id=vector_id,
        content="Content stored in ChromaDB.",
        metadata={"document_id": "1"},
        distance=distance,
    )


def make_database_row(
    vector_id="chunk-001",
    document_id=1,
    title="TOEIC Grammar",
    content="Since is used for a starting point.",
):
    chunk = SimpleNamespace(
        vector_id=vector_id,
        document_id=document_id,
        chunk_index=0,
        content=content,
        page_number=3,
    )

    document = SimpleNamespace(
        id=document_id,
        title=title,
        original_filename="toeic-grammar.pdf",
        source_name="ETS",
        source_reference="https://example.com/source",
        source_license="Authorized",
        processing_status="indexed",
        usage_permission_status="granted",
    )

    return chunk, document


def make_service(results=None):
    embedding_service = FakeEmbeddingService()
    vector_store = FakeVectorStore(results)

    service = RetrievalService(
        embedding_service=embedding_service,
        vector_store=vector_store,
    )

    return service, embedding_service, vector_store


def test_retrieve_returns_approved_chunks_in_vector_rank_order():
    service, embedding, vector_store = make_service(
        results=[
            make_vector_result("chunk-001", 0.05),
            make_vector_result("chunk-002", 0.10),
        ]
    )

    db = MagicMock()
    db.execute.return_value.all.return_value = [
        make_database_row(
            vector_id="chunk-001",
            content="Since indicates a starting point.",
        ),
        make_database_row(
            vector_id="chunk-002",
            content="For indicates a duration.",
        ),
    ]

    results = service.retrieve(
        db=db,
        query="Explain since and for.",
        top_k=2,
    )

    assert len(results) == 2
    assert results[0].content == (
        "Since indicates a starting point."
    )
    assert results[1].content == (
        "For indicates a duration."
    )
    assert results[0].distance == 0.05
    assert results[0].document_title == "TOEIC Grammar"

    assert embedding.received_queries == [
        "Explain since and for."
    ]

    assert vector_store.received_arguments == {
        "query_embedding": [0.1, 0.2, 0.3],
        "top_k": 10,
        "document_id": None,
    }


def test_retrieve_skips_chunks_without_approved_database_metadata():
    service, _, _ = make_service(
        results=[
            make_vector_result("unapproved-chunk", 0.01),
            make_vector_result("approved-chunk", 0.05),
        ]
    )

    db = MagicMock()
    db.execute.return_value.all.return_value = [
        make_database_row(
            vector_id="approved-chunk",
        )
    ]

    results = service.retrieve(
        db=db,
        query="TOEIC grammar",
        top_k=5,
    )

    assert len(results) == 1
    assert results[0].content == (
        "Since is used for a starting point."
    )


def test_retrieve_returns_empty_when_vector_search_has_no_results():
    service, _, _ = make_service(results=[])

    db = MagicMock()

    results = service.retrieve(
        db=db,
        query="TOEIC grammar",
    )

    assert results == []
    db.execute.assert_not_called()


def test_retrieve_respects_top_k_after_metadata_filtering():
    service, _, _ = make_service(
        results=[
            make_vector_result("chunk-001", 0.01),
            make_vector_result("chunk-002", 0.02),
            make_vector_result("chunk-003", 0.03),
        ]
    )

    db = MagicMock()
    db.execute.return_value.all.return_value = [
        make_database_row(vector_id="chunk-001"),
        make_database_row(vector_id="chunk-002"),
        make_database_row(vector_id="chunk-003"),
    ]

    results = service.retrieve(
        db=db,
        query="TOEIC grammar",
        top_k=2,
    )

    assert len(results) == 2


def test_retrieve_can_restrict_search_to_one_document():
    service, _, vector_store = make_service(
        results=[
            make_vector_result("chunk-001", 0.05),
        ]
    )

    db = MagicMock()
    db.execute.return_value.all.return_value = [
        make_database_row(),
    ]

    service.retrieve(
        db=db,
        query="TOEIC grammar",
        document_id=1,
    )

    assert vector_store.received_arguments["document_id"] == "1"


@pytest.mark.parametrize(
    "query",
    [
        "",
        "   ",
        None,
        123,
    ],
)
def test_retrieve_rejects_invalid_query(query):
    service, _, _ = make_service()

    with pytest.raises(ValueError):
        service.retrieve(
            db=MagicMock(),
            query=query,
        )


@pytest.mark.parametrize(
    "top_k",
    [
        0,
        -1,
        1.5,
        True,
    ],
)
def test_retrieve_rejects_invalid_top_k(top_k):
    service, _, _ = make_service()

    with pytest.raises(ValueError):
        service.retrieve(
            db=MagicMock(),
            query="TOEIC grammar",
            top_k=top_k,
        )


@pytest.mark.parametrize(
    "document_id",
    [
        0,
        -1,
        1.5,
        True,
        "1",
    ],
)
def test_retrieve_rejects_invalid_document_id(document_id):
    service, _, _ = make_service()

    with pytest.raises(ValueError):
        service.retrieve(
            db=MagicMock(),
            query="TOEIC grammar",
            document_id=document_id,
        )


def test_retrieve_wraps_embedding_or_vector_store_failure():
    class BrokenEmbeddingService:
        def embed_queries(self, texts):
            raise RuntimeError("Simulated embedding failure")

    service = RetrievalService(
        embedding_service=BrokenEmbeddingService(),
        vector_store=FakeVectorStore(),
    )

    with pytest.raises(RetrievalServiceError):
        service.retrieve(
            db=MagicMock(),
            query="TOEIC grammar",
        )


def test_candidate_multiplier_must_be_positive():
    with pytest.raises(ValueError):
        RetrievalService(
            embedding_service=FakeEmbeddingService(),
            vector_store=FakeVectorStore(),
            candidate_multiplier=0,
        )
