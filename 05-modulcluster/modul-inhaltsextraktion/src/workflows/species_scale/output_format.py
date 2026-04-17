# src/workflows/species_scale/output_format.py
"""Pydantic models for the Species/Scale extraction workflow."""

from pydantic import BaseModel, Field


class SpeciesAndScaleResult(BaseModel):
    """Schema for extracting species and scale information from a text chunk."""

    wildlife_mentioned: bool = Field(default=False, description="True if any wildlife species are mentioned by name.")
    plant_species_mentioned: bool = Field(default=False, description="True if any plant species are mentioned by name.")
    wildlife_species: list[str] = Field(
        default_factory=list,
        description="A list of specific wildlife species mentioned by name (e.g., 'Feldhase', 'Rotmilan').",
    )
    plant_species: list[str] = Field(
        default_factory=list,
        description="A list of specific plant species mentioned by name (e.g., 'Eiche', 'Acker-Schmalwand').",
    )
    map_scale: str | None = Field(
        None,
        description="The scale, if one is mentioned in the text (e.g., '1:250', '1:1000').",
    )


class BatchedSpeciesAndScaleResponse(BaseModel):
    """Response containing species/scale extractions for multiple text chunks."""

    extractions: list[SpeciesAndScaleResult]
