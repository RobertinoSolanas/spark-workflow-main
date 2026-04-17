from pathlib import PurePosixPath
from typing import TypeVar

from src.models.db.file_enum import FileTypeEnum
from src.services.files.path_builder.path_builder_base import FileContext, PathBuilder
from src.services.files.path_builder.path_builders import (
    ContentExtractionDataPathBuilder,
    LawDataPathBuilder,
    ProjectDocumentPathBuilder,
    ProjectZipFilePathBuilder,
    TemplatePathBuilder,
    TemporalCheckpointPathBuilder,
)

T = TypeVar("T", bound=FileContext)


class PathBuilderFactory:
    """
    Factory for resolving `PathBuilder` instances based on file type.
    """

    _registry: dict["FileTypeEnum", type[PathBuilder]] = {}

    @classmethod
    def register(
        cls,
        file_type: FileTypeEnum,
        path_builder_cls: type[PathBuilder],
    ) -> None:
        """Register a PathBuilder subclass for a specific file type."""
        cls._registry[file_type] = path_builder_cls

    @classmethod
    def get(cls, file_type: "FileTypeEnum") -> PathBuilder:
        """Retrieve the path builder for the given file type.

        Args:
            file_type (FileTypeEnum): The type of file whose builder is needed.

        Returns:
            PathBuilder: The concrete builder responsible for this file type.

        Raises:
            ValueError: If no builder is registered for the given file type.
        """
        builder = cls._registry.get(file_type)
        if not builder:
            raise ValueError(f"No path builder for {file_type}")
        return builder()

    @classmethod
    def build_path(cls, filename: str, context: FileContext) -> PurePosixPath:
        """Construct the full object path for a file using the appropriate builder.

        Args:
            filename (str): Name of the file to be stored. Should already be
                sanitized; if not, the builder may sanitize it internally.
            context (FileContext): A context object carrying metadata such as
                `type`, `project_id`, etc., which determine the path structure.

        Returns:
            PurePosixPath: A fully constructed storage path (POSIX-style).
        """
        file_type = context.type
        if isinstance(file_type, str):
            file_type = FileTypeEnum(file_type)

        builder = cls.get(file_type)
        path = builder.build(filename=filename, context=context)
        return path


PathBuilderFactory.register(
    file_type=FileTypeEnum.DOCUMENT,
    path_builder_cls=ProjectDocumentPathBuilder,
)
PathBuilderFactory.register(
    file_type=FileTypeEnum.ZIP,
    path_builder_cls=ProjectZipFilePathBuilder,
)
PathBuilderFactory.register(
    file_type=FileTypeEnum.TEMPLATE,
    path_builder_cls=TemplatePathBuilder,
)
PathBuilderFactory.register(
    file_type=FileTypeEnum.LAW_DATA,
    path_builder_cls=LawDataPathBuilder,
)
PathBuilderFactory.register(
    file_type=FileTypeEnum.TEMPORAL_CHECKPOINT,
    path_builder_cls=TemporalCheckpointPathBuilder,
)
PathBuilderFactory.register(
    file_type=FileTypeEnum.CONTENT_EXTRACTION,
    path_builder_cls=ContentExtractionDataPathBuilder,
)
