# src/processors/enhancer.py
"""
Handles non-LLM based markdown enhancement tasks.
"""

import re
from typing import cast

from temporalio import activity

from src.providers.base import ContentItemDict, ContentItemImage, ContentItemTable, ContentItemText
from src.utils.text_utils import fix_utf8_mojibake


class MarkdownEnhancer:
    """
    A class for enhancing markdown files, e.g. like inserting page numbers.
    """

    @staticmethod
    def replace_latex_symbols(markdown_content: str) -> str:
        """Replaces common LaTeX symbols with their unicode equivalents in a string."""
        try:
            original_content = markdown_content
            # Rule for paragraph symbol: $\S$ -> §
            content = re.sub(r"\$\\S\$", "§", markdown_content)
            # Rule for degree symbol: $...^{\circ}...$ -> ...°...
            content = re.sub(r"\$([^\$]*)\^\{[c]irc\}([^\$]*)\$", r"\1°\2", content)

            if original_content != content:
                activity.logger.info("Replaced LaTeX symbols in markdown content.")
            return content
        except Exception as e:
            activity.logger.error(f"Error replacing LaTeX symbols: {e}")
            return markdown_content

    @staticmethod
    def _normalize_img_path(img_path: str) -> str:
        """Strips leading 'images/' prefix so callers get a bare filename."""
        path = img_path.strip()
        if path.startswith("images/"):
            path = path[len("images/") :]
        return path

    @staticmethod
    def _build_anchor_pattern(item: ContentItemDict) -> str | None:
        """Builds a regex pattern that can locate *item* inside the markdown.

        Returns ``None`` when no usable pattern can be constructed (e.g. the
        item is discarded or has no text / path).
        """
        item_type = str(item.get("type", ""))

        if item_type in ("text", "title"):
            text_item = cast(ContentItemText, item)
            text = fix_utf8_mojibake(str(text_item.get("text", "")).strip())
            if not text:
                return None
            words = re.split(r"\s+", text)
            if not words:
                return None
            return r"\s+".join(re.escape(w) for w in words)

        if item_type == "image":
            img_item = cast(ContentItemImage, item)
            raw = str(img_item.get("img_path", "")).strip()
            if not raw:
                return None
            bare = MarkdownEnhancer._normalize_img_path(raw)
            escaped = re.escape(f"images/{bare}")
            # Match any alt-text: ![...](images/file.jpg)
            return r"!\[.*?\]\(" + escaped + r"\)"

        if item_type == "table":
            table_item = cast(ContentItemTable, item)
            table_html = str(table_item.get("table_body", ""))
            if table_html:
                snippet = table_html.strip()[:150]
                words = re.split(r"\s+", snippet)
                if words:
                    return r"\s+".join(re.escape(w) for w in words)
            # Fallback: table rendered as image
            raw = str(table_item.get("img_path", "")).strip()
            if raw:
                bare = MarkdownEnhancer._normalize_img_path(raw)
                escaped = re.escape(f"images/{bare}")
                return r"!\[.*?\]\(" + escaped + r"\)"

        # equation – use img_path like image
        if item_type == "equation":
            img_item = cast(ContentItemImage, item)
            raw = str(img_item.get("img_path", "")).strip()
            if not raw:
                return None
            bare = MarkdownEnhancer._normalize_img_path(raw)
            escaped = re.escape(f"images/{bare}")
            return r"!\[.*?\]\(" + escaped + r"\)"

        return None

    @staticmethod
    def insert_page_numbers(
        markdown_content: str,
        content_list: list[ContentItemDict],
    ) -> str:
        """
        Inserts page numbers into a markdown string based on a content list.

        Algorithm
        ---------
        1. Walk every item in *content_list* (document order).
        2. For each item build a regex pattern and search forward from a
           monotonically advancing *search_offset*.
        3. Record the position of the **first** matched item per page.
        4. After all items are processed, insert ``<seite …/>`` tags in
           **reverse** page order so that earlier positions stay valid.
        5. Ensure page 1 is present exactly once at the start.
        """
        if not content_list:
            activity.logger.warning("Content list is empty. Skipping page number insertion.")
            return markdown_content

        # --- pass 1: locate first anchor position per page ----------------
        search_offset = 0
        page_first_pos: dict[int, int] = {}  # page_idx -> char position

        for item in content_list:
            page_idx = item["page_idx"]
            pattern = MarkdownEnhancer._build_anchor_pattern(item)
            if pattern is None:
                continue

            try:
                match = re.search(pattern, markdown_content[search_offset:])
            except re.error as exc:
                activity.logger.error(f"Invalid regex for page {page_idx + 1}: {exc}")
                continue

            if match is None:
                continue

            abs_pos = match.start() + search_offset

            # Only record the first hit per page
            if page_idx not in page_first_pos:
                page_first_pos[page_idx] = abs_pos

            # Advance offset so subsequent items search further forward
            search_offset = abs_pos + match.end() - match.start()

        # --- pass 2: insert tags in reverse order -------------------------
        modified_content = markdown_content

        # Collect all page indices present in content_list
        all_page_indices = sorted({item["page_idx"] for item in content_list})

        # Warn for pages (other than 0) with zero matched items
        for page_idx in all_page_indices:
            if page_idx != 0 and page_idx not in page_first_pos:
                activity.logger.warning(f"Could not find anchor to insert page number {page_idx + 1}.")

        # Insert in reverse so positions stay valid
        for page_idx in sorted(page_first_pos.keys(), reverse=True):
            if page_idx == 0:
                # Page 1 is handled below (always prepended)
                continue
            position = page_first_pos[page_idx]

            # If the anchor falls on a heading line, move to the line start
            line_start = modified_content.rfind("\n", 0, position) + 1
            if modified_content[line_start:].lstrip().startswith("#"):
                position = line_start

            page_tag = f'<seite nummer="{page_idx + 1}" />\n\n'
            modified_content = f"{modified_content[:position]}{page_tag}{modified_content[position:]}"

        # Always prepend page 1 exactly once
        page_one_tag = '<seite nummer="1" />\n\n'
        modified_content = f"{page_one_tag}{modified_content}"

        activity.logger.info("Successfully inserted page numbers into markdown content.")
        return modified_content
