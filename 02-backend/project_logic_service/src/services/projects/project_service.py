from collections.abc import Sequence
from uuid import UUID

from event_logging.enums import EventAction, EventCategory, EventOutcome
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.exceptions import InvalidStatusError, ProjectNotFoundError
from src.models.db_models import Applicant, Project, ProjectStatus, ProjectType
from src.models.schemas.project_schemas import (
    CreateProjectRequest,
    ProjectResponse,
    ProjectStatusEnum,
    UpdateProjectRequest,
    UpdateProjectStatusRequest,
)
from src.utils.logger import logger


async def list_projects(
    db: AsyncSession,
    name: str | None = None,
) -> Sequence[ProjectResponse]:
    """Retrieve a list of all projects, optionally filtered by name.

    Args:
        db: Async database session
        name: Optional filter string for project name

    Returns:
        List of matching Project instances
    """
    query = (
        select(
            Project,
            ProjectType.name.label("project_type_name"),
            ProjectStatus.name.label("status_name"),
        )
        .join(ProjectType, Project.project_type_id == ProjectType.id)
        .join(ProjectStatus, Project.status_id == ProjectStatus.id)
        .options(selectinload(Project.applicant))
    )

    if name:
        query = query.where(Project.name.ilike(f"%{name}%"))

    result = await db.execute(query)
    rows = result.all()

    projects = []
    for project, project_type_name, status_name in rows:
        # Extract applicant fields if applicant exists
        applicant_dict = {}
        if project.applicant:
            applicant_dict = {
                "salutation": project.applicant.salutation,
                "company": project.applicant.company,
                "first_name": project.applicant.first_name,
                "last_name": project.applicant.last_name,
                "street": project.applicant.street,
                "house_number": project.applicant.house_number,
                "address_supplement": project.applicant.address_supplement,
                "plz": project.applicant.plz,
                "location": project.applicant.location,
                "country": project.applicant.country,
                "email": project.applicant.email,
                "phone": project.applicant.phone,
                "fax": project.applicant.fax,
            }

        project_dict = {**project.__dict__}
        # Remove applicant_id from project_dict as it's not in ProjectResponse
        project_dict.pop("applicant_id", None)
        project_dict.pop("applicant", None)  # Remove relationship object

        projects.append(
            ProjectResponse(
                **project_dict,
                **applicant_dict,
                project_type_name=project_type_name,
                status_name=status_name,
            )
        )

    return projects


async def get_project_orm(db: AsyncSession, project_id: UUID) -> Project | None:
    """Get project ORM object by ID.

    Args:
        db: Database session
        project_id: Project ID

    Returns:
        Project if found, None otherwise
    """
    result = await db.execute(
        select(Project)
        .where(Project.id == project_id)
        .options(selectinload(Project.applicant))
    )
    return result.scalar_one_or_none()


async def get_project(db: AsyncSession, project_id: UUID) -> ProjectResponse:
    """Retrieve a single project by its unique ID, including project type and status names.

    Args:
        db: Async database session
        project_id: Unique identifier of the project

    Returns:
        The ProjectResponse instance if found

    Raises:
        ProjectNotFoundError: If project is not found
    """
    query = (
        select(
            Project,
            ProjectType.name.label("project_type_name"),
            ProjectStatus.name.label("status_name"),
        )
        .join(ProjectType, Project.project_type_id == ProjectType.id)
        .join(ProjectStatus, Project.status_id == ProjectStatus.id)
        .where(Project.id == project_id)
        .options(selectinload(Project.applicant))
    )

    result = await db.execute(query)
    row = result.fetchone()

    if row is None:
        raise ProjectNotFoundError(str(project_id))

    project, project_type_name, status_name = row

    # Extract applicant fields if applicant exists
    applicant_dict = {}
    if project.applicant:
        applicant_dict = {
            "salutation": project.applicant.salutation,
            "company": project.applicant.company,
            "first_name": project.applicant.first_name,
            "last_name": project.applicant.last_name,
            "street": project.applicant.street,
            "house_number": project.applicant.house_number,
            "address_supplement": project.applicant.address_supplement,
            "plz": project.applicant.plz,
            "location": project.applicant.location,
            "country": project.applicant.country,
            "email": project.applicant.email,
            "phone": project.applicant.phone,
            "fax": project.applicant.fax,
        }

    project_dict = {**project.__dict__}
    # Remove applicant_id from project_dict as it's not in ProjectResponse
    project_dict.pop("applicant_id", None)
    project_dict.pop("applicant", None)  # Remove relationship object

    return ProjectResponse(
        **project_dict,
        **applicant_dict,
        project_type_name=project_type_name,
        status_name=status_name,
    )


