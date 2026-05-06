# src/processors/filtering_config.py
"""
Centralized filtering configuration for header/footer detection.

This module provides a single source of truth for all filtering-related
constants and helper functions used by both filter.py and docling_provider.py.

Configuration can be adjusted via environment variables:
- FILTER__HEADER_ZONE_RATIO: Percentage of page height for header zone (default: 0.12)
- FILTER__FOOTER_ZONE_RATIO: Percentage of page height for footer zone (default: 0.18)
- FILTER__IMAGE_SIMILARITY_THRESHOLD: Max Hamming distance for image similarity (default: 8)
"""

from src.config import get_config

# Page dimensions (A4 default in points)
DEFAULT_PAGE_HEIGHT_POINTS = 842.0
DEFAULT_PAGE_WIDTH_POINTS = 595.0

# Filtering zones - loaded from environment via config
# These define what percentage of the page is considered header/footer zone
HEADER_ZONE_RATIO = get_config().FILTER_HEADER_ZONE_RATIO  # Default: 0.12 (12% from top)
FOOTER_ZONE_RATIO = get_config().FILTER_FOOTER_ZONE_RATIO  # Default: 0.18 (18% from bottom)

# Image similarity settings for recurring element detection
IMAGE_HASH_SIZE = get_config().FILTER_IMAGE_HASH_SIZE  # Default: 8
IMAGE_SIMILARITY_THRESHOLD = get_config().FILTER_IMAGE_SIMILARITY_THRESHOLD  # Default: 5

# Labels that indicate header/footer content (used by Docling provider)
# Include both underscore and hyphen versions for compatibility
FURNITURE_LABELS = {"page_header", "page_footer", "page-header", "page-footer"}


def get_header_zone_height(page_height: float = DEFAULT_PAGE_HEIGHT_POINTS) -> float:
    """
    Get the header zone height in points.

    Elements with their bottom edge above this value are considered
    potential header elements.

    Args:
        page_height: Page height in points. Defaults to A4 height (842.0).

    Returns:
        Header zone height in points.
    """
    return page_height * HEADER_ZONE_RATIO


def get_footer_zone_start(page_height: float = DEFAULT_PAGE_HEIGHT_POINTS) -> float:
    """
    Get the footer zone start position in points.

    Elements with their top edge below this value are considered
    potential footer elements.

    Args:
        page_height: Page height in points. Defaults to A4 height (842.0).

    Returns:
        Footer zone start position in points (measured from bottom for BOTTOMLEFT origin).
    """
    return page_height * (1 - FOOTER_ZONE_RATIO)


def get_header_region_height(page_height: float = DEFAULT_PAGE_HEIGHT_POINTS) -> float:
    """
    Get the header region height in points (for BOTTOMLEFT coordinate origin).

    This is the distance from the top of the page that defines the header region.
    Used when coordinates have BOTTOMLEFT origin (like Docling).

    Args:
        page_height: Page height in points. Defaults to A4 height (842.0).

    Returns:
        Header region height in points.
    """
    return page_height * HEADER_ZONE_RATIO


def get_footer_region_height(page_height: float = DEFAULT_PAGE_HEIGHT_POINTS) -> float:
    """
    Get the footer region height in points (for BOTTOMLEFT coordinate origin).

    This is the distance from the bottom of the page that defines the footer region.
    Used when coordinates have BOTTOMLEFT origin (like Docling).

    Args:
        page_height: Page height in points. Defaults to A4 height (842.0).

    Returns:
        Footer region height in points.
    """
    return page_height * FOOTER_ZONE_RATIO
