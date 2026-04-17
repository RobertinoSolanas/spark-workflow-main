"""Markdown generation from docling JSON structure."""

import logging
from dataclasses import dataclass, field
from typing import Any

from src.providers.docling.transforms import resolve_json_ref

logger = logging.getLogger(__name__)


@dataclass
class FurnitureRefs:
    """
    Container for element references that should be filtered as furniture (headers/footers).

    Used by MarkdownBuilder to skip recurring header/footer elements.
    """

    # Text refs that have picture parents (OCR'd text from images)
    texts_with_picture_parent: set[str] = field(default_factory=set)
    # Table refs that are in furniture regions or contain furniture content
    furniture_table_refs: set[str] = field(default_factory=set)
    # Picture refs that are in header/footer regions (except first occurrence)
    furniture_picture_refs: set[str] = field(default_factory=set)
    # Text refs that are in header/footer regions by position
    furniture_text_refs_by_position: set[str] = field(default_factory=set)
    # Text content marked as furniture (for content-based table matching)
    furniture_texts: set[str] = field(default_factory=set)
    # Labels that indicate furniture elements
    furniture_labels: set[str] = field(
        default_factory=lambda: {
            "page_footer",
            "page_header",
            "page-footer",
            "page-header",
        }
    )


class FurnitureDetector:
    """Detects header/footer elements for filtering."""

    @staticmethod
    def detect(doc_json: dict[str, Any]) -> FurnitureRefs:
        """
        Detect header/footer elements that should be filtered from the output.

        Uses label-based and content-based strategies only (no position-based filtering).
        Position-based filtering was removed because it incorrectly filtered content
        that starts at the top of the page (e.g., full-page images, large tables).

        Filtering strategies:
        1. Label-based: Elements marked as furniture by Docling (content_layer or label)
        2. Content-based: Tables containing >50% furniture text in cells
        3. Parent-based: Text OCR'd from within pictures (children of picture elements)

        Note: Position-based recurring element detection is handled separately by
        filter.py using perceptual hashing and other techniques.

        Args:
            doc_json: Document JSON from doc.export_to_dict()

        Returns:
            FurnitureRefs containing sets of refs to filter
        """
        refs = FurnitureRefs()

        # --- Step 1: Find texts with picture parents (OCR'd text from images) ---
        # These are text elements extracted via OCR from within pictures.
        # We skip them because the picture itself will be processed by VLM.
        for txt in doc_json.get("texts", []):
            parent = txt.get("parent", {})
            parent_ref = parent.get("$ref", "") if isinstance(parent, dict) else ""
            if "/pictures/" in parent_ref:
                self_ref = txt.get("self_ref", "")
                refs.texts_with_picture_parent.add(self_ref)
                logger.debug(f"Text {self_ref} has picture parent {parent_ref}, will be skipped")

        if refs.texts_with_picture_parent:
            logger.info(
                f"Found {len(refs.texts_with_picture_parent)} text elements with picture parents (will be skipped)"
            )

        # --- Step 2: Collect furniture text content for content-based matching ---
        # Identify text marked as furniture by Docling's classification
        for txt in doc_json.get("texts", []):
            content_layer = txt.get("content_layer", "").lower()
            label = txt.get("label", "").lower()
            if content_layer == "furniture" or label in refs.furniture_labels:
                text = txt.get("text", "").strip()
                if text:
                    refs.furniture_texts.add(text)

        if refs.furniture_texts:
            logger.debug(f"Collected {len(refs.furniture_texts)} furniture text snippets")

        # --- Step 3: Detect furniture tables (content-based only) ---
        # Tables where >50% of cells contain text matching known furniture content
        for tbl in doc_json.get("tables", []):
            table_ref = tbl.get("self_ref", "")
            table_data = tbl.get("data", {})
            table_cells = table_data.get("table_cells", [])

            # Content-based matching: filter if >50% cells match furniture text
            if not table_cells or not refs.furniture_texts:
                continue
            cell_texts = [cell.get("text", "").strip() for cell in table_cells if cell.get("text", "").strip()]
            if not cell_texts:
                continue
            matching_cells = sum(1 for ct in cell_texts if any(ct in ft for ft in refs.furniture_texts))
            match_ratio = matching_cells / len(cell_texts)
            if match_ratio > 0.5:
                refs.furniture_table_refs.add(table_ref)
                logger.debug(f"Table {table_ref} has {match_ratio:.0%} cells matching furniture content")

        if refs.furniture_table_refs:
            logger.info(f"Found {len(refs.furniture_table_refs)} tables with furniture content (will be skipped)")

        # Note: Position-based filtering for pictures and text was removed.
        # It incorrectly filtered full-page images and tables that start at the top.
        # Recurring header/footer detection is handled by filter.py instead.

        return refs


