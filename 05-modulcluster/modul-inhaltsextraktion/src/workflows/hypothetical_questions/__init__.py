# src/workflows/hypothetical_questions/__init__.py
"""Hypothetical questions extraction workflow package."""

# Note: Workflow classes are imported directly from workflow.py to avoid circular imports
# with activities. Only import models that don't depend on activities here.

from src.workflows.hypothetical_questions.output_format import (
    HypotheticalQuestionsResult,
)
from src.workflows.hypothetical_questions.prompt import (
    HQ_SYSTEM_PROMPT,
    HQ_USER_TEMPLATE,
)

__all__ = [
    "HypotheticalQuestionsResult",
    "HQ_SYSTEM_PROMPT",
    "HQ_USER_TEMPLATE",
]
