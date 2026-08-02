"""Index Management Module.

Provides operations to query and manage the state of the FAISS Vector Store
and its associated JSON metadata (chunks.json).
"""

import logging
import os
from datetime import datetime, timezone

from .config import (
    CHUNKS_METADATA_PATH,
    EMBEDDING_PROVIDER,
    FAISS_INDEX_PATH,
    FAISS_METADATA_PATH,
)
import faiss
from .embedding_service import EmbeddingError, EmbeddingService
from .utils import read_json, write_json
from .vector_store import VectorStore, VectorStoreError

logger = logging.getLogger(__name__)


class IndexManagerError(Exception):
    """Raised for errors during index management operations."""


class IndexManager:
    """Manages Vector Store and Metadata persistence state."""

    def __init__(self, vector_store: VectorStore, embedding_service: EmbeddingService):
        self._store = vector_store
        self._embedder = embedding_service

    def get_documents(self) -> list[str]:
        """List all unique documents currently indexed in chunks.json."""
        metadata = read_json(CHUNKS_METADATA_PATH, {})
        documents = {meta.get("document") for meta in metadata.values() if meta.get("document")}
        return sorted(list(documents))

    def get_stats(self) -> dict:
        """Return statistics about the current index."""
        metadata = read_json(CHUNKS_METADATA_PATH, {})
        documents = {meta.get("document") for meta in metadata.values() if meta.get("document")}
        
        index_size = 0
        creation_time = "Unknown"
        if os.path.exists(FAISS_INDEX_PATH):
            stat = os.stat(FAISS_INDEX_PATH)
            index_size = stat.st_size
            creation_time = datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc).isoformat()

        return {
            "document_count": len(documents),
            "chunk_count": len(metadata),
            "embedding_dimension": self._embedder.dimension,
            "index_size": index_size,
            "provider": EMBEDDING_PROVIDER,
            "creation_time": creation_time,
        }

    def delete_document(self, filename: str) -> int:
        """Delete all chunks and vectors associated with a specific document."""
        if not filename:
            raise IndexManagerError("Filename cannot be empty.")

        metadata = read_json(CHUNKS_METADATA_PATH, {})
        
        # 1. Identify chunk IDs
        chunks_to_delete = []
        for chunk_id_str, meta in metadata.items():
            if meta.get("document") == filename:
                try:
                    chunks_to_delete.append(int(chunk_id_str))
                except ValueError:
                    logger.warning(f"Invalid chunk ID format: {chunk_id_str}")

        if not chunks_to_delete:
            return 0  # Missing document or already deleted

        # 2. Remove from VectorStore
        try:
            num_removed = self._store.remove_ids(chunks_to_delete)
            self._store.save()
        except VectorStoreError as exc:
            raise IndexManagerError(f"Failed to remove vectors: {exc}") from exc

        # 3. Remove from Metadata
        for chunk_id in chunks_to_delete:
            metadata.pop(str(chunk_id), None)
        write_json(CHUNKS_METADATA_PATH, metadata)

        logger.info(f"Deleted document '{filename}'. Removed {len(chunks_to_delete)} chunks. VectorStore reported {num_removed} vectors removed.")
        return len(chunks_to_delete)

    def delete_all(self) -> None:
        """Clear the entire index and metadata."""
        try:
            self._store.clear()
            self._store.save()
        except VectorStoreError as exc:
            raise IndexManagerError(f"Failed to clear FAISS index: {exc}") from exc

        write_json(CHUNKS_METADATA_PATH, {})
        logger.info("Cleared all indexed documents.")

    def health_check(self) -> dict:
        """Verify the integrity between FAISS and chunks.json."""
        faiss_exists = os.path.exists(FAISS_INDEX_PATH)
        metadata_exists = os.path.exists(CHUNKS_METADATA_PATH)

        metadata = read_json(CHUNKS_METADATA_PATH, {})
        faiss_meta = read_json(FAISS_METADATA_PATH, {"dimension": 0, "count": 0})

        faiss_count = faiss_meta.get("count", 0)
        json_count = len(metadata)

        dimensions_match = (faiss_meta.get("dimension") == self._embedder.dimension)
        chunk_counts_match = (faiss_count == json_count)

        # Precise orphan check
        faiss_ids = set()
        if self._store.index is not None and self._store.index.ntotal > 0:
            faiss_ids = set(faiss.vector_to_array(self._store.index.id_map))
        
        json_ids = set()
        for k in metadata.keys():
            try:
                json_ids.add(int(k))
            except ValueError:
                pass

        orphan_metadata = len(json_ids - faiss_ids)
        orphan_vector = len(faiss_ids - json_ids)

        status = "Healthy"
        details = "Index is in sync."
        
        if not faiss_exists or not metadata_exists:
            status = "Warning"
            details = "Index or metadata files are missing."
        elif not dimensions_match:
            status = "Corrupted"
            details = f"Dimension mismatch: FAISS({faiss_meta.get('dimension')}) vs Embedder({self._embedder.dimension})"
        elif not chunk_counts_match:
            status = "Warning"
            details = f"Count mismatch: FAISS has {faiss_count}, Metadata has {json_count}."

        if json_count == 0 and faiss_count == 0:
            status = "Healthy"
            details = "Index is empty."

        return {
            "status": status,
            "faiss_exists": faiss_exists,
            "metadata_exists": metadata_exists,
            "dimensions_match": dimensions_match,
            "chunk_counts_match": chunk_counts_match,
            "orphan_metadata_count": orphan_metadata,
            "orphan_vector_count": orphan_vector,
            "details": details
        }

    def rebuild_faiss(self) -> int:
        """Re-embed all texts from chunks.json and rebuild FAISS."""
        metadata = read_json(CHUNKS_METADATA_PATH, {})
        if not metadata:
            return 0

        self.delete_all()
        
        # Prepare payloads for EmbeddingService
        chunks_to_embed = []
        for chunk_id_str, meta in metadata.items():
            if not meta.get("text"):
                continue
            try:
                chunks_to_embed.append({
                    "chunk_id": int(chunk_id_str),
                    "text": meta["text"]
                })
            except ValueError:
                continue

        if not chunks_to_embed:
            return 0

        # Batch embed BEFORE clearing FAISS to ensure network success
        try:
            embeddings = self._embedder.embed_chunks(chunks_to_embed)
        except EmbeddingError as exc:
            raise IndexManagerError(f"Rebuild failed during embedding: {exc}") from exc

        # Now clear and add back to FAISS
        self.delete_all()
        try:
            self._store.add_embeddings(embeddings)
            self._store.save()
        except VectorStoreError as exc:
            raise IndexManagerError(f"Rebuild failed during FAISS insert: {exc}") from exc

        # Restore JSON
        write_json(CHUNKS_METADATA_PATH, metadata)
        
        logger.info(f"Rebuilt FAISS index with {len(embeddings)} chunks.")
        return len(embeddings)

    def rebuild_metadata(self) -> int:
        """Clean up orphan JSON entries by cross-referencing with FAISS."""
        metadata = read_json(CHUNKS_METADATA_PATH, {})
        
        faiss_ids = set()
        if self._store.index is not None and self._store.index.ntotal > 0:
            faiss_ids = set(faiss.vector_to_array(self._store.index.id_map))

        cleaned_count = 0
        keys_to_delete = []
        for k in metadata.keys():
            try:
                if int(k) not in faiss_ids:
                    keys_to_delete.append(k)
            except ValueError:
                keys_to_delete.append(k)
                
        for k in keys_to_delete:
            metadata.pop(k, None)
            cleaned_count += 1
            
        write_json(CHUNKS_METADATA_PATH, metadata)
        return cleaned_count


# ---------------------------------------------------------------------------
# Module-level convenience
# ---------------------------------------------------------------------------

_index_manager_instance: IndexManager | None = None

def get_index_manager(store: VectorStore, embedder: EmbeddingService) -> IndexManager:
    global _index_manager_instance
    if _index_manager_instance is None:
        _index_manager_instance = IndexManager(store, embedder)
    return _index_manager_instance
