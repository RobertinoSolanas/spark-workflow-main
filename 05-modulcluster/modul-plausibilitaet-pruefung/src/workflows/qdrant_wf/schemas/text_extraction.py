
from pydantic import BaseModel, Field


class ClaimQuotes(BaseModel):
    claim_quotes: list[str] = Field(
        ...,
        description="Liste der exakt wörtlich extrahierten Key-Claims aus dem Quelltext. "
        "Keine Umformulierungen, keine Korrekturen.",
    )


class TextKeyClaimExtraction(BaseModel):
    claim_quotes: ClaimQuotes
    claims: list[str] = Field(
        ...,
        description="Eine Liste von präzisen, atomaren und selbsterklärenden Key-Claims",
    )


class TextClaimFormulation(BaseModel):
    claims: list[str] = Field(
        ...,
        description="Eine Liste von präzisen, atomaren und selbsterklärenden Key-Claims",
    )
