"""Document processing layer for text extraction from PDF, TXT, and DOCX files.

This module provides a clean separation between route handlers and extraction
logic. Each supported format has its own extraction function, and the
``process_document`` dispatcher routes by file extension, returning a
consistent result dict.
"""

from __future__ import annotations

import io
import logging
from pathlib import PurePosixPath

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS: dict[str, str] = {
    ".pdf": "pdf",
    ".txt": "txt",
    ".docx": "docx",
}


# ---------------------------------------------------------------------------
# Individual extractors
# ---------------------------------------------------------------------------

def extract_pdf(data: bytes) -> str:
    """Extract text from PDF bytes using PyPDF2.

    Handles encrypted PDFs and corrupted files gracefully by raising
    ``ValueError`` with a human-readable message.
    """
    import PyPDF2  # lazy import — only loaded when needed

    try:
        reader = PyPDF2.PdfReader(io.BytesIO(data))
    except Exception as exc:
        raise ValueError(f"Failed to read PDF: {exc}") from exc

    if reader.is_encrypted:
        try:
            # Attempt to decrypt with an empty password (common default).
            if not reader.decrypt(""):
                raise ValueError("PDF is encrypted or unreadable")
        except Exception:
            raise ValueError("PDF is encrypted or unreadable")

    pages: list[str] = []
    for page_num, page in enumerate(reader.pages):
        try:
            text = page.extract_text()
            if text:
                pages.append(text)
        except Exception as exc:
            logger.warning("Skipping PDF page %d: %s", page_num, exc)

    return "\n".join(pages)


def extract_txt(data: bytes) -> str:
    """Decode a plain-text file, falling back from UTF-8 to Latin-1.

    Raises ``ValueError`` only if both decodings fail (extremely unlikely for
    Latin-1, but handled for safety).
    """
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass

    try:
        return data.decode("latin-1")
    except UnicodeDecodeError as exc:
        raise ValueError(f"Unable to decode text file: {exc}") from exc


def extract_docx(data: bytes) -> str:
    """Extract paragraph text from a DOCX file using python-docx.

    Raises ``ValueError`` for corrupted or invalid DOCX archives.
    """
    import docx  # lazy import

    try:
        document = docx.Document(io.BytesIO(data))
    except Exception as exc:
        raise ValueError(f"Failed to read DOCX: {exc}") from exc

    paragraphs = [p.text for p in document.paragraphs if p.text]
    return "\n".join(paragraphs)


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

_EXTRACTORS = {
    "pdf": extract_pdf,
    "txt": extract_txt,
    "docx": extract_docx,
}


def process_document(filename: str, data: bytes) -> dict:
    """Process a single uploaded document and return a result dict.

    Returns
    -------
    dict
        Always contains ``filename``, ``text``, ``status``, and ``error``.
        ``status`` is ``"success"`` or ``"error"``.
    """
    ext = PurePosixPath(filename).suffix.lower()

    # --- unsupported type ---------------------------------------------------
    if ext not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS.keys()))
        return {
            "filename": filename,
            "text": "",
            "status": "error",
            "error": f"Unsupported file type: {ext or '(none)'}. Supported: {supported}",
        }

    # --- empty document -----------------------------------------------------
    if len(data) == 0:
        return {
            "filename": filename,
            "text": "",
            "status": "error",
            "error": "Document is empty (0 bytes)",
        }

    # --- extract ------------------------------------------------------------
    extractor = _EXTRACTORS[SUPPORTED_EXTENSIONS[ext]]
    try:
        text = extractor(data)
    except ValueError as exc:
        return {
            "filename": filename,
            "text": "",
            "status": "error",
            "error": str(exc),
        }
    except Exception as exc:
        logger.exception("Unexpected error processing %s", filename)
        return {
            "filename": filename,
            "text": "",
            "status": "error",
            "error": f"Unexpected error: {exc}",
        }

    return {
        "filename": filename,
        "text": text,
        "status": "success",
        "error": None,
    }
