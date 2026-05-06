"""Qdrant-specific payload models for vector index entries."""

from typing import Any

from pydantic import BaseModel, Field


class ChunkMetadata(BaseModel):
    """Represents the source text segment and its position within the document,
    including pointers to neighboring chunks for contextual analysis.
    """

    chunk_id: str = Field(description="Unique identifier for the specific text chunk.")
    previous_chunk_id: str | None = Field(None, description="ID of the preceding chunk to maintain document flow.")
    next_chunk_id: str | None = Field(None, description="ID of the following chunk to maintain document flow.")

    page_content: str = Field(description="The raw text content contained within this chunk.")
    page_numbers: list[int] = Field(
        default_factory=list,
        description="List of physical page numbers where this content originates.",
    )

    chunk_type: str | None = Field(None, description="The type of the chunk.")

    parent_chunk_id: str | None = Field(None, description="ID of the parent chunk.")

    # --- headers / structure (from chunker) ---
    header_1: str | None = Field(None, description="Level-1 heading text.")
    header_2: str | None = Field(None, description="Level-2 heading text.")
    header_3: str | None = Field(None, description="Level-3 heading text.")
    toc_path: list[str] = Field(default_factory=list, description="Table-of-contents path breadcrumbs.")
    all_subchapters: list[str] = Field(default_factory=list, description="Subchapter titles within this chunk.")

    # --- element metadata (images/tables, from chunker) ---
    asset_path: str | None = Field(None, description="DMS path of the associated image/table asset.")
    caption: str | None = Field(None, description="Caption text for images/tables.")
    summary: str | None = Field(None, description="AI-generated summary of the element.")
    description: str | None = Field(None, description="AI-generated description of the element.")
    content: str | None = Field(None, description="Raw extracted content of images/tables.")
    footnote: str | None = Field(None, description="Footnote text associated with this chunk.")

    # --- cross-chunk linking (from chunker) ---
    related_assets: list[dict[str, Any]] = Field(
        default_factory=list, description="Linked image/table assets from other chunks."
    )
    related_text: list[dict[str, Any]] = Field(
        default_factory=list, description="Linked text segments from other chunks."
    )

    # --- enrichment: schwerpunkt ---
    focus_topic: str | None = Field(None, description="Primary topic classification.")

    # --- enrichment: species/scale ---
    wildlife_mentioned: bool | None = Field(None, description="Whether wildlife species are mentioned.")
    plant_species_mentioned: bool | None = Field(None, description="Whether plant species are mentioned.")
    wildlife_species: list[str] = Field(default_factory=list, description="Wildlife species names found in this chunk.")
    plant_species: list[str] = Field(default_factory=list, description="Plant species names found in this chunk.")
    map_scale: str | None = Field(None, description="Map scale if referenced in the chunk.")

    # --- enrichment: hypothetical questions ---
    hypothetical_questions: list[str] = Field(
        default_factory=list,
        description="AI-generated hypothetical questions for this chunk.",
    )


class QuestionMetadata(BaseModel):
    """A hypothetical question generated from a chunk, indexed for query matching."""

    question_text: str = Field(description="The hypothetical question text.")
    chunk_id: str = Field(description="ID of the chunk this question was generated from.")
    parent_chunk_id: str | None = Field(None, description="ID of the parent chunk, if this is a sub-chunk question.")


class ParentChunkMetadata(BaseModel):
    """Payload-only record for retrieving full parent chunk content by ID."""

    chunk_id: str = Field(description="Unique identifier of the parent chunk.")
    page_content: str = Field(description="Full text content of the parent chunk.")
    page_numbers: list[int] = Field(
        default_factory=list,
        description="Page numbers spanned by this parent chunk.",
    )


class SummaryMetadata(BaseModel):
    """A document-level summary, indexed for document-level search."""

    summary_text: str = Field(description="The generated document summary.")


class QdrantDocumentContext(BaseModel):
    """Per-document context passed alongside chunks during Qdrant upload."""

    project_id: str = Field(description="Unique identifier of the project.")
    document_id: str = Field(description="Unique identifier of the document.")
    source_file_id: str | None = Field(
        None,
        description="DMS file_id of the original source document (e.g. the uploaded PDF).",
    )
    title: str | None = Field(None, description="Optional document or section title.")
