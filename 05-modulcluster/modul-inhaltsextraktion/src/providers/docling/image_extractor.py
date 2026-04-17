"""Image extractor for docling document processing."""

import base64
import logging
import re
from typing import Any

from src.config import get_config
from src.providers.base import ContentItemDict, ContentItemImage

logger = logging.getLogger(__name__)


class ImageExtractor:
    """Extracts images from docling API responses."""

    @staticmethod
    def extract_from_json(
        doc_json: dict[str, Any],
        output_prefix: str,
    ) -> tuple[list[dict[str, Any]], dict[str, bytes]]:
        """
        Extract embedded base64 images from docling JSON response.

        Args:
            doc_json: Document JSON with embedded images
            output_prefix: Prefix for output filenames

        Returns:
            Tuple of (images_metadata, image_bytes_dict)
        """
        images_meta: list[dict[str, Any]] = []
        images_bytes: dict[str, bytes] = {}

        for idx, picture in enumerate(doc_json.get("pictures", [])):
            image_data = picture.get("image") or {}
            uri = image_data.get("uri", "") if image_data else ""

            if not uri.startswith("data:"):
                logger.debug(f"Picture {idx} has no embedded image data")
                continue

            # Parse data URI: data:image/png;base64,XXXXX
            try:
                _, b64_data = uri.split(",", 1)
                image_bytes = base64.b64decode(b64_data)
            except Exception as e:
                logger.warning(f"Failed to decode image {idx}: {e}")
                continue

            # Get page number from provenance
            prov = picture.get("prov", [])
            page_no = prov[0].get("page_no", 1) if prov else 1

            # Use same naming convention as local extraction
            filename = f"{output_prefix}_p{page_no}_picture{idx + 1}.png"
            images_bytes[filename] = image_bytes

            # Get bbox if available
            bbox = None
            if prov and prov[0].get("bbox"):
                bbox = prov[0]["bbox"]

            # Get caption if available
            caption = ""
            caption_data = picture.get("caption")
            if caption_data:
                if isinstance(caption_data, dict):
                    caption = caption_data.get("text", "")
                elif isinstance(caption_data, str):
                    caption = caption_data

            # Build metadata (same format as _extract_images)
            images_meta.append(
                {
                    "filename": filename,
                    "page_no": page_no,
                    "index": idx + 1,
                    "self_ref": picture.get("self_ref", f"#/pictures/{idx}"),
                    "bbox": bbox,
                    "caption": caption,
                }
            )

        logger.info(f"Extracted {len(images_meta)} images from API response")
        return images_meta, images_bytes

    @staticmethod
    def extract_from_markdown(
        md_content: str,
        doc_json: dict[str, Any],
        output_prefix: str,
    ) -> tuple[list[dict[str, Any]], dict[str, bytes]]:
        """
        Extract embedded base64 images from markdown content.

        Docling embeds images as data URIs in markdown for PDF documents.
        Format: ![alt text](data:image/png;base64,XXXXX)

        Args:
            md_content: Markdown content with embedded images
            doc_json: Document JSON (for picture metadata matching)
            output_prefix: Prefix for output filenames

        Returns:
            Tuple of (images_metadata, image_bytes_dict)
        """
        images_meta: list[dict[str, Any]] = []
        images_bytes: dict[str, bytes] = {}

        # Pattern to match markdown images with data URIs
        # ![alt](data:image/TYPE;base64,DATA)
        pattern = r"!\[([^\]]*)\]\((data:image/[^;]+;base64,([^)]+))\)"

        pictures = doc_json.get("pictures", [])

        for idx, match in enumerate(re.finditer(pattern, md_content)):
            alt_text = match.group(1)
            b64_data = match.group(3)

            try:
                image_bytes = base64.b64decode(b64_data)
            except Exception as e:
                logger.warning(f"Failed to decode markdown image {idx}: {e}")
                continue

            # Try to get page number from corresponding picture in JSON
            page_no = 1
            self_ref = f"#/pictures/{idx}"
            bbox = None

            if idx < len(pictures):
                pic = pictures[idx]
                prov = pic.get("prov", [])
                if prov:
                    page_no = prov[0].get("page_no", 1)
                    bbox = prov[0].get("bbox")
                self_ref = pic.get("self_ref", self_ref)

            filename = f"{output_prefix}_p{page_no}_picture{idx + 1}.png"
            images_bytes[filename] = image_bytes

            images_meta.append(
                {
                    "filename": filename,
                    "page_no": page_no,
                    "index": idx + 1,
                    "self_ref": self_ref,
                    "bbox": bbox,
                    "caption": alt_text if alt_text else "",
                }
            )

        logger.info(f"Extracted {len(images_meta)} images from markdown content")
        return images_meta, images_bytes

    @staticmethod
    def detect_full_page_images(  # noqa: C901
        doc_json: dict[str, Any],
        output_prefix: str,
        threshold: float | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, bytes]]:
        """
        Detect pages where docling missed dominant/full-page images.

        For each page that has no detected pictures or tables, checks whether
        the text coverage is below a threshold. If so, extracts the full-page
        render from ``doc_json["pages"][page_no]["image"]``.

        Args:
            doc_json: Document JSON from docling-serve
            output_prefix: Prefix for output filenames
            threshold: Text-coverage threshold (fraction of page area).
                       Defaults to ``get_config().FULL_PAGE_IMAGE_TEXT_COVERAGE_THRESHOLD``.

        Returns:
            Tuple of (images_metadata, image_bytes_dict) for newly detected
            full-page images (same format as ``extract_from_json``).
        """
        if threshold is None:
            threshold = get_config().FULL_PAGE_IMAGE_TEXT_COVERAGE_THRESHOLD

        # Build sets of pages that already have pictures or tables
        pages_with_pictures: set[int] = set()
        for pic in doc_json.get("pictures", []):
            for prov in pic.get("prov", []):
                page_no = prov.get("page_no")
                if page_no is not None:
                    pages_with_pictures.add(page_no)

        pages_with_tables: set[int] = set()
        for tbl in doc_json.get("tables", []):
            for prov in tbl.get("prov", []):
                page_no = prov.get("page_no")
                if page_no is not None:
                    pages_with_tables.add(page_no)

        # Collect text bbox areas per page
        text_areas_by_page: dict[int, float] = {}
        for text_elem in doc_json.get("texts", []):
            for prov in text_elem.get("prov", []):
                page_no = prov.get("page_no")
                bbox = prov.get("bbox")
                if page_no is None or bbox is None:
                    continue
                width = abs(bbox.get("r", 0) - bbox.get("l", 0))
                height = abs(bbox.get("t", 0) - bbox.get("b", 0))
                text_areas_by_page.setdefault(page_no, 0.0)
                text_areas_by_page[page_no] += width * height

        images_meta: list[dict[str, Any]] = []
        images_bytes: dict[str, bytes] = {}

        pages = doc_json.get("pages", {})
        for page_no_str, page_data in pages.items():
            try:
                page_no = int(page_no_str)
            except (ValueError, TypeError):
                continue

            # Skip if page already has pictures or tables
            if page_no in pages_with_pictures or page_no in pages_with_tables:
                continue

            # Calculate text coverage as fraction of page area
            page_size = page_data.get("size", {})
            page_width = page_size.get("width", 0)
            page_height = page_size.get("height", 0)
            page_area = page_width * page_height
            if page_area <= 0:
                continue

            text_area = text_areas_by_page.get(page_no, 0.0)
            coverage = text_area / page_area

            if coverage >= threshold:
                continue

            # Check for page-level image
            image_data = page_data.get("image")
            if not image_data:
                continue
            uri = image_data.get("uri", "") if isinstance(image_data, dict) else ""
            if not uri.startswith("data:"):
                continue

            # Decode base64 image
            try:
                _, b64_data = uri.split(",", 1)
                image_bytes_decoded = base64.b64decode(b64_data)
            except Exception as e:
                logger.warning(f"Failed to decode full-page image for page {page_no}: {e}")
                continue

            filename = f"{output_prefix}_p{page_no}_fullpage.png"
            images_bytes[filename] = image_bytes_decoded
            images_meta.append(
                {
                    "filename": filename,
                    "page_no": page_no,
                    "index": 0,
                    "self_ref": f"#/fullpage/{page_no}",
                    "bbox": None,
                    "caption": "",
                }
            )

        if images_meta:
            logger.info(
                f"Detected {len(images_meta)} full-page image(s) on pages: {sorted(m['page_no'] for m in images_meta)}"
            )

        return images_meta, images_bytes

    @staticmethod
    def inject_full_page_images(
        doc_json: dict[str, Any],
        images_meta: list[dict[str, Any]],
        images_bytes: dict[str, bytes],
        content_list: list[ContentItemDict],
        markdown: str,
        output_prefix: str,
    ) -> tuple[list[dict[str, Any]], dict[str, bytes], list[ContentItemDict], str]:
        """
        Detect and inject full-page images into extraction results.

        Calls ``detect_full_page_images`` and, if any are found, updates
        images_meta, images_bytes, content_list, and markdown in-place-style
        (returns new copies).

        Args:
            doc_json: Document JSON from docling-serve
            images_meta: Existing image metadata list
            images_bytes: Existing image bytes dict
            content_list: Existing content list
            markdown: Existing markdown string
            output_prefix: Prefix for output filenames

        Returns:
            Tuple of (images_meta, images_bytes, content_list, markdown) with
            full-page images injected.
        """
        new_meta, new_bytes = ImageExtractor.detect_full_page_images(
            doc_json,
            output_prefix,
        )
        if not new_meta:
            return images_meta, images_bytes, content_list, markdown

        # Update images
        images_bytes = {**images_bytes, **new_bytes}
        images_meta = list(images_meta) + list(new_meta)

        # Update content_list and markdown
        content_list = list(content_list)
        for meta in new_meta:
            filename = meta["filename"]
            page_no = meta["page_no"]
            page_idx = page_no - 1

            # Add content_list item
            image_item: ContentItemImage = {
                "type": "image",
                "img_path": f"images/{filename}",
                "page_idx": page_idx,
                "label": "picture",
            }
            content_list.append(image_item)

            # Inject markdown reference
            page_marker = f'<seite nummer="{page_no}" />'
            img_md = f"![Full page image](images/{filename})"
            if page_marker in markdown:
                markdown = markdown.replace(
                    page_marker,
                    f"{page_marker}\n{img_md}",
                    1,
                )
            else:
                markdown += f"\n{page_marker}\n{img_md}"

        # Re-sort content_list by (page_idx, bbox_y)
        content_list.sort(
            key=lambda x: (
                x.get("page_idx", 0),
                x.get("bbox", [0, 0, 0, 0])[1] if x.get("bbox") else 0,
            )
        )

        return images_meta, images_bytes, content_list, markdown
