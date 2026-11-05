
"""Unit tests for the document indexing service."""

from types import SimpleNamespace

import pytest

from backend.app.services.indexing_service import (
    DocumentIndexingError,
    DocumentIndexingPermissionError,
    DocumentIndexingService,
    DocumentNotFoundError,
)


MODEL_NAME = "intfloat/multilingual-e5-small"


def make_chunk(index: int):
    return SimpleNamespace(
        vector_id=f"document-1-chunk-{index}",
        document_id=1,
        chunk_index=index,
        content=f"TOEIC grammar content number {index}.",
        page_number=index + 1,
        content_hash=f"{index:064x}",
    )


def make_document(
    document_id=1,
    permission="granted",
    status="pending",
    chunk_count=3,
):
    return SimpleNamespace(
        id=document_id,
        title="TOEIC Grammar",
        original_filename="toeic-grammar.pdf",
        usage_permission_status=permission,
        processing_status=status,
        processing_error=None,
        embedding_model=None,
        chunks=[
            make_chunk(index)
            for index in range(chunk_count)
        ],
    )


class FakeDB:
    def __init__(self, documents=None):
        self.documents = documents or {}
        self.commit_count = 0
        self.rollback_count = 0

    def get(self, model, document_id):
        return self.documents.get(document_id)

    def commit(self):
        self.commit_count += 1

    def rollback(self):
        self.rollback_count += 1


class FakeEmbeddingService:
    def __init__(self, fail_on_call=None):
        self.model_name = MODEL_NAME
        self.fail_on_call = fail_on_call
        self.calls = []

    def embed_passages(self, texts):
        self.calls.append(list(texts))

        if self.fail_on_call == len(self.calls):
            raise RuntimeError("Simulated embedding failure")

        return [
            [0.1, 0.2, 0.3]
            for _ in texts
        ]


class FakeVectorStore:
    def __init__(
        self,
        fail_on_upsert_call=None,
        fail_on_delete=False,
    ):
        self.fail_on_upsert_call = fail_on_upsert_call
        self.fail_on_delete = fail_on_delete
        self.upsert_calls = []
        self.delete_calls = []
        self.records = {}

    def delete_document(self, document_id):
        self.delete_calls.append(document_id)

        if self.fail_on_delete:
            raise RuntimeError("Simulated deletion failure")

        ids = [
            vector_id
            for vector_id, record in self.records.items()
            if record.document_id == document_id
        ]

        for vector_id in ids:
            del self.records[vector_id]

        return len(ids)

    def upsert_chunks(self, chunks, embeddings):
        self.upsert_calls.append((chunks, embeddings))

        if self.fail_on_upsert_call == len(self.upsert_calls):
            raise RuntimeError("Simulated ChromaDB failure")

        if len(chunks) != len(embeddings):
            raise ValueError("Mismatched records and embeddings")

        for chunk in chunks:
            self.records[chunk.vector_id] = chunk

        return len(chunks)


def make_service(
    batch_size=2,
    fail_on_embedding_call=None,
    fail_on_upsert_call=None,
    fail_on_delete=False,
):
    embedding = FakeEmbeddingService(
        fail_on_call=fail_on_embedding_call,
    )

    vector_store = FakeVectorStore(
        fail_on_upsert_call=fail_on_upsert_call,
        fail_on_delete=fail_on_delete,
    )

    service = DocumentIndexingService(
        embedding_service=embedding,
        vector_store=vector_store,
        batch_size=batch_size,
    )

    return service, embedding, vector_store


def test_index_document_successfully_indexes_all_chunks():
    document = make_document(chunk_count=3)
    db = FakeDB({1: document})

    service, embedding, vector_store = make_service(
        batch_size=2,
    )

    result = service.index_document(db, 1)

    assert result.document_id == 1
    assert result.chunks_indexed == 3
    assert result.batches_processed == 2
    assert result.embedding_model == MODEL_NAME

    assert document.processing_status == "indexed"
    assert document.embedding_model == MODEL_NAME
    assert document.processing_error is None

    assert len(embedding.calls) == 2
    assert len(vector_store.upsert_calls) == 2
    assert len(vector_store.records) == 3


def test_index_document_uses_configured_batch_size():
    document = make_document(chunk_count=5)
    db = FakeDB({1: document})

    service, embedding, _ = make_service(
        batch_size=2,
    )

    result = service.index_document(db, 1)

    assert result.batches_processed == 3
    assert [len(batch) for batch in embedding.calls] == [
        2,
        2,
        1,
    ]


def test_index_document_rejects_missing_document():
    db = FakeDB({})

    service, _, _ = make_service()

    with pytest.raises(DocumentNotFoundError):
        service.index_document(db, 999)


