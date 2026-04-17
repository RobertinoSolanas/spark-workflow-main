# src/workflows/schwerpunkt/output_format.py
"""Pydantic models for the Schwerpunkt extraction workflow."""

from pydantic import BaseModel, Field

# --- Classifier Output Models ---


class LLMResponse(BaseModel):
    """The topic ID that best fits the text, as determined by the LLM."""

    topic_id: int = Field(description="The exact ID of the topic that is defined in the topics list.")
    confidence: str = Field(description="Confidence level: 'high', 'medium', or 'low'")
    reasoning: str = Field(description="Brief explanation of why this topic was chosen")


class BatchedClassificationResponse(BaseModel):
    """Response containing classifications for multiple text chunks."""

    classifications: list[LLMResponse]


# --- Schwerpunkt Metadata Output Model ---


class SchwerpunktMetadata(BaseModel):
    """Schema for Schwerpunktthema classification result."""

    focus_topic: str = Field(
        ...,
        description="Das zentrale Thema des Textabschnitts, zusammengefasst in 2-7 Wörtern. Überschriften geben häufig bereits einen Hinweis auf das Thema, um das es geht.",
    )
