
"""Tests for the ChromaDB vector store."""

import pytest

from backend.app.services.vector_store import (
    ChromaVectorStore,
    ChunkVectorRecord,
    VectorStoreError,
)


class FakeCollection:
    """Fake ChromaDB collection for unit tests."""

    def __init__(self) -> None:
        self.records = {}
        self.last_query = None

    def upsert(
        self,
        ids,
        embeddings,
        documents,
        metadatas,
    ):
        for index, vector_id in enumerate(ids):
            self.records[vector_id] = {
                "embedding": embeddings[index],
                "document": documents[index],
                "metadata": metadatas[index],
            }

    def count(self):
        return len(self.records)

    def query(
        self,
        query_embeddings,
        n_results,
        where,
        include,
    ):
        self.last_query = {
            "query_embeddings": query_embeddings,
            "n_results": n_results,
            "where": where,
            "include": include,
        }

        matching = list(self.records.items())

        if where is not None:
            matching = [
                item
                for item in matching
                if item[1]["metadata"].get("document_id")
                == where["document_id"]
            ]

        matching = matching[:n_results]

        return {
            "ids": [
                [item[0] for item in matching]
            ],
            "documents": [
                [item[1]["document"] for item in matching]
            ],
            "metadatas": [
                [item[1]["metadata"] for item in matching]
            ],
            "distances": [
                [0.1 for _ in matching]
            ],
        }

    def get(
        self,
        where=None,
        include=None,
    ):
        matching_ids = [
            vector_id
            for vector_id, record in self.records.items()
            if (
                where is None
                or record["metadata"].get("document_id")
                == where["document_id"]
            )
        ]

        return {"ids": matching_ids}

    def delete(self, where=None):
        ids_to_delete = [
            vector_id
            for vector_id, record in self.records.items()
            if (
                where is None
                or record["metadata"].get("document_id")
                == where["document_id"]
            )
        ]

        for vector_id in ids_to_delete:
            del self.records[vector_id]


def make_chunk(
    vector_id="chunk-001",
    document_id="document-001",
    chunk_index=0,
    page_number=1,
):
    return ChunkVectorRecord(
        vector_id=vector_id,
        document_id=document_id,
        chunk_index=chunk_index,
        content="Since indicates a starting point in time.",
        page_number=page_number,
        content_hash="abc123",
    )


def make_store():
    collection = FakeCollection()

    store = ChromaVectorStore(
        collection=collection,
    )

    return store, collection


def test_default_collection_name() -> None:
    store = ChromaVectorStore()

    assert store.collection_name == "toeic_chunks"


def test_collection_is_loaded_lazily() -> None:
    store = ChromaVectorStore()

    assert store._collection is None


def test_empty_upsert_returns_zero() -> None:
    store, _ = make_store()

    assert store.upsert_chunks([], []) == 0


def test_upsert_stores_chunk_and_embedding() -> None:
    store, collection = make_store()

    chunks = [
        make_chunk(),
    ]

    embeddings = [
        [0.1, 0.2, 0.3],
    ]

    inserted = store.upsert_chunks(
        chunks=chunks,
        embeddings=embeddings,
    )

    assert inserted == 1
    assert collection.records["chunk-001"]["document"] == (
        "Since indicates a starting point in time."
    )
    assert collection.records["chunk-001"]["embedding"] == (
        [0.1, 0.2, 0.3]
    )


def test_upsert_stores_chunk_metadata() -> None:
    store, collection = make_store()

    store.upsert_chunks(
        chunks=[make_chunk()],
        embeddings=[[0.1, 0.2, 0.3]],
    )

    metadata = collection.records["chunk-001"]["metadata"]

    assert metadata == {
        "document_id": "document-001",
        "chunk_index": 0,
        "page_number": 1,
        "content_hash": "abc123",
    }


def test_upsert_omits_missing_optional_metadata() -> None:
    store, collection = make_store()

    chunk = ChunkVectorRecord(
        vector_id="chunk-002",
        document_id="document-001",
        chunk_index=1,
        content="A TOEIC grammar passage.",
    )

    store.upsert_chunks(
        chunks=[chunk],
        embeddings=[[0.1, 0.2, 0.3]],
    )

    metadata = collection.records["chunk-002"]["metadata"]

    assert metadata == {
        "document_id": "document-001",
        "chunk_index": 1,
    }


def test_upsert_updates_existing_vector_id() -> None:
    store, collection = make_store()

    chunk = make_chunk()

    store.upsert_chunks(
        chunks=[chunk],
        embeddings=[[0.1, 0.2, 0.3]],
    )

    updated_chunk = ChunkVectorRecord(
        vector_id="chunk-001",
        document_id="document-001",
        chunk_index=0,
        content="Updated TOEIC passage.",
    )

    store.upsert_chunks(
        chunks=[updated_chunk],
        embeddings=[[0.3, 0.2, 0.1]],
    )

    assert collection.count() == 1
    assert collection.records["chunk-001"]["document"] == (
        "Updated TOEIC passage."
    )


def test_upsert_rejects_mismatched_embedding_count() -> None:
    store, _ = make_store()

    with pytest.raises(ValueError):
        store.upsert_chunks(
            chunks=[
                make_chunk(),
                make_chunk(
                    vector_id="chunk-002",
                    chunk_index=1,
                ),
            ],
            embeddings=[
                [0.1, 0.2, 0.3],
            ],
        )


