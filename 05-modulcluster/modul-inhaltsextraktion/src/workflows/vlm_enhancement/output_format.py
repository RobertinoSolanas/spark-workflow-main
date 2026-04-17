# src/workflows/vlm_enhancement/output_format.py
"""
Pydantic models for the VLM enhancement workflow.

This module contains all input/output models for the VLM enhancement workflow:
- Workflow I/O models (VLMWorkflowInput, VLMWorkflowOutput)
- LLM analysis output (VlmAnalysis)
"""

from pydantic import BaseModel, Field
from temporal import Base64Bytes

# --- Workflow I/O Models ---


class VLMWorkflowInput(BaseModel):
    """
    Input for the VLMWorkflow.
    """

    element_type: str  # 'image' or 'table'
    image_ref: str  # Reference in markdown (e.g., 'images/foo.png')
    image_data: Base64Bytes
    context_text: str
    # For replacement: use raw_html if available (tables), otherwise full_tag (images)
    full_tag: str | None = None  # The markdown tag for images, e.g. '![alt](images/foo.png)'
    raw_html: str | None = None  # For tables: the HTML content to replace


class VLMWorkflowOutput(BaseModel):
    """Output for the VLMWorkflow."""

    original_content: str
    replacement_block: str


class VLMExtractDescribeOutput(BaseModel):
    """Intermediate result from extract+describe phase (before summarize).

    Does not carry image_data -- image bytes are only needed for the VLM
    calls, not the text-based summary that follows.
    """

    image_ref: str
    element_type: str
    extraction_result: str
    description_result: str
    context_text: str
    full_tag: str | None = None
    raw_html: str | None = None
    extraction_hallucinated_by_size: bool = False
    description_hallucinated_by_size: bool = False


# --- LLM Analysis Output ---


class VlmAnalysis(BaseModel):
    """
    Schema for the structured output of the VLM/LLM analysis pipeline.
    Includes a summary and quality control flags for hallucination detection.

    Note: Boolean fields have defaults to handle models that may not return all fields.
    """

    summary: str = Field(
        ...,
        description="The final, synthesized summary of the image or table, explaining its purpose and main message in the context of the document.",
    )
    extraction_is_hallucinated: bool = Field(
        default=False,
        description="Set to True if the extracted content appears to be hallucinated, nonsensical, or contains bizarre, nonsensical repetitions. Otherwise, set to False.",
    )
    description_is_hallucinated: bool = Field(
        default=False,
        description="Set to True if the visual description appears to be hallucinated, nonsensical, or factually incorrect based on the other provided context. Otherwise, set to False.",
    )
    caption: str | None = Field(
        default=None,
        description="The caption for the image or table, if present in the surrounding text. Typically appears before the content.",
    )
    footnote: str | None = Field(
        default=None,
        description="The footnote for the image or table, if present in the surrounding text. Typically appears after the content.",
    )


# --- Batch Processing Wrapper Models ---


class VLMProcessingWorkflowInput(BaseModel):
    """Input wrapper for the VLM batch processing child workflow."""

    vlm_inputs: list[VLMWorkflowInput]


class VLMProcessingWorkflowOutput(BaseModel):
    """Output wrapper from the VLM batch processing child workflow."""

    vlm_results: list[VLMWorkflowOutput]
