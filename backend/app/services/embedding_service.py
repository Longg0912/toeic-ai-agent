
"""Embedding service using Sentence Transformers."""

from __future__ import annotations

import math
import os

from collections.abc import Iterable
from typing import Any


DEFAULT_MODEL_NAME = "intfloat/multilingual-e5-small"
DEFAULT_BATCH_SIZE = 32
DEFAULT_DEVICE = "cpu"


class EmbeddingConfigurationError(RuntimeError):
    """Raised when embedding configuration is invalid."""


class EmbeddingServiceError(RuntimeError):
    """Raised when the embedding model cannot process text."""


def _load_sentence_transformer(
    model_name: str,
    device: str,
) -> Any:
    """Load a Sentence Transformer model."""

    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise EmbeddingConfigurationError(
            "Sentence Transformers is not installed. "
            "Install dependencies from requirements.txt."
        ) from exc

    try:
        return SentenceTransformer(
            model_name,
            device=device,
        )
    except Exception as exc:
        raise EmbeddingServiceError(
            "Could not load the embedding model. "
            "Check the model name, internet connection "
            "and available memory."
        ) from exc


class EmbeddingService:
    """Create normalized embeddings for TOEIC RAG text."""

    def __init__(
        self,
        model_name: str | None = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
        device: str | None = None,
        model: Any | None = None,
    ) -> None:
        configured_model = (
            model_name
            or os.getenv("EMBEDDING_MODEL_NAME")
            or DEFAULT_MODEL_NAME
        )

        configured_device = (
            device
            or os.getenv("EMBEDDING_DEVICE")
            or DEFAULT_DEVICE
        )

        if not isinstance(configured_model, str):
            raise EmbeddingConfigurationError(
                "model_name must be a string."
            )

        if not configured_model.strip():
            raise EmbeddingConfigurationError(
                "model_name must not be empty."
            )

        if (
            not isinstance(batch_size, int)
            or isinstance(batch_size, bool)
            or batch_size <= 0
        ):
            raise EmbeddingConfigurationError(
                "batch_size must be a positive integer."
            )

        if not isinstance(configured_device, str):
            raise EmbeddingConfigurationError(
                "device must be a string."
            )

        if not configured_device.strip():
            raise EmbeddingConfigurationError(
                "device must not be empty."
            )

        self.model_name = configured_model.strip()
        self.batch_size = batch_size
        self.device = configured_device.strip()

        # Model loading is lazy:
        # the model is loaded only when the first embedding is requested.
        self._model = model

    def _get_model(self) -> Any:
        """Load the model once per service instance."""

        if self._model is None:
            self._model = _load_sentence_transformer(
                model_name=self.model_name,
                device=self.device,
            )

        return self._model

    @staticmethod
    def _validate_texts(
        texts: Iterable[str],
    ) -> list[str]:
        """Validate and normalize the input collection."""

        if isinstance(texts, (str, bytes)):
            raise ValueError(
                "texts must be an iterable of strings, "
                "not a single string."
            )

        try:
            text_list = list(texts)
        except TypeError as exc:
            raise ValueError(
                "texts must be an iterable of strings."
            ) from exc

        validated: list[str] = []

        for index, text in enumerate(text_list):
            if not isinstance(text, str):
                raise ValueError(
                    f"Text at index {index} must be a string."
                )

            text = text.strip()

            if not text:
                raise ValueError(
                    f"Text at index {index} must not be empty."
                )

            validated.append(text)

        return validated

    @staticmethod
    def _validate_vectors(
        raw_vectors: Any,
        expected_count: int,
    ) -> list[list[float]]:
        """Validate the model output and convert it to Python lists."""

        if hasattr(raw_vectors, "tolist"):
            raw_vectors = raw_vectors.tolist()

        if not isinstance(raw_vectors, (list, tuple)):
            raise EmbeddingServiceError(
                "The embedding model returned an invalid result."
            )

        if len(raw_vectors) != expected_count:
            raise EmbeddingServiceError(
                "The number of returned vectors does not "
                "match the number of input texts."
            )

        vectors: list[list[float]] = []
        expected_dimension: int | None = None

        for index, raw_vector in enumerate(raw_vectors):
            if hasattr(raw_vector, "tolist"):
                raw_vector = raw_vector.tolist()

            if not isinstance(raw_vector, (list, tuple)):
                raise EmbeddingServiceError(
                    f"Vector at index {index} has an invalid format."
                )

            if not raw_vector:
                raise EmbeddingServiceError(
                    f"Vector at index {index} is empty."
                )

            try:
                vector = [
                    float(value)
                    for value in raw_vector
                ]
            except (TypeError, ValueError) as exc:
                raise EmbeddingServiceError(
                    f"Vector at index {index} contains invalid values."
                ) from exc

            if not all(math.isfinite(value) for value in vector):
                raise EmbeddingServiceError(
                    f"Vector at index {index} contains "
                    "NaN or infinite values."
                )

            if expected_dimension is None:
                expected_dimension = len(vector)

            elif len(vector) != expected_dimension:
                raise EmbeddingServiceError(
                    "Embedding vectors have inconsistent dimensions."
                )

            norm = math.sqrt(
                sum(value * value for value in vector)
            )

            if norm == 0:
                raise EmbeddingServiceError(
                    f"Vector at index {index} has zero magnitude."
                )

            vectors.append(vector)

        return vectors

    def _encode(
        self,
        texts: Iterable[str],
        prefix: str,
    ) -> list[list[float]]:
        """Encode text with the task prefix required by E5."""

        validated_texts = self._validate_texts(texts)

        # Avoid loading the model for an empty batch.
        if not validated_texts:
            return []

        prepared_texts = [
            f"{prefix}{text}"
            for text in validated_texts
        ]

        model = self._get_model()

        try:
            raw_vectors = model.encode(
                prepared_texts,
                batch_size=self.batch_size,
                show_progress_bar=False,
                convert_to_numpy=True,
                normalize_embeddings=True,
            )
        except Exception as exc:
            raise EmbeddingServiceError(
                "The embedding model failed to encode the input texts."
            ) from exc

        return self._validate_vectors(
            raw_vectors=raw_vectors,
            expected_count=len(prepared_texts),
        )

    def embed_passages(
        self,
        texts: Iterable[str],
    ) -> list[list[float]]:
        """Create passage embeddings for document chunks.

        E5 requires the 'passage: ' prefix for source documents.
        """

        return self._encode(
            texts=texts,
            prefix="passage: ",
        )

    def embed_queries(
        self,
        texts: Iterable[str],
    ) -> list[list[float]]:
        """Create query embeddings for semantic search.

        E5 requires the 'query: ' prefix for search queries.
        """

        return self._encode(
            texts=texts,
            prefix="query: ",
        )
