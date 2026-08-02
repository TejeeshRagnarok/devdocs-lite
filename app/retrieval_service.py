"""Retrieval Pipeline Service.

Coordinates EmbeddingService and VectorStore to perform end-to-end
semantic search over indexed chunks, returning full text matches.
"""

import logging

from .config import CHUNKS_METADATA_PATH, DEFAULT_RETRIEVAL_TOP_K, DEFAULT_MIN_SCORE
from .embedding_service import EmbeddingService, EmbeddingError
from .utils import read_json
from .vector_store import VectorStore, VectorStoreError

logger = logging.getLogger(__name__)


class RetrievalError(Exception):
    """Raised for errors during the retrieval pipeline."""


class RetrievalService:
    """Coordinates embedding, vector search, and metadata lookup."""

    def __init__(self, embedding_service: EmbeddingService, vector_store: VectorStore):
        self._embedder = embedding_service
        self._store = vector_store
        
        # Load metadata lazily
        self._metadata_cache: dict | None = None

    def _load_metadata(self) -> dict:
        """Load the chunk metadata mapping freshly to prevent stale data and excessive memory usage."""
        return read_json(CHUNKS_METADATA_PATH, {})

    def retrieve(
        self, 
        query: str, 
        top_k: int = DEFAULT_RETRIEVAL_TOP_K, 
        min_score: float = DEFAULT_MIN_SCORE
    ) -> list[dict]:
        """Perform semantic search for the given query.

        Returns
        -------
        list[dict]
            List of dictionaries matching RetrievalResult schema.
        """
        query = query.strip()
        if not query:
            raise RetrievalError("Query cannot be empty.")

        # 1. Embed the query
        try:
            # We mock a chunk structure to reuse embed_chunks
            query_chunks = [{"chunk_id": -1, "text": query}]
            embed_results = self._embedder.embed_chunks(query_chunks)
            if not embed_results or not embed_results[0]["embedding"]:
                raise RetrievalError("Failed to generate embedding for the query.")
            
            query_vector = embed_results[0]["embedding"]
        except EmbeddingError as exc:
            logger.error("Embedding provider failed during retrieval: %s", exc)
            raise RetrievalError(f"Embedding generation failed: {exc}") from exc

        # 2. Search FAISS
        try:
            search_results = self._store.search(query_vector, top_k=top_k)
        except VectorStoreError as exc:
            logger.error("Vector store search failed: %s", exc)
            raise RetrievalError(f"Vector search failed: {exc}") from exc

        if not search_results:
            return []

        # 3. Metadata Lookup & Filtering
        metadata = self._load_metadata()
        final_results = []

        for item in search_results:
            chunk_id = item["chunk_id"]
            score = item["score"]

            if score < min_score:
                continue

            meta = metadata.get(str(chunk_id))
            if not meta:
                logger.warning("Chunk %d found in FAISS but missing from chunks.json metadata", chunk_id)
                continue

            final_results.append({
                "chunk_id": chunk_id,
                "score": score,
                "text": meta.get("text", ""),
                "document": meta.get("document", "unknown"),
                "start_char": meta.get("start_char", 0),
                "end_char": meta.get("end_char", 0),
            })

        # FAISS search results are already sorted by score descending.
        return final_results


# ---------------------------------------------------------------------------
# Module-level convenience
# ---------------------------------------------------------------------------

_retrieval_service_instance: RetrievalService | None = None

def get_retrieval_service(embedder: EmbeddingService, store: VectorStore) -> RetrievalService:
    """Return a singleton RetrievalService."""
    global _retrieval_service_instance
    if _retrieval_service_instance is None:
        _retrieval_service_instance = RetrievalService(embedder, store)
    return _retrieval_service_instance
