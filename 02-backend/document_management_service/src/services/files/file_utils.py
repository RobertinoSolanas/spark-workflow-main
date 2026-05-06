from collections.abc import Sequence
from pathlib import Path

import puremagic

from src.utils.exceptions import (
    FileInvalidFileExtensionError,
    FileInvalidFileTypeError,
)


def get_file_extension(filename: str) -> str:
    """
    Extract file extension from filename.

    Args:
        filename (str): The filename with extension

    Returns:
        str: File extension in lowercase (including the dot)
    """
    return Path(filename).suffix.lower()


def validate_mime_type_allowed(
    mime_type: str,
    allowed_types: Sequence[str] | set[str],
) -> str:
    """
    Validate that the MIME type is in the allowed list.

    Args:
        mime_type (str): The MIME type to validate
        allowed_types (Sequence[str] | set[str]): Set of allowed MIME types

    Returns:
        str: The validated MIME type

    Raises:
        FileInvalidFileTypeError: If the MIME type is not allowed
    """
    if mime_type not in allowed_types:
        allowed_list = list(allowed_types)
        raise FileInvalidFileTypeError(
            f"MIME type '{mime_type}' is not supported. "
            f"Allowed types: {', '.join(sorted(allowed_list))}"
        )
    return mime_type


def validate_file_type_by_extension(
    filename: str,
    allowed_extensions: dict[str, str],
) -> str:
    """
    Validate file type based on extension and return the expected MIME type.

    Args:
        filename: The original filename with extension
        allowed_extensions: Dict mapping extensions to MIME types

    Returns:
        str: The expected MIME type for the file

    Raises:
        FileInvalidFileExtensionError: If the file extension is not allowed
    """
    extension = get_file_extension(filename)

    if extension not in allowed_extensions:
        allowed_list = list(allowed_extensions.keys())
        raise FileInvalidFileExtensionError(
            f"File type '{extension}' is not supported. "
            f"Allowed types: {', '.join(sorted(allowed_list))}"
        )

    return allowed_extensions[extension]


def validate_file_by_content_bytes(
    content: bytes,
    allowed_mime_types: Sequence[str] | set[str],
) -> None:
    """
    Validate file type directly from raw bytes.

    Args:
        content: Raw file bytes.
        allowed_mime_types: Set/list of allowed MIME types.

    Raises:
        FileInvalidFileTypeError: If the detected file type is not allowed.
    """
    mime_types = set(allowed_mime_types)

    # Reject scripts with a shebang immediately, regardless of extension.
    # puremagic cannot reliably detect text-based scripts; check explicitly.
    # Strip common BOMs first so a UTF-8 BOM prefix cannot bypass the check.
    _boms = (b"\xef\xbb\xbf", b"\xff\xfe", b"\xfe\xff")
    raw = content
    for bom in _boms:
        if content.startswith(bom):
            raw = content[len(bom) :]
            break
    if raw[:2] == b"#!":
        raise FileInvalidFileTypeError(
            "File appears to be a script (starts with #!) and is not allowed."
        )

    try:
        detected_mime_type = puremagic.from_string(
            string=content,
            mime=True,
        )
    except Exception as e:
        raise FileInvalidFileTypeError(
            f"File type could not be determined and is not allowed. "
            f"Allowed types: {', '.join(sorted(mime_types))}"
        ) from e

    # Validate
    if detected_mime_type not in mime_types:
        raise FileInvalidFileTypeError(
            f"File type '{detected_mime_type}' is not allowed. "
            f"Allowed types: {', '.join(sorted(mime_types))}"
        )
