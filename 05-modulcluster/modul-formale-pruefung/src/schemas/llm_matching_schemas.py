"""
Schemas for LLM-based document type matching within the FVP context.
"""

from pydantic import BaseModel, Field
from temporal.workflows.formale_pruefung.types import DocumentTypeDefinition

from src.schemas.dms_schemas import DMSDocument, DMSInhaltsExtraction


class DocumentSummaryGenerationResult(BaseModel):
    """Represents the result of document summarization for classification purposes.
    This model defines the expected output structure from the LLM when it is tasked
    with generating a concise summary optimized for matching against a predefined
    list of document types.
    Attributes:
        summary_for_classification (str): A precise summary of the document that
            explicitly addresses the type (e.g., plan, report, table) and content
            (e.g., environmental, technical, legal) to enable matching against
            the defined document list.
    """

    summary_for_classification: str


class DocumentGroup(BaseModel):
    """Represents a logical group of documents identified by the LLM using indices.
    A group consists of multiple files that belong together (e.g., a main report
    and its appendices) and a designated representative file used for classification.
    References are made via indices into the original file list.
    Attributes:
        group_name (str): A descriptive name for the group (e.g., "Kapitel 19.1 Bodenschutz").
        document_indices (List[int]): The list of indices from the input list belonging to this group.
        representative_index (int): The index of the file chosen as the best representative
            for the group.
    """

    group_name: str
    document_indices: list[int]
    representative_index: int


class DocumentGroupingResult(BaseModel):
    """The result of the document grouping task using indices.
    Attributes:
        groups (List[DocumentGroup]): A list of all identified document groups.
            Every input document index must be assigned to exactly one group.
    """

    groups: list[DocumentGroup]


class ClassificationSummaryActivityParams(BaseModel):
    """Input parameters for the classification summary generation activity.
    Attributes:
        document_name (str): The filename of the document.
        document_summary (str): The existing generic summary of the document.
        chunk (str): Text content from the first few pages of the document.
    """

    document_name: str
    document_summary: str
    chunk: str


class DocumentGroupingActivityParams(BaseModel):
    """Input parameters for the document grouping activity.
    Attributes:
        document_names (List[str]): A list of unsorted filenames that need to be
            grouped logically (e.g., based on prefixes, chapters, or appendices).
    """

    document_names: list[str]


class DocumentData(BaseModel):
    """Result model containing filtered document chunks and metadata.
    Attributes:
        dms_doc (DMSDocument): DMS document identifier and info
        should_classify (bool): Determines if the document requires ML classification
        inhalts_extraction (Optional[DMSInhaltsExtraction]): Inhalts extraction data from DMS
        classification_summary (Optional[str]): The specialized summary generated
            specifically for the classification step.
        document_group (Optional[str]): The name of the logical group or folder
            context assigned to the document (e.g., "Kapitel 19.1 Bodenschutz").
            Defaults to None.
        assigned_document_type (Optional[DocumentTypeDefinition]): The full definition of the
            document type to which the file was matched.
        reasoning (Optional[str]): The explanation provided by the LLM for why this
            specific assignment was made.
        confidence (Optional[float]): The confidence score (0.0 to 1.0) of the assignment.
    """

    dms_doc: DMSDocument
    should_classify: bool
    inhalts_extraction: DMSInhaltsExtraction | None = None
    classification_summary: str | None = None
    document_group: str | None = None
    assigned_document_type: DocumentTypeDefinition | None = None
    reasoning: str | None = None
    confidence: float | None = None


class DocumentClassificationMatchResult(BaseModel):
    """Result of matching a single document against a candidate list.
    Attributes:
        reasoning (str): A brief explanation for the decision, detailing why
            the filename and/or summary match the selected description (or why
            no match was found).
        confidence (float): A score between 0.0 and 1.0 indicating how certain
            the model is about the match.
        match_index (int): The 0-based index of the matching element from the
            candidate list. Returns -1 if no match is found or the result is uncertain.
    """

    reasoning: str
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
    )
    match_index: int


class DocumentMatchingActivityParams(BaseModel):
    """Input parameters for the document matching activity.
    Attributes:
        document_name (str): The filename of the document.
        document_summary (str): The specialized classification summary of the document.
        document_group (Optional[str]): The name of the logical group or folder
            context assigned to the document (e.g., "Kapitel 19.1 Bodenschutz").
            Defaults to None.
        candidate_list (List[DocumentTypeDefinition]): The list of candidate
            document types to be formatted and passed to the LLM.
    """

    document_name: str
    document_summary: str
    document_group: str | None = None
    candidate_list: list[DocumentTypeDefinition]


class UnassignedDocumentAnalysisParams(BaseModel):
    """Parameters for analyzing an unassigned document.
    Attributes:
        document_name: The name of the document being analyzed.
        document_summary: A brief summary of the document's content.
        reasoning_history: A list of reasoning traces explaining why previous
            classification attempts failed.
    """

    document_name: str
    document_summary: str
    reasoning_history: list[str]


class UnassignedDocumentReason(BaseModel):
    """
    The final diagnosis of why a document could not be categorized,
    derived from its content summary and a history of rejection reasons.
    Attributes:
        reasoning: A concise, single-paragraph synthesis of the reasoning history.
        confidence: A confidence score from 0.0 to 1.0 indicating the certainty of the diagnosis.
    """

    reasoning: str
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
    )
