from dataclasses import dataclass
from typing import Literal


# FileProcessing
@dataclass
class FileProcessingInput:
    file_id: str
    filename: str
    project_id: str
    file_type: Literal["ZIP"] = "ZIP"
    zip_path: str = ""


@dataclass
class FileProcessingSuccess:
    file_id: str | None
    filename: str
    action: str


@dataclass
class FileProcessingFailure:
    filename: str
    action: str
    error_code: str | None
    error_message: str | None


@dataclass
class FileProcessingSummary:
    total: int
    succeeded: int
    failed: int


@dataclass
class FileProcessingOutput:
    successful: list[FileProcessingSuccess]
    failed: list[FileProcessingFailure]
    summary: FileProcessingSummary
    status: str
