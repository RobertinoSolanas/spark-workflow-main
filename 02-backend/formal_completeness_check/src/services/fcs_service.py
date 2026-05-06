"""Service layer for document CRUD operations."""

from uuid import UUID

import httpx
from event_logging.enums import (
    EventAction,
    EventCategory,
    EventOutcome,
    LogEventDefault,
)
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.config.settings import settings
from src.exceptions.exceptions import ForbiddenError, NotFoundError
from src.models.db_models import (
    Category,
    Document,
    DocumentType,
    ProjectTemplateVersion,
    TemplateCategory,
    TemplateDocumentType,
)
from src.models.schemas.fcs_types import (
    AssignedDocument,
    CategoryRequiredDocumentsResponse,
    DocumentAssignmentItem,
    DocumentAssignmentsResponse,
    DocumentTypeDefinition,
    FormalCompletenessCheckResults,
    MatchedDocumentTypeOutput,
    RequiredDocumentResponse,
    RequiredDocumentTypesResponse,
    TemplateDocumentTypeResponse,
    UnassignedDocument,
)
from src.utils.logger import logger


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=4),
    retry=retry_if_exception_type(httpx.RequestError),
    reraise=True,
)
async def _fetch_project_type_id(project_id: UUID) -> UUID:
    """Fetch project_type_id from PLS for a given project_id.

    Raises:
        NotFoundError: If PROJECT_LOGIC_SERVICE_URL is not configured or PLS returns an error.
    """
    pls_url = settings.PROJECT_LOGIC_SERVICE_URL
    if not pls_url:
        raise NotFoundError("PROJECT_LOGIC_SERVICE_URL is not configured")

    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(f"{pls_url}/projects/{project_id}")

    if response.status_code == 404:
        raise NotFoundError(f"Project {project_id} not found in PLS")

    response.raise_for_status()

    data = response.json()
    try:
        return UUID(data["projectTypeId"])
    except (KeyError, ValueError) as exc:
        raise NotFoundError(f"PLS returned invalid or missing projectTypeId for project {project_id}") from exc


async def _register_project(
    project_id: UUID,
    project_type_id: UUID,
    db: AsyncSession,
) -> UUID:
    """Register project to project_type mapping for template lookup.

    Raises:
        NotFoundError: If no template categories exist for the given project_type_id.
    """
    has_templates_stmt = (
        select(TemplateCategory.id)
        .where(
            TemplateCategory.project_type_id == project_type_id,
            TemplateCategory.deleted.is_(False),
        )
        .limit(1)
    )
    template_id = (await db.execute(has_templates_stmt)).scalar_one_or_none()

    if template_id is None:
        raise NotFoundError(f"No template categories found for project_type_id={project_type_id}")

    project_template_version = ProjectTemplateVersion(
        project_id=project_id,
        project_type_id=project_type_id,
    )
    db.add(project_template_version)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing_stmt = select(ProjectTemplateVersion.project_type_id).where(
            ProjectTemplateVersion.project_id == project_id
        )
        existing_project_type_id = (await db.execute(existing_stmt)).scalar_one_or_none()
        if existing_project_type_id is None:
            raise
        return existing_project_type_id

    return project_type_id


