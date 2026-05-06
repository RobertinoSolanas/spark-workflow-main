"""Consolidated type definitions for all formale_pruefung workflows.

This module contains all Pydantic models and TypedDicts used as inputs and outputs
for the LLM matching, Inhaltsverzeichnis finder, and Inhaltsverzeichnis matching workflows.
"""

from datetime import datetime
from typing import Literal, TypedDict

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Shared types (used across multiple workflows)
# ---------------------------------------------------------------------------


# TODO Import this from the DMSClient if the shared package is created or not use it here
class DMSFileResponse(BaseModel):
    """Pydantic model representing a file response from the DMS API.

    This model encapsulates the metadata and storage information for a file
    managed within the Document Management System (DMS), including its
    physical location in storage and its association with specific projects
    and workflow executions.

    Attributes:
        id: Unique identifier for the file entry.
        type: The category or classification of the document.
        filename: The original name of the uploaded file.
        bucketPath: The storage path or URI where the file is located.
        projectId: ID of the project the file belongs to.
        mimeType: The IANA media type of the file (e.g., 'application/pdf').
        workflowId: ID of the workflow that processed or generated this file.
        runId: Specific execution ID of the workflow run.
        vectorSearchable: Indicates if the file has been indexed for vector search.
        createdAt: Timestamp of when the file record was created.
        updatedAt: Timestamp of the last update to the file record.
    """

    id: str
    type: str
    filename: str
    bucketPath: str
    projectId: str
    mimeType: str | None = None
    workflowId: str | None = None
    runId: str | None = None
    vectorSearchable: bool | None = None
    createdAt: datetime | None = Field(default_factory=datetime.now)
    updatedAt: datetime | None = Field(default_factory=datetime.now)


class DocumentTypeDefinitionDict(TypedDict):
    """
    Represents the schema for a document type definition dictionary.
    Attributes:
        category: An optional grouping label for the document.
        document_type_name: The title of the document type.
        document_type_description: A detailed explanation of the document's purpose.
    """

    category: str | None = None
    document_type_name: str
    document_type_description: str


class DocumentTypeDefinition(BaseModel):
    """Schema for defining a document type for matching.
    This model holds the metadata for a specific document type found in the
    requirements list, including its category, official name, and a semantic
    description used for the matching logic.
    Attributes:
        category (Optional[str]): The supercategory (e.g., 'Environmental Part')
            for better structuring.
        document_type_name (str): The official designation of the document
            (e.g., 'Explanatory Report').
        document_type_description (str): A concise description of the document's
            content and purpose, used for semantic matching.
    """

    category: str | None = None
    document_type_name: str
    document_type_description: str


# ---------------------------------------------------------------------------
# LLM Matching types
# ---------------------------------------------------------------------------


class ExternalDocumentType(TypedDict):
    """
    Defines a document type within a External document structure.
    Attributes:
        name: The human-readable name of the document type.
        id: A unique identifier for the document type.
        required: Specifies whether the document is mandatory.
        contentRequirements: A description of what the document must contain. This is injected in to the classification
            prompt
    """

    name: str
    id: str
    required: bool
    contentRequirements: str


class ExternalDocumentCategory(TypedDict):
    """
    Represents a major category of the External document types.
    Attributes:
        name: The name of the document category.
        children: A list of ExternalDocumentType dictionaries within this category.
    """

    name: str
    children: list[ExternalDocumentType]


class LLMMatchingParams(BaseModel):
    """Configuration parameters for the LLM matching workflow.
    Attributes:
        project_id (str): The unique identifier of the project.
        document_types (List[dict]): A list of dictionaries containing document type definitions.
        document_ids (Optional[List[str]]): A list of DMS document_ids if given only these
            files are classified. The document grouping is still done across all files,
            but the remaining classification only for the given files.
        external_preprocessing (bool): Flag indicating whether to apply preprocessing steps
            to the input data. Defaults to False.
    """

    project_id: str
    document_types: list[DocumentTypeDefinitionDict | ExternalDocumentCategory]
    document_ids: list[str] | None = None
    external_preprocessing: bool = False


class DocumentOutput(BaseModel):
    """Final output representation of an assigned document within a category.
    Attributes:
        document_name (str): The name of the document file.
        document_id (str): Unique identifier for the document.
        document_extraction_id: Unique DMS identifier for the extracted _processed.json
        reasoning (str): The explanation provided by the LLM for this assignment.
        confidence (float): The confidence score (0.0 to 1.0) of the assignment.
    """

    document_name: str
    document_id: str
    document_extraction_id: str
    reasoning: str
    confidence: float


class MatchedDocumentTypeOutput(BaseModel):
    """Represents a specific document type definition and the files assigned to it.
    Attributes:
        required_document_type (DocumentTypeDefinition): The definition of the
            document type from the requirements list.
        assigned_documents (List[DocumentOutput]): A list of structured
            outputs for documents that have been matched to this document type.
        confidence (float): The confidence score (0.0 to 1.0) of all assignments
            for this document type.
    """

    required_document_type: DocumentTypeDefinition
    assigned_documents: list[DocumentOutput]
    confidence: float


