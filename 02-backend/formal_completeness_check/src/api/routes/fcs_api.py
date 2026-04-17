from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.db.database import get_db_session
from src.models.schemas.fcs_types import (
    CreateRequiredDocumentTypeRequest,
    DocumentAssignmentItem,
    DocumentAssignmentsResponse,
    FormalCompletenessCheckResults,
    JobDoneRequest,
    JobDoneResponse,
    PatchDocumentByFileIdRequest,
    PatchRequiredDocumentTypeRequest,
    RequiredDocumentResponse,
    RequiredDocumentTypesResponse,
    SuccessResponse,
    TemplateDocumentTypeResponse,
)
from src.services.fcs_service import (
    create_custom_document_type,
    delete_custom_document_type,
    get_document_assignments,
    get_required_document_types_by_category,
    get_results_for_project,
    get_template_document_types,
    patch_document_by_file_id,
    patch_required_document_type,
)
from src.services.job_service import process_job_results

router = APIRouter(prefix="/{project_id}", tags=["Documents"])


@router.get(
    "/template-document-types",
    response_model=list[TemplateDocumentTypeResponse],
)
async def get_template(
    project_id: UUID,
    db: AsyncSession = Depends(get_db_session),
) -> list[TemplateDocumentTypeResponse]:
    """Return template document types for a project"""
    return await get_template_document_types(project_id, db)


@router.get(
    "",
    response_model=FormalCompletenessCheckResults,
)
async def get_formal_completeness_results(
    project_id: UUID,
    db: AsyncSession = Depends(get_db_session),
) -> FormalCompletenessCheckResults:
    """Return the formal completeness check results for the specified project."""
    return await get_results_for_project(project_id, db)


@router.get(
    "/required-document-types",
    response_model=RequiredDocumentTypesResponse,
)
async def get_required_document_types(
    project_id: UUID,
    db: AsyncSession = Depends(get_db_session),
) -> RequiredDocumentTypesResponse:
    """Return categories with their required document types for the specified project."""
    return await get_required_document_types_by_category(project_id, db)


@router.post(
    "/required-document-types",
    response_model=RequiredDocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_required_document_type(
    project_id: UUID,
    payload: CreateRequiredDocumentTypeRequest,
    db: AsyncSession = Depends(get_db_session),
) -> RequiredDocumentResponse:
    """Create a new custom document type in the 'Benutzerdefiniert' category."""
    return await create_custom_document_type(project_id, payload.document_name, db)


@router.patch(
    "/required-document-types/{document_type_id}",
    response_model=RequiredDocumentResponse,
)
async def patch_required_doc_type(
    project_id: UUID,
    document_type_id: UUID,
    payload: PatchRequiredDocumentTypeRequest,
    db: AsyncSession = Depends(get_db_session),
) -> RequiredDocumentResponse:
    """Partially update a required document type.

    - `document_name` is only allowed for custom types (origin=custom); returns 403 for system types.
    - `is_resolved` is allowed for both system and custom types.
    """
    patch = payload.model_dump(exclude_unset=True)
    return await patch_required_document_type(project_id, document_type_id, patch, db)


@router.delete(
    "/required-document-types/{document_type_id}",
    response_model=SuccessResponse,
)
async def delete_required_document_type(
    project_id: UUID,
    document_type_id: UUID,
    db: AsyncSession = Depends(get_db_session),
) -> SuccessResponse:
    """Delete a required document type. Only allowed for custom types (origin=custom)."""
    await delete_custom_document_type(project_id, document_type_id, db)
    return SuccessResponse()


@router.get(
    "/document-assignments",
    response_model=DocumentAssignmentsResponse,
)
async def get_doc_assignments(
    project_id: UUID,
    db: AsyncSession = Depends(get_db_session),
) -> DocumentAssignmentsResponse:
    """Return AI-suggested and human document type assignments for all documents in the project."""
    return await get_document_assignments(project_id, db)


@router.patch(
    "/documents/{file_id}",
    response_model=DocumentAssignmentItem,
)
async def patch_document(
    project_id: UUID,
    file_id: UUID,
    payload: PatchDocumentByFileIdRequest,
    db: AsyncSession = Depends(get_db_session),
) -> DocumentAssignmentItem:
    """Set the human document type assignment for a document. AI fields are read-only."""
    patch = payload.model_dump(exclude_unset=True)
    return await patch_document_by_file_id(project_id, file_id, patch, db)


@router.post(
    "/results",
    response_model=JobDoneResponse,
    status_code=status.HTTP_200_OK,
)
async def job_done(
    project_id: UUID,
    payload: JobDoneRequest,
    db: AsyncSession = Depends(get_db_session),
) -> JobDoneResponse:
    """Process completed formal completeness check job results.

    Fetches the results JSON from Document Management Service using the provided
    file_id, clears existing data for the project, and stores the new results.
    """
    return await process_job_results(project_id, payload.file_id, db)
