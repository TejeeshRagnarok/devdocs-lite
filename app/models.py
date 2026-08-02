from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=600)


class SearchResponseItem(BaseModel):
    path: str
    score: float
    language: str
    snippet: str


class PreviewResponse(BaseModel):
    path: str
    language: str
    content: str
    truncated: bool
    insights: dict | None = None


class UploadResponse(BaseModel):
    message: str
    files_indexed: int
    project_name: str


class DocumentResult(BaseModel):
    filename: str
    text: str
    status: str
    error: str | None = None


class IngestResponse(BaseModel):
    results: list[DocumentResult]


class ChunkItem(BaseModel):
    chunk_id: int
    text: str
    start_char: int
    end_char: int


class ChunkResult(BaseModel):
    filename: str
    chunks: list[ChunkItem]
    status: str
    error: str | None = None


class ChunkResponse(BaseModel):
    results: list[ChunkResult]


class EmbeddingItem(BaseModel):
    chunk_id: int
    embedding: list[float]


class EmbeddingResult(BaseModel):
    filename: str
    embeddings: list[EmbeddingItem]
    dimension: int
    status: str
    error: str | None = None


class EmbedResponse(BaseModel):
    results: list[EmbeddingResult]


class VectorSearchRequest(BaseModel):
    embedding: list[float]
    top_k: int = Field(default=5, ge=1, le=100)


class VectorSearchItem(BaseModel):
    chunk_id: int
    score: float


class VectorSearchResponse(BaseModel):
    results: list[VectorSearchItem]
    status: str
    error: str | None = None


class RetrievalRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=100)
    min_score: float = Field(default=0.7, ge=0.0, le=1.0)


class RetrievalResult(BaseModel):
    chunk_id: int
    score: float
    text: str
    document: str
    start_char: int
    end_char: int


class RetrievalResponse(BaseModel):
    results: list[RetrievalResult]
    status: str
    error: str | None = None


class RAGRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=100)
    min_score: float = Field(default=0.7, ge=0.0, le=1.0)


class RAGSource(BaseModel):
    document: str
    chunk_id: int


class RAGResponse(BaseModel):
    answer: str
    sources: list[RAGSource]
    status: str
    error: str | None = None


class DocumentListResponse(BaseModel):
    documents: list[str]


class IndexStatsResponse(BaseModel):
    document_count: int
    chunk_count: int
    embedding_dimension: int
    index_size: int
    provider: str
    creation_time: str


class IndexHealthResponse(BaseModel):
    status: str
    faiss_exists: bool
    metadata_exists: bool
    dimensions_match: bool
    chunk_counts_match: bool
    orphan_metadata_count: int
    orphan_vector_count: int
    details: str
