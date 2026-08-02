from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from typing import Annotated
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from .config import BASE_DIR, DEFAULT_CHUNK_OVERLAP, DEFAULT_CHUNK_SIZE, FILES_INDEX_PATH, METADATA_PATH
from .explainer import explain_class, explain_file, explain_function, explain_project
from .chunker import chunk_text
from .document_processor import process_document
from .embedding_service import EmbeddingError, get_embedding_service
from .ingest import ingest_upload
from .insights import classes_by_file, functions_by_file, imports_by_file
from .metadata import ensure_insight_metadata
from .models import (
    AskRequest, ChunkResponse, EmbedResponse, IngestResponse, 
    PreviewResponse, UploadResponse, VectorSearchRequest, VectorSearchResponse,
    RetrievalRequest, RetrievalResponse, RAGRequest, RAGResponse,
    DocumentListResponse, IndexStatsResponse, IndexHealthResponse
)
from .retrieval_service import RetrievalError, get_retrieval_service
from .llm_provider import GroqProvider, LLMError
from .rag_service import RAGError, get_rag_service
from .index_management import IndexManagerError, get_index_manager
from .vector_store import VectorStoreError, get_vector_store
from .config import CHUNKS_METADATA_PATH
from .preview import preview_file
from .rag import answer_question
from .search import search_entries
from .tree import build_tree
from .utils import ensure_workspace, read_json


app = FastAPI(title="DevDocs Lite", version="0.3.0")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


@app.on_event("startup")
def startup() -> None:
    ensure_workspace()


def get_entries() -> list[dict]:
    """Read the current file index from disk."""
    return read_json(FILES_INDEX_PATH, [])


@app.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html")


@app.post("/upload", response_model=UploadResponse)
async def upload(file: UploadFile = File(...)) -> dict:
    return await ingest_upload(file)


@app.post("/ingest", response_model=IngestResponse)
async def ingest_documents(
    files: Annotated[list[UploadFile], File(...)],
) -> dict:
    """Upload one or more documents and extract their raw text."""
    results = []
    for uploaded in files:
        data = await uploaded.read()
        result = process_document(uploaded.filename or "unknown", data)
        results.append(result)
    return {"results": results}


@app.post("/chunk", response_model=ChunkResponse)
async def chunk_documents(
    files: Annotated[list[UploadFile], File(...)],
    chunk_size: int = Query(DEFAULT_CHUNK_SIZE, ge=50, le=100_000),
    overlap: int = Query(DEFAULT_CHUNK_OVERLAP, ge=0),
) -> dict:
    """Upload documents, extract text, and return overlapping chunks."""
    results = []
    for uploaded in files:
        filename = uploaded.filename or "unknown"
        data = await uploaded.read()
        doc_result = process_document(filename, data)

        if doc_result["status"] != "success":
            results.append({
                "filename": filename,
                "chunks": [],
                "status": "error",
                "error": doc_result["error"],
            })
            continue

        chunks = chunk_text(doc_result["text"], chunk_size=chunk_size, overlap=overlap)
        results.append({
            "filename": filename,
            "chunks": chunks,
            "status": "success",
            "error": None,
        })
    return {"results": results}


