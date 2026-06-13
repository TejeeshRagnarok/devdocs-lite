from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = BASE_DIR / "uploads"
PROJECTS_DIR = BASE_DIR / "projects"
CURRENT_PROJECT_DIR = PROJECTS_DIR / "current"

FILES_INDEX_PATH = DATA_DIR / "files.json"
METADATA_PATH = DATA_DIR / "metadata.json"

MAX_UPLOAD_SIZE = 50 * 1024 * 1024
MAX_TEXT_BYTES = 250_000
MAX_PREVIEW_CHARS = 80_000
MAX_SEARCH_RESULTS = 12

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
