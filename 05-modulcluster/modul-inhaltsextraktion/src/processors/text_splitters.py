"""Lightweight text splitting utilities.

Drop-in replacements for langchain_core.documents.Document,
langchain_text_splitters.MarkdownHeaderTextSplitter, and
langchain_text_splitters.RecursiveCharacterTextSplitter.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence


# ---------------------------------------------------------------------------
# Document
# ---------------------------------------------------------------------------


@dataclass
class Document:
    """Minimal document container matching the langchain_core interface."""

    page_content: str
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# MarkdownHeaderTextSplitter
# ---------------------------------------------------------------------------


class MarkdownHeaderTextSplitter:
    """Split markdown text by header lines, tracking the header hierarchy.

    Parameters
    ----------
    headers_to_split_on:
        List of (marker, metadata_key) tuples, e.g.
        [("#", "Header 1"), ("##", "Header 2")].
    strip_headers:
        If True the header line itself is removed from page_content.
    """

    def __init__(
        self,
        headers_to_split_on: list[tuple[str, str]],
        strip_headers: bool = True,
    ) -> None:
        # Sort longest marker first so "##" is tested before "#".
        self.headers_to_split_on = sorted(
            headers_to_split_on, key=lambda pair: len(pair[0]), reverse=True
        )
        self.strip_headers = strip_headers

    # ------------------------------------------------------------------

    def split_text(self, text: str) -> list[Document]:
        """Split *text* into Document objects at header boundaries."""
        lines = text.split("\n")

        sections: list[tuple[dict[str, str], list[str]]] = []
        current_metadata: dict[str, str] = {}
        current_lines: list[str] = []

        for line in lines:
            matched_header = self._match_header(line)
            if matched_header is not None:
                # Flush previous section
                if current_lines:
                    sections.append((dict(current_metadata), current_lines))
                    current_lines = []

                marker, key = matched_header
                # Extract the header text after the marker in the stripped line
                stripped = line.lstrip()
                header_text = stripped[len(marker) :].strip()
                # Update hierarchy: clear lower-level headers
                current_metadata = self._update_metadata(
                    current_metadata, key, header_text
                )
                if not self.strip_headers:
                    current_lines.append(line)
            else:
                current_lines.append(line)

        # Flush last section
        if current_lines:
            sections.append((dict(current_metadata), current_lines))

        # Build documents, skipping empty sections
        documents: list[Document] = []
        for metadata, section_lines in sections:
            content = "\n".join(section_lines).strip()
            if content:
                documents.append(
                    Document(page_content=content, metadata=dict(metadata))
                )
        return documents

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _match_header(self, line: str) -> tuple[str, str] | None:
        """Return (marker, key) if *line* starts with a known header marker."""
        stripped = line.lstrip()
        for marker, key in self.headers_to_split_on:
            # The line must start with the marker followed by a space.
            if stripped.startswith(marker + " ") and not stripped.startswith(
                marker + "#"
            ):
                return marker, key
        return None

    def _update_metadata(
        self,
        current: dict[str, str],
        key: str,
        value: str,
    ) -> dict[str, str]:
        """Set *key* and drop any lower-level headers from the hierarchy.

        Uses marker length to determine hierarchy: shorter markers (e.g. "#")
        are higher-level than longer markers (e.g. "##").
        """
        marker_len_for_key: dict[str, int] = {
            k: len(m) for m, k in self.headers_to_split_on
        }
        current_marker_len = marker_len_for_key.get(key, 0)
        new: dict[str, str] = {}
        for k, v in current.items():
            # Keep only keys whose marker is shorter (higher level)
            if k in marker_len_for_key and marker_len_for_key[k] < current_marker_len:
                new[k] = v
        new[key] = value
        return new


# ---------------------------------------------------------------------------
# RecursiveCharacterTextSplitter
# ---------------------------------------------------------------------------

_DEFAULT_SEPARATORS: list[str] = ["\n\n", "\n", " ", ""]


class RecursiveCharacterTextSplitter:
    """Recursively split text by a list of separators.

    Parameters
    ----------
    chunk_size:
        Maximum length of a chunk (measured by *length_function*).
    chunk_overlap:
        Number of characters to overlap between consecutive chunks.
    separators:
        Ordered list of separators to try.  Defaults to
        ``["\\n\\n", "\\n", " ", ""]``.
    length_function:
        Callable that returns the length of a string (default ``len``).
    is_separator_regex:
        Treat separators as regex patterns.
    keep_separator:
        If True, separators are kept at the start of each split.
    """

    def __init__(
        self,
        chunk_size: int = 4000,
        chunk_overlap: int = 200,
        separators: list[str] | None = None,
        length_function: Callable[[str], int] = len,
        is_separator_regex: bool = False,
        keep_separator: bool = False,
    ) -> None:
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._separators = list(separators) if separators is not None else list(_DEFAULT_SEPARATORS)
        self._length_function = length_function
        self._is_separator_regex = is_separator_regex
        self._keep_separator = keep_separator

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def split_text(self, text: str) -> list[str]:
        """Split *text* into chunks respecting *chunk_size* and *chunk_overlap*."""
        return self._split_text(text, self._separators)

    def split_documents(self, documents: Sequence[Document]) -> list[Document]:
        """Split each document's page_content, copying metadata."""
        result: list[Document] = []
        for doc in documents:
            for chunk in self.split_text(doc.page_content):
                result.append(
                    Document(page_content=chunk, metadata=dict(doc.metadata))
                )
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _split_text(self, text: str, separators: list[str]) -> list[str]:
        """Core recursive splitting logic."""
        final_chunks: list[str] = []

        # Find the best separator (first one that appears in text)
        separator = separators[-1]
        new_separators: list[str] = []
        for i, sep in enumerate(separators):
            pattern = sep if self._is_separator_regex else re.escape(sep)
            if sep == "":
                separator = sep
                break
            if re.search(pattern, text):
                separator = sep
                new_separators = separators[i + 1 :]
                break

        splits = self._split_by_separator(text, separator)

        # Merge small pieces together; recursively split oversized ones
        good_splits: list[str] = []
        for piece in splits:
            if self._length_function(piece) < self._chunk_size:
                good_splits.append(piece)
            else:
                if good_splits:
                    merged = self._merge_splits(good_splits, separator)
                    final_chunks.extend(merged)
                    good_splits = []
                if new_separators:
                    final_chunks.extend(self._split_text(piece, new_separators))
                else:
                    final_chunks.append(piece)

        if good_splits:
            merged = self._merge_splits(good_splits, separator)
            final_chunks.extend(merged)

        return final_chunks

    def _split_by_separator(self, text: str, separator: str) -> list[str]:
        """Split text by *separator*, optionally keeping it."""
        if separator == "":
            return list(text)

        if self._is_separator_regex:
            pattern = separator
        else:
            pattern = re.escape(separator)

        if self._keep_separator:
            parts = re.split(f"({pattern})", text)
            # Re-attach separators to the following piece
            result: list[str] = []
            i = 0
            if len(parts) > 0 and parts[0]:
                result.append(parts[0])
                i = 1
            elif len(parts) > 0:
                i = 1
            while i < len(parts) - 1:
                result.append(parts[i] + parts[i + 1])
                i += 2
            if i < len(parts) and parts[i]:
                result.append(parts[i])
            return [s for s in result if s]
        else:
            return [s for s in re.split(pattern, text) if s]

    def _merge_splits(self, splits: list[str], separator: str) -> list[str]:
        """Merge small splits into chunks up to *chunk_size*, with overlap."""
        merged: list[str] = []
        current_pieces: list[str] = []
        current_len = 0

        for piece in splits:
            piece_len = self._length_function(piece)
            sep_len = self._length_function(separator) if current_pieces else 0

            if current_len + piece_len + sep_len > self._chunk_size and current_pieces:
                chunk_text = separator.join(current_pieces)
                merged.append(chunk_text)

                # Keep trailing pieces for overlap
                while current_len > self._chunk_overlap and len(current_pieces) > 1:
                    removed = current_pieces.pop(0)
                    current_len -= self._length_function(removed) + self._length_function(separator)

            current_pieces.append(piece)
            current_len = self._length_function(separator.join(current_pieces))

        if current_pieces:
            chunk_text = separator.join(current_pieces)
            merged.append(chunk_text)

        return merged
