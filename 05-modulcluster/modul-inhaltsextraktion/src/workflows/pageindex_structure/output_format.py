"""Pydantic models for the pageindex structure extraction workflow."""

from __future__ import annotations

from pydantic import BaseModel, Field


class DocumentNodeOutput(BaseModel):
    """A single node in the hierarchical document structure.

    Leaf nodes have ``summary``; parent nodes have ``prefix_summary`` and
    recursive ``nodes`` children.
    """

    title: str = Field(
        ...,
        description="The title of the section.",
    )
    node_id: str = Field(
        ...,
        description="The unique node identifier (zero-padded, e.g. '0001').",
    )
    text: str = Field(
        ...,
        description="The textual content of the node as extracted from the markdown.",
    )
    line_num: int = Field(
        ...,
        description="The line where the node starts in the markdown.",
    )
    summary: str | None = Field(
        default=None,
        description="Summary of the section content (leaf nodes only).",
    )
    prefix_summary: str | None = Field(
        default=None,
        description="Summary of the section content (parent nodes only).",
    )
    pages: list[int] = Field(
        default_factory=list,
        description="Page numbers where the text is located (1-based).",
    )
    nodes: list[DocumentNodeOutput] | None = Field(
        default=None,
        description="Child nodes (recursive hierarchy).",
    )


class DocumentStructureOutputFormat(BaseModel):
    """The full structure output for a single document."""

    doc_name: str = Field(
        ...,
        description="The document name (without extension).",
    )
    project_id: str = Field(
        ...,
        description="The project the original _processed.json document belongs to.",
    )
    document_id: str = Field(
        ...,
        description="The UUID of the original raw document in DMS.",
    )
    source_file_id: str = Field(
        ...,
        description="The UUID of the _processed.json in DMS.",
    )
    structure: list[DocumentNodeOutput] | None = Field(
        ...,
        description="Hierarchical list representing the document structure.",
    )