class MarkdownBuilder:
    """Builds custom markdown from docling JSON structure."""

    @staticmethod
    def build(  # noqa: C901
        doc_json: dict[str, Any],
        images_meta: list[dict[str, Any]],
        tables_meta: list[dict[str, Any]],
    ) -> str:
        """
        Build custom markdown from docling JSON structure.

        Walks the document body in reading order and outputs:
        - Text elements as markdown
        - Tables as <TABELLE> tags with image references
        - Pictures as ![Image](path) references
        - Page markers (<seite nummer="X" />) at page boundaries

        Filters out:
        - Headers and footers (content_layer: "furniture")
        - Text OCR'd from within pictures (children of picture elements)

        Args:
            doc_json: Document JSON from doc.export_to_dict()
            images_meta: Our extracted image metadata (with self_ref)
            tables_meta: Our extracted table metadata (with self_ref)

        Returns:
            Custom markdown string with page markers
        """
        # Build lookup maps from self_ref to our metadata
        images_by_ref: dict[str, dict[str, Any]] = {img["self_ref"]: img for img in images_meta if img.get("self_ref")}
        tables_by_ref: dict[str, dict[str, Any]] = {tbl["self_ref"]: tbl for tbl in tables_meta if tbl.get("self_ref")}

        # Also build index-based lookups as fallback
        images_by_index: dict[int, dict[str, Any]] = dict(enumerate(images_meta))
        tables_by_index: dict[int, dict[str, Any]] = dict(enumerate(tables_meta))

        # Detect furniture elements (headers/footers) to filter
        furniture = FurnitureDetector.detect(doc_json)

        # Extract refs for use in process_element
        texts_with_picture_parent = furniture.texts_with_picture_parent
        furniture_table_refs = furniture.furniture_table_refs
        furniture_picture_refs = furniture.furniture_picture_refs
        furniture_text_refs_by_position = furniture.furniture_text_refs_by_position

        output_parts: list[str] = []

        # Get the body structure
        body = doc_json.get("body", {})
        if not body:
            logger.warning("No body found in document JSON")
            return ""

        # Track counters for index-based fallback
        picture_counter = 0
        table_counter = 0

        # Track current page for inserting page markers
        current_page = 0  # Will be set to 1 when first element is processed

        def get_element_page(element: dict[str, Any]) -> int:
            """Get page number from element's prov array."""
            prov = element.get("prov", [])
            if prov and isinstance(prov, list) and len(prov) > 0:
                return prov[0].get("page_no", 1)
            return 1

        def maybe_insert_page_marker(element: dict[str, Any]) -> None:
            """Insert page marker if we've moved to a new page."""
            nonlocal current_page
            element_page = get_element_page(element)

            if element_page > current_page:
                # Insert marker for the new page
                output_parts.append(f'\n<seite nummer="{element_page}" />\n')
                current_page = element_page

        def process_element(ref: str, level: int = 0) -> None:  # noqa: C901
            """Recursively process an element and its children."""
            nonlocal picture_counter, table_counter

            # Get the ref string for filtering
            ref_str = ref.get("$ref", "") if isinstance(ref, dict) else str(ref)

            # Skip if this text element has a picture parent (OCR'd text from image)
            if ref_str in texts_with_picture_parent:
                logger.debug(f"Skipping text with picture parent: {ref_str}")
                return

            element = resolve_json_ref(doc_json, ref)
            if element is None:
                return

            self_ref = element.get("self_ref", "")
            label = element.get("label", "").lower()
            content_layer = element.get("content_layer", "").lower()

            # Skip furniture (headers/footers)
            # Check both content_layer AND label since docling is inconsistent
            is_furniture = content_layer == "furniture" or label in {
                "page_footer",
                "page_header",
                "page-footer",
                "page-header",
            }
            if is_furniture:
                logger.debug(f"Skipping furniture element: {self_ref} ({label}, {content_layer})")
                return

            # Handle different element types based on the ref path
            if "/texts/" in self_ref:
                # Text element
                # Skip texts in header/footer regions by position (except first of each unique text)
                if self_ref in furniture_text_refs_by_position:
                    logger.debug(f"Skipping text in header/footer region by position: {self_ref}")
                    return

                text = element.get("text", "")
                if text:
                    # Insert page marker if page changed
                    maybe_insert_page_marker(element)
                    md_text = MarkdownBuilder._format_text_element(element, level)
                    if md_text:
                        output_parts.append(md_text)

            elif "/tables/" in self_ref:
                # Table element - output <TABELLE> tag
                table_counter += 1

                # Skip tables that contain only furniture content (headers/footers)
                if self_ref in furniture_table_refs:
                    logger.debug(f"Skipping furniture table: {self_ref}")
                    return

                # Insert page marker if page changed
                maybe_insert_page_marker(element)

                # Try to find matching table metadata
                table_info = tables_by_ref.get(self_ref)
                if not table_info:
                    # Fallback to index-based lookup
                    idx = int(self_ref.split("/")[-1]) if "/" in self_ref else table_counter - 1
                    table_info = tables_by_index.get(idx, {})

                # Get caption if available
                caption = ""
                captions_refs = element.get("captions", [])
                for cap_ref in captions_refs:
                    cap_element = resolve_json_ref(doc_json, cap_ref)
                    if cap_element and cap_element.get("text"):
                        caption = cap_element.get("text", "")
                        break

                # Build TABELLE tag
                img_path = table_info.get("img_path", "")
                html_content = table_info.get("html", "")

                # Output caption as text (preserves document reading flow)
                if caption:
                    output_parts.append(f"\n{caption}\n")

                # Build TABELLE tag with caption_text inside for VLM metadata processing
                # Caption appears both in text AND inside tag for structured extraction
                caption_tag = f"\n<caption_text>{caption}</caption_text>" if caption else ""

                if img_path:
                    if html_content:
                        output_parts.append(
                            f'\n<TABELLE img_path="images/{img_path}">{caption_tag}\n{html_content}\n</TABELLE>\n'
                        )
                    else:
                        output_parts.append(f'\n<TABELLE img_path="images/{img_path}">{caption_tag}\n</TABELLE>\n')
                elif html_content:
                    # No image but have HTML
                    output_parts.append(f"\n<TABELLE>{caption_tag}\n{html_content}\n</TABELLE>\n")

            elif "/pictures/" in self_ref:
                # Picture element - output image reference
                picture_counter += 1

                # Skip pictures in header/footer regions (except first occurrence)
                if self_ref in furniture_picture_refs:
                    logger.debug(f"Skipping furniture picture: {self_ref}")
                    return

                # Insert page marker if page changed
                maybe_insert_page_marker(element)

                # Try to find matching image metadata
                img_info = images_by_ref.get(self_ref)
                if not img_info:
                    # Fallback to index-based lookup
                    idx = int(self_ref.split("/")[-1]) if "/" in self_ref else picture_counter - 1
                    img_info = images_by_index.get(idx, {})

                filename = img_info.get("filename", "")

                # Get caption from docling JSON (similar to tables)
                caption = ""
                captions_refs = element.get("captions", [])
                for cap_ref in captions_refs:
                    cap_element = resolve_json_ref(doc_json, cap_ref)
                    if cap_element and cap_element.get("text"):
                        caption = cap_element.get("text", "")
                        break

                # Fallback to caption from images_meta
                if not caption:
                    caption = img_info.get("caption", "")

                if filename:
                    # Filter out generic/placeholder captions
                    # These don't add value and cause duplicate "Image\n![Image]" output
                    generic_caption_patterns = {
                        "image",
                        "picture",
                        "figure",
                        "bild",
                        "abbildung",
                        "grafik",
                        "foto",
                    }
                    is_generic = False
                    if caption:
                        caption_lower = caption.lower().strip()
                        # Check if caption is just a generic word or "word N" pattern
                        for pattern in generic_caption_patterns:
                            if caption_lower == pattern or caption_lower.startswith(f"{pattern} "):
                                is_generic = True
                                break

                    # Use caption as alt_text only if it's meaningful
                    # Don't output caption as separate text - VLM will extract it from context
                    alt_text = caption if (caption and not is_generic) else f"Image {picture_counter}"
                    output_parts.append(f"\n![{alt_text}](images/{filename})\n")

            elif "/groups/" in self_ref:
                # Group element - process children recursively
                children = element.get("children", [])
                for child_ref in children:
                    process_element(child_ref, level + 1)

            # Process children if any (for non-group elements)
            children = element.get("children", [])
            if children and "/groups/" not in self_ref:
                for child_ref in children:
                    # Skip caption children for tables (already handled)
                    child = resolve_json_ref(doc_json, child_ref)  # pyrefly: ignore[unbound-name]
                    if child and child.get("label") == "caption":
                        continue
                    process_element(child_ref, level + 1)

        # Process body children in order
        body_children = body.get("children", [])
        for child_ref in body_children:
            process_element(child_ref)

        return "\n".join(output_parts)

    @staticmethod
    def _format_text_element(element: dict[str, Any], level: int = 0) -> str:
        """
        Format a text element as markdown.

        Args:
            element: Text element from docling JSON
            level: Nesting level for indentation

        Returns:
            Formatted markdown string
        """
        text = element.get("text", "")
        if not text:
            return ""

        label = element.get("label", "").lower()

        # Handle different text types
        if label in ["title", "document_title"]:
            return f"\n# {text}\n"
        elif label in ["section_header", "section-header"]:
            # Determine header level based on text or default to h2
            return f"\n## {text}\n"
        elif label in ["subtitle"]:
            return f"\n### {text}\n"
        elif label == "caption":
            # Captions are usually handled with their parent element
            return f"\n*{text}*\n"
        elif label == "list_item":
            marker = element.get("marker", "-")
            return f"{marker} {text}"
        elif label in ["footnote"]:
            return f"\n[^]: {text}\n"
        elif label in ["page_header", "page_footer", "page-header", "page-footer"]:
            # Skip headers/footers or include as comments
            return ""
        else:
            # Default paragraph
            return f"\n{text}\n"