async def create_project(
    db: AsyncSession,
    project: CreateProjectRequest,
) -> ProjectResponse:
    """Create a new project record.

    Args:
        db: Async database session
        project: Project creation data

    Returns:
        The newly created ProjectResponse instance
    """
    # Retrieve initial project status
    status = await db.execute(
        select(ProjectStatus).where(ProjectStatus.name == ProjectStatusEnum.IN_CREATION)
    )
    default_status = status.scalar_one_or_none()
    if not default_status:
        raise ValueError("Default project status not found.")

    # Create applicant if applicant data is provided
    applicant_id = None
    if any(
        [
            project.salutation,
            project.company,
            project.first_name,
            project.last_name,
            project.street,
            project.house_number,
            project.address_supplement,
            project.plz,
            project.location,
            project.country,
            project.email,
            project.phone,
            project.fax,
        ]
    ):
        db_applicant = Applicant(
            salutation=project.salutation,
            company=project.company,
            first_name=project.first_name,
            last_name=project.last_name,
            street=project.street,
            house_number=project.house_number,
            address_supplement=project.address_supplement,
            plz=project.plz,
            location=project.location,
            country=project.country,
            email=project.email,
            phone=project.phone,
            fax=project.fax,
        )
        db.add(db_applicant)
        await db.flush()
        applicant_id = db_applicant.id

    db_project = Project(
        # Details
        name=project.name,
        project_type_id=project.project_type_id,
        created_by_id=project.created_by_id,
        entry_date=project.entry_date,
        internal_project_number=project.internal_project_number,
        applicant_id=applicant_id,
        # Metadata
        status_id=default_status.id,
        current_process_step_id=None,
    )
    try:
        db.add(db_project)
        await db.flush()
        await db.refresh(db_project)
        await db.commit()

    except Exception as e:
        logger.error(
            action=EventAction.WRITE,
            outcome=EventOutcome.FAILURE,
            category=EventCategory.DATABASE,
            message=f"Creation of project failed: {e}",
        )
        await db.rollback()
        raise e

    # Return ProjectResponse directly to avoid double lookup in routes
    project_response = await get_project(db=db, project_id=db_project.id)
    if not project_response:
        raise ValueError("Failed to retrieve created project")
    return project_response


async def update_project(
    db: AsyncSession,
    project_id: UUID,
    data: UpdateProjectRequest,
) -> Project:
    """Update an existing project with provided fields.

    Args:
        db: Async database session
        project_id: Unique identifier of the project to update
        data: Data to update the project with

    Returns:
        Updated Project instance

    Raises:
        ProjectNotFoundError: If project is not found
    """
    project = await get_project_orm(db=db, project_id=project_id)
    if not project:
        raise ProjectNotFoundError(str(project_id))

    # Extract applicant fields from update data
    applicant_fields = [
        "salutation",
        "company",
        "first_name",
        "last_name",
        "street",
        "house_number",
        "address_supplement",
        "plz",
        "location",
        "country",
        "email",
        "phone",
        "fax",
    ]

    applicant_data = {}
    project_data = {}
    for field, value in data.model_dump(exclude_unset=True, by_alias=False).items():
        if field in applicant_fields:
            applicant_data[field] = value
        else:
            project_data[field] = value

    # Update applicant if applicant data is provided
    if applicant_data:
        if project.applicant_id:
            # Update existing applicant (already loaded via relationship)
            if project.applicant:
                for field, value in applicant_data.items():
                    setattr(project.applicant, field, value)
        else:
            # Create new applicant
            db_applicant = Applicant(**applicant_data)
            db.add(db_applicant)
            await db.flush()
            project_data["applicant_id"] = db_applicant.id

    # Update project fields
    for field, value in project_data.items():
        setattr(project, field, value)

    await db.commit()
    await db.refresh(project)
    return project


async def update_project_status(
    db: AsyncSession,
    project_id: UUID,
    payload: UpdateProjectStatusRequest,
) -> Project:
    """Update the status of a project.

    Note: This function does NOT handle project transition side effects
    (e.g., queuing jobs). Those should be handled by the calling service
    (e.g., the main backend service that handles agent triggers).

    Args:
        db: SQLAlchemy async session for database operations
        project_id: Unique identifier of the project to update
        payload: Request payload containing the target status name

    Returns:
        The updated Project object

    Raises:
        ProjectNotFoundError: If the project is not found
        InvalidStatusError: If the requested status does not exist in the database
    """
    project = await get_project_orm(db=db, project_id=project_id)

    if not project:
        raise ProjectNotFoundError(str(project_id))

    result = await db.execute(
        select(ProjectStatus).where(ProjectStatus.name == payload.status_name)
    )
    status_obj = result.scalar_one_or_none()
    if not status_obj:
        raise InvalidStatusError(payload.status_name)

    updated_project = await update_project(
        db=db,
        project_id=project_id,
        data=UpdateProjectRequest(status_id=status_obj.id),
    )

    # NOTE: Project transition handling (e.g., job queuing) is excluded
    # from this service as it involves agent triggers. The main backend
    # service should handle those transitions.

    return updated_project
