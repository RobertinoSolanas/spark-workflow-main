"""Table extractor for docling document processing."""

import base64
import io
import logging
from typing import Any

import pypdfium2 as pdfium

from src.config import get_config

logger = logging.getLogger(__name__)


class TableExtractor:
    """Extracts tables from docling API responses."""

    @staticmethod
    def extract_from_json(
        doc_json: dict[str, Any],
        output_prefix: str,
        images_bytes: dict[str, bytes],
    ) -> list[dict[str, Any]]:
        """
        Extract table metadata from docling JSON response.

        Args:
            doc_json: Document JSON with table data
            output_prefix: Prefix for output filenames
            images_bytes: Dict to add table images to (mutated)

        Returns:
            List of table metadata dicts
        """
        tables_meta: list[dict[str, Any]] = []

        for idx, table in enumerate(doc_json.get("tables", [])):
            prov = table.get("prov", [])
            page_no = prov[0].get("page_no", 1) if prov else 1

            # Generate HTML from table cells
            html_content = TableExtractor.build_html(table)

            # Get bbox if available
            bbox = None
            if prov and prov[0].get("bbox"):
                bbox = prov[0]["bbox"]

            # Check for embedded table image
            image_data = table.get("image") or {}
            uri = image_data.get("uri", "") if image_data else ""
            img_filename = None

            if uri.startswith("data:"):
                try:
                    _, b64_data = uri.split(",", 1)
                    image_bytes = base64.b64decode(b64_data)
                    # Use same naming convention as local extraction
                    img_filename = f"{output_prefix}_p{page_no}_table{idx + 1}.png"
                    images_bytes[img_filename] = image_bytes
                except Exception as e:
                    logger.warning(f"Failed to decode table image {idx}: {e}")

            # Get table dimensions
            table_data = table.get("data", {})

            tables_meta.append(
                {
                    "index": idx + 1,
                    "html": html_content,
                    "page_no": page_no,
                    "self_ref": table.get("self_ref", f"#/tables/{idx}"),
                    "bbox": bbox,
                    "img_path": img_filename,
                    "rows": table_data.get("num_rows", 0),
                    "cols": table_data.get("num_cols", 0),
                }
            )

        logger.info(f"Extracted {len(tables_meta)} tables from API response")
        return tables_meta

    @staticmethod
    def build_html(table: dict[str, Any]) -> str:
        """
        Generate HTML table from table_cells structure.

        Args:
            table: Table element from docling JSON

        Returns:
            HTML table string
        """
        data = table.get("data", {})
        num_rows = data.get("num_rows", 0)
        num_cols = data.get("num_cols", 0)
        cells = data.get("table_cells", [])

        if not cells or num_rows == 0 or num_cols == 0:
            return "<table></table>"

        # Build grid to track which cells are occupied (for row/col spans)
        grid: list[list[dict[str, Any] | None]] = [[None] * num_cols for _ in range(num_rows)]

        # Place cells in grid
        for cell in cells:
            row = cell.get("start_row_offset_idx", 0)
            col = cell.get("start_col_offset_idx", 0)
            text = cell.get("text", "")
            row_span = cell.get("row_span", 1)
            col_span = cell.get("col_span", 1)
            is_header = cell.get("column_header", False) or cell.get("row_header", False)

            if 0 <= row < num_rows and 0 <= col < num_cols:
                grid[row][col] = {
                    "text": text,
                    "row_span": row_span,
                    "col_span": col_span,
                    "is_header": is_header,
                }

                # Mark spanned cells as occupied (set to empty dict)
                for r in range(row, min(row + row_span, num_rows)):
                    for c in range(col, min(col + col_span, num_cols)):
                        if r != row or c != col:
                            grid[r][c] = {}  # Mark as spanned (occupied)

        # Generate HTML
        html_parts: list[str] = ["<table>"]
        for _row_idx, row_cells in enumerate(grid):
            html_parts.append("<tr>")
            for _col_idx, cell in enumerate(row_cells):
                if cell is None:
                    # Empty cell (shouldn't happen if data is complete)
                    html_parts.append("<td></td>")
                elif cell == {}:
                    # Spanned cell - skip (already covered by spanning cell)
                    continue
                else:
                    tag = "th" if cell.get("is_header") else "td"
                    attrs: list[str] = []
                    if cell.get("row_span", 1) > 1:
                        attrs.append(f'rowspan="{cell["row_span"]}"')
                    if cell.get("col_span", 1) > 1:
                        attrs.append(f'colspan="{cell["col_span"]}"')
                    attr_str = " " + " ".join(attrs) if attrs else ""
                    # Escape HTML in text content
                    text = cell.get("text", "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    html_parts.append(f"<{tag}{attr_str}>{text}</{tag}>")
            html_parts.append("</tr>")
        html_parts.append("</table>")

        return "".join(html_parts)

    @staticmethod
    def crop_table_images(
        pdf_bytes: bytes,
        doc_json: dict[str, Any],
        tables_meta: list[dict[str, Any]],
        images_bytes: dict[str, bytes],
        output_prefix: str,
    ) -> None:
        """
        Crop table images from PDF pages for tables missing images.

        Uses pypdfium2 to render PDF pages and crop table regions based on bbox coordinates.
        This is used when docling-serve doesn't provide embedded table images.

        For Temporal: This is a CPU-bound operation that should be called within an activity.
        It modifies tables_meta and images_bytes in-place.

        Args:
            pdf_bytes: Raw PDF file bytes
            doc_json: Document JSON with page dimensions
            tables_meta: Table metadata (modified in-place to add img_path)
            images_bytes: Image bytes dict (modified in-place to add table images)
            output_prefix: Prefix for output filenames
        """
        # Find tables without images
        tables_without_images: list[dict[str, Any]] = [
            t for t in tables_meta if not t.get("img_path") and t.get("bbox")
        ]
        if not tables_without_images:
            logger.debug("All tables have images or no bbox - skipping cropping")
            return

        logger.info(f"Cropping {len(tables_without_images)} table images from PDF pages")

        try:
            pdf_doc = pdfium.PdfDocument(pdf_bytes)
            page_images_cache: dict[int, Any] = {}  # Cache rendered pages

            for table_info in tables_without_images:
                try:
                    bbox = table_info["bbox"]
                    page_no = table_info.get("page_no", 1)
                    table_idx = table_info.get("index", 0)

                    page_idx = page_no - 1
                    if page_idx < 0 or page_idx >= len(pdf_doc):
                        logger.warning(f"Invalid page {page_no} for table {table_idx}")
                        continue

                    # Get or render page image (with caching)
                    if page_idx not in page_images_cache:
                        page = pdf_doc[page_idx]
                        scale = get_config().DOCLING_IMAGES_SCALE
                        bitmap = page.render(scale=scale)
                        pil_image = bitmap.to_pil()
                        page_images_cache[page_idx] = {
                            "pil_image": pil_image,
                            "pdf_width": page.get_width(),
                            "pdf_height": page.get_height(),
                        }

                    page_data = page_images_cache[page_idx]
                    pil_image = page_data["pil_image"]
                    pdf_height = page_data["pdf_height"]

                    scale = get_config().DOCLING_IMAGES_SCALE
                    img_width = pil_image.width
                    img_height = pil_image.height

                    # Convert bbox from docling format (BOTTOMLEFT origin) to image coords (TOPLEFT)
                    left = bbox.get("l", 0) * scale
                    right = bbox.get("r", 0) * scale
                    top = (pdf_height - bbox.get("t", 0)) * scale
                    bottom = (pdf_height - bbox.get("b", 0)) * scale

                    # Add padding
                    padding = 5
                    left = max(0, left - padding)
                    top = max(0, top - padding)
                    right = min(img_width, right + padding)
                    bottom = min(img_height, bottom + padding)

                    if left >= right or top >= bottom:
                        logger.warning(f"Invalid crop region for table {table_idx}: ({left}, {top}, {right}, {bottom})")
                        continue

                    crop_box = (int(left), int(top), int(right), int(bottom))
                    cropped_image = pil_image.crop(crop_box)

                    img_buffer = io.BytesIO()
                    cropped_image.save(img_buffer, format="PNG")
                    img_bytes = img_buffer.getvalue()

                    img_filename = f"{output_prefix}_p{page_no}_table{table_idx}.png"
                    table_info["img_path"] = img_filename
                    images_bytes[img_filename] = img_bytes

                    logger.debug(f"Cropped table image: {img_filename} ({int(right - left)}x{int(bottom - top)}px)")

                except Exception as e:
                    logger.warning(f"Failed to crop table {table_info.get('index', '?')}: {e}")
                    continue

            pdf_doc.close()
            page_images_cache.clear()
            logger.info(
                f"Successfully cropped {sum(1 for t in tables_without_images if t.get('img_path'))} table images"
            )

        except Exception as e:
            logger.error(f"Failed to open PDF for table cropping: {e}")
