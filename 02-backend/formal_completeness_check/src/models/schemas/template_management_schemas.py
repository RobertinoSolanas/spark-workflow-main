"""Schemas for template category and document type CRUD endpoints."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

MAX_TEMPLATE_CATEGORIES_PER_REQUEST = 50
MAX_TEMPLATE_DOCUMENT_TYPES_PER_CATEGORY = 100
TEMPLATE_NAME_MAX_LENGTH = 255
TEMPLATE_DESCRIPTION_MAX_LENGTH = 2000


# --- Request schemas: POST (create full structure) ---


class CreateTemplateDocumentTypeRequest(BaseModel):
    """A document type to create within a category."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=TEMPLATE_NAME_MAX_LENGTH,
        description="Name of the document type",
    )
    description: str = Field(
        ...,
        min_length=1,
        max_length=TEMPLATE_DESCRIPTION_MAX_LENGTH,
        description="Description of the document type",
    )
    expected_count: int | None = Field(
        None,
        ge=0,
        description="Expected number of documents",
    )

    model_config = ConfigDict(str_strip_whitespace=True)


class CreateTemplateCategoryRequest(BaseModel):
    """A category with nested document types for creation."""

    name: str = Field(
        ...,
        alias="category",
        min_length=1,
        max_length=TEMPLATE_NAME_MAX_LENGTH,
        description="Category name (seed-data compatible key: 'category')",
    )
    document_types: list[CreateTemplateDocumentTypeRequest] = Field(
        default_factory=list,
        max_length=MAX_TEMPLATE_DOCUMENT_TYPES_PER_CATEGORY,
        description="Document types belonging to this category",
    )

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)


# --- Response schemas ---


class TemplateDocumentTypeItemResponse(BaseModel):
    """A single template document type within a category response."""

    id: UUID
    name: str
    description: str
    expected_count: int | None

    model_config = ConfigDict(from_attributes=True)


class TemplateCategoryResponse(BaseModel):
    """A template category with its nested document types."""

    id: UUID
    name: str
    project_type_id: UUID | None
    template_document_types: list[TemplateDocumentTypeItemResponse]

    model_config = ConfigDict(from_attributes=True)


class TemplateSoftDeleteResponse(BaseModel):
    """Response for the soft-delete operation."""

    deleted_categories: int
    deleted_document_types: int
