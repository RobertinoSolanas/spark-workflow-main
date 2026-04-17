from typing import Any

from pydantic import BaseModel, Field


class ChunkMetadata(BaseModel):
    """Metadata associated with a document text chunk.

    Attributes:
        page_numbers: List of page numbers where this chunk appears.
    """

    page_numbers: list[int] = Field(default_factory=list)


class DocumentChunk(BaseModel):
    """Represents a specific segment of text from a document."""

    chunk_id: str = Field(
        ...,
        description="Unique identifier for this specific chunk.",
    )
    page_content: str = Field(
        ...,
        description="The actual text content of the chunk.",
    )
    metadata: ChunkMetadata = Field(..., description="Associated metadata including page numbers")


class DocumentMetadata(BaseModel):
    """High-level metadata for a document.

    Attributes:
        document_id (str): Unique identifier for the document.
        summary: A text summary of the document contents, if available.
    """

    document_id: str
    summary: str | None = None


class DocumentDetailsResponse(BaseModel):
    """Raw response model for the document details API endpoint.

    Attributes:
        chunks: List of text chunks extracted from the document.
        metadata: Document-level metadata including summary.
    """

    chunks: list[DocumentChunk] = Field(default_factory=list)
    metadata: DocumentMetadata


class DMSInhaltsExtraction(BaseModel):
    """Result model containing filtered document chunks and metadata.

    Attributes:
        chunks: A list of `DocumentChunk` objects that matched the
            page filtering criteria.
        summary: An optional summary of the document's content.
        error: An error message string if the fetch operation failed;
            otherwise None.
    """

    chunks: list[DocumentChunk]
    summary: str | None = None
    error: str | None = None


class DMSDocument(BaseModel):
    """Data model representing a document managed within the DMS.

    This model provides the necessary identifiers to locate a specific document,
    its parent project, and its associated extracted content within the
    Document Management System.

    Attributes:
        project_id: Unique identifier for the project the document belongs to.
        document_id: Unique identifier for the specific document record.
        document_name: The full name or path of the document file.
        content_extraction_id: Identifier for the specific text extraction
            result associated with this document.
    """

    project_id: str
    document_id: str
    document_name: str
    content_extraction_id: str


class DownloadJsonFromDmsInput(BaseModel):
    """Input parameters for the download_json_from_dms activity.

    Attributes:
        file_id (str): The unique identifier of the file to download from the DMS.
    """

    file_id: str


class UploadTemporalCheckpointInput(BaseModel):
    """Input parameters for the upload_temporal_checkpoint activity.

    This model defines the data required to persist a state or data checkpoint
    during a Temporal workflow execution, allowing for results
    to be stored and referenced.

    Attributes:
        project_id: The unique identifier of the project associated with
            the checkpoint.
        workflow_id: The identifier of the specific workflow triggering
            the upload.
        run_id: The specific execution ID of the current workflow run.
        filename: The name to be assigned to the checkpoint file in storage.
        payload: The actual data content to be uploaded, supporting any
            serializable format.
    """

    project_id: str
    workflow_id: str
    run_id: str
    filename: str
    payload: dict[str, Any] | list[Any] | str | int | float | bool | None


class InhaltsExtraktionChunksActivityParams(BaseModel):
    """Parameters for the document chunk extraction activity.

    This model defines the required data for identifying and fetching relevant
    text segments (chunks) from a document, specifically optimized for locating
    table of contents information.

    Attributes:
        dms_document: The full DMS document object containing metadata,
            summaries, and references.
        n_pages: The maximum number of pages to be analyzed during the
            chunk extraction process.
        include_summary: Flag indicating whether the document's general
            summary should be retrieved and included in the context.
    """

    dms_document: DMSDocument
    n_pages: int
    include_summary: bool
