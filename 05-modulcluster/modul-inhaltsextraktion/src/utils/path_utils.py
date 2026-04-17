# src/utils/path_utils.py
"""
Utility functions for path manipulation.
"""

from pathlib import Path


def get_output_dir(original_filename: str) -> str:
    """
    Get the output directory path that mirrors the input folder structure.

    For input 'files/data/erläuterungsbericht.pdf':
        Returns 'files/data/erläuterungsbericht'

    For input 'sicherheitsstudie.pdf':
        Returns 'sicherheitsstudie'

    Args:
        original_filename: Original filename with optional path

    Returns:
        Output directory path (parent/stem)
    """
    path = Path(original_filename)
    parent = path.parent
    stem = path.stem
    if parent == Path(".") or str(parent) == ".":
        return stem
    return f"{parent}/{stem}"
