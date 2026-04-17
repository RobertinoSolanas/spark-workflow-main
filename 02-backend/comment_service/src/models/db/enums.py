"""Enums for Comment Service."""

from enum import Enum


class ProcessStep(str, Enum):
    """Process step for the comment."""

    UNSORTED = "unsorted"
    FORMAL_COMPLETENESS_CHECK = "formalCompletenessCheck"
    PLAUSIBILITY_CHECK = "plausibilityCheck"
    MATERIAL_COMPLETENESS_CHECK = "materialCompletenessCheck"
    LEGAL_REVIEW = "legalReview"


class SourceType(str, Enum):
    """Source reference type for the comment."""

    TABLE_OF_CONTENTS = "tableOfContents"
    REQUIRED_DOCUMENTS = "requiredDocuments"
    CONTRADICTION = "contradiction"
    MATERIAL_LAW = "materialLaw"
    MATERIAL_NORM = "materialNorm"
    MATERIAL_SATZ = "materialSatz"
    MATERIAL_FUNDSTELLE = "materialFundstelle"
    MANUAL = "manual"
