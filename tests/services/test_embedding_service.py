
"""Tests for the Sentence Transformers embedding service."""

import pytest

from backend.app.services.embedding_service import (
    DEFAULT_MODEL_NAME,
    EmbeddingConfigurationError,
    EmbeddingService,
    EmbeddingServiceError,
)


class FakeEmbeddingModel:
    """Fake model that does not download or load real weights."""

    def __init__(self) -> None:
        self.received_texts = None
        self.received_options = None

    def encode(
        self,
        sentences,
        **kwargs,
    ):
        self.received_texts = sentences
        self.received_options = kwargs

        return [
            [1.0, 0.0, 0.0]
            for _ in sentences
        ]


def test_default_model_configuration() -> None:
    """The service uses multilingual E5 by default."""

    service = EmbeddingService()

    assert service.model_name == DEFAULT_MODEL_NAME
    assert service.batch_size == 32
    assert service.device == "cpu"


def test_model_is_loaded_lazily_and_only_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The model is loaded only when the first embedding is requested."""

    fake_model = FakeEmbeddingModel()
    load_calls = []

    def fake_loader(
        model_name: str,
        device: str,
    ):
        load_calls.append((model_name, device))
        return fake_model

    monkeypatch.setattr(
        "backend.app.services.embedding_service."
        "_load_sentence_transformer",
        fake_loader,
    )

    service = EmbeddingService()

    assert load_calls == []

    service.embed_passages(["First document."])
    service.embed_passages(["Second document."])

    assert len(load_calls) == 1
    assert load_calls[0] == (
        DEFAULT_MODEL_NAME,
        "cpu",
    )


def test_embed_passages_uses_passage_prefix() -> None:
    """Document chunks must use the E5 passage prefix."""

    fake_model = FakeEmbeddingModel()

    service = EmbeddingService(
        model=fake_model,
        batch_size=16,
    )

    vectors = service.embed_passages([
        "Present perfect describes an action.",
        "Since indicates a starting point.",
    ])

    assert fake_model.received_texts == [
        "passage: Present perfect describes an action.",
        "passage: Since indicates a starting point.",
    ]

    assert len(vectors) == 2
    assert vectors[0] == [1.0, 0.0, 0.0]


def test_embed_queries_uses_query_prefix() -> None:
    """Search queries must use the E5 query prefix."""

    fake_model = FakeEmbeddingModel()

    service = EmbeddingService(model=fake_model)

    vectors = service.embed_queries([
        "Explain present perfect.",
    ])

    assert fake_model.received_texts == [
        "query: Explain present perfect.",
    ]

    assert len(vectors) == 1


def test_embedding_uses_normalized_batch_encoding() -> None:
    """Encoding must use normalized vectors and configured batch size."""

    fake_model = FakeEmbeddingModel()

    service = EmbeddingService(
        model=fake_model,
        batch_size=8,
    )

    service.embed_passages([
        "First chunk.",
        "Second chunk.",
    ])

    assert fake_model.received_options == {
        "batch_size": 8,
        "show_progress_bar": False,
        "convert_to_numpy": True,
        "normalize_embeddings": True,
    }


def test_empty_input_returns_empty_list() -> None:
    """An empty batch does not need model inference."""

    service = EmbeddingService()

    assert service.embed_passages([]) == []
    assert service.embed_queries([]) == []
    assert service._model is None


def test_single_string_input_is_rejected() -> None:
    """A single string must not be treated as an iterable of characters."""

    service = EmbeddingService(
        model=FakeEmbeddingModel(),
    )

    with pytest.raises(ValueError):
        service.embed_passages("This is not a list.")


@pytest.mark.parametrize(
    "texts",
    [
        ["   "],
        ["Valid text.", ""],
        ["Valid text.", "   "],
    ],
)
def test_empty_text_is_rejected(texts) -> None:
    """Blank text must not reach the embedding model."""

    service = EmbeddingService(
        model=FakeEmbeddingModel(),
    )

    with pytest.raises(ValueError):
        service.embed_passages(texts)


def test_non_string_input_is_rejected() -> None:
    """Every input item must be a string."""

    service = EmbeddingService(
        model=FakeEmbeddingModel(),
    )

    with pytest.raises(ValueError):
        service.embed_passages([
            "Valid text.",
            123,
        ])


@pytest.mark.parametrize(
    "batch_size",
    [
        0,
        -1,
        1.5,
        True,
    ],
)
def test_invalid_batch_size_is_rejected(batch_size) -> None:
    """Batch size must be a positive integer."""

    with pytest.raises(EmbeddingConfigurationError):
        EmbeddingService(batch_size=batch_size)


def test_empty_model_name_is_rejected() -> None:
    """The model name cannot be empty."""

    with pytest.raises(EmbeddingConfigurationError):
        EmbeddingService(model_name="   ")


def test_model_failure_is_wrapped() -> None:
    """Model errors should become EmbeddingServiceError."""

    class BrokenModel:
        def encode(self, sentences, **kwargs):
            raise RuntimeError("Simulated model failure")

    service = EmbeddingService(model=BrokenModel())

    with pytest.raises(EmbeddingServiceError):
        service.embed_passages(["A TOEIC document chunk."])


def test_model_output_count_must_match_input_count() -> None:
    """The model must return one vector for each input."""

    class InvalidModel:
        def encode(self, sentences, **kwargs):
            return [[1.0, 0.0]]

    service = EmbeddingService(model=InvalidModel())

    with pytest.raises(EmbeddingServiceError):
        service.embed_passages([
            "First chunk.",
            "Second chunk.",
        ])


def test_vector_dimensions_must_be_consistent() -> None:
    """Every vector in a batch must have the same dimension."""

    class InvalidModel:
        def encode(self, sentences, **kwargs):
            return [
                [1.0, 0.0],
                [1.0, 0.0, 0.0],
            ]

    service = EmbeddingService(model=InvalidModel())

    with pytest.raises(EmbeddingServiceError):
        service.embed_passages([
            "First chunk.",
            "Second chunk.",
        ])


def test_vector_rejects_non_finite_values() -> None:
    """NaN and infinite values are not valid embeddings."""

    class InvalidModel:
        def encode(self, sentences, **kwargs):
            return [[float("nan"), 0.0]]

    service = EmbeddingService(model=InvalidModel())

    with pytest.raises(EmbeddingServiceError):
        service.embed_passages(["A TOEIC document chunk."])


def test_vector_rejects_zero_magnitude() -> None:
    """An all-zero vector cannot be used for similarity search."""

    class InvalidModel:
        def encode(self, sentences, **kwargs):
            return [[0.0, 0.0, 0.0]]

    service = EmbeddingService(model=InvalidModel())

    with pytest.raises(EmbeddingServiceError):
        service.embed_passages(["A TOEIC document chunk."])
