"""
Exception registry for the project logic service.

This module consolidates all exception types used in the application:
- Third-party exceptions (asyncpg, SQLAlchemy, FastAPI)
- Custom domain exceptions

This centralization makes it easier to:
- Maintain a single source of truth for all exceptions
- Import exceptions consistently across the codebase
- Register exception handlers in one place
"""

# Third-party exceptions
from asyncpg.exceptions import ForeignKeyViolationError, PostgresError
from fastapi.exceptions import FastAPIError, RequestValidationError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError


class ResourceNotFoundError(Exception):
    """Base exception for resource not found errors."""

    def __init__(self, resource_type: str, resource_id: str):
        """Initialize resource not found error.

        Args:
            resource_type: Type of resource (e.g., "Project")
            resource_id: ID of the resource that was not found
        """
        self.resource_type = resource_type
        self.resource_id = resource_id
        super().__init__(f"{resource_type} {resource_id} not found")


class DeadlineNotFoundError(ResourceNotFoundError):
    """Raised when a deadline is not found or doesn't belong to the project."""

    def __init__(self, deadline_id: str):
        """Initialize deadline not found error.

        Args:
            deadline_id: ID of the deadline that was not found
        """
        super().__init__("Deadline", deadline_id)


class ProjectNotFoundError(ResourceNotFoundError):
    """Raised when a project is not found."""

    def __init__(self, project_id: str):
        """Initialize project not found error.

        Args:
            project_id: ID of the project that was not found
        """
        super().__init__("Project", project_id)


class ProcessStepNotFoundError(ResourceNotFoundError):
    """Raised when a process step is not found."""

    def __init__(self, process_step_id: str):
        """Initialize process step not found error.

        Args:
            process_step_id: ID of the process step that was not found
        """
        super().__init__("ProcessStep", process_step_id)


class ProjectTypeNotFoundError(ResourceNotFoundError):
    """Raised when a project type is not found."""

    def __init__(self, project_type_id: str):
        """Initialize project type not found error.

        Args:
            project_type_id: ID of the project type that was not found
        """
        super().__init__("ProjectType", project_type_id)


class DuplicateProjectTypeError(Exception):
    """Raised when a project type name already exists."""

    def __init__(self, name: str = ""):
        """Initialize duplicate project type error.

        Args:
            name: The duplicate project type name
        """
        self.name = name
        msg = f"ProjectType with name '{name}' already exists" if name else "Duplicate project type name"
        super().__init__(msg)


class InvalidStatusError(Exception):
    """Raised when an invalid project status is provided."""

    def __init__(self, status_name: str):
        """Initialize invalid status error.

        Args:
            status_name: Name of the invalid status
        """
        self.status_name = status_name
        super().__init__(f"Project status {status_name} not found")


# Export all exception types for easy importing
__all__ = [
    # Third-party exceptions
    "ForeignKeyViolationError",
    "PostgresError",
    "IntegrityError",
    "SQLAlchemyError",
    "FastAPIError",
    "RequestValidationError",
    # Custom domain exceptions
    "ResourceNotFoundError",
    "DeadlineNotFoundError",
    "ProjectNotFoundError",
    "ProjectTypeNotFoundError",
    "ProcessStepNotFoundError",
    "DuplicateProjectTypeError",
    "InvalidStatusError",
]
