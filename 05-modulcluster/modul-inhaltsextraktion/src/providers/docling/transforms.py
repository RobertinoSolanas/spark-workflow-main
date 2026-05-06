"""Utility functions for docling data transformations."""

import unicodedata
from typing import Any


def sanitize_output_prefix(output_prefix: str) -> str:
    """
    Sanitize output_prefix to prevent problematic characters in filenames.

    Note: Primary sanitization now happens in extraction.py. This is a safety net.

    Args:
        output_prefix: Original output prefix (usually document stem)

    Returns:
        Sanitized output prefix safe for use in filenames
    """
    # Normalize Unicode to composed form (NFC) and remove problematic chars
    sanitized = unicodedata.normalize("NFC", output_prefix)
    sanitized = "".join(
        c for c in sanitized if unicodedata.category(c) not in {"Cc", "Cf", "Zl", "Zp"} or c in (" ", "\t")
    )
    sanitized = sanitized.replace("\u2028", "_").replace("\u2029", "_")
    sanitized = sanitized.replace("\n", "_").replace("\r", "_")

    for char in ["<", ">", ":", '"', "|", "?", "*"]:
        sanitized = sanitized.replace(char, "_")

    return sanitized


def convert_bbox_bottomleft_to_topleft(
    bbox: dict[str, float],
    page_height: float,
) -> list[float]:
    """
    Convert docling bbox dict to top-left origin format [x0, y0, x1, y1].

    Docling uses bottom-left origin; this converts to top-left.

    Args:
        bbox: Bbox dict with l, t, r, b keys
        page_height: Page height in points

    Returns:
        List of [x0, y0, x1, y1] in top-left origin
    """
    # Extract coordinates
    left = bbox.get("l", 0)
    top = bbox.get("t", 0)
    right = bbox.get("r", 0)
    bottom = bbox.get("b", 0)

    # Convert from bottom-left to top-left origin
    # In bottom-left: top is the higher y, bottom is the lower y
    # In top-left: y increases downward
    y0 = page_height - top
    y1 = page_height - bottom

    return [left, y0, right, y1]


def resolve_json_ref(doc_json: dict[str, Any], ref: str | dict[str, Any] | None) -> Any:
    """
    Resolve a JSON pointer reference like '#/texts/53' to the actual object.

    Args:
        doc_json: The full document JSON
        ref: JSON pointer like '#/texts/53' or {'$ref': '#/texts/53'}, or None

    Returns:
        The resolved object or None if not found
    """
    # Handle both string refs and dict refs
    if isinstance(ref, dict):
        ref = ref.get("$ref", "")

    if not ref or not ref.startswith("#/"):
        return None

    # Parse the path: #/texts/53 -> ['texts', '53']
    path_parts = ref[2:].split("/")

    try:
        current = doc_json
        for part in path_parts:
            if isinstance(current, list):
                current = current[int(part)]
            elif isinstance(current, dict):
                current = current[part]
            else:
                return None
        return current
    except (KeyError, IndexError, ValueError):
        return None
