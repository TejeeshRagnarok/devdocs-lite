"""Embedding service with provider abstraction for generating vector embeddings.

This module implements a provider-based architecture:

    EmbeddingProvider (ABC)  →  JinaProvider (concrete)  →  EmbeddingService (public API)

The rest of the project should only interact with ``EmbeddingService``.
Adding a new provider requires only subclassing ``EmbeddingProvider`` and
updating the factory in ``get_embedding_service()``.
"""

from __future__ import annotations

import logging
import os
import time
from abc import ABC, abstractmethod

import httpx

from .config import (
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_MAX_RETRIES,
    EMBEDDING_MODEL,
    EMBEDDING_PROVIDER,
    EMBEDDING_TIMEOUT,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class EmbeddingProvider(ABC):
    """Interface that every concrete embedding provider must implement."""

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a list of text strings.

        Parameters
        ----------
        texts:
            Non-empty list of non-empty strings.

        Returns
        -------
        list[list[float]]
            One embedding vector per input text, in the same order.

        Raises
        ------
        EmbeddingError
            On any API / network / auth failure.
        """

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Dimensionality of the vectors produced by this provider."""


class EmbeddingError(Exception):
    """Raised when an embedding provider encounters a non-recoverable error."""


# ---------------------------------------------------------------------------
# Jina AI provider
# ---------------------------------------------------------------------------

_JINA_API_URL = "https://api.jina.ai/v1/embeddings"
_JINA_DIMENSION = 768  # jina-embeddings-v2-base-en


class JinaProvider(EmbeddingProvider):
    """Jina AI Embeddings v2 provider.

    Requires ``JINA_API_KEY`` environment variable.
    Free tier: 1 M tokens / month, no credit card required.
    """

    def __init__(
        self,
        model: str = EMBEDDING_MODEL,
        timeout: int = EMBEDDING_TIMEOUT,
        max_retries: int = EMBEDDING_MAX_RETRIES,
    ) -> None:
        self._model = model
        self._timeout = timeout
        self._max_retries = max_retries

        self._api_key = os.environ.get("JINA_API_KEY", "").strip()
        if not self._api_key:
            raise EmbeddingError(
                "Missing JINA_API_KEY environment variable. "
                "Get a free key at https://jina.ai/embeddings/ and set it:\n"
                "  export JINA_API_KEY='jina_...'"
            )

    # -- public interface ---------------------------------------------------

    @property
    def dimension(self) -> int:
        return _JINA_DIMENSION

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Call the Jina API with retry and exponential backoff."""
        if not texts:
            return []

        payload = {
            "model": self._model,
            "input": texts,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        last_exc: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                response = httpx.post(
                    _JINA_API_URL,
                    json=payload,
                    headers=headers,
                    timeout=self._timeout,
                )

                if response.status_code == 200:
                    return self._parse_response(response.json(), len(texts))

                # Retryable status codes
                if response.status_code in (429, 500, 502, 503, 504):
                    wait = self._backoff_delay(attempt, response)
                    logger.warning(
                        "Jina API returned %d (attempt %d/%d). Retrying in %.1fs...",
                        response.status_code,
                        attempt,
                        self._max_retries,
                        wait,
                    )
                    time.sleep(wait)
                    last_exc = EmbeddingError(
                        f"Jina API error {response.status_code}: {response.text[:300]}"
                    )
                    continue

                # Non-retryable errors
                if response.status_code == 401:
                    raise EmbeddingError(
                        "Invalid JINA_API_KEY. Check your key at https://jina.ai/embeddings/"
                    )

                raise EmbeddingError(
                    f"Jina API error {response.status_code}: {response.text[:300]}"
                )

            except httpx.TimeoutException as exc:
                wait = self._backoff_delay(attempt)
                logger.warning(
                    "Jina API timeout (attempt %d/%d). Retrying in %.1fs...",
                    attempt,
                    self._max_retries,
                    wait,
                )
                time.sleep(wait)
                last_exc = EmbeddingError(f"Jina API timeout after {self._timeout}s")
                last_exc.__cause__ = exc

            except httpx.RequestError as exc:
                wait = self._backoff_delay(attempt)
                logger.warning(
                    "Jina API network error (attempt %d/%d): %s. Retrying in %.1fs...",
                    attempt,
                    self._max_retries,
                    exc,
                    wait,
                )
                time.sleep(wait)
                last_exc = EmbeddingError(f"Network error: {exc}")
                last_exc.__cause__ = exc

            except EmbeddingError:
                raise

        # All retries exhausted
        raise last_exc or EmbeddingError("Embedding failed after all retries")

    # -- internal helpers ---------------------------------------------------

    @staticmethod
    def _parse_response(data: dict, expected_count: int) -> list[list[float]]:
        """Extract embeddings from the Jina API JSON response."""
        if "data" not in data:
            raise EmbeddingError(
                f"Unexpected Jina response format: {str(data)[:300]}"
            )

        items = sorted(data["data"], key=lambda x: x.get("index", 0))
        vectors = [item["embedding"] for item in items]

        if len(vectors) != expected_count:
            raise EmbeddingError(
                f"Expected {expected_count} embeddings but received {len(vectors)}"
            )

        return vectors

    @staticmethod
    def _backoff_delay(attempt: int, response: httpx.Response | None = None) -> float:
        """Exponential backoff: 1s, 2s, 4s. Respects Retry-After header."""
        if response is not None:
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    return min(float(retry_after), 30.0)
                except ValueError:
                    pass
        return min(2 ** (attempt - 1), 16.0)


# ---------------------------------------------------------------------------
# Provider factory
# ---------------------------------------------------------------------------

_PROVIDERS: dict[str, type[EmbeddingProvider]] = {
    "jina": JinaProvider,
}


def _create_provider(name: str | None = None) -> EmbeddingProvider:
    """Instantiate the configured embedding provider."""
    provider_name = (name or EMBEDDING_PROVIDER).lower()
    if provider_name not in _PROVIDERS:
        available = ", ".join(sorted(_PROVIDERS.keys()))
        raise EmbeddingError(
            f"Unknown embedding provider '{provider_name}'. Available: {available}"
        )
    return _PROVIDERS[provider_name]()


# ---------------------------------------------------------------------------
# Public service
# ---------------------------------------------------------------------------

class EmbeddingService:
    """Public API for generating embeddings from text chunks.

    Usage::

        service = EmbeddingService()
        results = service.embed_chunks([
            {"chunk_id": 1, "text": "Hello world"},
            {"chunk_id": 2, "text": "Another chunk"},
        ])
    """

    def __init__(
        self,
        provider: EmbeddingProvider | None = None,
        batch_size: int = EMBEDDING_BATCH_SIZE,
    ) -> None:
        self._provider = provider or _create_provider()
        self._batch_size = batch_size

    @property
    def dimension(self) -> int:
        """Vector dimensionality of the current provider."""
        return self._provider.dimension

    def embed_chunks(self, chunks: list[dict]) -> list[dict]:
        """Generate embeddings for a list of chunk dicts.

        Parameters
        ----------
        chunks:
            List of dicts, each containing at least ``chunk_id`` and ``text``.

        Returns
        -------
        list[dict]
            Ordered list of ``{"chunk_id": int, "embedding": list[float]}``.
            Chunks with empty text are returned with an empty embedding.
        """
        if not chunks:
            return []

        # Separate non-empty chunks from empty ones and deduplicate texts.
        results: list[dict] = []
        unique_texts: dict[str, int] = {}
        ordered_unique_texts: list[str] = []
        chunk_to_unique_idx: list[tuple[int, int]] = []  # (result_idx, unique_idx)

        for idx, chunk in enumerate(chunks):
            chunk_id = chunk.get("chunk_id", idx + 1)
            text = chunk.get("text", "").strip()

            if not text:
                logger.warning("Chunk %d has empty text — skipping embedding", chunk_id)
                results.append({"chunk_id": chunk_id, "embedding": []})
            else:
                if text not in unique_texts:
                    unique_texts[text] = len(ordered_unique_texts)
                    ordered_unique_texts.append(text)
                
                chunk_to_unique_idx.append((len(results), unique_texts[text]))
                results.append({"chunk_id": chunk_id, "embedding": []})  # placeholder

        if not ordered_unique_texts:
            return results

        # Batch the API calls for unique texts only.
        unique_vectors = self._embed_in_batches(ordered_unique_texts)

        # Fill in placeholders.
        for result_idx, unique_idx in chunk_to_unique_idx:
            results[result_idx]["embedding"] = unique_vectors[unique_idx]

        return results

    def _embed_in_batches(self, texts: list[str]) -> list[list[float]]:
        """Split texts into batches and call the provider for each."""
        all_vectors: list[list[float]] = []

        for batch_start in range(0, len(texts), self._batch_size):
            batch = texts[batch_start : batch_start + self._batch_size]
            logger.info(
                "Embedding batch %d-%d of %d texts",
                batch_start + 1,
                batch_start + len(batch),
                len(texts),
            )
            vectors = self._provider.embed(batch)
            all_vectors.extend(vectors)

        return all_vectors


# ---------------------------------------------------------------------------
# Module-level convenience
# ---------------------------------------------------------------------------

_service_instance: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    """Return a lazily-initialised singleton ``EmbeddingService``.

    Raises ``EmbeddingError`` if the provider cannot be initialised
    (e.g. missing API key).
    """
    global _service_instance
    if _service_instance is None:
        _service_instance = EmbeddingService()
    return _service_instance
