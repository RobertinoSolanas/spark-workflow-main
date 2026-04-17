import stat
import zipfile
from pathlib import PurePosixPath

MAX_ZIP_ENTRIES = 5000
MAX_COMPRESSION_RATIO = 100
MAX_ZIP_EXTRACTION_SIZE_BYTES = 10 * 1024 * 1024 * 1024  # 10 GB
MAX_SINGLE_ENTRY_SIZE_BYTES = 10 * 1024 * 1024 * 1024  # 10 GB


def validate_zip_metadata(
    zf: zipfile.ZipFile, zip_filename: str
) -> list[zipfile.ZipInfo]:
    """Validate ZIP metadata and return list of safe entries.

    Args:
        zf: An opened zipfile.ZipFile instance.
        zip_filename: Original ZIP filename (for error messages).

    Returns:
        List of valid ZipInfo entries (directories and symlinks filtered out).

    Raises:
        ValueError: If the ZIP violates security constraints.
    """
    entries = zf.infolist()

    if len(entries) > MAX_ZIP_ENTRIES:
        raise ValueError(
            f"ZIP '{zip_filename}' contains {len(entries)} entries, "
            f"exceeding limit of {MAX_ZIP_ENTRIES}."
        )

    valid_entries: list[zipfile.ZipInfo] = []
    total_uncompressed = 0

    for entry in entries:
        # Skip directories
        if entry.is_dir():
            continue

        # Detect symlinks via external_attr (Unix mode in upper 16 bits)
        unix_mode = (entry.external_attr >> 16) & 0xFFFF
        if unix_mode and stat.S_ISLNK(unix_mode):
            continue

        # Check single entry size
        if entry.file_size > MAX_SINGLE_ENTRY_SIZE_BYTES:
            raise ValueError(
                f"Entry '{entry.filename}' in ZIP '{zip_filename}' is "
                f"{entry.file_size} bytes, exceeding limit of "
                f"{MAX_SINGLE_ENTRY_SIZE_BYTES} bytes."
            )

        # Check compression ratio (only if compressed size > 0)
        if entry.compress_size > 0:
            ratio = entry.file_size / entry.compress_size
            if ratio > MAX_COMPRESSION_RATIO:
                raise ValueError(
                    f"Entry '{entry.filename}' in ZIP '{zip_filename}' has "
                    f"compression ratio {ratio:.1f}:1, exceeding limit of "
                    f"{MAX_COMPRESSION_RATIO}:1 (possible zip bomb)."
                )

        total_uncompressed += entry.file_size
        valid_entries.append(entry)

    if total_uncompressed > MAX_ZIP_EXTRACTION_SIZE_BYTES:
        raise ValueError(
            f"ZIP '{zip_filename}' total uncompressed size is "
            f"{total_uncompressed} bytes, exceeding limit of "
            f"{MAX_ZIP_EXTRACTION_SIZE_BYTES} bytes."
        )

    return valid_entries


def _normalize_zip_entry_name(entry_name: str) -> str | None:
    """Return a safe relative file path from a zip entry name."""
    if entry_name.endswith("/") or entry_name.endswith("\\"):
        return None

    normalized = entry_name.replace("\\", "/")
    parts: list[str] = []
    for part in normalized.split("/"):
        if not part or part == ".":
            continue
        if part == "..":
            return None
        parts.append(part)

    if not parts or parts[0] == "__MACOSX":
        return None

    relative_path = PurePosixPath(*parts).as_posix()
    if relative_path.startswith("._"):
        return None

    return relative_path
