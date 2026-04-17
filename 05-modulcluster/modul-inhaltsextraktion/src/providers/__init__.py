# src/providers/__init__.py
"""
Extraction providers package.

Provides the Docling-based PDF extraction provider.

Usage:
    from src.providers.docling_provider import DoclingProvider

    result = await DoclingProvider.extract(pdf_bytes, "doc.pdf", "doc")
"""

from src.providers.base import (
    ContentItemDict,
    ContentItemImage,
    ContentItemTable,
    ContentItemText,
    ExtractionResult,
)

__all__ = [
    "ContentItemDict",
    "ContentItemImage",
    "ContentItemTable",
    "ContentItemText",
    "ExtractionResult",
]