class LLMMatchingOutput(BaseModel):
    """The final output of the LLM matching workflow.
    Attributes:
        matched_document_types (List[MatchedDocumentTypeOutput]): A list of
            document types that were successfully matched with one or more files.
        unassigned_documents (List[DocumentOutput]): A list of structured
            outputs for documents that could not be confidently matched to any document type
            in the definition list.
    """

    matched_document_types: list[MatchedDocumentTypeOutput]
    unassigned_documents: list[DocumentOutput]


# ---------------------------------------------------------------------------
# Inhaltsverzeichnis Finder types
# ---------------------------------------------------------------------------


class InhaltsverzeichnisEntry(BaseModel):
    """Represents a single 'leaf' entry (the lowest hierarchical level) extracted from a Table of Contents.

    This model captures the specific document or section name (title) and preserves
    the structural context by capturing the path of parent headers as a list.

    Attributes:
        hierarchy_path (Optional[List[str]]): The 'path' of parent headings leading up to this element,
            EXCLUDING the title of the element itself. Parent levels are added as items in order.
            Example: If the line '3.1 Results' is under 'Chapter 3: Environment' and 'Part B',
            the path is: ['Part B', 'Chapter 3: Environment'].
            If there are no parent levels (top-level item), this field is null or empty.
        entry_title (str): The specific title or text of the entry as it appears in the TOC.
            Exclude outline numbers (e.g., '1.1') and page numbers.
            Example: From '1.1 Project Description ....... 5', extract only 'Project Description'.
        entry_number (Optional[str]): The outline number of the element, if present.
            Example: 'A', '1.1', 'III', '2.3.1'.
            If no number is present, this field is null.
    """

    hierarchy_path: list[str] = Field(default_factory=list)
    entry_title: str
    entry_number: str | None = None


class ChunkOutput(BaseModel):
    """Represents a specific segment of text identified as part of the Table of Contents.

    Attributes:
        chunk_id: Unique identifier for this specific chunk.
        page_content: The actual text content of the chunk.
    """

    chunk_id: str
    page_content: str


class InhaltsverzeichnisDocumentData(BaseModel):
    """Container for metadata and text segments of a document identified as a Table of Contents.

    Attributes:
        document_id (str): The unique identifier of the source document in the system.
        document_name (str): The original filename of the document containing the TOC.
        chunks (List[ChunkOutput]): A list of extracted text chunks that form the TOC content.
    """

    document_id: str
    document_name: str
    chunks: list[ChunkOutput]


class InhaltsverzeichnisFinderParams(BaseModel):
    """
    Input parameters for the Table-of-Contents (Inhaltsverzeichnis) finder workflow.

    Attributes:
        project_id (str): ID of the project whose documents should be scanned.
        document_types (List[dict]): A list of dictionaries containing document type definitions.
    """

    project_id: str
    document_types: list[DocumentTypeDefinitionDict]


class InhaltsverzeichnisFinderOutput(BaseModel):
    """The standardized output object returned by the Table of Contents processing workflow.

    Attributes:
        status (Literal["success", "no_inhaltsverzeichnis_found"]): The execution result status.
        metadata (Optional[InhaltsverzeichnisDocumentData]): Source metadata and text chunks.
        document_types (Optional[List[DocumentTypeDefinition]]): Final enriched document definitions.
        inhaltsverzeichnis_entries (Optional[List[InhaltsverzeichnisEntry]]): Raw entries extracted from text.
    """

    status: Literal["success", "no_inhaltsverzeichnis_found"]
    metadata: InhaltsverzeichnisDocumentData | None = None
    document_types: list[DocumentTypeDefinition] | None = None
    inhaltsverzeichnis_entries: list[InhaltsverzeichnisEntry] | None = None


# ---------------------------------------------------------------------------
# Inhaltsverzeichnis Matching types
# ---------------------------------------------------------------------------


class InhaltsverzeichnisMatchingParams(BaseModel):
    """Input parameters for the InhaltsverzeichnisMatchingWorkflow.

    This model defines the configuration required to start the orchestration workflow,
    including the target project scope and execution policies for timeouts and retries.

    Attributes:
        project_id (str): The unique identifier of the project to be processed.
            This ID is used to scope the workflow execution and fetch relevant
            documents from the DMS.
        document_types (List[dict]): A list of dictionaries containing document type definitions.
    """

    project_id: str
    document_types: list[DocumentTypeDefinitionDict]


class InhaltsverzeichnisMatchingOutput(BaseModel):
    """The composite result object for the entire matching pipeline.

    This model aggregates the outputs from the two main stages of the workflow:
    the extraction of the Table of Contents and the subsequent matching of documents
    based on the extracted types.

    Attributes:
        inhaltsverzeichnis_extraction_output (InhaltsverzeichnisExtractionOutput): The
            structured output from the TOC finder workflow, containing metadata and
            extracted document definitions.
        inhaltsverzeichnis_matching_output (LLMMatchingOutput): The final
            output from the matching workflow, containing lists of documents that
            were successfully assigned to a type and those that remained unassigned.
    """

    inhaltsverzeichnis_extraction_output: InhaltsverzeichnisFinderOutput
    inhaltsverzeichnis_matching_output: LLMMatchingOutput
