import re
from abc import ABC, abstractmethod
from pathlib import PurePosixPath
from uuid import UUID

from pydantic import BaseModel

from src.models.db.file_enum import FileTypeEnum


class FileContext(BaseModel):
    """
    Protocol describing the minimum fields required to build a file path.
    """

    type: "FileTypeEnum"

    # Optional common fields
    project_id: UUID | None = None
    workflow_id: str | None = None
    run_id: str | None = None
    version: int = 1


class PathBuilder(ABC):
    """Abstract base class for storage path builders."""

    @abstractmethod
    def build(self, filename: str, context: FileContext) -> PurePosixPath:
        """
        Construct the full object path for a file.

        Args:
            filename (str): The original file name (must be sanitized).
            context (FileContext): A typed context object that contains
                information required to construct the folder hierarchy
                (e.g. project_id, file type, org_id).

        Returns:
            PurePosixPath: A POSIX-compliant path representing the target
            object location inside the bucket.

        Raises:
            ValueError: If required context fields are missing.
            RuntimeError: If path construction fails in a concrete implementation.
        """
        ...

    @staticmethod
    def sanitize_filename(name: str) -> PurePosixPath:
        """
        Sanitize user-supplied filenames for safe storage across providers.

        Args:
            name (str): Raw filename supplied by the user.

        Returns:
            PurePosixPath: Sanitized and URL-safe filename. Guaranteed to be non-empty.

        Examples:
            >>> PathBuilder.sanitize_filename("my file?.pdf")
            'my%20file_.pdf'

            >>> PathBuilder.sanitize_filename("folder/secret.txt")
            'folder/secret.txt'
        """
        parts = name.split("/")

        sanitized_parts = []
        for part in parts:
            part = re.sub(r'[<>:"\\|?*\x00-\x1F ]', "_", part)
            part = re.sub(r"\.+", ".", part)
            part = part.strip(" .")
            if part:
                sanitized_parts.append(part)

        sanitized_name = PurePosixPath("/".join(part for part in sanitized_parts))

        if not sanitized_name:
            raise ValueError(f"Filename cannot be empty: {name=} and {sanitized_name=}")

        return sanitized_name
