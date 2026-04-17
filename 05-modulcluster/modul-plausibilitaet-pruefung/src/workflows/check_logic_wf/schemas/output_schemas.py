from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ContradictionStatus(str, Enum):
    """Lifecycle state exposed to downstream consumers."""

    OPEN = "OPEN"
    CLOSED = "CLOSED"


class Occurrence(BaseModel):
    """One document-local occurrence supporting a contradiction."""

    model_config = ConfigDict(populate_by_name=True)

    document_id: str = Field(
        alias="documentId",
        description="Identifier of the document containing the claim.",
    )
    document_name: str | None = Field(
        alias="documentName",
        description="Human-readable title of the document.",
    )
    content_excerpt: str = Field(
        alias="contentExcerpt",
        description="Text excerpt illustrating the contradiction.",
    )
    contradiction: str = Field(
        description="Description of the contradiction identified in this occurrence."
    )
    page_number: int | None = Field(
        default=None,
        alias="pageNumber",
        description="Page number where the excerpt appears, if available.",
    )


class Contradiction(BaseModel):
    """Top-level contradiction entity produced for one clustered inconsistency."""

    id: str = Field(description="Workflow-generated unique contradiction identifier.")
    title: str = Field(
        description=(
            "Short title summarizing the contradiction, ideally in a way that is "
            "understandable even without reading the full explanation."
        )
    )
    description: str = Field(
        description="Detailed contradiction explanation from the cluster summarizer."
    )
    status: ContradictionStatus = Field(
        description="Current lifecycle state of this contradiction."
    )
    occurrences: list[Occurrence] = Field(
        default_factory=list,
        description="Concrete document occurrences supporting this contradiction.",
    )


class DocumentOutput(BaseModel):
    """Document-level output payload uploaded as the temporal checkpoint."""

    contradictions: list[Contradiction] = Field(
        description="Contradictions identified for the processed document."
    )
