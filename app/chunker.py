"""Text chunking module for splitting extracted document text into overlapping chunks.

This module implements a paragraph-aware, code-block-preserving chunking
algorithm. It sits between document ingestion (which produces raw text) and
any downstream processing layer.

Public API
----------
- ``clean_text(text)`` — normalise whitespace while keeping structure.
- ``chunk_text(text, chunk_size, overlap)`` — split into ordered, overlapping chunks.
"""

from __future__ import annotations

import re

from .config import DEFAULT_CHUNK_OVERLAP, DEFAULT_CHUNK_SIZE


# ---------------------------------------------------------------------------
# Text cleaning
# ---------------------------------------------------------------------------

def clean_text(text: str) -> str:
    """Normalise whitespace in *text* while preserving paragraph structure.

    * Strips trailing whitespace from every line.
    * Collapses runs of 3+ blank lines into exactly 2 newlines (one blank line).
    * Strips leading/trailing whitespace from the whole document.
    """
    # Strip trailing spaces per line
    text = re.sub(r"[ \t]+$", "", text, flags=re.MULTILINE)
    # Collapse 3+ consecutive newlines → 2 (keeps paragraph boundaries)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Block splitting (paragraph + code-block aware)
# ---------------------------------------------------------------------------

_FENCE_RE = re.compile(r"^(`{3,}|~{3,})", re.MULTILINE)


def _split_into_blocks(text: str) -> list[str]:
    """Split *text* into semantic blocks.

    * Fenced code blocks (``` or ~~~) are kept as single atomic blocks, even
      if they contain blank lines internally.
    * Everything outside a code block is split on paragraph boundaries
      (double-newline).
    """
    blocks: list[str] = []
    pos = 0

    for match in _FENCE_RE.finditer(text):
        fence_start = match.start()
        fence_marker = match.group(1)
        fence_char = fence_marker[0]
        fence_len = len(fence_marker)

        # Only process if this fence starts a new code block (not already
        # inside one that we've consumed).
        if fence_start < pos:
            continue

        # Flush any text before this fence as paragraph blocks.
        if fence_start > pos:
            pre_text = text[pos:fence_start]
            blocks.extend(_paragraph_split(pre_text))

        # Find the closing fence (same char, same or greater length).
        closing_pattern = re.compile(
            r"^" + re.escape(fence_char) + r"{" + str(fence_len) + r",}\s*$",
            re.MULTILINE,
        )
        close_match = closing_pattern.search(text, match.end())

        if close_match:
            # Include everything from opening fence through closing fence.
            code_block = text[fence_start : close_match.end()]
            blocks.append(code_block.strip())
            pos = close_match.end()
        else:
            # Unclosed fence — treat rest of text as a single code block.
            code_block = text[fence_start:]
            blocks.append(code_block.strip())
            pos = len(text)
            break

    # Flush remaining text after the last code block.
    if pos < len(text):
        blocks.extend(_paragraph_split(text[pos:]))

    # If there were no fences at all, we never entered the loop.
    if not blocks and text:
        blocks = _paragraph_split(text)

    return [b for b in blocks if b]


def _paragraph_split(text: str) -> list[str]:
    """Split *text* on double-newline boundaries and strip each part."""
    return [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]


# ---------------------------------------------------------------------------
# Oversized-block splitting (word-boundary safe)
# ---------------------------------------------------------------------------

def _split_oversized_block(block: str, max_size: int) -> list[str]:
    """Split a single block that exceeds *max_size* on word boundaries.

    Falls back to hard character slicing only if there are no spaces at all
    (e.g. a very long URL or base64 blob).
    """
    pieces: list[str] = []
    remaining = block

    while len(remaining) > max_size:
        # Find the last space within the allowed window.
        split_at = remaining.rfind(" ", 0, max_size)
        if split_at <= 0:
            # No space found — hard split.
            split_at = max_size
        pieces.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip()

    if remaining:
        pieces.append(remaining)

    return pieces


# ---------------------------------------------------------------------------
# Main chunking logic
# ---------------------------------------------------------------------------

def chunk_text(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[dict]:
    """Split *text* into overlapping chunks of roughly *chunk_size* characters.

    Parameters
    ----------
    text:
        The cleaned document text to chunk.
    chunk_size:
        Target maximum characters per chunk (default from config).
    overlap:
        Number of trailing characters from the previous chunk to prepend to
        the next chunk (default from config).

    Returns
    -------
    list[dict]
        Ordered list of ``{"chunk_id", "text", "start_char", "end_char"}``.
        ``start_char`` and ``end_char`` are character offsets into the
        *cleaned* text.
    """
    cleaned = clean_text(text)

    if not cleaned:
        return []

    # Expand every block; split oversized ones.
    raw_blocks = _split_into_blocks(cleaned)
    blocks: list[str] = []
    for block in raw_blocks:
        if len(block) > chunk_size:
            blocks.extend(_split_oversized_block(block, chunk_size))
        else:
            blocks.append(block)

    if not blocks:
        return []

    # --- greedy accumulation with overlap --------------------------------
    chunks: list[str] = []
    current_parts: list[str] = []
    current_len = 0

    for block in blocks:
        addition = len(block) + (2 if current_parts else 0)  # "\n\n" joiner

        if current_parts and current_len + addition > chunk_size:
            # Emit the current chunk.
            chunks.append("\n\n".join(current_parts))

            # Build overlap seed from the tail of the emitted chunk.
            emitted = chunks[-1]
            if overlap > 0 and len(emitted) > overlap:
                overlap_seed = emitted[-overlap:]
                # Trim to the nearest word boundary at the start.
                first_space = overlap_seed.find(" ")
                if first_space != -1 and first_space < len(overlap_seed) - 1:
                    overlap_seed = overlap_seed[first_space + 1:]
                current_parts = [overlap_seed]
                current_len = len(overlap_seed)
            elif overlap > 0:
                current_parts = [emitted]
                current_len = len(emitted)
            else:
                current_parts = []
                current_len = 0

        if current_parts and current_len > 0 and current_parts[-1] != block:
            current_parts.append(block)
            current_len += 2 + len(block)
        elif not current_parts:
            current_parts.append(block)
            current_len = len(block)
        else:
            # Block is the overlap seed itself — already counted.
            pass

    # Emit the final chunk.
    if current_parts:
        chunks.append("\n\n".join(current_parts))

    # --- map chunks back to character offsets in the cleaned text ----------
    import random
    results: list[dict] = []
    search_from = 0
    for chunk_text_content in chunks:
        # Generate a perfectly unique 63-bit integer ID for the vector store
        chunk_id = random.getrandbits(63)

        start = cleaned.find(chunk_text_content[:80], search_from)
        if start == -1:
            # Overlap-seeded chunks may not appear verbatim; use sequential.
            start = search_from
        end = start + len(chunk_text_content)
        results.append({
            "chunk_id": chunk_id,
            "text": chunk_text_content,
            "start_char": start,
            "end_char": end,
        })
        # Allow overlapping offsets but advance at least a little.
        search_from = start + 1 if overlap > 0 else end

    return results
