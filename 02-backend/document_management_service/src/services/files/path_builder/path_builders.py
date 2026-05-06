from pathlib import PurePosixPath

from src.services.files.path_builder.path_builder_base import FileContext, PathBuilder


class ProjectDocumentPathBuilder(PathBuilder):
    """Path builder for project-scoped document files (Antragsdokumente)."""

    def build(self, filename: str, context: FileContext) -> PurePosixPath:
        if not context.project_id:
            raise ValueError("project_id required for DOCUMENT")
        safe = self.sanitize_filename(name=filename)
        return (
            PurePosixPath("documents")
            / str(context.project_id)
            / f"v{context.version}"
            / safe
        )


class ProjectZipFilePathBuilder(PathBuilder):
    """Path builder for project-scoped zip files."""

    def build(self, filename: str, context: FileContext) -> PurePosixPath:
        if not context.project_id:
            raise ValueError("project_id required for ZIP")
        safe = self.sanitize_filename(name=filename)
        return (
            PurePosixPath("zips")
            / str(context.project_id)
            / f"v{context.version}"
            / safe
        )


class TemplatePathBuilder(PathBuilder):
    """Path builder for template files."""

    def build(self, filename: str, context: FileContext) -> PurePosixPath:
        safe = self.sanitize_filename(filename)

        # Optional project_id
        if context.project_id:
            return (
                PurePosixPath("templates")
                / str(context.project_id)
                / f"v{context.version}"
                / safe
            )

        return PurePosixPath("templates") / f"v{context.version}" / safe


class ContentExtractionDataPathBuilder(PathBuilder):
    """Path builder for content extraction data files."""

    def build(self, filename: str, context: FileContext) -> PurePosixPath:
        if not context.project_id:
            raise ValueError("project_id required for DOCUMENT")
        safe = self.sanitize_filename(filename)
        return (
            PurePosixPath("content_extraction")
            / str(context.project_id)
            / f"v{context.version}"
            / safe
        )


class LawDataPathBuilder(PathBuilder):
    """Path builder for law data files."""

    def build(self, filename: str, context: FileContext) -> PurePosixPath:
        safe = self.sanitize_filename(filename)
        return PurePosixPath("law_data") / f"v{context.version}" / safe


class TemporalCheckpointPathBuilder(PathBuilder):
    """Path builder for temporal checkpoint files."""

    def build(self, filename: str, context: FileContext) -> PurePosixPath:
        if not context.workflow_id or not context.run_id:
            raise ValueError(
                "workflow_id and run_id required for Temporal Checkpoints",
            )
        safe = self.sanitize_filename(filename)

        # Optional project_id
        if context.project_id:
            return (
                PurePosixPath("temporal_checkpoints")
                / str(context.workflow_id)
                / str(context.run_id)
                / str(context.project_id)
                / f"v{context.version}"
                / safe
            )

        return (
            PurePosixPath("temporal_checkpoints")
            / str(context.workflow_id)
            / str(context.run_id)
            / f"v{context.version}"
            / safe
        )
