from pydantic import BaseModel, Field


class ScreeningCandidateBundle(BaseModel):
    """Data structure representing the input for one screening run of the RiskScreener LLM agent."""

    project_id: str = Field(description="Project scope used for Qdrant collections.")
    document_id: str = Field(description="Document containing the check claim.")
    claim_id: str = Field(description="ID of the claim currently being screened.")
    reference_claims: list[str] = Field(description="Candidate reference claim IDs evaluated against `claim_id`.")


class ScreeningHit(BaseModel):
    """Intermediate screening result indicating risky claim pairings."""

    claim_id: str = Field(description="Claim being screened.")
    reference_id: str = Field(description="Reference claim judged as potentially risky.")
    rating: int = Field(
        ge=0,
        le=100,
        description="Risk score for the pair as returned by the screener LLM.",
    )
    note: str = Field(description="Compact handoff note for downstream context checking.")
    reasoning: str = Field(description="Detailed rationale for auditability and debugging.")


class ScreeningBundleResult(BaseModel):
    """Screening outcome for one check claim and its reference candidates."""

    hits: list[ScreeningHit] = Field(description="Pairs whose screener rating met the configured threshold.")


class RiskScreenerItem(BaseModel):
    """Value of the screener output dictionary for one reference_id."""

    rating: int = Field(
        ...,
        ge=0,
        le=100,
        description="Risikobewertung einer möglichen Inkonsistenz (0..100).",
    )
    note: str = Field(
        ...,
        min_length=1,
        description=(
            "Kompakte, neutrale Arbeitsnotiz für die nachfolgende Kontextprüfung "
            "(inkl. Unsicherheiten/fehlender Kontext/Prüffragen) als Freitext."
        ),
    )
    reasoning: str = Field(
        ...,
        min_length=10,
        description=("Begründung für die Risikobewertung als Freitext zwecks Nachvollziehbarkeit und Fehleranalyse."),
    )


class RiskScreenerResponse(BaseModel):
    """Screener result keyed by original reference claim IDs."""

    screening_result_dict: dict[str, RiskScreenerItem] = Field(
        ...,
        description="Dictionary mapping the reference claim ID's to the corresponding screening result.",
    )


class RiskScreenerIndexedResponse(BaseModel):
    """Screener result keyed by prompt-local 1-based reference indices."""

    screening_result_dict: dict[int, RiskScreenerItem] = Field(
        ...,
        description="Dictionary mapping 1-based reference indices to screening results.",
    )


class RiskScreenerReferencePromptItem(BaseModel):
    """Prompt item for one reference claim in index-based form."""

    reference_id: int = Field(description="1-based index used in the prompt and LLM response.")
    claim_text: str = Field(description="Reference claim text shown to the LLM.")


class RiskScreenerPromptPayload(BaseModel):
    """JSON payload rendered into the screener user prompt."""

    check_claim_text: str = Field(description="Text of the claim under evaluation.")
    reference_claims: list[RiskScreenerReferencePromptItem] = Field(
        description="Indexed reference claims to compare against `check_claim_text`."
    )


class DocumentBundleRequest(BaseModel):
    """Input for building screening bundles for all claims in a document at once."""

    project_id: str = Field(description="Project scope used for Qdrant collections.")
    document_id: str = Field(description="Document whose claims are screened.")
    claim_ids: list[str] = Field(description="Ordered list of claim IDs to build bundles for.")


class DocumentBundleResult(BaseModel):
    """Raw (pre-deduplication) screening bundles for all claims in a document."""

    bundles: list[ScreeningCandidateBundle] = Field(
        description="One bundle per claim in the same order as the input claim_ids."
    )
