"""RAG Generation Module.

Implements the ContextBuilder, PromptBuilder, and RAGService
orchestrator for strictly grounded question-answering.
"""

import logging

from .config import MAX_CONTEXT_LENGTH
from .llm_provider import LLMError, LLMProvider
from .retrieval_service import RetrievalError, RetrievalService

logger = logging.getLogger(__name__)


class RAGError(Exception):
    """Raised for errors during RAG generation."""


class ContextBuilder:
    """Formats and deduplicates retrieved chunks into a strict context block."""

    @staticmethod
    def build(chunks: list[dict], max_length: int = MAX_CONTEXT_LENGTH) -> tuple[str, list[dict]]:
        """Merge chunks into a context string, preserving sources and deduplicating."""
        if not chunks:
            return "", []

        seen_texts = set()
        formatted_blocks = []
        sources = []
        current_length = 0

        for chunk in chunks:
            text = chunk.get("text", "").strip()
            if not text or text in seen_texts:
                continue

            doc_name = chunk.get("document", "unknown")
            chunk_id = chunk.get("chunk_id", -1)

            block = f"--- Document: {doc_name} ---\n{text}\n"
            block_len = len(block)

            if current_length + block_len > max_length:
                logger.info("Max context length reached. Truncating further chunks.")
                break

            seen_texts.add(text)
            formatted_blocks.append(block)
            sources.append({"document": doc_name, "chunk_id": chunk_id})
            current_length += block_len

        return "\n".join(formatted_blocks), sources


class PromptBuilder:
    """Builds the strict System Prompt for grounded Q&A."""

    @staticmethod
    def build(question: str, context: str) -> list[dict[str, str]]:
        """Construct the OpenAI-compatible message list."""
        
        system_prompt = (
            "You are a highly technical, senior software engineer and technical writer. "
            "Your task is to answer the user's question ONLY using the provided Context. "
            "Follow these strict rules:\n"
            "1. If the answer is not contained in the Context, you MUST output exactly: "
            "'I cannot answer this question based on the provided documents.' Do not attempt to guess or use outside knowledge.\n"
            "2. Keep your answers concise, technical, and directly address the user's query.\n"
            "3. Do not mention 'Based on the context' or 'The context says' in your answer. Just answer the question directly.\n"
            "4. If providing code, use markdown formatting."
        )

        user_prompt = f"Context:\n\n{context}\n\nQuestion: {question}"

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]


class RAGService:
    """Orchestrates Retrieval, Context Building, Prompting, and LLM Generation."""

    def __init__(self, retrieval_service: RetrievalService, llm_provider: LLMProvider):
        self._retrieval = retrieval_service
        self._llm = llm_provider

    def generate_answer(self, query: str, top_k: int = 5, min_score: float = 0.7) -> dict:
        """Execute the full RAG pipeline."""
        query = query.strip()
        if not query:
            raise RAGError("Question cannot be empty.")

        # 1. Retrieve
        try:
            chunks = self._retrieval.retrieve(query=query, top_k=top_k, min_score=min_score)
        except RetrievalError as exc:
            raise RAGError(f"Retrieval failed: {exc}") from exc

        if not chunks:
            return {
                "answer": "I cannot answer this question based on the provided documents.",
                "sources": []
            }

        # 2. Build Context
        context_str, sources = ContextBuilder.build(chunks)
        if not context_str:
            return {
                "answer": "I cannot answer this question based on the provided documents.",
                "sources": []
            }

        # 3. Build Prompt
        messages = PromptBuilder.build(question=query, context=context_str)

        # 4. Generate
        try:
            answer = self._llm.generate(messages)
        except LLMError as exc:
            logger.error("LLM Generation failed: %s", exc)
            raise RAGError(f"Generation failed: {exc}") from exc

        return {
            "answer": answer,
            "sources": sources
        }


# ---------------------------------------------------------------------------
# Module-level convenience
# ---------------------------------------------------------------------------

_rag_service_instance: RAGService | None = None

def get_rag_service(retrieval_service: RetrievalService, llm_provider: LLMProvider) -> RAGService:
    """Return a singleton RAGService."""
    global _rag_service_instance
    if _rag_service_instance is None:
        _rag_service_instance = RAGService(retrieval_service, llm_provider)
    return _rag_service_instance
