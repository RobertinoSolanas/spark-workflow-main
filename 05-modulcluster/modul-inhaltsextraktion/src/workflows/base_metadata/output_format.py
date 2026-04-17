# src/workflows/metadata_extraction/base/base_metadata_output_format.py
"""Pydantic models for LLM-facing metadata extraction (evidence gathering and consolidation).

The final BaseMetadata output model lives in the shared services package:
    temporal.workflows.inhaltsextraktion.types.BaseMetadata
"""

from typing import Any

from pydantic import BaseModel, Field


class ValueWithEvidence(BaseModel):
    """A container for a value and the source text that justifies it."""

    value: Any = Field(..., description="The extracted value for a metadata field.")
    source: str = Field(
        ...,
        description="The exact text snippet from the document that justifies the extracted value.",
    )


class BaseMetadataWithEvidence(BaseModel):
    """A temporary schema to hold extracted metadata with its evidence before consolidation."""

    project_applicant: ValueWithEvidence | None = None
    planned_project: ValueWithEvidence | None = None
    project_location: ValueWithEvidence | None = None
    affected_municipalities: ValueWithEvidence | None = None
    affected_federal_states: ValueWithEvidence | None = None
    planning_company: ValueWithEvidence | None = None
    application_subject: ValueWithEvidence | None = None
    pipeline_length: ValueWithEvidence | None = None
    pipeline_diameter: ValueWithEvidence | None = None
    application_receipt_date: ValueWithEvidence | None = None
    responsible_planning_authority: ValueWithEvidence | None = None


class LlmConsolidatedMetadata(BaseModel):
    """A schema for the consolidated metadata from the LLM, before system fields are added."""

    project_applicant: str | None = Field(
        None,
        description="Der Vorhabensträger, wenn möglich mit Bundesland. Zum Beispiel: 'Landesdirektion Sachsen'.",
    )
    planned_project: str | None = Field(None, description="Das konkret geplante Vorhaben.")
    project_location: str | None = Field(None, description="Der Ort, wo das geplante Vorhaben ausgeführt wird.")
    affected_municipalities: list[str] = Field(
        default_factory=list,
        description="Alle Städte und Gemeinden die vom Vorhaben betroffen sind. Keine Bundesländer hier.",
    )
    affected_federal_states: list[str] = Field(
        default_factory=list,
        description="Alle Bundesländer die vom Vorhaben betroffen sind, z.B. 'Bayern', 'Sachsen'.",
    )
    planning_company: str | None = Field(None, description="Der Generalplaner des Vorhabens.")
    application_subject: str | None = Field(
        None,
        description="Der Antragsgegenstand. Extrahiere hier bitte den vollständigen Text, der diesen beschreibt. Also zum Beispiel Anlagen- und Nebenanlagen, die dazu gehören.",
    )
    pipeline_length: str | None = Field(None, description="Die Gesamtlänge der Leitung in km.")
    pipeline_diameter: str | None = Field(
        None,
        description="Der Durchmesser der Leitung, falls im Text erwähnt (z.B. 'DN400'). Häufig auch Leitungsdimension genannt.",
    )
    application_receipt_date: str | None = Field(
        None,
        description="Das Datum des Antragseingangs, falls im Text erwähnt. Häufig in einer Fußnote wie 'Stand: 12.04.2023'.",
    )
    responsible_planning_authority: str | None = Field(
        None,
        description="Die zuständige Behörde für das Planfeststellungsverfahren. Hier ist der genaue Name der Behörde wichtig.",
    )
