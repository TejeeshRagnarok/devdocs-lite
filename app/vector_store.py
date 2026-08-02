"""Vector Store module for efficient similarity search using FAISS.

This module implements a provider-based architecture:
    VectorStore (ABC) → FAISSVectorStore (Concrete)

The rest of the application should interact only with the VectorStore interface.
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from typing import Any

import faiss
import numpy as np

from .config import FAISS_INDEX_PATH, FAISS_METADATA_PATH, DEFAULT_TOP_K
from .utils import read_json, write_json

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class VectorStore(ABC):
    """Abstract interface for a vector database."""

    @abstractmethod
    def add_embeddings(self, embeddings: list[dict]) -> None:
        """Add a batch of embeddings to the store.

        Parameters
        ----------
        embeddings:
            List of dicts, each with ``chunk_id`` (int) and ``embedding`` (list[float]).
        """

    @abstractmethod
    def search(self, query_embedding: list[float], top_k: int = DEFAULT_TOP_K) -> list[dict]:
        """Search for the most similar vectors to the query.

        Returns
        -------
        list[dict]
            Ordered list of ``{"chunk_id": int, "score": float}``.
        """

    @abstractmethod
    def save(self) -> None:
        """Persist the vector store to disk."""

    @abstractmethod
    def load(self) -> None:
        """Load the vector store from disk."""


    @abstractmethod
    def remove_ids(self, chunk_ids: list[int]) -> int:
        """Remove specific chunk IDs from the vector store."""
        
    @abstractmethod
    def clear(self) -> None:
        """Clear all vectors from the store."""


class VectorStoreError(Exception):
    """Raised on invalid dimensions, corrupted indexes, etc."""


# ---------------------------------------------------------------------------
# FAISS implementation
# ---------------------------------------------------------------------------

class FAISSVectorStore(VectorStore):
    """Local vector store using faiss-cpu and IndexIDMap for custom IDs."""

    def __init__(self, dimension: int = 768) -> None:
        self.dimension = dimension
        self.index: faiss.IndexIDMap | None = None
        
        # We store metadata locally in a dict, then flush to json on save()
        # Not strictly needed since IndexIDMap stores our integer IDs natively,
        # but tracking them helps if we ever need chunk_id -> metadata lookups.
        self._meta: dict[str, Any] = {"dimension": dimension, "count": 0}

    def _init_index(self) -> None:
        if self.index is None:
            # IndexFlatL2 provides exact L2 distance search (brute force)
            base_index = faiss.IndexFlatL2(self.dimension)
            # IndexIDMap allows us to assign our own integer IDs (chunk_ids)
            self.index = faiss.IndexIDMap(base_index)
            logger.info("Initialized new empty FAISS index (dim=%d)", self.dimension)

    def add_embeddings(self, embeddings: list[dict]) -> None:
        """Add embeddings. If chunk_id already exists, FAISS IndexIDMap 
        allows appending multiple times, but standard usage expects unique IDs.
        For exact deduplication/upsert, one would typically remove old IDs first.
        Since IndexFlatL2 doesn't easily support targeted remove(), we simply add.
        """
        if not embeddings:
            return

        self._init_index()

        # Filter out empty embeddings (if upstream didn't already)
        valid_initial = [e for e in embeddings if e.get("embedding")]
        if not valid_initial:
            return

        # Deduplicate within the payload, keeping the latest vector per chunk_id
        valid_dict = {e["chunk_id"]: e for e in valid_initial}
        valid = list(valid_dict.values())

        # Ensure correct dimension
        if len(valid[0]["embedding"]) != self.dimension:
            raise VectorStoreError(
                f"Embedding dimension mismatch. Expected {self.dimension}, "
                f"got {len(valid[0]['embedding'])}."
            )

        # Prepare numpy arrays
        vectors = np.array([e["embedding"] for e in valid], dtype=np.float32)
        ids = np.array([e["chunk_id"] for e in valid], dtype=np.int64)

        # Remove existing IDs to prevent duplicates
        if self.index.ntotal > 0:
            selector = faiss.IDSelectorBatch(ids.size, faiss.swig_ptr(ids))
            self.index.remove_ids(selector)

        # FAISS add
        self.index.add_with_ids(vectors, ids)
        
        # Update meta
        self._meta["count"] = int(self.index.ntotal)
        logger.info("Added %d embeddings to FAISS. Total: %d", len(valid), self.index.ntotal)

    def remove_ids(self, chunk_ids: list[int]) -> int:
        if not self.index or self.index.ntotal == 0 or not chunk_ids:
            return 0
        
        ids = np.array(chunk_ids, dtype=np.int64)
        selector = faiss.IDSelectorBatch(ids.size, faiss.swig_ptr(ids))
        num_removed = self.index.remove_ids(selector)
        self._meta["count"] = int(self.index.ntotal)
        return num_removed

    def clear(self) -> None:
        if self.index:
            self.index.reset()
            self._meta["count"] = 0

    def search(self, query_embedding: list[float], top_k: int = DEFAULT_TOP_K) -> list[dict]:
        """Perform exact L2 search. FAISS returns L2 distances (lower is better).
        We invert them to a similarity score (higher is better) for the API.
        """
        if self.index is None or self.index.ntotal == 0:
            return []

        if len(query_embedding) != self.dimension:
            raise VectorStoreError(
                f"Query dimension mismatch. Expected {self.dimension}, "
                f"got {len(query_embedding)}."
            )

        # Convert to numpy and reshape to (1, dimension)
        q_vec = np.array([query_embedding], dtype=np.float32)

        # Search
        # D = distances (L2 squared), I = chunk_ids
        distances, indices = self.index.search(q_vec, top_k)

        results = []
        for dist, chunk_id in zip(distances[0], indices[0]):
            # FAISS returns -1 for chunk_id if it didn't find enough vectors
            if chunk_id == -1:
                continue
            
            # L2 distance is non-negative.
            # Convert to a pseudo-similarity score (0 to 1, where 1 is identical)
            # score = 1 / (1 + distance)
            score = 1.0 / (1.0 + float(dist))
            
            results.append({
                "chunk_id": int(chunk_id),
                "score": round(score, 4)
            })

        return results

    def save(self) -> None:
        """Persist FAISS index and metadata to disk."""
        if self.index is None:
            return

        try:
            faiss.write_index(self.index, str(FAISS_INDEX_PATH))
            write_json(FAISS_METADATA_PATH, self._meta)
            logger.info("Saved FAISS index to %s", FAISS_INDEX_PATH)
        except Exception as exc:
            raise VectorStoreError(f"Failed to save FAISS index: {exc}") from exc

    def load(self) -> None:
        """Load FAISS index from disk. Creates empty if missing or corrupted."""
        if not os.path.exists(FAISS_INDEX_PATH):
            logger.info("FAISS index not found. Will create fresh on first add.")
            self.index = None
            self._meta = {"dimension": self.dimension, "count": 0}
            return

        try:
            self.index = faiss.read_index(str(FAISS_INDEX_PATH))
            meta = read_json(FAISS_METADATA_PATH, {"dimension": self.dimension, "count": 0})
            
            if meta.get("dimension") != self.dimension:
                logger.warning("Dimension mismatch in loaded index. Starting fresh.")
                self.index = None
                self._meta = {"dimension": self.dimension, "count": 0}
                return

            self._meta = meta
            logger.info("Loaded FAISS index with %d vectors", self.index.ntotal)
            
        except Exception as exc:
            logger.warning("Corrupted FAISS index detected: %s. Starting fresh.", exc)
            self.index = None
            self._meta = {"dimension": self.dimension, "count": 0}


# ---------------------------------------------------------------------------
# Module-level convenience
# ---------------------------------------------------------------------------

_store_instance: VectorStore | None = None

def get_vector_store() -> VectorStore:
    """Return a lazily-initialized singleton VectorStore."""
    global _store_instance
    if _store_instance is None:
        _store_instance = FAISSVectorStore()
        _store_instance.load()
    return _store_instance
