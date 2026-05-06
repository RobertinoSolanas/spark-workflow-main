# src/processors/preprocessor.py
"""
Handles document preprocessing tasks like validation and conversion.

This module provides the Preprocessor class, which encapsulates the logic
for validating PDF files and converting other document formats to PDF.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pypdfium2 as pdfium
from temporalio import activity
from unoserver.client import UnoClient

from src.env import ENV


class NotValidPdfError(Exception):
    """Exception for not valid PDF files."""


class Preprocessor:
    """A class to handle document preprocessing."""

    @staticmethod
    async def validate_pdf(file_bytes: bytes) -> None:
        try:
            pdfium.PdfDocument(file_bytes)
        except Exception as err:
            raise NotValidPdfError() from err

    @staticmethod
    async def convert_to_pdf_if_needed(file_name: str, file_bytes: bytes) -> tuple[bytes, str]:
        """
        Ensures the input is a valid PDF, converting via LibreOffice if needed.
        Returns the PDF bytes and the (potentially updated) filename.
        """
        try:
            await Preprocessor.validate_pdf(file_bytes)
            return file_bytes, file_name
        except NotValidPdfError:
            pass

        activity.logger.info("Converting '%s' to PDF.", file_name)
        client = UnoClient(
            server=ENV.UNO_HOST,
            port=str(ENV.UNO_PORT),
            host_location="remote",
            protocol=ENV.UNO_PROTOCOL,
        )
        pdf_bytes = await asyncio.to_thread(client.convert, indata=file_bytes, outpath=None, convert_to="pdf")
        if not pdf_bytes:
            raise ValueError("File is empty.")
        await Preprocessor.validate_pdf(pdf_bytes)

        new_filename = str(Path(file_name).with_suffix(".pdf"))
        activity.logger.info("Successfully converted '%s' to '%s' in memory.", file_name, new_filename)
        return pdf_bytes, new_filename
