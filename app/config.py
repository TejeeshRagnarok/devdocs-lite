from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = BASE_DIR / "uploads"
PROJECTS_DIR = BASE_DIR / "projects"
CURRENT_PROJECT_DIR = PROJECTS_DIR / "current"

FILES_INDEX_PATH = DATA_DIR / "files.json"
METADATA_PATH = DATA_DIR / "metadata.json"
PARSED_METADATA_PATH = DATA_DIR / "parsed.json"

MAX_UPLOAD_SIZE = 50 * 1024 * 1024
MAX_TEXT_BYTES = 250_000
MAX_PREVIEW_CHARS = 80_000
MAX_SEARCH_RESULTS = 12

DEFAULT_CHUNK_SIZE = 1000
DEFAULT_CHUNK_OVERLAP = 200

EMBEDDING_PROVIDER = "jina"
EMBEDDING_MODEL = "jina-embeddings-v2-base-en"
EMBEDDING_BATCH_SIZE = 64
EMBEDDING_TIMEOUT = 30
EMBEDDING_MAX_RETRIES = 3

FAISS_INDEX_PATH = DATA_DIR / "vector_store.faiss"
FAISS_METADATA_PATH = DATA_DIR / "vector_store_meta.json"
DEFAULT_TOP_K = 5

CHUNKS_METADATA_PATH = DATA_DIR / "chunks.json"
DEFAULT_RETRIEVAL_TOP_K = 5
DEFAULT_MIN_SCORE = 0.7

LLM_PROVIDER = "groq"
LLM_MODEL = "llama-3.1-8b-instant"
LLM_TIMEOUT = 30
LLM_MAX_RETRIES = 3
MAX_CONTEXT_LENGTH = 15000  # max characters to feed into the prompt

IGNORED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".next",
    ".nuxt",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "__pycache__",
    "dist",
    "build",
    "coverage",
    "target",
}

IGNORED_FILE_SUFFIXES = {
    ".7z",
    ".bmp",
    ".class",
    ".dll",
    ".exe",
    ".gif",
    ".ico",
    ".jar",
    ".jpeg",
    ".jpg",
    ".lock",
    ".mp3",
    ".mp4",
    ".pdf",
    ".png",
    ".pyc",
    ".so",
    ".sqlite",
    ".webp",
    ".zip",
}
