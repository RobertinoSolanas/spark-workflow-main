"""
Page number tracking utilities for markdown chunking.

Extracted from MarkdownChunker to improve separation of concerns.
"""

import re
from typing import Any

from src.schemas import SubChunk

PAGE_TAG_RE = re.compile(r'<seite nummer="(\d+)"\s*/>')
PAGE_TAG_STRIP_RE = re.compile(r'<seite nummer="\d+"\s*/>')


def extract_page_numbers(text: str) -> list[int]:
    """Extracts all page numbers from a given text."""
    return [int(num) for num in PAGE_TAG_RE.findall(text)]


def build_page_map(content: str, doc_wide_last_known_page: int) -> tuple[dict[int, int], int, int]:
    """
    Builds a page map from page tags in content.

    Returns:
        Tuple of (page_map, chunk_starts_on_page, updated_last_known_page)
    """
    page_map: dict[int, int] = {}
    first_page_tag_pos = -1

    for match in PAGE_TAG_RE.finditer(content):
        pos = match.start()
        num = int(match.group(1))
        if first_page_tag_pos == -1:
            first_page_tag_pos = pos
        page_map[pos] = num

    # Determine starting page
    content_before_first_tag = content[:first_page_tag_pos] if first_page_tag_pos != -1 else content

    if first_page_tag_pos == 0 or not re.sub(r"\s|__SPECIAL_ELEMENT_PLACEHOLDER_\d+__", "", content_before_first_tag):
        chunk_starts_on_page = page_map.get(first_page_tag_pos, doc_wide_last_known_page)
    else:
        chunk_starts_on_page = doc_wide_last_known_page

    page_map[0] = chunk_starts_on_page

    all_pages = list(page_map.values())
    updated_last_known_page = max(all_pages) if all_pages else doc_wide_last_known_page

    return page_map, chunk_starts_on_page, updated_last_known_page


def assign_page_numbers(
    sub_chunks_with_type: list[dict[str, Any]],
    page_map: dict[int, int],
    sorted_page_positions: list[int],
    chunk_starts_on_page: int,
) -> list[SubChunk]:
    """Assign page numbers to each sub-chunk based on its position in the parent chunk."""
    final_sub_chunks: list[SubChunk] = []
    for item in sub_chunks_with_type:
        sub_chunk = item["chunk"]
        start_pos = item["start_pos"]

        current_page = chunk_starts_on_page
        for pos in sorted_page_positions:
            if start_pos >= pos:
                current_page = page_map[pos]
            else:
                break

        sub_page_numbers = extract_page_numbers(sub_chunk.page_content)

        all_pages = sorted(set([current_page] + sub_page_numbers))
        sub_chunk.metadata["page_numbers"] = all_pages

        final_sub_chunks.append(sub_chunk)

    return final_sub_chunks
