# src/utils/text_utils.py
"""Utility functions for text manipulation."""

import logging
import re

from bs4 import BeautifulSoup

from src.config import get_config

logger = logging.getLogger(__name__)


def fix_utf8_mojibake(text: str) -> str:
    """
    Attempts to fix UTF-8 mojibake, where text was decoded using a
    single-byte encoding (like latin-1) but was originally UTF-8.
    """
    try:
        # If the text contains characters that are common in mojibake,
        # attempt to fix it. Otherwise, return the original text.
        if any(ord(c) > 127 and ord(c) < 256 for c in text):
            return text.encode("latin1").decode("utf-8")
        return text
    except (UnicodeEncodeError, UnicodeDecodeError):
        # If fixing fails, return the original text
        return text


def clean_vlm_output(text: str) -> str:
    """
    Cleans up noisy or repetitive patterns often found in VLM outputs,
    especially from table transcriptions.
    """
    if not isinstance(text, str):
        return text

    # 1. Remove lines that are just separators like '----' or '....'
    text = re.sub(r"^\s*[-_.]{10,}\s*$", "", text, flags=re.MULTILINE)

    # 2. Remove empty markdown table rows, like '| | |' or '|---|---|'
    # This pattern looks for lines that consist of pipes, hyphens, and spaces only.
    text = re.sub(r"^\s*(\|(\s*|[-=]+))+\s*\|?\s*$", "", text, flags=re.MULTILINE)

    # 3. Remove empty HTML table content
    # This removes empty <td></td> tags, and also empty <tr>...</tr> rows.
    text = re.sub(r"<td>\s*</td>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<tr>\s*</tr>", "", text, flags=re.IGNORECASE)

    # 4. Remove lines containing only whitespace.
    text = re.sub(r"^\s+$", "", text, flags=re.MULTILINE)

    # 5. Collapse excessive newlines that might result from the above operations
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def clean_model_hallucinations(text: str) -> str:
    """
    Removes common model hallucination patterns from text, such as highly
    repetitive sequences of table cells.
    """
    # Pattern 1: Excessive empty table cells. Looks for 10 or more.
    text = re.sub(
        r"(<td>\s*</td>\s*){10,}",
        "<!-- Repetitive empty cells removed -->",
        text,
        flags=re.IGNORECASE,
    )

    # Pattern 2: Highly repetitive table cell content.
    # This looks for a table cell `<td>...</td>` that is repeated 10 or more times.
    # The content inside the cell can be anything that doesn't contain '<' or '>'.
    text = re.sub(
        r"((<td>[^<>]*</td>\s*)\2{9,})",
        "<!-- Repetitive cells removed -->",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    return text


def detect_hallucination_loop(text: str, max_length: int = 100000) -> bool:
    """
    Detects if text contains hallucination patterns indicating infinite loops.

    This catches cases where VLM produces extremely repetitive or excessively long output,
    which can cause the final markdown file to grow to gigabytes.

    Args:
        text: The text to check
        max_length: Maximum allowed length (default 100KB per element)

    Returns:
        True if hallucination pattern detected, False otherwise
    """
    if not text or not isinstance(text, str):
        return False

    # Check 1: Excessive length
    if len(text) > max_length:
        return True

    # Check 2: Repeated word patterns (e.g., "decadecadeca..." or "Kreis OK Kreis OK...")
    # Look for any word/phrase repeated 25+ times consecutively (raised from 15 to reduce false positives)
    repeated_pattern = re.search(r"(\b\w{3,}\b)(?:\s*\1){24,}", text)
    if repeated_pattern:
        return True

    return False


def truncate_hallucinated_content(text: str, max_length: int = 10000) -> str:
    """
    Truncates content that appears to be hallucinated, keeping only the beginning.

    Args:
        text: The text to potentially truncate
        max_length: Maximum allowed length

    Returns:
        Truncated text with a note if truncation occurred
    """
    if not text or len(text) <= max_length:
        return text

    return text[:max_length] + "\n\n[... Content truncated due to excessive length ...]"


def normalize_german_text(text: str) -> str:
    """
    Normalizes a string by converting to lowercase and replacing German
    umlauts and special characters with their ASCII equivalents.

    Args:
        text: The input string.

    Returns:
        The normalized string.
    """
    if not isinstance(text, str):
        return ""

    text = text.lower()
    replacements = {
        "ä": "a",
        "ö": "o",
        "ü": "u",
        "ß": "ss",
        "ae": "a",
        "oe": "o",
        "ue": "u",
    }
    for char, replacement in replacements.items():
        text = text.replace(char, replacement)
    return text


def remove_leading_numbers(text: str) -> str:
    """
    Removes leading numbers, periods, and whitespace from a string.
    e.g., "1.2.3. Some Text" -> "Some Text"
    """
    if not isinstance(text, str):
        return ""
    return re.sub(r"^[0-9.\s]+", "", text).strip()


def normalize_html_for_lookup(html_content: str) -> str:
    """
    Parses and re-serializes HTML to create a consistent representation for lookups.
    This is more robust than simple whitespace stripping.
    """
    if not html_content:
        return ""
    soup = BeautifulSoup(html_content, "html.parser")
    return str(soup)


def _split_oversized_chunk(chunk: str, max_chars: int) -> list[str]:
    """
    Split an oversized chunk into smaller pieces at natural boundaries.
    Tries to split at paragraph boundaries (double newlines), falling back
    to single newlines if paragraphs are too large.
    Args:
        chunk: The chunk content to split
        max_chars: Maximum characters per resulting chunk
    Returns:
        List of smaller chunks
    """
    if len(chunk) <= max_chars:
        return [chunk]
    result = []
    remaining = chunk
    while len(remaining) > max_chars:
        # Find a split point within max_chars limit
        split_point = max_chars
        # Try to find a paragraph boundary (double newline)
        paragraph_boundary = remaining.rfind("\n\n", 0, max_chars)
        if paragraph_boundary > max_chars // 4:  # Only use if not too early
            split_point = paragraph_boundary + 2
        else:
            # Fall back to single newline
            line_boundary = remaining.rfind("\n", 0, max_chars)
            if line_boundary > max_chars // 4:
                split_point = line_boundary + 1
        result.append(remaining[:split_point])
        remaining = remaining[split_point:]
    if remaining:
        result.append(remaining)
    return result


def split_markdown_by_pages(
    markdown_content: str,
    pages_per_chunk: int = 5,
    max_chunk_chars: int = 0,
) -> list[str]:
    """
    Split markdown content into chunks based on <seite nummer="x"/> markers.

    This is a pure function that can be tested independently.

    Args:
        markdown_content: The markdown text to split
        pages_per_chunk: Number of pages to include in each chunk

    Returns:
        List of markdown chunks, each respecting the max_chunk_chars limit
    """
    parts = re.split(r'(<seite\s+nummer\s*=\s*"\d+"\s*/>)', markdown_content)

    chunks = []
    for i in range(1, len(parts), 2):
        marker = parts[i]
        text = parts[i + 1] if i + 1 < len(parts) else ""
        chunks.append(marker + text)

    grouped_chunks = []
    for idx in range(0, len(chunks), pages_per_chunk):
        sub_content = "".join(chunks[idx : idx + pages_per_chunk])
        grouped_chunks.append(sub_content)

    # Use config default if not specified
    if max_chunk_chars <= 0:
        max_chunk_chars = get_config().SUMMARIZATION_CHUNK_MAX_CHARACTERS
    # Safety: Split any oversized chunks
    final_chunks = []
    for chunk in grouped_chunks:
        if len(chunk) > max_chunk_chars:
            logger.warning(f"Chunk exceeds max size ({len(chunk)} > {max_chunk_chars}). Splitting into smaller pieces.")
            final_chunks.extend(_split_oversized_chunk(chunk, max_chunk_chars))
        else:
            final_chunks.append(chunk)
    return final_chunks
