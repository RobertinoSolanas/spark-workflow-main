from dataclasses import dataclass, field


@dataclass
class SingleFileResult:
    success: bool
    filename: str
    action: str
    file_id: str | None = None
    bucket_path: str | None = None
    error_code: str | None = None
    error_message: str | None = None


# Validate ZIP
@dataclass
class ValidateZipInput:
    zip_path: str
    filename: str


@dataclass
class ValidateZipOutput:
    entry_count: int
    total_uncompressed_size: int


# ZIP Status
@dataclass
class UpdateFileStatusInput:
    zip_file_id: str
    status: str


# Extract ZIP
@dataclass
class ExtractZipInput:
    zip_file_id: str
    filename: str
    project_id: str
    zip_path: str


# Compute Sha256 Diff
@dataclass
class ComputeShaDiffInput:
    project_id: str
    zip_file_id: str
    files: list[SingleFileResult]
    rename_similarity_threshold: float = 0.65
    rename_same_dir_only: bool = True


@dataclass
class NewFile:
    filename: str
    bucket_path: str
    sha: str


@dataclass
class FileChange:
    file_id: str
    bucket_path: str
    filename: str
    source_sha: str
    target_sha: str


@dataclass
class RenameChange:
    file_id: str
    old_name: str
    new_name: str
    sha: str


@dataclass
class DeleteChange:
    file_id: str
    filename: str
    sha: str


@dataclass
class Unchanged:
    file_id: str
    filename: str
    sha: str


@dataclass
class FileDiffResult:
    new: list[NewFile] = field(default_factory=list)
    deleted: list[DeleteChange] = field(default_factory=list)
    changed: list[FileChange] = field(default_factory=list)
    renamed: list[RenameChange] = field(default_factory=list)
    unchanged: list[Unchanged] = field(default_factory=list)


# Ingest Files
@dataclass
class IngestFileInput:
    zip_file_id: str
    project_id: str
    filename: str
    bucket_path: str


# Delete Files
@dataclass
class DeleteFileInput:
    project_id: str
    filename: str
    file_id: str


# Rename Files
@dataclass
class RenameFileInput:
    project_id: str
    file_id: str
    old_name: str
    new_name: str
