# src/workflows/hypothetical_questions/output_format.py
"""Pydantic models for the Hypothetical Questions extraction workflow."""

from pydantic import BaseModel, Field


class HypotheticalQuestionsResult(BaseModel):
    """LLM output: list of hypothetical questions for a chunk."""

    questions: list[str] = Field(
        default_factory=list,
        max_length=3,
        description="Liste von bis zu 3 Fragen, die der Textabschnitt beantworten kann.",
    )


class BatchedHypotheticalQuestionsResponse(BaseModel):
    """Response containing hypothetical questions for multiple text chunks."""

    results: list[HypotheticalQuestionsResult]
