"""Content list builder for creating unified format output from docling JSON."""

import logging
from typing import Any

from src.providers.base import (
    ContentItemDict,
    ContentItemImage,
    ContentItemTable,
    ContentItemText,
)
from src.providers.docling.transforms import convert_bbox_bottomleft_to_topleft

logger = logging.getLogger(__name__)


class ContentBuilder:
    """Builds unified format content list from docling JSON structure."""

    @staticmethod
    def build_from_json(
        doc_json: dict[str, Any],
        images_meta: list[dict[str, Any]],
        tables_meta: list[dict[str, Any]],
    ) -> list[ContentItemDict]:
        """
        Build unified format content list from docling JSON.

        Args:
            doc_json: Document JSON from docling-serve
            images_meta: Extracted image metadata
            tables_meta: Extracted table metadata

        Returns:
            List of content items as dicts
        """
        content_list: list[ContentItemDict] = []

        # Create lookup maps
        images_by_ref: dict[str, dict[str, Any]] = {img["self_ref"]: img for img in images_meta if img.get("self_ref")}
        tables_by_ref: dict[str, dict[str, Any]] = {tbl["self_ref"]: tbl for tbl in tables_meta if tbl.get("self_ref")}

        # Process texts
        for text_elem in doc_json.get("texts", []):
            prov = text_elem.get("prov", [])
            page_no = prov[0].get("page_no", 1) if prov else 1
            label = text_elem.get("label", "text")
            content_layer = text_elem.get("content_layer", "")

            # Skip furniture elements (case-insensitive comparison)
            label_lower = label.lower() if label else ""
            content_layer_lower = content_layer.lower() if content_layer else ""
            if content_layer_lower == "furniture" or label_lower in {
                "page_header",
                "page_footer",
                "page-header",
                "page-footer",
            }:
                continue

            text = text_elem.get("text", "")
            if not text:
                continue

            text_item: ContentItemText = {
                "type": "text",
                "text": text,
                "page_idx": page_no - 1,  # 0-based
                "label": label,
            }

            # Set text level for headers
            if label in ("section_header", "title", "section-header"):
                text_item["text_level"] = 1

            # Convert bbox if present
            if prov and prov[0].get("bbox"):
                # Get page height for coordinate conversion
                pages = doc_json.get("pages", {})
                page_key = str(page_no)
                page_info = pages.get(page_key, {})
                page_size = page_info.get("size", {})
                page_height = page_size.get("height", 842.0)  # A4 default
                text_item["bbox"] = convert_bbox_bottomleft_to_topleft(prov[0]["bbox"], page_height)

            content_list.append(text_item)

        # Process tables
        for table_elem in doc_json.get("tables", []):
            ref = table_elem.get("self_ref", "")
            meta = tables_by_ref.get(ref, {})
            prov = table_elem.get("prov", [])
            page_no = prov[0].get("page_no", 1) if prov else 1

            table_item: ContentItemTable = {
                "type": "table",
                "table_body": meta.get("html", ""),
                "page_idx": page_no - 1,
                "label": "table",
            }

            if meta.get("img_path"):
                table_item["img_path"] = f"images/{meta['img_path']}"

            if prov and prov[0].get("bbox"):
                # Get page height for coordinate conversion
                pages = doc_json.get("pages", {})
                page_key = str(page_no)
                page_info = pages.get(page_key, {})
                page_size = page_info.get("size", {})
                page_height = page_size.get("height", 842.0)  # A4 default
                table_item["bbox"] = convert_bbox_bottomleft_to_topleft(prov[0]["bbox"], page_height)

            content_list.append(table_item)

        # Process images
        for picture_elem in doc_json.get("pictures", []):
            ref = picture_elem.get("self_ref", "")
            meta = images_by_ref.get(ref, {})
            prov = picture_elem.get("prov", [])
            page_no = prov[0].get("page_no", 1) if prov else 1
            label = picture_elem.get("label", "picture")
            content_layer = picture_elem.get("content_layer", "")

            image_item: ContentItemImage = {
                "type": "image",
                "page_idx": page_no - 1,
                "label": label,
                "content_layer": content_layer,  # Preserve for filtering
            }

            if meta.get("filename"):
                image_item["img_path"] = f"images/{meta['filename']}"

            if prov and prov[0].get("bbox"):
                # Get page height for coordinate conversion
                pages = doc_json.get("pages", {})
                page_key = str(page_no)
                page_info = pages.get(page_key, {})
                page_size = page_info.get("size", {})
                page_height = page_size.get("height", 842.0)  # A4 default
                image_item["bbox"] = convert_bbox_bottomleft_to_topleft(prov[0]["bbox"], page_height)

            content_list.append(image_item)

        # Sort by page then vertical position
        content_list.sort(
            key=lambda x: (
                x.get("page_idx", 0),
                x.get("bbox", [0, 0, 0, 0])[1] if x.get("bbox") else 0,
            )
        )

        return content_list
