
from pydantic import BaseModel, Field


class TableRows(BaseModel):
    rows: list[list[str]] = Field(
        ...,
        description="Eine Liste aller Zeilen, wobei jede Zeile eine Liste ihrer Zellwerte ist.",
    )

class TableExtractionResponse(BaseModel):
    header: list[str] = Field(
        ..., description="Die exakten Spaltenüberschriften der Tabelle."
    )
    rows: list[list[str]] = Field(
        ...,
        description="Eine Liste aller Zeilen, wobei jede Zeile eine Liste ihrer Zellwerte ist.",
    )

class ParsedTable(BaseModel):
    chunk_id: str = Field(description="Unique identifier for the specific text chunk.")
    raw_content: str = Field(
        description="Der unstrukturierte Inhalt der Tabelle, wie er im Dokument vorlag."
    )
    header: list[str] = Field(
        ..., description="Die exakten Spaltenüberschriften der Tabelle."
    )
    rows: list[list[str]] = Field(
        ...,
        description="Eine Liste aller Zeilen, wobei jede Zeile eine Liste ihrer Zellwerte ist.",
    )
    title: str = Field(..., description="Der Titel des Dokumentes")


class TableKeyClaimExtraction(BaseModel):
    table_extraction: ParsedTable
    claims: list[str] = Field(
        ...,
        description="Eine Liste von präzisen, atomaren und selbsterklärenden Key-Claims",
    )
