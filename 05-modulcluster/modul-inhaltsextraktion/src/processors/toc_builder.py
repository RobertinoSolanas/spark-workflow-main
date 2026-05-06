"""
Table of Contents (ToC) building and resolution utilities for markdown chunking.

Extracted from MarkdownChunker to improve separation of concerns.
"""

import re
from typing import Any, cast

from src.providers.base import ContentItemDict, ContentItemText
from src.schemas import Chunk


def get_header_level_and_title(
    metadata: dict[str, Any],
) -> tuple[int, str] | None:
    """
    Determines the hierarchical level of a header based on its numbering.
    e.g., "1.2.3" is level 3.
    """
    # Find the most specific header available
    for i in range(3, 0, -1):
        header_key = f"Header {i}"
        if header_key in metadata:
            title = metadata[header_key]
            # Find the numeric prefix like "1.2.3."
            match = re.match(r"^([\d\.]+)", title)
            if match:
                prefix = match.group(1).strip(".")
                level = prefix.count(".") + 1
                return level, title
            # Fallback for non-numbered headers (e.g., "Introduction")
            return 1, title
    return None


def get_clean_header(metadata: dict[str, Any]) -> str | None:
    """
    Extracts the most specific header from metadata and removes leading numbers and whitespace.
    e.g., {"Header 2": "1.3.6 Title"} -> "Title"
    """
    for i in range(3, 0, -1):
        header_key = f"Header {i}"
        if header_key in metadata:
            header_value = metadata[header_key]
            # Remove leading numbers, periods, and whitespace
            return re.sub(r"^[0-9.\s]+", "", header_value).strip()
    return None


def build_toc_from_content_list(
    content_list: list[ContentItemDict],
) -> tuple[dict[str, list[str]], dict[str, str]]:
    """
    Builds a Table of Contents from the structured content_list.
    Returns a tuple containing:
    1. A ToC dictionary mapping each parent header to its direct child headers.
    2. A parent_map dictionary mapping each child header to its parent.
    """
    toc: dict[str, list[str]] = {"_DOCUMENT_ROOT_": []}
    parent_map: dict[str, str] = {}
    lineage: list[dict[str, str]] = []  # Stores the current path of headers with their numbering

    # Filter for true, numbered headers
    headers: list[dict[str, str]] = []
    for item in content_list:
        if item.get("type") == "text":
            text_item = cast(ContentItemText, item)
            if text_item.get("text_level") != 1:
                continue
            text_val = text_item.get("text")
            if not text_val:
                continue
            text = str(text_val).strip()
            # A header must start with a number (e.g., "1", "1.2", "1.2.3")
            match = re.match(r"^([\d\.]+)\s+(.*)", text)
            if match:
                headers.append({"numbering": match.group(1).strip("."), "title": text})

    for header in headers:
        numbering, title = header["numbering"], header["title"]
        level = len(numbering.split("."))

        while lineage and len(lineage[-1]["numbering"].split(".")) >= level:
            lineage.pop()

        parent_title = lineage[-1]["title"] if lineage else "_DOCUMENT_ROOT_"

        if parent_title not in toc:
            toc[parent_title] = []
        if title not in toc[parent_title]:
            toc[parent_title].append(title)

        parent_map[title] = parent_title
        lineage.append(header)
        if title not in toc:
            toc[title] = []

    return toc, parent_map


def get_all_descendants(header_title: str, toc: dict[str, list[str]]) -> list[str]:
    """Recursively finds all descendant headers for a given header title."""
    descendants: list[str] = []
    children = toc.get(header_title, [])
    for child in children:
        descendants.append(child)
        descendants.extend(get_all_descendants(child, toc))
    return descendants


def resolve_toc_path(
    main_chunk: Chunk,
    all_valid_headers: list[str],
    toc: dict[str, list[str]],
    parent_map: dict[str, str],
    last_valid_path: list[str],
    last_valid_unterkapitel: list[str],
) -> tuple[list[str], list[str]]:
    """Resolve the ToC path and subchapter list for a chunk.

    Returns:
        Tuple of (updated_last_valid_path, updated_last_valid_unterkapitel)
    """
    last_header_in_chunk = None
    for header_title in all_valid_headers:
        # Match header only at line boundaries (with optional # prefix) to avoid
        # false matches against body text containing the header string.
        pattern = rf"^(?:#+\s*)?{re.escape(header_title)}\s*$"
        if re.search(pattern, main_chunk.page_content, re.MULTILINE):
            last_header_in_chunk = header_title

    path: list[str] = []
    if last_header_in_chunk:
        current: str | None = last_header_in_chunk
        while current and current != "_DOCUMENT_ROOT_":
            path.append(current)
            current = parent_map.get(current)
        path.reverse()

    if path:
        main_chunk.metadata["toc_path"] = path
        top_level_parent = path[0]
        main_chunk.metadata["all_subchapters"] = [top_level_parent] + get_all_descendants(top_level_parent, toc)
        return main_chunk.metadata["toc_path"], main_chunk.metadata["all_subchapters"]
    else:
        main_chunk.metadata["toc_path"] = last_valid_path
        main_chunk.metadata["all_subchapters"] = last_valid_unterkapitel
        return last_valid_path, last_valid_unterkapitel