async def get_template_document_types(
    project_id: UUID,
    db: AsyncSession,
) -> list[TemplateDocumentTypeResponse]:
    """Return template document types for a project.

    If the project is not yet registered, fetches the project_type_id from PLS and
    registers it automatically (lazy registration).
    """
    project_template_version_stmt = select(ProjectTemplateVersion.project_type_id).where(
        ProjectTemplateVersion.project_id == project_id
    )
    project_type_id = (await db.execute(project_template_version_stmt)).scalar_one_or_none()

    if project_type_id is None:
        project_type_id = await _fetch_project_type_id(project_id)
        project_type_id = await _register_project(project_id, project_type_id, db)

    # Query template document types for the assigned project type
    stmt = (
        select(TemplateDocumentType)
        .join(TemplateCategory)
        .options(selectinload(TemplateDocumentType.template_category))
        .where(TemplateCategory.project_type_id == project_type_id)
        .where(TemplateDocumentType.deleted.is_(False))
        .where(TemplateCategory.deleted.is_(False))
        .order_by(TemplateCategory.name.asc(), TemplateDocumentType.name.asc())
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()

    return [
        TemplateDocumentTypeResponse(
            category=row.template_category.name,
            document_type_id=row.id,
            document_type_name=row.name,
            document_type_description=row.description,
            expected_count=row.expected_count,
        )
        for row in rows
    ]


async def delete_all_for_project(project_id: UUID, db: AsyncSession) -> int:
    """Delete all document types and documents for a project.

    Documents are deleted via cascade when document types are deleted.
    Unassigned documents (ai_suggested_required_document_type_id=None) are deleted separately.

    Both deletes run in a single transaction to prevent inconsistent state.

    Returns:
        Total number of rows deleted (unassigned documents + document types).
    """
    logger.info(
        EventAction.DELETE,
        EventOutcome.UNKNOWN,
        EventCategory.DATABASE,
        default_event=LogEventDefault.DB_WRITE,
        message=f"Deleting all FCS data for project_id={project_id}",
    )

    async with db.begin_nested():
        unassigned_result = await db.execute(
            delete(Document).where(
                Document.project_id == project_id,
                Document.ai_suggested_required_document_type_id.is_(None),
            )
        )
        unassigned_deleted = unassigned_result.rowcount

        doc_types_result = await db.execute(delete(DocumentType).where(DocumentType.project_id == project_id))
        doc_types_deleted = doc_types_result.rowcount

    total_deleted = unassigned_deleted + doc_types_deleted
    logger.info(
        EventAction.DELETE,
        EventOutcome.SUCCESS,
        EventCategory.DATABASE,
        default_event=LogEventDefault.DB_SUCCESS,
        message=f"Deleted {unassigned_deleted} unassigned documents and {doc_types_deleted} document types (total: {total_deleted}) for project_id={project_id}",
    )
    return total_deleted


async def bulk_insert_results(
    project_id: UUID,
    results: FormalCompletenessCheckResults,
    db: AsyncSession,
) -> None:
    """Insert document types, assigned documents, and unassigned documents from job results."""
    logger.info(
        EventAction.WRITE,
        EventOutcome.UNKNOWN,
        EventCategory.DATABASE,
        default_event=LogEventDefault.DB_WRITE,
        message=f"Inserting FCS results for project_id={project_id}: {len(results.matched_document_types)} document types, {len(results.unassigned_documents)} unassigned documents",
    )

    # Resolve category names to Category objects (get or create)
    category_cache: dict[str, Category] = {}
    for matched in results.matched_document_types:
        cat_name = matched.required_document_type.category
        if cat_name and cat_name not in category_cache:
            cat_stmt = select(Category).where(Category.project_id == project_id, Category.name == cat_name)
            cat_result = await db.execute(cat_stmt)
            category = cat_result.scalar_one_or_none()
            if category is None:
                category = Category(project_id=project_id, name=cat_name)
                db.add(category)
                await db.flush()
            category_cache[cat_name] = category

    # Ensure the hardcoded "Benutzerdefiniert" category exists (no document types)
    custom_cat_name = "Benutzerdefiniert"
    if custom_cat_name not in category_cache:
        cat_stmt = select(Category).where(Category.project_id == project_id, Category.name == custom_cat_name)
        cat_result = await db.execute(cat_stmt)
        category = cat_result.scalar_one_or_none()
        if category is None:
            category = Category(project_id=project_id, name=custom_cat_name)
            db.add(category)
            await db.flush()
        category_cache[custom_cat_name] = category

    for matched in results.matched_document_types:
        cat_name = matched.required_document_type.category
        category_id = category_cache[cat_name].id if cat_name and cat_name in category_cache else None
        doc_type = DocumentType(
            project_id=project_id,
            category_id=category_id,
            name=matched.required_document_type.document_type_name,
            description=matched.required_document_type.document_type_description,
            confidence=matched.confidence,
            origin="system",
        )
        db.add(doc_type)
        await db.flush()

        for assigned in matched.assigned_documents:
            document = Document(
                project_id=project_id,
                file_id=assigned.document_id,
                ai_suggested_required_document_type_id=doc_type.id,
                document_name=assigned.document_name,
                reasoning=assigned.reasoning,
                confidence=assigned.confidence,
                content_extraction_id=assigned.content_extraction_id,
            )
            db.add(document)

    for unassigned in results.unassigned_documents:
        unassigned_doc = Document(
            project_id=project_id,
            file_id=unassigned.document_id,
            ai_suggested_required_document_type_id=None,
            document_name=unassigned.document_name,
            reasoning=unassigned.reasoning,
            confidence=unassigned.confidence,
            content_extraction_id=unassigned.content_extraction_id,
        )
        db.add(unassigned_doc)

    await db.flush()
    logger.info(
        EventAction.WRITE,
        EventOutcome.SUCCESS,
        EventCategory.DATABASE,
        default_event=LogEventDefault.DB_SUCCESS,
        message=f"Successfully inserted FCS results for project_id={project_id}",
    )


async def get_results_for_project(
    project_id: UUID,
    db: AsyncSession,
) -> FormalCompletenessCheckResults:
    """Reconstruct `FormalCompletenessCheckResults` from stored data."""
    logger.debug(
        EventAction.READ,
        EventOutcome.UNKNOWN,
        EventCategory.DATABASE,
        default_event=LogEventDefault.DB_READ,
        message=f"Fetching FCS results for project_id={project_id}",
    )

    type_stmt = (
        select(DocumentType)
        .where(
            DocumentType.project_id == project_id,
            DocumentType.deleted.is_(False),
        )
        .options(
            selectinload(DocumentType.assigned_documents),
            selectinload(DocumentType.category),
        )
        .order_by(DocumentType.created_at.asc())
    )
    type_result = await db.execute(type_stmt)
    document_types = type_result.scalars().unique().all()

    matched_outputs: list[MatchedDocumentTypeOutput] = []

    for doc_type in document_types:
        required_document_type = DocumentTypeDefinition(
            category=doc_type.category.name if doc_type.category else None,
            document_type_name=doc_type.name,
            document_type_description=doc_type.description,
        )

        assigned_documents: list[AssignedDocument] = []
        for document in doc_type.assigned_documents:
            assigned_documents.append(
                AssignedDocument(
                    document_id=document.file_id,
                    document_name=document.document_name,
                    reasoning=document.reasoning if document.reasoning is not None else "",
                    confidence=document.confidence if document.confidence is not None else 0.0,
                    ai_suggested_required_document_type_id=doc_type.id,
                    human_required_document_type_id=document.human_required_document_type_id,
                    content_extraction_id=document.content_extraction_id,
                )
            )

        matched_outputs.append(
            MatchedDocumentTypeOutput(
                required_document_type=required_document_type,
                assigned_documents=assigned_documents,
                confidence=doc_type.confidence if doc_type.confidence is not None else 0.0,
            )
        )

    unassigned_stmt = select(Document).where(
        Document.project_id == project_id,
        Document.ai_suggested_required_document_type_id.is_(None),
    )
    unassigned_result = await db.execute(unassigned_stmt)
    unassigned_docs = unassigned_result.scalars().all()

    unassigned_documents = [
        UnassignedDocument(
            document_id=doc.file_id,
            document_name=doc.document_name,
            reasoning=doc.reasoning if doc.reasoning is not None else "",
            confidence=doc.confidence if doc.confidence is not None else 0.0,
            ai_suggested_required_document_type_id=None,
            human_required_document_type_id=doc.human_required_document_type_id,
            content_extraction_id=doc.content_extraction_id,
        )
        for doc in unassigned_docs
    ]

    logger.debug(
        EventAction.READ,
        EventOutcome.SUCCESS,
        EventCategory.DATABASE,
        default_event=LogEventDefault.DB_SUCCESS,
        message=f"Retrieved FCS results for project_id={project_id}: {len(matched_outputs)} document types, {len(unassigned_documents)} unassigned",
    )
    return FormalCompletenessCheckResults(
        matched_document_types=matched_outputs,
        unassigned_documents=unassigned_documents,
    )


async def get_required_document_types_by_category(
    project_id: UUID,
    db: AsyncSession,
) -> RequiredDocumentTypesResponse:
    """Return categories with their document types for a project."""
    stmt = (
        select(Category)
        .where(Category.project_id == project_id)
        .options(selectinload(Category.document_types.and_(DocumentType.deleted.is_(False))))
        .order_by(Category.name.asc())
    )
    result = await db.execute(stmt)
    categories = result.scalars().unique().all()

    return RequiredDocumentTypesResponse(
        categories=[
            CategoryRequiredDocumentsResponse(
                category_id=cat.id,
                category_name=cat.name,
                required_documents=[
                    RequiredDocumentResponse(
                        document_type_id=dt.id,
                        document_name=dt.name,
                        origin=dt.origin,
                        is_resolved=dt.is_resolved,
                    )
                    for dt in cat.document_types
                    if not dt.deleted
                ],
            )
            for cat in categories
        ]
    )


CUSTOM_CATEGORY_NAME = "Benutzerdefiniert"


async def get_document_assignments(
    project_id: UUID,
    db: AsyncSession,
) -> DocumentAssignmentsResponse:
    """Return AI-suggested vs human document type assignments for all documents in a project."""
    stmt = select(Document).where(Document.project_id == project_id)
    result = await db.execute(stmt)
    documents = result.scalars().all()

    return DocumentAssignmentsResponse(
        items=[
            DocumentAssignmentItem(
                file_id=doc.file_id,
                ai_suggested_required_document_type_id=doc.ai_suggested_required_document_type_id,
                human_required_document_type_id=doc.human_required_document_type_id,
            )
            for doc in documents
            if doc.file_id is not None
        ]
    )


async def patch_document_by_file_id(
    project_id: UUID,
    file_id: UUID,
    patch: dict,
    db: AsyncSession,
) -> DocumentAssignmentItem:
    """Update the human document type assignment for a document identified by file_id.

    Only `human_required_document_type_id` may be patched.

    Raises:
        NotFoundError: If the document is not found or the target document type does not exist.
    """
    stmt = select(Document).where(
        Document.file_id == file_id,
        Document.project_id == project_id,
    )
    result = await db.execute(stmt)
    document = result.scalar_one_or_none()
    if document is None:
        raise NotFoundError(f"Document not found for project_id={project_id}, file_id={file_id}")

    if "human_required_document_type_id" in patch and patch["human_required_document_type_id"] is not None:
        new_type_exists = (
            await db.execute(
                select(DocumentType.id).where(
                    DocumentType.project_id == project_id,
                    DocumentType.id == patch["human_required_document_type_id"],
                    DocumentType.deleted.is_(False),
                )
            )
        ).scalar_one_or_none()
        if new_type_exists is None:
            raise NotFoundError(
                f"Document type not found for project_id={project_id}, document_type_id={patch['human_required_document_type_id']}"
            )

    if "human_required_document_type_id" in patch:
        document.human_required_document_type_id = patch["human_required_document_type_id"]
    await db.commit()
    return DocumentAssignmentItem(
        file_id=document.file_id,
        ai_suggested_required_document_type_id=document.ai_suggested_required_document_type_id,
        human_required_document_type_id=document.human_required_document_type_id,
    )


async def _get_custom_category(project_id: UUID, db: AsyncSession) -> Category:
    """Return the 'Benutzerdefiniert' category for a project.

    Raises:
        NotFoundError: If the category does not exist (project not initialized).
    """
    stmt = select(Category).where(Category.project_id == project_id, Category.name == CUSTOM_CATEGORY_NAME)
    result = await db.execute(stmt)
    category = result.scalar_one_or_none()
    if category is None:
        raise NotFoundError(f"Category '{CUSTOM_CATEGORY_NAME}' not found for project_id={project_id}")
    return category


async def create_custom_document_type(
    project_id: UUID, document_name: str, db: AsyncSession
) -> RequiredDocumentResponse:
    """Create a new document type in the 'Benutzerdefiniert' category."""
    category = await _get_custom_category(project_id, db)
    doc_type = DocumentType(
        project_id=project_id,
        category_id=category.id,
        name=document_name,
        description="",
        origin="custom",
    )
    db.add(doc_type)
    await db.flush()
    await db.commit()
    return RequiredDocumentResponse(
        document_type_id=doc_type.id,
        document_name=doc_type.name,
        origin=doc_type.origin,
        is_resolved=doc_type.is_resolved,
    )


async def patch_required_document_type(
    project_id: UUID, document_type_id: UUID, patch: dict, db: AsyncSession
) -> RequiredDocumentResponse:
    """Partially update a required document type.

    - `document_name` is only allowed for custom (origin=custom) types.
    - `is_resolved` is always allowed.

    Raises:
        NotFoundError: If the document type is not found.
        ForbiddenError: If `document_name` is patched on a system document type.
    """
    stmt = select(DocumentType).where(
        DocumentType.id == document_type_id,
        DocumentType.project_id == project_id,
        DocumentType.deleted.is_(False),
    )
    result = await db.execute(stmt)
    doc_type = result.scalar_one_or_none()
    if doc_type is None:
        raise NotFoundError(f"Document type not found for project_id={project_id}, document_type_id={document_type_id}")

    is_custom = doc_type.origin == "custom"

    if "document_name" in patch and not is_custom:
        raise ForbiddenError(f"Cannot rename a system document type (document_type_id={document_type_id})")

    if "document_name" in patch:
        doc_type.name = patch["document_name"]
    if "is_resolved" in patch:
        doc_type.is_resolved = patch["is_resolved"]

    await db.commit()
    return RequiredDocumentResponse(
        document_type_id=doc_type.id,
        document_name=doc_type.name,
        origin=doc_type.origin,
        is_resolved=doc_type.is_resolved,
    )


async def delete_custom_document_type(project_id: UUID, document_type_id: UUID, db: AsyncSession) -> None:
    """Soft delete a required document type.

    Only allowed for custom (origin=custom) types. Sets the document type as deleted
    and unassigns all associated documents.

    Raises:
        NotFoundError: If the document type is not found.
        ForbiddenError: If the document type is a system type.
    """
    stmt = (
        select(DocumentType)
        .where(
            DocumentType.id == document_type_id,
            DocumentType.project_id == project_id,
            DocumentType.deleted.is_(False),
        )
        .options(selectinload(DocumentType.assigned_documents))
    )
    result = await db.execute(stmt)
    doc_type = result.scalar_one_or_none()
    if doc_type is None:
        raise NotFoundError(f"Document type not found for project_id={project_id}, document_type_id={document_type_id}")

    is_custom = doc_type.origin == "custom"
    if not is_custom:
        raise ForbiddenError(f"Cannot delete a system document type (document_type_id={document_type_id})")

    # Soft delete the document type
    doc_type.deleted = True

    # Clear AI assignment for documents linked via ai_suggested_required_document_type_id
    for document in doc_type.assigned_documents:
        document.ai_suggested_required_document_type_id = None

    # Clear human assignment for any document that manually points to this type
    human_assigned_stmt = select(Document).where(
        Document.project_id == project_id,
        Document.human_required_document_type_id == document_type_id,
    )
    human_assigned_result = await db.execute(human_assigned_stmt)
    for document in human_assigned_result.scalars().all():
        document.human_required_document_type_id = None

    await db.commit()
