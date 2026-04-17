from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from src.providers.base import ContentItemDict, ContentItemTable
from src.workflows.vlm_enhancement.output_format import VLMWorkflowInput

if TYPE_CHECKING:
    from src.activities.postprocessing import FilterEnhanceResult

logger = logging.getLogger(__name__)


def prepare_vlm_inputs(
    filtered_results: FilterEnhanceResult,
) -> list[VLMWorkflowInput]:
    """
    Build VLMWorkflowInput entries for visual elements.

    Steps:
    1) Extract table elements from content_list (if enabled) and only keep those
       that still exist in the markdown (raw HTML or image tag).
    2) Extract image elements from markdown
    3) De-duplicate image elements by checking if the image_ref is already in a table input
        Tables have either HTML or an img_path like images/b427dacc7a02ec240fe63781d599db15ca3ee532cf54065f091f14a7dd3acc61.jpg
        If they are as an image, we dont want to add them again in prepare_image_input from the markdown
        Our regex for images matches strings like these: ![](images/fd3d92c085ca46c5bd69eccf560ca2c2c8fe6a85bef62cb8b530066580ffc86d.jpg)
        As such, we can de-duplicate the image inputs by just checking if the image_ref of a image input is already in a table input

    4) Return the combined list of table and image inputs
    """

    markdown = filtered_results.markdown
    content_list: list[ContentItemDict] = filtered_results.content_list

    table_inputs: list[VLMWorkflowInput] = []

    logger.debug("Processing tables from content_list...")
    added_tables: set[str] = set()
    for item in content_list:
        if item["type"] != "table" or not item.get("img_path"):
            continue
        table_item: ContentItemTable = item  # type: ignore[assignment]
        key = table_item.get("table_body") or table_item.get("img_path", "")
        if key and key in added_tables:
            continue
        added_tables.add(key)
        table_input = _prepare_table_input(
            item=table_item,
            markdown=markdown,
            images=filtered_results.images,
        )
        if table_input is not None:
            table_inputs.append(table_input)

    logger.debug("Processing image tags from markdown...")
    image_inputs = _prepare_image_inputs(
        markdown_content=markdown,
        images=filtered_results.images,
    )

    table_image_refs = {t.image_ref for t in table_inputs}
    filtered_image_inputs = [img for img in image_inputs if img.image_ref not in table_image_refs]
    inputs = table_inputs + filtered_image_inputs

    logger.info(f"Prepared {len(inputs)} VLM inputs")
    return inputs


def _find_tabelle_tag_by_img_path(markdown: str, img_path: str) -> str | None:
    """
    Find the full <TABELLE> tag in markdown by its img_path attribute.

    Docling outputs tables as:
        <TABELLE img_path="images/...">
        <caption_text>...</caption_text>
        {html_content}
        </TABELLE>

    We need to find and return the entire tag for proper replacement.
    Using img_path is more reliable than searching by HTML content because
    each table has a unique img_path.

    Args:
        markdown: The full markdown content
        img_path: The image path (e.g., "images/filename.png") to match

    Returns:
        The full <TABELLE>...</TABELLE> tag if found, None otherwise
    """
    # Pattern to match TABELLE tag with specific img_path
    # This prevents nested TABELLE tags when replacing
    tabelle_pattern = rf'<TABELLE[^>]*img_path="{re.escape(img_path)}"[^>]*>.*?</TABELLE>'
    tabelle_match = re.search(tabelle_pattern, markdown, re.DOTALL)

    if tabelle_match:
        return tabelle_match.group(0)

    return None


def _prepare_table_input(
    item: ContentItemTable,
    markdown: str,
    images: dict[str, bytes],
) -> VLMWorkflowInput | None:
    """Build a VLM input for a single table item."""
    image_ref = item.get("img_path", "")
    if not image_ref:
        return None

    filename_only = image_ref.split("/")[-1] if "/" in image_ref else image_ref
    image_bytes = images.get(filename_only)

    if not image_bytes:
        logger.warning(f"Image bytes for table not found: {image_ref}")
        return None

    raw_table_html: str | None = item.get("table_body")

    # Try to find the full TABELLE tag in markdown (used by Docling provider)
    # This prevents nested TABELLE tags when replacing
    full_tabelle_tag = _find_tabelle_tag_by_img_path(markdown, image_ref)

    if full_tabelle_tag:
        # Found full TABELLE tag - use it as replacement target
        full_tag_for_replacement = full_tabelle_tag
    elif raw_table_html and raw_table_html.strip():
        # Fallback to raw HTML for providers that don't use TABELLE tags
        full_tag_for_replacement = raw_table_html
    else:
        # Final fallback to image reference
        full_tag_for_replacement = f"![](images/{filename_only})"

    # Skip elements that no longer exist in the markdown.
    if full_tag_for_replacement not in markdown:
        return None

    # For context extraction, use the image_ref (single line) rather than the
    # full multi-line TABELLE tag, so extract_context_around_image can find it
    context_text = extract_context_around_image(markdown, image_ref, context_lines=5)
    if not context_text:
        # Fall back to a minimal location hint if the surrounding context is empty.
        context_text = f"Table on page {item['page_idx']}"

    # raw_html contains the pre-extracted content (skips VLM extraction)
    # Note: full_tag is always required for VLMWorkflowOutput.original_content
    if raw_table_html and raw_table_html.strip():
        return VLMWorkflowInput(
            element_type="table",
            image_ref=image_ref,
            image_data=image_bytes,
            context_text=context_text,
            raw_html=raw_table_html,
            full_tag=full_tag_for_replacement,
        )
    else:
        return VLMWorkflowInput(
            element_type="table",
            image_ref=image_ref,
            image_data=image_bytes,
            context_text=context_text,
            full_tag=full_tag_for_replacement,
        )


def _prepare_image_inputs(
    markdown_content: str,
    images: dict[str, bytes],
) -> list[VLMWorkflowInput]:
    """Build VLM inputs for markdown image tags."""
    inputs: list[VLMWorkflowInput] = []
    # Capture full markdown tag + filename for local image refs.
    image_pattern = r"(!\[.*?]\(images/([^)]+)\))"
    added_images: set[str] = set()
    for match in re.finditer(image_pattern, markdown_content):
        full_image_tag = match.group(1)
        image_filename = match.group(2)
        image_ref = f"images/{image_filename}"

        image_bytes = images.get(image_filename)
        if not image_bytes:
            logger.warning(f"Image bytes not found for: {image_filename}")
            continue
        if full_image_tag in added_images:
            continue
        added_images.add(full_image_tag)

        # Use nearby markdown as context for VLM grounding.
        context_text = extract_context_around_image(markdown_content, image_ref)
        inputs.append(
            VLMWorkflowInput(
                element_type="image",
                image_ref=image_ref,
                image_data=image_bytes,
                context_text=context_text,
                full_tag=full_image_tag,
            )
        )

    return inputs


def extract_context_around_image(
    markdown_content: str,
    image_ref: str,
    context_lines: int = 10,
) -> str:
    """
    Extracts text context from around an image reference in markdown.
    """
    lines = markdown_content.split("\n")
    image_line_idx = next((i for i, line in enumerate(lines) if image_ref in line), None)

    if image_line_idx is None:
        return ""

    start_idx = max(0, image_line_idx - context_lines)
    end_idx = min(len(lines), image_line_idx + context_lines + 1)
    context_lines_list = lines[start_idx:end_idx]

    result_lines: list[str] = []
    for line in context_lines_list:
        if image_ref in line:
            result_lines.append("< Hier das Bild/>")
        elif line.strip():
            result_lines.append(line.strip())
    return "\n".join(result_lines)
