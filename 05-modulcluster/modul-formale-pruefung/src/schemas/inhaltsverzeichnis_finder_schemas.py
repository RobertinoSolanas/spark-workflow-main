"""Defines Pydantic schemas and data models for the Inhaltsverzeichnis Finder workflow.

These models structure the data exchange between the Temporal workflow, the
content extraction API, and the LLM classification tasks. They cover workflow
configuration, activity parameters, internal state tracking, and structured
LLM responses required for identifying the Table of Contents.
"""

from pydantic import BaseModel, Field
from temporal.workflows.formale_pruefung.types import (
    ChunkOutput,
    DocumentTypeDefinitionDict,
    InhaltsverzeichnisEntry,
)

from src.schemas.dms_schemas import ChunkMetadata, DMSDocument, DocumentChunk


class MergedDocumentChunk(BaseModel):
    """Represents a merged text segment composed of multiple original chunks.

    Attributes:
        merged_page_content: The combined text content of the original chunks.
        original_chunks: The list of original `DocumentChunk` objects that
            were merged to create this segment.
        metadata: Aggregated metadata (e.g., combined page numbers) for the
            merged content.
    """

    merged_page_content: str
    original_chunks: list[DocumentChunk]
    metadata: ChunkMetadata


class ProcessedInhaltsExtraction(BaseModel):
    """Result model containing processed (merged) document chunks.

    Attributes:
        dms_document: The document object containing the file identifier and metadata.
        chunks: A list of `MergedDocumentChunk` objects containing merged text
            and original source tracking.
        summary: An optional summary of the document's content.
    """

    dms_document: DMSDocument
    chunks: list[MergedDocumentChunk]
    summary: str | None = None


class CandidateDoc(BaseModel):
    """Internal helper to structure candidate data between workflow steps.

    Attributes:
        data: The original filtered chunk result from the API.
        start_index: The index of the chunk identified as the start of the TOC.
    """

    data: ProcessedInhaltsExtraction
    start_index: int


class ChunkLLMClassificationActivityParams(BaseModel):
    """Parameters for context-aware LLM classification.

    Attributes:
        chunk: The text content of the chunk to classify.
    """

    chunk: str


class OverallLLMClassificationActivityParams(BaseModel):
    """Parameters for context-aware LLM classification.

    Attributes:
        document_name: Name of the document being classified.
        document_summary: Summary of the document's content.
        chunk: The text content of the chunk to classify.
    """

    document_name: str
    document_summary: str
    chunk: str


class SelectInhaltsverzeichnisLLMActivityParams(BaseModel):
    """
    Parameters for selecting the file that contains the table of contents (TOC)
    using an LLM.

    Attributes:
        document_names:
            List of file names to evaluate.
    """

    document_names: list[str]


class ConnectedChunkLLMClassificationActivityParams(BaseModel):
    """Parameters for determining if two chunks are sequentially connected.

    Attributes:
        first_chunk: The content of the preceding text chunk.
        second_chunk: The content of the succeeding text chunk.
    """

    first_chunk: str
    second_chunk: str


class InhaltsverzeichnisClassificationResult(BaseModel):
    """Structured output from the LLM for single chunk classification.

    Attributes:
        reasoning: A brief explanation of why the chunk was classified as global or local.
        is_global_inhalts_verzeichnis: True if the chunk is a Global Table of Contents.
    """

    reasoning: str
    is_global_inhalts_verzeichnis: bool


class FileNameClassificationResult(BaseModel):
    """The structured output expected from the LLM.

    Attributes:
        chosen_file_index (int): The 0-based index of the file in the provided list
            identified as the global Table of Contents (Master Index).
            Returns -1 if no suitable candidate is found.
    """

    chosen_file_index: int


class InhaltsverzeichnisConnectedChunksClassificationResult(BaseModel):
    """Structured output from the LLM for connected chunk classification.

    Attributes:
        are_connected_chunks: True if the second chunk continues the first.
    """

    are_connected_chunks: bool


class InhaltsverzeichnisParsedResult(BaseModel):
    """Container for the extracted Table of Contents structure.

    Attributes:
        entries (List[InhaltsverzeichnisEntry]): A list of all extracted lowest-level elements.
    """

    entries: list[InhaltsverzeichnisEntry] = Field(
        ..., description="Eine Liste der extrahierten untersten Elemente (Leaf Nodes)."
    )


class InhaltsverzeichnisParserActivityInput(BaseModel):
    """
    Input model for the Inhaltsverzeichnis parser activity.

    Attributes:
        chunk_list(List[ChunkOutput]): List of TOC chunks (chunk_id + page_content) that should be
            parsed into the structured Inhaltsverzeichnis representation.
    """

    chunk_list: list[ChunkOutput]


class DocumentTypeDescriptionResult(BaseModel):
    """
    The result of generating a document type description.

    Attributes:
        document_type_description(str): A generated document type description for better matching.
    """

    document_type_description: str = Field(
        ...,
        description=(
            "Eine präzise, diskriminierende Beschreibung des Dokumententyps. "
            "Sie dient dazu, echte PDF-Dokumente später diesem Typ zuzuordnen. "
            "Die Beschreibung sollte den typischen Inhalt (Text, Karte, Tabelle), "
            "den Zweck und spezifische Merkmale erklären. "
            "Wenn ein Match in der Referenzliste gefunden wurde, basiert der Text darauf, "
            "angereichert um spezifische Details aus dem Titel und der Kategorie."
        ),
    )


class DocumentTypeDescriptionGenerationActivityInput(BaseModel):
    """Input parameters for the activity that generates a semantic description for a TOC entry.

    This model encapsulates the data required to prompt an LLM to generate a
    'document_type_description'. It combines the specific entry details extracted
    from the Table of Contents with configuration settings for the LLM execution.

    Attributes:
        hierarchy_path (Optional[List[str]]): The hierarchical path (breadcrumbs) of
            parent chapters leading to this entry (e.g., ["Part B", "Chapter 19"]).
            Used as context to determine the document category. Can be None or empty
            if the entry is at the top level.
        entry_title (str): The specific title of the document or section as found
            in the Table of Contents (e.g., "Erosionsgefährdungskarte").
        entry_number (Optional[str]): The outline number of the element, if present.
            Example: 'A', '1.1', 'III', '2.3.1'.
            If no number is present, this field is null.
        document_types (List[dict]): A list of dictionaries containing document type definitions.
    """

    hierarchy_path: list[str] = Field(default_factory=list)
    entry_title: str
    entry_number: str | None = None
    document_types: list[DocumentTypeDefinitionDict]
