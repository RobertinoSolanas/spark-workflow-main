# src/workflows/metadata_extraction/document/document_metadata_output_format.py
"""Pydantic models for extracted document-specific metadata."""

from pydantic import BaseModel, Field


class DocumentSpecificMetadata(BaseModel):
    """Schema for the metadata to be extracted from any document text.

    Note: Page count is calculated programmatically from page markers, not extracted by LLM.
    """

    title: str | None = Field(
        None,
        description="Der Titel des Dokuments. Gegebenenfalls der passende Sub-Titel dazu.",
    )
    document_type: str | None = Field(
        None,
        description="The type or category of the document (e.g., 'Antragsunterlage').",
    )
