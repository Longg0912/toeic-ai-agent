
"""Integration tests using a real persistent ChromaDB collection."""

from backend.app.services.vector_store import (
    ChromaVectorStore,
    ChunkVectorRecord,
)


def make_store(tmp_path):
    """Create an isolated real ChromaDB collection for one test."""

    return ChromaVectorStore(
        persist_directory=tmp_path / "chroma",
        collection_name="toeic_integration_test",
    )


def make_chunk(
    vector_id: str,
    document_id: str,
    chunk_index: int,
    content: str,
) -> ChunkVectorRecord:
    return ChunkVectorRecord(
        vector_id=vector_id,
        document_id=document_id,
        chunk_index=chunk_index,
        content=content,
        page_number=1,
    )


def test_real_chroma_can_insert_and_count_vectors(tmp_path):
    store = make_store(tmp_path)

    chunks = [
        make_chunk(
            "chunk-001",
            "document-001",
            0,
            "The present perfect describes an action connected to the present.",
        ),
        make_chunk(
            "chunk-002",
            "document-001",
            1,
            "Since indicates the starting point of an action.",
        ),
    ]

    embeddings = [
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
    ]

    inserted = store.upsert_chunks(chunks, embeddings)

    assert inserted == 2
    assert store.count() == 2


def test_real_chroma_can_search_by_query_embedding(tmp_path):
    store = make_store(tmp_path)

    store.upsert_chunks(
        chunks=[
            make_chunk(
                "chunk-001",
                "document-001",
                0,
                "Information about present perfect.",
            ),
            make_chunk(
                "chunk-002",
                "document-001",
                1,
                "Information about business meetings.",
            ),
        ],
        embeddings=[
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
        ],
    )

    results = store.search(
        query_embedding=[0.99, 0.01, 0.0],
        top_k=1,
    )

    assert len(results) == 1
    assert results[0].vector_id == "chunk-001"
    assert results[0].content == (
        "Information about present perfect."
    )


def test_real_chroma_can_filter_by_document_id(tmp_path):
    store = make_store(tmp_path)

    store.upsert_chunks(
        chunks=[
            make_chunk(
                "chunk-001",
                "document-001",
                0,
                "Content from document one.",
            ),
            make_chunk(
                "chunk-002",
                "document-002",
                0,
                "Content from document two.",
            ),
        ],
        embeddings=[
            [1.0, 0.0, 0.0],
            [0.99, 0.01, 0.0],
        ],
    )

    results = store.search(
        query_embedding=[1.0, 0.0, 0.0],
        top_k=5,
        document_id="document-002",
    )

    assert len(results) == 1
    assert results[0].vector_id == "chunk-002"
    assert results[0].metadata["document_id"] == "document-002"


def test_real_chroma_can_update_existing_vector(tmp_path):
    store = make_store(tmp_path)

    original_chunk = make_chunk(
        "chunk-001",
        "document-001",
        0,
        "Original TOEIC content.",
    )

    store.upsert_chunks(
        [original_chunk],
        [[1.0, 0.0, 0.0]],
    )

    updated_chunk = make_chunk(
        "chunk-001",
        "document-001",
        0,
        "Updated TOEIC content.",
    )

    store.upsert_chunks(
        [updated_chunk],
        [[0.0, 1.0, 0.0]],
    )

    assert store.count() == 1

    results = store.search(
        query_embedding=[0.0, 1.0, 0.0],
        top_k=1,
    )

    assert len(results) == 1
    assert results[0].content == "Updated TOEIC content."


def test_real_chroma_can_delete_vectors_by_document(tmp_path):
    store = make_store(tmp_path)

    store.upsert_chunks(
        chunks=[
            make_chunk(
                "chunk-001",
                "document-001",
                0,
                "First document content.",
            ),
            make_chunk(
                "chunk-002",
                "document-001",
                1,
                "Another chunk in first document.",
            ),
            make_chunk(
                "chunk-003",
                "document-002",
                0,
                "Second document content.",
            ),
        ],
        embeddings=[
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ],
    )

    deleted = store.delete_document("document-001")

    assert deleted == 2
    assert store.count() == 1

    remaining = store.search(
        query_embedding=[0.0, 0.0, 1.0],
        top_k=5,
    )

    assert len(remaining) == 1
    assert remaining[0].vector_id == "chunk-003"


def test_real_chroma_persists_vectors_after_reopening(tmp_path):
    first_store = make_store(tmp_path)

    first_store.upsert_chunks(
        chunks=[
            make_chunk(
                "chunk-001",
                "document-001",
                0,
                "Persistent TOEIC document content.",
            ),
        ],
        embeddings=[
            [1.0, 0.0, 0.0],
        ],
    )

    assert first_store.count() == 1

    # Create another client pointing to the same directory
    # and collection. It should see the previously stored vector.
    reopened_store = make_store(tmp_path)

    assert reopened_store.count() == 1

    results = reopened_store.search(
        query_embedding=[1.0, 0.0, 0.0],
        top_k=1,
    )

    assert len(results) == 1
    assert results[0].vector_id == "chunk-001"
    assert results[0].content == (
        "Persistent TOEIC document content."
    )
