"""
Sub-chunk building utilities for markdown chunking.

Handles the creation of sub-chunks from special elements (images, tables)
and text segments within a parent chunk, including element parsing,
splitting, linking, and merging.
"""

import re
from dataclasses import dataclass
from typing import Any, Literal

from bs4 import BeautifulSoup, Tag
from src.processors.text_splitters import RecursiveCharacterTextSplitter
from temporalio import activity

from src.config import get_config
from src.processors.page_tracker import PAGE_TAG_STRIP_RE
from src.schemas import Chunk, SubChunk

# Type alias for sub-chunk specifications returned by element processors.
# Each tuple is (content, chunk_type, metadata_updates, start_pos).
SubChunkSpec = tuple[str, str, dict[str, Any], int]


@dataclass
class SpecialElement:
    """A parsed special element (BILD, TABELLE, or raw HTML table)."""

    type: Literal["bild", "tabelle", "raw_table"]
    start: int  # position in parent string
    end: int  # end position
    full_text: str  # complete matched text
    img_path: str = ""
    caption: str = ""
    content: str = ""
    description: str = ""
    summary: str = ""
    footnote: str = ""


def find_special_elements(text: str) -> list[SpecialElement]:
    """Find all special elements (BILD, TABELLE, raw table) in text.

    Uses a simple boundary regex to locate elements, then BeautifulSoup
    to extract child tags.
    """
    boundary_pattern = re.compile(
        r'<BILD\s+img_path="[^"]*">.*?</BILD>'
        r'|<TABELLE\s+img_path="[^"]*">.*?</TABELLE>'
        r"|<table\b[^>]*>.*?</table>",
        re.DOTALL | re.IGNORECASE,
    )

    def _child_text(parent_tag: Tag, child_name: str) -> str:
        """Extract direct-child tag's inner text (not recursive to avoid nested matches)."""
        tag = parent_tag.find(child_name, recursive=False)
        return tag.get_text().strip() if tag else ""

    def _child_content(parent_tag: Tag, child_name: str) -> str:
        """Extract direct-child tag's inner HTML (preserves nested markup like <table>)."""
        tag = parent_tag.find(child_name, recursive=False)
        return tag.decode_contents().strip() if tag else ""

    elements: list[SpecialElement] = []
    for match in boundary_pattern.finditer(text):
        full_text = match.group(0)
        soup = BeautifulSoup(full_text, "html.parser")

        bild_tag = soup.find("bild")
        tabelle_tag = soup.find("tabelle")

        if bild_tag:
            elements.append(
                SpecialElement(
                    type="bild",
                    start=match.start(),
                    end=match.end(),
                    full_text=full_text,
                    img_path=str(bild_tag.get("img_path", "")),
                    caption=_child_text(bild_tag, "caption_text"),
                    content=_child_content(bild_tag, "content"),
                    description=_child_text(bild_tag, "description"),
                    summary=_child_text(bild_tag, "summary"),
                    footnote=_child_text(bild_tag, "footnote_text"),
                )
            )
        elif tabelle_tag:
            elements.append(
                SpecialElement(
                    type="tabelle",
                    start=match.start(),
                    end=match.end(),
                    full_text=full_text,
                    img_path=str(tabelle_tag.get("img_path", "")),
                    caption=_child_text(tabelle_tag, "caption_text"),
                    content=_child_content(tabelle_tag, "content"),
                    description=_child_text(tabelle_tag, "description"),
                    summary=_child_text(tabelle_tag, "summary"),
                    footnote=_child_text(tabelle_tag, "footnote_text"),
                )
            )
        else:
            elements.append(
                SpecialElement(
                    type="raw_table",
                    start=match.start(),
                    end=match.end(),
                    full_text=full_text,
                    content=full_text.strip(),
                )
            )

    return elements


def is_table_fragment(content: str) -> bool:
    """Heuristically determines if a content string is a fragment of an HTML table."""
    normalized_content = content.strip().lower()

    if normalized_content.startswith(("<tr", "<td", "<th")):
        return True

    tr_count = normalized_content.count("<tr")
    td_count = normalized_content.count("<td")
    th_count = normalized_content.count("<th")

    if (tr_count + td_count + th_count) >= 2:
        return True

    return False