def test_upsert_rejects_duplicate_vector_ids() -> None:
    store, _ = make_store()

    with pytest.raises(ValueError):
        store.upsert_chunks(
            chunks=[
                make_chunk(),
                make_chunk(),
            ],
            embeddings=[
                [0.1, 0.2, 0.3],
                [0.2, 0.3, 0.4],
            ],
        )


def test_upsert_rejects_empty_chunk_content() -> None:
    store, _ = make_store()

    chunk = ChunkVectorRecord(
        vector_id="chunk-001",
        document_id="document-001",
        chunk_index=0,
        content="   ",
    )

    with pytest.raises(ValueError):
        store.upsert_chunks(
            chunks=[chunk],
            embeddings=[[0.1, 0.2, 0.3]],
        )


def test_upsert_rejects_invalid_page_number() -> None:
    store, _ = make_store()

    chunk = make_chunk(page_number=0)

    with pytest.raises(ValueError):
        store.upsert_chunks(
            chunks=[chunk],
            embeddings=[[0.1, 0.2, 0.3]],
        )


def test_upsert_rejects_inconsistent_dimensions() -> None:
    store, _ = make_store()

    chunks = [
        make_chunk(),
        make_chunk(
            vector_id="chunk-002",
            chunk_index=1,
        ),
    ]

    with pytest.raises(ValueError):
        store.upsert_chunks(
            chunks=chunks,
            embeddings=[
                [0.1, 0.2, 0.3],
                [0.1, 0.2],
            ],
        )


def test_upsert_rejects_non_finite_embedding() -> None:
    store, _ = make_store()

    with pytest.raises(ValueError):
        store.upsert_chunks(
            chunks=[make_chunk()],
            embeddings=[
                [float("nan"), 0.2, 0.3],
            ],
        )


def test_upsert_rejects_zero_embedding() -> None:
    store, _ = make_store()

    with pytest.raises(ValueError):
        store.upsert_chunks(
            chunks=[make_chunk()],
            embeddings=[
                [0.0, 0.0, 0.0],
            ],
        )


def test_search_returns_vector_search_results() -> None:
    store, _ = make_store()

    store.upsert_chunks(
        chunks=[make_chunk()],
        embeddings=[[0.1, 0.2, 0.3]],
    )

    results = store.search(
        query_embedding=[0.1, 0.2, 0.3],
        top_k=3,
    )

    assert len(results) == 1
    assert results[0].vector_id == "chunk-001"
    assert results[0].content == (
        "Since indicates a starting point in time."
    )
    assert results[0].distance == 0.1


def test_search_can_filter_by_document_id() -> None:
    store, collection = make_store()

    store.upsert_chunks(
        chunks=[
            make_chunk(
                vector_id="chunk-001",
                document_id="document-001",
            ),
            make_chunk(
                vector_id="chunk-002",
                document_id="document-002",
                chunk_index=1,
            ),
        ],
        embeddings=[
            [0.1, 0.2, 0.3],
            [0.2, 0.3, 0.4],
        ],
    )

    results = store.search(
        query_embedding=[0.1, 0.2, 0.3],
        document_id="document-002",
    )

    assert len(results) == 1
    assert results[0].vector_id == "chunk-002"
    assert collection.last_query["where"] == {
        "document_id": "document-002",
    }


def test_search_empty_collection_returns_empty_list() -> None:
    store, _ = make_store()

    results = store.search(
        query_embedding=[0.1, 0.2, 0.3],
    )

    assert results == []


@pytest.mark.parametrize(
    "top_k",
    [
        0,
        -1,
        1.5,
        True,
    ],
)
def test_search_rejects_invalid_top_k(top_k) -> None:
    store, _ = make_store()

    with pytest.raises(ValueError):
        store.search(
            query_embedding=[0.1, 0.2, 0.3],
            top_k=top_k,
        )


def test_delete_document_removes_its_vectors() -> None:
    store, collection = make_store()

    store.upsert_chunks(
        chunks=[
            make_chunk(
                vector_id="chunk-001",
                document_id="document-001",
            ),
            make_chunk(
                vector_id="chunk-002",
                document_id="document-001",
                chunk_index=1,
            ),
            make_chunk(
                vector_id="chunk-003",
                document_id="document-002",
                chunk_index=0,
            ),
        ],
        embeddings=[
            [0.1, 0.2, 0.3],
            [0.2, 0.3, 0.4],
            [0.3, 0.4, 0.5],
        ],
    )

    deleted = store.delete_document("document-001")

    assert deleted == 2
    assert collection.count() == 1
    assert "chunk-003" in collection.records


def test_delete_missing_document_returns_zero() -> None:
    store, _ = make_store()

    assert store.delete_document("missing-document") == 0


def test_count_returns_number_of_vectors() -> None:
    store, _ = make_store()

    store.upsert_chunks(
        chunks=[
            make_chunk(),
            make_chunk(
                vector_id="chunk-002",
                chunk_index=1,
            ),
        ],
        embeddings=[
            [0.1, 0.2, 0.3],
            [0.2, 0.3, 0.4],
        ],
    )

    assert store.count() == 2


def test_chroma_failure_is_wrapped() -> None:
    class BrokenCollection:
        def upsert(self, **kwargs):
            raise RuntimeError("Simulated ChromaDB failure")

    store = ChromaVectorStore(
        collection=BrokenCollection(),
    )

    with pytest.raises(VectorStoreError):
        store.upsert_chunks(
            chunks=[make_chunk()],
            embeddings=[[0.1, 0.2, 0.3]],
        )
