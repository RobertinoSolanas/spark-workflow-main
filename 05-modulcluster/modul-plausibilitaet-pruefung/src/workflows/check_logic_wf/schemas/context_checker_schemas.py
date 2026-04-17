from pydantic import BaseModel, Field

from src.dms.schemas import BaseMetadata, ProjectBaseMetadataStatus


class ContextCheckerInput(BaseModel):
    """Input for context-level conflict checking of one claim pair."""

    project_id: str = Field(description="Project scope used for DMS/Qdrant lookups.")
    document_id: str = Field(description="Document currently being processed.")
    claim_id: str = Field(description="Primary claim ID from risk screening.")
    reference_claim_id: str = Field(description="Reference claim ID from risk screening.")
    screening_note: str = Field(description="Screener note used as a weak hint for contextual verification.")


class ChunkWithContext(BaseModel):
    """Chunk text plus bounded neighboring context used by the LLM."""

    chunk_text: str = Field(description="Main chunk content containing the claim.")
    preceding_text: str = Field(description="Concatenated preceding context in document reading order.")
    following_text: str = Field(description="Concatenated following context.")
    page_numbers: list[int] = Field(description="Page numbers associated with the base chunk.")
    document_name: str | None = Field(description="Human-readable source document title, if available.")
    toc_path: list[str] | None = Field(
        description="TOC path of the base chunk used for section-aware context filtering."
    )


class ContextCheckerLLMInput(BaseModel):
    """Prompt payload for the first-pass conflict checker LLM."""

    project_base_md: BaseMetadata = Field(
        description="Project metadata constraints relevant for contradiction checking."
    )
    project_base_md_status: ProjectBaseMetadataStatus = Field(
        description="Whether project metadata is complete or an explicit unknown fallback."
    )
    chunk_a: ChunkWithContext = Field(description="Context window for the first claim.")
    chunk_b: ChunkWithContext = Field(description="Context window for the second claim.")
    screening_note: str = Field(description="Screener handoff note.")


class ContextCheckVerdict(BaseModel):
    """Contradiction verdict produced by checker or verifier LLM."""

    rating: int = Field(
        ge=0,
        le=100,
        description="Contradiction severity between the two claims (0 = none, 100 = strong).",
    )
    title: str = Field(
        description="Short title describing the identified contradiction.",
        min_length=5,
        max_length=200,
    )
    explanation: str = Field(
        description="Detailed reasoning from the LLM about the identified contradiction.",
        min_length=20,
        max_length=5000,
    )
    chunk_a_excerpt: str = Field(
        description="Short excerpt from chunk_a that contains the relevant information for the contradiction.",
        min_length=5,
        max_length=500,
    )
    chunk_b_excerpt: str = Field(
        description="Short excerpt from chunk_b that contains the relevant information for the contradiction.",
        min_length=5,
        max_length=500,
    )


class VerificationInput(BaseModel):
    """Prompt payload for the verifier LLM that audits the initial verdict."""

    project_md: BaseMetadata = Field(description="Project metadata constraints used during verification.")
    project_md_status: ProjectBaseMetadataStatus = Field(
        description="Whether project metadata is complete or an explicit unknown fallback."
    )
    chunk_a: ChunkWithContext = Field(description="Context window for the first claim.")
    chunk_b: ChunkWithContext = Field(description="Context window for the second claim.")
    original_verdict: ContextCheckVerdict = Field(description="Initial checker verdict to be audited/adjusted.")


class VerificationOutput(BaseModel):
    """Verifier output containing corrected verdict and explanation."""

    updated_verdict: ContextCheckVerdict = Field(description="Verified or adjusted contradiction verdict.")
    explanation: str = Field(
        min_length=20,
        max_length=5000,
        description="Audit-Ergebnis: Welche Regeln verletzt wurden (falls), welche Aussagen nicht belegt sind, und warum das Rating angepasst wurde.",
    )


class ContextCheckerOutput(BaseModel):
    """Result of context checking and optional verification for one claim pair."""

    chunk_a_id: str = Field(description="Chunk ID for the primary claim.")
    chunk_b_id: str = Field(description="Chunk ID for the reference claim.")
    claim_a_id: str = Field(description="Claim ID for the primary claim (echoed from input).")
    claim_b_id: str = Field(description="Claim ID for the reference claim (echoed from input).")

    chunk_a_context: ChunkWithContext = Field(description="Full context payload for chunk A (traceability/auditing).")
    chunk_b_context: ChunkWithContext = Field(description="Full context payload for chunk B (traceability/auditing).")

    original_verdict: ContextCheckVerdict = Field(description="Raw first-pass checker verdict before verifier review.")
    updated_verdict: ContextCheckVerdict | None = Field(
        default=None,
        description=(
            "Verifier-adjusted verdict. `None` when the original rating stayed below the verification threshold."
        ),
    )

    is_verified_inconsistency: bool = Field(
        description="Indicates whether the context checker identified an inconsistency between the two text passages based on the defined threshold."
    )

    verification_explanation: str | None = Field(
        default=None,
        description="Explanation from the verifier LLM about why the original verdict was confirmed or adjusted. Only provided if a verification was performed.",
    )

    screening_note: str = Field(
        description=("Original screener note included for traceability; not a reliable decision signal by itself.")
    )