def process_text_segment(
    text_segment: str,
    text_splitter: RecursiveCharacterTextSplitter,
    start_pos: int,
) -> list[SubChunkSpec]:
    """Process a text segment between special elements into sub-chunk specs."""
    if not text_segment.strip():
        return []

    chunk_type = "table" if is_table_fragment(text_segment) else "text"
    cfg = get_config()
    text_splits = (
        text_splitter.split_text(text_segment) if len(text_segment) > cfg.CHUNKING_MAX_CHARACTERS else [text_segment]
    )
    results: list[SubChunkSpec] = []
    for text_split in text_splits:
        if PAGE_TAG_STRIP_RE.sub("", text_split).strip():
            results.append((text_split, chunk_type, {}, start_pos))
    return results


def process_image_element(
    elem: SpecialElement,
    text_splitter: RecursiveCharacterTextSplitter,
) -> list[SubChunkSpec]:
    """Process a BILD element into sub-chunk specs."""
    caption_tag = f"<caption_text>{elem.caption}</caption_text>\n" if elem.caption else ""
    footnote_tag = f"<footnote_text>{elem.footnote}</footnote_text>\n" if elem.footnote else ""
    page_content = (
        f"{caption_tag}"
        f"<summary>{elem.summary}</summary>\n"
        f"<description>{elem.description}</description>\n"
        f"<content>{elem.content}</content>\n"
        f"{footnote_tag}"
    ).strip()

    base_metadata: dict[str, Any] = {
        "asset_path": elem.img_path,
        "caption": elem.caption,
        "summary": elem.summary,
        "description": elem.description,
        "content": elem.content,
        "footnote": elem.footnote,
    }
    chunk_type = "image"
    cfg = get_config()

    if len(page_content) <= cfg.CHUNKING_MAX_CHARACTERS:
        return [(page_content, chunk_type, base_metadata, elem.start)]

    component_parts: list[tuple[str, str]] = [
        (f"<caption_text>{elem.caption}</caption_text>", elem.caption),
        (f"<summary>{elem.summary}</summary>", elem.summary),
        (f"<description>{elem.description}</description>", elem.description),
        (f"<content>{elem.content}</content>", elem.content),
    ]
    results: list[SubChunkSpec] = []
    for full_text, raw_text in component_parts:
        if not raw_text.strip():
            continue
        text_splits = text_splitter.split_text(full_text)
        for split in text_splits:
            results.append((split, chunk_type, base_metadata, elem.start))
    return results


def _split_table_by_rows(
    content_html: str,
    max_chars: int,
    base_metadata: dict[str, Any],
    chunk_type: str,
    start_pos: int,
) -> list[SubChunkSpec]:
    """Split table HTML content into row-based sub-chunk specs."""
    table_body_match = re.search(
        r"<tbody[^>]*>(.*)</tbody>",
        content_html,
        re.DOTALL | re.IGNORECASE,
    )
    table_inner_html = (
        table_body_match.group(1)
        if table_body_match
        else re.sub(
            r"</?table[^>]*>",
            "",
            content_html,
            flags=re.DOTALL | re.IGNORECASE,
        ).strip()
    )

    soup = BeautifulSoup(table_inner_html, "html.parser")
    rows = [str(row) for row in soup.find_all("tr")]

    if not rows:
        final_table_html = f"<table>\n{table_inner_html}\n</table>"
        return [(final_table_html, chunk_type, base_metadata.copy(), start_pos)]

    results: list[SubChunkSpec] = []
    current_split_content = ""
    for row in rows:
        if current_split_content and len(current_split_content) + len(row) > max_chars:
            final_table_html = f"<table>\n{current_split_content}\n</table>"
            results.append((final_table_html, chunk_type, base_metadata.copy(), start_pos))
            current_split_content = row
        else:
            current_split_content += f"\n{row}"

    if current_split_content:
        final_table_html = f"<table>\n{current_split_content.strip()}\n</table>"
        results.append((final_table_html, chunk_type, base_metadata.copy(), start_pos))

    return results


