"""Output formats for the summarization workflow."""

from pydantic import BaseModel, Field


class SummaryOutput(BaseModel):
    """Pydantic model for the final summary output."""

    summary: str = Field(
        ...,
        description="Die generierte Zusammenfassung des Dokuments als einfacher String.",
    )

    class Config:
        # Helps with JSON serialization
        json_schema_extra = {"example": {"summary": "Dies ist eine Beispielzusammenfassung des Dokuments."}}