def test_index_document_rejects_invalid_document_id():
    service, _, _ = make_service()

    for invalid_id in [0, -1, 1.5, True]:
        with pytest.raises(ValueError):
            service.index_document(FakeDB(), invalid_id)


def test_index_document_rejects_unapproved_permission():
    document = make_document(permission="unknown")
    db = FakeDB({1: document})

    service, embedding, vector_store = make_service()

    with pytest.raises(DocumentIndexingPermissionError):
        service.index_document(db, 1)

    assert document.processing_status == "pending"
    assert "permission" in document.processing_error.lower()
    assert embedding.calls == []
    assert vector_store.upsert_calls == []
    assert vector_store.delete_calls == ["1"]


def test_index_document_rejects_archived_document():
    document = make_document(status="archived")
    db = FakeDB({1: document})

    service, embedding, vector_store = make_service()

    with pytest.raises(DocumentIndexingError):
        service.index_document(db, 1)

    assert embedding.calls == []
    assert vector_store.upsert_calls == []


def test_index_document_rejects_document_already_processing():
    document = make_document(status="processing")
    db = FakeDB({1: document})

    service, embedding, vector_store = make_service()

    with pytest.raises(DocumentIndexingError):
        service.index_document(db, 1)

    assert embedding.calls == []
    assert vector_store.upsert_calls == []


def test_index_document_rejects_document_without_chunks():
    document = make_document(chunk_count=0)
    db = FakeDB({1: document})

    service, embedding, vector_store = make_service()

    with pytest.raises(DocumentIndexingError):
        service.index_document(db, 1)

    assert document.processing_status == "failed"
    assert document.processing_error is not None
    assert embedding.calls == []
    assert vector_store.upsert_calls == []
    assert vector_store.delete_calls == ["1"]


def test_index_document_deletes_old_vectors_before_reindexing():
    document = make_document(chunk_count=2)
    db = FakeDB({1: document})

    service, _, vector_store = make_service()

    vector_store.records["old-vector"] = SimpleNamespace(
        document_id="1",
    )

    service.index_document(db, 1)

    assert vector_store.delete_calls == ["1"]
    assert "old-vector" not in vector_store.records
    assert len(vector_store.records) == 2


def test_index_document_marks_failed_when_embedding_fails():
    document = make_document(chunk_count=3)
    db = FakeDB({1: document})

    service, embedding, vector_store = make_service(
        batch_size=2,
        fail_on_embedding_call=2,
    )

    with pytest.raises(DocumentIndexingError):
        service.index_document(db, 1)

    assert len(embedding.calls) == 2
    assert document.processing_status == "failed"
    assert document.processing_error is not None
    assert vector_store.delete_calls == ["1", "1"]
    assert vector_store.records == {}


def test_index_document_cleans_up_when_chroma_upsert_fails():
    document = make_document(chunk_count=3)
    db = FakeDB({1: document})

    service, _, vector_store = make_service(
        batch_size=2,
        fail_on_upsert_call=2,
    )

    with pytest.raises(DocumentIndexingError):
        service.index_document(db, 1)

    assert document.processing_status == "failed"
    assert document.processing_error is not None
    assert vector_store.delete_calls == ["1", "1"]
    assert vector_store.records == {}


def test_index_document_does_not_mark_indexed_after_failure():
    document = make_document(chunk_count=3)
    db = FakeDB({1: document})

    service, _, _ = make_service(
        batch_size=2,
        fail_on_embedding_call=2,
    )

    with pytest.raises(DocumentIndexingError):
        service.index_document(db, 1)

    assert document.processing_status == "failed"
    assert document.processing_status != "indexed"


def test_index_document_reports_cleanup_failure():
    document = make_document(chunk_count=2)
    db = FakeDB({1: document})

    service, _, vector_store = make_service(
        fail_on_upsert_call=1,
        fail_on_delete=True,
    )

    with pytest.raises(DocumentIndexingError):
        service.index_document(db, 1)

    assert document.processing_status == "failed"
    assert "cleanup failed" in document.processing_error.lower()


def test_index_document_rejects_invalid_batch_size():
    for invalid_size in [0, -1, 1.5, True]:
        with pytest.raises(ValueError):
            DocumentIndexingService(
                embedding_service=FakeEmbeddingService(),
                vector_store=FakeVectorStore(),
                batch_size=invalid_size,
            )


def test_index_document_stores_document_metadata_in_vector_records():
    document = make_document(chunk_count=1)
    db = FakeDB({1: document})

    service, _, vector_store = make_service()

    service.index_document(db, 1)

    record = vector_store.records["document-1-chunk-0"]

    assert record.document_id == "1"
    assert record.chunk_index == 0
    assert record.page_number == 1
    assert record.content_hash == f"{0:064x}"
