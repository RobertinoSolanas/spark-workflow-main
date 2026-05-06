# src/workflows/species_scale/__init__.py
"""Species and Scale extraction workflow module.

Note: Workflow classes are imported directly from workflow.py to avoid circular imports.
Activities import from output_format.py, so we don't re-export workflow here.
"""

from src.workflows.species_scale.output_format import (
    BatchedSpeciesAndScaleResponse,
    SpeciesAndScaleResult,
)
from src.workflows.species_scale.prompt import (
    BATCHED_SPECIES_SCALE_SYSTEM_PROMPT,
    BATCHED_SPECIES_SCALE_USER_TEMPLATE,
    SPECIES_SCALE_SYSTEM_PROMPT,
    SPECIES_SCALE_USER_TEMPLATE,
)

__all__ = [
    "BatchedSpeciesAndScaleResponse",
    "SpeciesAndScaleResult",
    "BATCHED_SPECIES_SCALE_SYSTEM_PROMPT",
    "BATCHED_SPECIES_SCALE_USER_TEMPLATE",
    "SPECIES_SCALE_SYSTEM_PROMPT",
    "SPECIES_SCALE_USER_TEMPLATE",
]
