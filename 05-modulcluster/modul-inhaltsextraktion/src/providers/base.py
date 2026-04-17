# src/providers/base.py
"""
Data models for extraction providers.

Defines the unified data models for extraction results used by downstream
processing (filtering, chunking, VLM processing).

Content items use discriminated unions keyed on the ``type`` field so that
each variant only carries the fields relevant to it.

Coordinate System (bbox):
    TOPLEFT origin: [left, top, right, bottom]
    - left: distance from left edge
    - top: distance from top edge (y increases downward)
    - right: distance from left edge to right side
    - bottom: distance from top edge to bottom side
"""

from typing import Any, Literal

from pydantic import BaseModel
from typing_extensions import TypedDict

# ---------------------------------------------------------------------------
# Text content item
# ---------------------------------------------------------------------------


class _ContentItemTextRequired(TypedDict):
    """Required fields for a text content item."""

    type: Literal["text"]
    page_idx: int
    text: str


class ContentItemText(_ContentItemTextRequired, total=False):
    """Text paragraph or heading extracted from the document."""

    text_level: int
    bbox: list[float]
    label: str


# ---------------------------------------------------------------------------
# Table content item
# ---------------------------------------------------------------------------


class _ContentItemTableRequired(TypedDict):
    """Required fields for a table content item."""

    type: Literal["table"]
    page_idx: int


class ContentItemTable(_ContentItemTableRequired, total=False):
    """Table extracted from the document (HTML body + optional image)."""

    table_body: str
    img_path: str
    bbox: list[float]
    label: str


# ---------------------------------------------------------------------------
# Image content item
# ---------------------------------------------------------------------------


class _ContentItemImageRequired(TypedDict):
    """Required fields for an image content item."""

    type: Literal["image"]
    page_idx: int


class ContentItemImage(_ContentItemImageRequired, total=False):
    """Image (picture) extracted from the document."""

    img_path: str
    bbox: list[float]
    label: str
    content_layer: str


# ---------------------------------------------------------------------------
# Discriminated union
# ---------------------------------------------------------------------------

ContentItemDict = ContentItemText | ContentItemTable | ContentItemImage
"""Discriminated union of all content item variants, keyed on ``type``."""


# ---------------------------------------------------------------------------
# Extraction result
# ---------------------------------------------------------------------------


class ExtractionResult(BaseModel):
    """
    Unified result from any extraction provider.

    This contains all the outputs needed by downstream processing:
    - Markdown content for text extraction
    - Content list for structural analysis (filtering, chunking, page insertion)
    - Images as bytes for VLM processing and storage
    """

    md_content: str  # Extracted markdown content (custom format with <TABELLE> tags)
    content_list: list[ContentItemDict]  # List of content items as dicts
    images: dict[str, bytes]  # filename -> image bytes
    original_md_content: str | None = None  # Original provider markdown (for comparison)
    provider_json: dict[str, Any] | None = None  # Raw provider JSON (for debugging)

    class Config:
        arbitrary_types_allowed = True  # Allow bytes in Pydantic model
