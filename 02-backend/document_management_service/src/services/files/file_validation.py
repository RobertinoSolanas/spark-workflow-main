from collections.abc import Sequence

from event_logging.enums import (
    EventAction,
    EventCategory,
    EventOutcome,
)

from src.services.files.file_utils import (
    validate_file_by_content_bytes,
    validate_file_type_by_extension,
    validate_mime_type_allowed,
)
from src.utils.exceptions import (
    FileInvalidFileExtensionError,
    FileInvalidFileTypeError,
)
from src.utils.logger import logger


def validate_file_upload(
    filename: str,
    allowed_extensions: dict[str, str],
    allowed_mime_types: Sequence[str] | set[str],
    content_bytes: bytes | None = None,
) -> str:
    """
    Validate a file upload by checking extension and MIME type.

    This function ensures that:
    - The file extension is supported and maps to a known MIME type.
    - The MIME type is in the list of allowed types.
    - If raw content bytes are provided, they match an allowed MIME type.

    Args:
        filename (str): Original filename including extension.
        allowed_extensions (dict[str, str]): Mapping of allowed extensions to
            MIME types.
        allowed_mime_types (Sequence[str]): List of allowed MIME types.
        content_bytes (bytes | None, optional): Raw file content bytes for type
            validation. Defaults to None.

    Returns:
        str: The validated MIME type for the file.

    Raises:
        FileInvalidFileExtensionError: If any validation step fails, with appropriate
            status code and error message.
    """
    # 1. Validate file extension
    try:
        expected_mime_type = validate_file_type_by_extension(
            filename=filename,
            allowed_extensions=allowed_extensions,
        )
    except FileInvalidFileExtensionError as e:
        logger.error(
            action=EventAction.VALIDATE,
            outcome=EventOutcome.FAILURE,
            category=EventCategory.FILE,
            file_name=filename,
            message=f"Unsupported file extension: {str(e)}",
        )
        raise

    # 2. Validate MIME type against allowed list
    try:
        mime_type = validate_mime_type_allowed(
            mime_type=expected_mime_type,
            allowed_types=allowed_mime_types,
        )
    except FileInvalidFileTypeError as e:
        logger.error(
            action=EventAction.VALIDATE,
            outcome=EventOutcome.FAILURE,
            category=EventCategory.FILE,
            file_name=filename,
            message=f"Unsupported MIME type: {str(e)}",
        )
        raise e

    # 3. Optional payload validation (raw bytes)
    if content_bytes is not None:
        validate_file_by_content_bytes(
            content=content_bytes,
            allowed_mime_types=allowed_mime_types,
        )

    logger.info(
        action=EventAction.VALIDATE,
        outcome=EventOutcome.SUCCESS,
        category=EventCategory.FILE,
        file_name=filename,
        message=f"File validation successful ({mime_type}).",
    )
    return mime_type