@app.post("/embed", response_model=EmbedResponse)
async def embed_documents(
    files: Annotated[list[UploadFile], File(...)],
    chunk_size: int = Query(DEFAULT_CHUNK_SIZE, ge=50, le=100_000),
    overlap: int = Query(DEFAULT_CHUNK_OVERLAP, ge=0),
) -> dict:
    """Upload documents, extract text, chunk, and return embeddings."""
    try:
        service = get_embedding_service()
    except EmbeddingError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    results = []
    for uploaded in files:
        filename = uploaded.filename or "unknown"
        data = await uploaded.read()
        doc_result = process_document(filename, data)

        if doc_result["status"] != "success":
            results.append({
                "filename": filename,
                "embeddings": [],
                "dimension": 0,
                "status": "error",
                "error": doc_result["error"],
            })
            continue

        chunks = chunk_text(doc_result["text"], chunk_size=chunk_size, overlap=overlap)

        try:
            embeddings = service.embed_chunks(chunks)
            results.append({
                "filename": filename,
                "embeddings": embeddings,
                "dimension": service.dimension,
                "status": "success",
                "error": None,
            })
            # Persist to Vector Store & Metadata
            # Delete existing document to prevent orphan chunks if this is a re-upload of a modified file
            try:
                manager = get_index_manager(get_vector_store(), get_embedding_service())
                manager.delete_document(filename)
            except Exception:
                pass # Safe to ignore if document didn't exist or manager failed
            
            store = get_vector_store()
            store.add_embeddings(embeddings)
            store.save()
            
            metadata = read_json(CHUNKS_METADATA_PATH, {})
            for chunk_meta in chunks:
                chunk_id = str(chunk_meta["chunk_id"])
                metadata[chunk_id] = {
                    "text": chunk_meta.get("text", ""),
                    "document": filename,
                    "start_char": chunk_meta.get("start_char", 0),
                    "end_char": chunk_meta.get("end_char", 0)
                }
            write_json(CHUNKS_METADATA_PATH, metadata)
            
        except EmbeddingError as exc:
            results.append({
                "filename": filename,
                "embeddings": [],
                "dimension": 0,
                "status": "error",
                "error": str(exc),
            })
    return {"results": results}


@app.post("/vector/store")
def vector_store(payload: EmbedResponse) -> dict:
    """Add a batch of embedded chunks to the FAISS index."""
    try:
        store = get_vector_store()
        
        # Flatten the embeddings from all documents in the response
        embeddings_to_add = []
        for result in payload.results:
            if result.status == "success":
                for item in result.embeddings:
                    embeddings_to_add.append({
                        "chunk_id": item.chunk_id,
                        "embedding": item.embedding
                    })
        
        store.add_embeddings(embeddings_to_add)
        store.save()
        return {"status": "success", "indexed_count": len(embeddings_to_add)}
    
    except VectorStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/vector/search", response_model=VectorSearchResponse)
def vector_search(payload: VectorSearchRequest) -> dict:
    """Search the FAISS index using a query embedding."""
    try:
        store = get_vector_store()
        results = store.search(payload.embedding, payload.top_k)
        return {"results": results, "status": "success", "error": None}
    except VectorStoreError as exc:
        return {"results": [], "status": "error", "error": str(exc)}


@app.post("/retrieve", response_model=RetrievalResponse)
def retrieve(payload: RetrievalRequest) -> dict:
    """Retrieve relevant document chunks for a natural language query."""
    try:
        embedder = get_embedding_service()
        store = get_vector_store()
        service = get_retrieval_service(embedder, store)
        
        results = service.retrieve(
            query=payload.query,
            top_k=payload.top_k,
            min_score=payload.min_score
        )
        return {"results": results, "status": "success", "error": None}
    
    except (EmbeddingError, VectorStoreError, RetrievalError) as exc:
        return {"results": [], "status": "error", "error": str(exc)}


@app.post("/rag/generate", response_model=RAGResponse)
def rag_generate(payload: RAGRequest) -> dict:
    """Generate an answer using retrieved document context."""
    try:
        embedder = get_embedding_service()
        store = get_vector_store()
        retrieval_service = get_retrieval_service(embedder, store)
        llm_provider = GroqProvider()
        rag_service = get_rag_service(retrieval_service, llm_provider)
        
        result = rag_service.generate_answer(
            query=payload.query,
            top_k=payload.top_k,
            min_score=payload.min_score
        )
        return {
            "answer": result["answer"],
            "sources": result["sources"],
            "status": "success",
            "error": None
        }
    
    except (EmbeddingError, VectorStoreError, RetrievalError, LLMError, RAGError) as exc:
        return {
            "answer": "",
            "sources": [],
            "status": "error", 
            "error": str(exc)
        }


@app.get("/index/documents", response_model=DocumentListResponse)
def index_documents() -> dict:
    """List all indexed document filenames."""
    manager = get_index_manager(get_vector_store(), get_embedding_service())
    return {"documents": manager.get_documents()}

