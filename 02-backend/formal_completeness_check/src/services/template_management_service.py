"""Service layer for template category and document type CRUD operations."""

from uuid import UUID

from event_logging.enums import (
    EventAction,
    EventCategory,
    EventOutcome,
    LogEventDefault,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, AsyncSessionTransaction
from sqlalchemy.orm import selectinload

from src.models.db_models import TemplateCategory, TemplateDocumentType
from src.models.schemas.template_management_schemas import (
    CreateTemplateCategoryRequest,
    TemplateCategoryResponse,
    TemplateSoftDeleteResponse,
)
from src.utils.logger import logger


def _transaction_context(db: AsyncSession) -> AsyncSessionTransaction:
    return db.begin_nested() if db.in_transaction() else db.begin()


async def _query_categories(
    project_type_id: UUID,
    db: AsyncSession,
) -> list[TemplateCategoryResponse]:
    """Shared helper: fetch non-deleted categories with non-deleted doc types."""
    stmt = (
        select(TemplateCategory)
        .where(
            TemplateCategory.project_type_id == project_type_id,
            TemplateCategory.deleted.is_(False),
        )
        .options(selectinload(TemplateCategory.template_document_types.and_(TemplateDocumentType.deleted.is_(False))))
        .order_by(TemplateCategory.name.asc())
    )
    result = await db.execute(stmt)
    categories = result.scalars().unique().all()
    return [TemplateCategoryResponse.model_validate(cat) for cat in categories]


async def get_template_categories(
    project_type_id: UUID,
    db: AsyncSession,
) -> list[TemplateCategoryResponse]:
    """Return all non-deleted template categories with their document types."""
    logger.debug(
        EventAction.READ,
        EventOutcome.UNKNOWN,
        EventCategory.DATABASE,
        default_event=LogEventDefault.DB_READ,
        message=f"Fetching template categories for project_type_id={project_type_id}",
    )

    categories = await _query_categories(project_type_id, db)

    logger.debug(
        EventAction.READ,
        EventOutcome.SUCCESS,
        EventCategory.DATABASE,
        default_event=LogEventDefault.DB_SUCCESS,
        message=f"Retrieved {len(categories)} template categories for project_type_id={project_type_id}",
    )
    return categories


async def create_template_categories(
    project_type_id: UUID,
    payloads: list[CreateTemplateCategoryRequest],
    db: AsyncSession,
) -> list[TemplateCategoryResponse]:
    """Create template categories with nested document types."""
    logger.info(
        EventAction.WRITE,
        EventOutcome.UNKNOWN,
        EventCategory.DATABASE,
        default_event=LogEventDefault.DB_WRITE,
        message=f"Creating {len(payloads)} template categories for project_type_id={project_type_id}",
    )

    async with _transaction_context(db):
        for payload in payloads:
            category = TemplateCategory(
                name=payload.name,
                project_type_id=project_type_id,
            )
            db.add(category)
            await db.flush()

            for dt in payload.document_types:
                doc_type = TemplateDocumentType(
                    template_category_id=category.id,
                    name=dt.name,
                    description=dt.description,
                    expected_count=dt.expected_count,
                )
                db.add(doc_type)

    logger.info(
        EventAction.WRITE,
        EventOutcome.SUCCESS,
        EventCategory.DATABASE,
        default_event=LogEventDefault.DB_SUCCESS,
        message=f"Successfully created {len(payloads)} template categories for project_type_id={project_type_id}",
    )

    return await _query_categories(project_type_id, db)


async def soft_delete_all_templates(
    project_type_id: UUID,
    db: AsyncSession,
) -> TemplateSoftDeleteResponse:
    """Soft-delete all template categories and their document types for a project type."""
    logger.info(
        EventAction.DELETE,
        EventOutcome.UNKNOWN,
        EventCategory.DATABASE,
        default_event=LogEventDefault.DB_WRITE,
        message=f"Soft-deleting all template data for project_type_id={project_type_id}",
    )

    cat_count = 0
    dt_count = 0
    async with _transaction_context(db):
        stmt = (
            select(TemplateCategory)
            .where(
                TemplateCategory.project_type_id == project_type_id,
                TemplateCategory.deleted.is_(False),
            )
            .options(
                selectinload(TemplateCategory.template_document_types.and_(TemplateDocumentType.deleted.is_(False)))
            )
        )
        result = await db.execute(stmt)
        categories = result.scalars().unique().all()

        for category in categories:
            category.deleted = True
            cat_count += 1
            for doc_type in category.template_document_types:
                doc_type.deleted = True
                dt_count += 1

    logger.info(
        EventAction.DELETE,
        EventOutcome.SUCCESS,
        EventCategory.DATABASE,
        default_event=LogEventDefault.DB_SUCCESS,
        message=f"Soft-deleted {cat_count} categories and {dt_count} document types for project_type_id={project_type_id}",
    )

    return TemplateSoftDeleteResponse(
        deleted_categories=cat_count,
        deleted_document_types=dt_count,
    )