def process_table_element(
    elem: SpecialElement,
    text_splitter: RecursiveCharacterTextSplitter,
) -> list[SubChunkSpec]:
    """Process a TABELLE or raw table element into sub-chunk specs."""
    cfg = get_config()
    chunk_type = "table"
    is_tabelle = elem.type == "tabelle"

    if is_tabelle:
        base_metadata: dict[str, Any] = {
            "asset_path": elem.img_path,
            "caption": elem.caption,
            "summary": elem.summary,
            "description": elem.description,
            "content": elem.content,
            "footnote": elem.footnote,
        }
        content_to_split = elem.content
    else:  # raw_table
        base_metadata = {"content": elem.content}
        content_to_split = elem.content

    if len(elem.full_text) <= cfg.CHUNKING_MAX_CHARACTERS:
        return [(elem.full_text, chunk_type, base_metadata, elem.start)]

    activity.logger.info(f"Large table found (length: {len(elem.full_text)}). Splitting by components.")

    results: list[SubChunkSpec] = []

    if is_tabelle:
        semantic_parts: list[tuple[str, str]] = [
            (f"<summary>{elem.summary}</summary>", elem.summary),
            (f"<description>{elem.description}</description>", elem.description),
        ]
        if elem.caption:
            semantic_parts.insert(
                0,
                (f"<caption_text>{elem.caption}</caption_text>", elem.caption),
            )

        for full_text, raw_text in semantic_parts:
            if not raw_text.strip():
                continue
            text_splits = text_splitter.split_text(full_text)
            for split in text_splits:
                results.append((split, chunk_type, base_metadata.copy(), elem.start))

    results.extend(
        _split_table_by_rows(
            content_to_split,
            cfg.CHUNKING_MAX_CHARACTERS,
            base_metadata,
            chunk_type,
            elem.start,
        )
    )

    return results


def _add_bidirectional_link(
    text_chunk: SubChunk,
    special_chunk: SubChunk,
    special_type: str,
) -> None:
    """Add bidirectional related_assets / related_text links between chunks."""
    text_chunk.metadata.setdefault("related_assets", []).append(
        {"chunk_id": special_chunk.chunk_id, "type": special_type}
    )
    special_chunk.metadata.setdefault("related_text", []).append({"chunk_id": text_chunk.chunk_id, "type": "text"})


def link_related_chunks(sub_chunks_with_type: list[dict[str, Any]]) -> None:
    """Link text chunks to adjacent special (image/table) chunks bidirectionally."""
    for i, item in enumerate(sub_chunks_with_type):
        if item["type"] != "text":
            continue
        text_chunk = item["chunk"]

        if i > 0 and sub_chunks_with_type[i - 1]["type"] != "text":
            prev = sub_chunks_with_type[i - 1]
            _add_bidirectional_link(text_chunk, prev["chunk"], prev["type"])

        if i < len(sub_chunks_with_type) - 1 and sub_chunks_with_type[i + 1]["type"] != "text":
            nxt = sub_chunks_with_type[i + 1]
            _add_bidirectional_link(text_chunk, nxt["chunk"], nxt["type"])


def merge_header_only_sub_chunks(
    final_sub_chunks: list[SubChunk],
    main_chunk: Chunk,
) -> list[SubChunk]:
    """Merge header-only sub-chunks with the following chunk."""
    raw_header = None
    for h_level in range(3, 0, -1):
        header_key = f"Header {h_level}"
        if header_key in main_chunk.metadata:
            raw_header = main_chunk.metadata[header_key]
            break

    merged_sub_chunks: list[SubChunk] = []
    i = 0
    while i < len(final_sub_chunks):
        current_sub_chunk = final_sub_chunks[i]

        is_header_only = (
            current_sub_chunk.metadata.get("chunk_type") == "text"
            and raw_header is not None
            and re.sub(r"#+\s*", "", current_sub_chunk.page_content).strip() == raw_header.strip()
        )

        if is_header_only and i + 1 < len(final_sub_chunks):
            next_sub_chunk = final_sub_chunks[i + 1]
            next_sub_chunk.page_content = f"{current_sub_chunk.page_content}\n\n{next_sub_chunk.page_content}"
            i += 1
            continue

        merged_sub_chunks.append(current_sub_chunk)
        i += 1

    return merged_sub_chunks