@app.get("/index/stats", response_model=IndexStatsResponse)
def index_stats() -> dict:
    """Return index statistics."""
    manager = get_index_manager(get_vector_store(), get_embedding_service())
    return manager.get_stats()

@app.get("/index/health", response_model=IndexHealthResponse)
def index_health() -> dict:
    """Check integrity of the index."""
    manager = get_index_manager(get_vector_store(), get_embedding_service())
    return manager.health_check()

@app.delete("/index/document/{filename}")
def index_delete_document(filename: str) -> dict:
    """Delete a specific document and its vectors."""
    try:
        manager = get_index_manager(get_vector_store(), get_embedding_service())
        removed = manager.delete_document(filename)
        return {"status": "success", "removed_chunks": removed}
    except IndexManagerError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@app.delete("/index/all")
def index_delete_all() -> dict:
    """Clear all indexed data."""
    try:
        manager = get_index_manager(get_vector_store(), get_embedding_service())
        manager.delete_all()
        return {"status": "success"}
    except IndexManagerError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@app.post("/index/rebuild/faiss")
def index_rebuild_faiss() -> dict:
    """Rebuild FAISS from existing metadata."""
    try:
        manager = get_index_manager(get_vector_store(), get_embedding_service())
        rebuilt = manager.rebuild_faiss()
        return {"status": "success", "rebuilt_chunks": rebuilt}
    except IndexManagerError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@app.post("/index/rebuild/metadata")
def index_rebuild_metadata() -> dict:
    """Rebuild and clean metadata structure."""
    manager = get_index_manager(get_vector_store(), get_embedding_service())
    cleaned = manager.rebuild_metadata()
    return {"status": "success", "metadata_entries": cleaned}

@app.get("/index/status")
def index_status() -> dict:
    """Check processing status (mocked since processing is synchronous)."""
    return {"status": "idle"}


@app.get("/summary")
def summary() -> dict:
    metadata = read_json(METADATA_PATH, {"file_count": 0, "languages": {}, "important_files": []})
    return ensure_insight_metadata(metadata, get_entries())


@app.get("/tree")
def tree() -> list[dict]:
    return build_tree(get_entries())


@app.get("/files")
def files() -> list[dict]:
    _STRIP = {"content", "parsed"}
    return [
        {key: value for key, value in entry.items() if key not in _STRIP}
        for entry in get_entries()
    ]


@app.get("/functions")
def functions() -> list[dict]:
    return functions_by_file(get_entries())


@app.get("/classes")
def classes() -> list[dict]:
    return classes_by_file(get_entries())


@app.get("/imports")
def imports() -> list[dict]:
    return imports_by_file(get_entries())


@app.get("/preview", response_model=PreviewResponse)
def preview(path: str = Query(..., min_length=1)) -> dict:
    result = preview_file(path, get_entries())
    if not result:
        raise HTTPException(status_code=404, detail="File not found in the current index.")
    return result


@app.get("/search")
def search(q: str = Query(..., min_length=1)) -> list[dict]:
    return search_entries(q, get_entries())


@app.post("/ask")
def ask(payload: AskRequest) -> dict:
    return answer_question(payload.question, get_entries())


@app.get("/explain/file")
def explain_file_endpoint(path: str = Query(..., min_length=1)) -> dict:
    """Return a natural-language explanation of a specific file."""
    return explain_file(path, get_entries())


@app.get("/explain/project")
def explain_project_endpoint() -> dict:
    """Return a full project explanation with architecture and workflows."""
    entries = get_entries()
    metadata = read_json(METADATA_PATH, {"file_count": 0, "languages": {}, "important_files": []})
    metadata = ensure_insight_metadata(metadata, entries)
    return explain_project(entries, metadata)


@app.get("/explain/function")
def explain_function_endpoint(name: str = Query(..., min_length=1)) -> dict:
    """Return an explanation of a specific function or method."""
    return explain_function(name, get_entries())


@app.get("/explain/class")
def explain_class_endpoint(name: str = Query(..., min_length=1)) -> dict:
    """Return an explanation of a specific class."""
    return explain_class(name, get_entries())
