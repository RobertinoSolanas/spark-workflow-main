# src/providers/docling_provider.py
"""
Docling extraction provider.

This provider uses the docling-serve API for PDF extraction. It extracts:
- Markdown content
- Structured document content (texts, tables, pictures)
- Images and tables as separate files

The output is transformed to a unified content format.

For large PDFs (> PDF_SIZE_THRESHOLD_MB), the document is split into chunks
and processed separately to avoid OOM issues in docling-serve.
"""

import asyncio
import io
import logging
from typing import Any

import pypdfium2 as pdfium

from src.config import get_config, get_docling_url
from src.providers.base import ContentItemDict, ExtractionResult
from src.providers.docling.api_client import DoclingApiClient
from src.providers.docling.content_builder import ContentBuilder
from src.providers.docling.extractors import ImageExtractor, TableExtractor
from src.providers.docling.markdown_builder import MarkdownBuilder
from src.providers.docling.transforms import sanitize_output_prefix

logger = logging.getLogger(__name__)


class DoclingProvider:
    """
    Docling extraction provider using the docling-serve API.

    Uses docling-serve for:
    - Layout analysis
    - Table and image extraction with OCR
    - Structured document JSON output
    - Markdown generation

    Note: We use our own VLM pipeline for visual element descriptions.
    """

    @staticmethod
    async def extract(
        pdf_bytes: bytes,
        pdf_filename: str,
        output_prefix: str,
    ) -> ExtractionResult:
        """
        Extract content via docling-serve API.

        For large PDFs (> PDF_SIZE_THRESHOLD_MB), the document is split into
        chunks and processed separately to avoid OOM issues in docling-serve.

        Args:
            pdf_bytes: Raw PDF file bytes
            pdf_filename: Original filename of the PDF
            output_prefix: Prefix for output files (document stem)

        Returns:
            ExtractionResult with markdown, content list, and images
        """
        docling_url = get_docling_url()
        if not docling_url:
            raise RuntimeError(
                "DOCLING_URL not configured. Set DOCLING_HOST environment variable to point to docling-serve API."
            )

        file_size_mb = len(pdf_bytes) / (1024 * 1024)
        logger.info(f"Docling extraction via API starting for {pdf_filename} ({file_size_mb:.2f} MB)")
        logger.info(f"Using docling-serve at {docling_url}")

        api_client = DoclingApiClient(docling_url, get_config().DOCLING_TIMEOUT)

        # Check if we need to chunk the PDF
        if file_size_mb > get_config().PDF_SIZE_THRESHOLD_MB:
            logger.info(
                f"File is larger than {get_config().PDF_SIZE_THRESHOLD_MB}MB, "
                f"processing in chunks of {get_config().PDF_PAGE_CHUNK_SIZE} pages"
            )
            result = await DoclingProvider._extract_chunked(api_client, pdf_bytes, pdf_filename, output_prefix)
        else:
            result = await DoclingProvider._extract_via_api(api_client, pdf_bytes, pdf_filename, output_prefix)

        logger.info(
            f"Docling extraction completed for {pdf_filename}: "
            f"{len(result.content_list)} content items, {len(result.images)} images"
        )

        return result

    @staticmethod
    async def _extract_chunked(
        api_client: DoclingApiClient,
        pdf_bytes: bytes,
        pdf_filename: str,
        output_prefix: str,
    ) -> ExtractionResult:
        """
        Extract large PDF by splitting into chunks and aggregating results.

        Args:
            pdf_bytes: Raw PDF file bytes
            pdf_filename: Original filename of the PDF
            output_prefix: Prefix for output files

        Returns:
            Aggregated ExtractionResult from all chunks
        """
        pdf = pdfium.PdfDocument(pdf_bytes)
        num_pages = len(pdf)
        chunk_size = get_config().PDF_PAGE_CHUNK_SIZE

        logger.info(f"Splitting {num_pages} pages into chunks of {chunk_size}")

        # Aggregated results
        all_md_content: list[str] = []
        all_original_md: list[str] = []
        all_content_list: list[ContentItemDict] = []
        all_images: dict[str, bytes] = {}
        all_provider_json: list[dict[str, Any]] = []

        for start_page in range(0, num_pages, chunk_size):
            end_page = min(start_page + chunk_size, num_pages)
            chunk_num = start_page // chunk_size + 1
            total_chunks = (num_pages + chunk_size - 1) // chunk_size

            logger.info(f"Processing chunk {chunk_num}/{total_chunks} (pages {start_page + 1}-{end_page})")

            # Create chunk PDF
            chunk_pdf = pdfium.PdfDocument.new()
            chunk_pdf.import_pages(pdf, pages=range(start_page, end_page))
            buffer = io.BytesIO()
            chunk_pdf.save(buffer, version=17)
            chunk_bytes = buffer.getvalue()
            chunk_pdf.close()

            # Process chunk with unique prefix to avoid filename collisions
            chunk_prefix = f"{output_prefix}_chunk{chunk_num}"
            chunk_result = await DoclingProvider._extract_via_api(api_client, chunk_bytes, pdf_filename, chunk_prefix)

            # Aggregate markdown (add page range header for clarity)
            chunk_header = f"\n\n<!-- Pages {start_page + 1}-{end_page} -->\n\n"
            all_md_content.append(chunk_header + chunk_result.md_content)
            if chunk_result.original_md_content:
                all_original_md.append(chunk_header + chunk_result.original_md_content)

            # Aggregate content list with page offset
            for item in chunk_result.content_list:
                adjusted_item = item.copy()
                # Adjust page numbers to reflect actual position in full document
                if "page_idx" in adjusted_item:
                    adjusted_item["page_idx"] = adjusted_item["page_idx"] + start_page
                all_content_list.append(adjusted_item)

            # Aggregate images (prefix already makes them unique)
            all_images.update(chunk_result.images)

            # Store provider JSON for reference
            if chunk_result.provider_json:
                all_provider_json.append(
                    {
                        "chunk": chunk_num,
                        "pages": f"{start_page + 1}-{end_page}",
                        "content": chunk_result.provider_json,
                    }
                )

        pdf.close()

        logger.info(f"Chunked extraction complete: {len(all_content_list)} items, {len(all_images)} images")

        return ExtractionResult(
            md_content="".join(all_md_content),
            content_list=all_content_list,
            images=all_images,
            original_md_content="".join(all_original_md) if all_original_md else None,
            provider_json={"chunks": all_provider_json} if all_provider_json else None,
        )

    # =========================================================================
    # API-based Extraction (docling-serve)
    # =========================================================================

    @staticmethod
    async def _extract_via_api(
        api_client: DoclingApiClient,
        pdf_bytes: bytes,
        pdf_filename: str,
        output_prefix: str,
    ) -> ExtractionResult:
        """
        Extract document content via docling-serve API.

        Args:
            api_client: Docling API client instance
            pdf_bytes: Raw PDF file bytes
            pdf_filename: Original filename of the PDF
            output_prefix: Prefix for output files

        Returns:
            ExtractionResult with markdown, content list, and images
        """
        # Sanitize output_prefix to prevent newlines/special chars in filenames
        # This can happen if the original filename has unusual Unicode characters
        output_prefix = sanitize_output_prefix(output_prefix)

        # Call docling-serve API
        result = await api_client.convert_document(pdf_bytes, pdf_filename)

        doc_data = result.get("document", {})
        doc_json = doc_data.get("json_content", {})
        original_md = doc_data.get("md_content", "")

        if not doc_json:
            raise RuntimeError("docling-serve returned empty json_content")

        logger.info(
            f"docling-serve returned {len(doc_json.get('texts', []))} texts, "
            f"{len(doc_json.get('tables', []))} tables, "
            f"{len(doc_json.get('pictures', []))} pictures"
        )

        # Extract images from embedded base64 in JSON
        images_meta, images_bytes = ImageExtractor.extract_from_json(doc_json, output_prefix)

        # If no images in JSON, try extracting from markdown (docling embeds images there for PDFs)
        if not images_bytes and original_md:
            logger.info("No images in JSON, extracting from markdown content")
            images_meta, images_bytes = ImageExtractor.extract_from_markdown(original_md, doc_json, output_prefix)

        # Extract tables (HTML from JSON structure)
        tables_meta = TableExtractor.extract_from_json(doc_json, output_prefix, images_bytes)

        # Crop table images from PDF if docling-serve didn't provide them
        # This ensures tables have images for VLM processing (consistent with local extraction)
        # Wrap in asyncio.to_thread since PDF rendering is CPU-bound (Temporal best practice)
        if get_config().DOCLING_TABLE_AS_IMAGE:
            await asyncio.to_thread(
                TableExtractor.crop_table_images,
                pdf_bytes=pdf_bytes,
                doc_json=doc_json,
                tables_meta=tables_meta,
                images_bytes=images_bytes,
                output_prefix=output_prefix,
            )

        # Build custom markdown
        custom_md = MarkdownBuilder.build(
            doc_json=doc_json,
            images_meta=images_meta,
            tables_meta=tables_meta,
        )

        # Build content list from JSON
        content_list = ContentBuilder.build_from_json(
            doc_json=doc_json,
            images_meta=images_meta,
            tables_meta=tables_meta,
        )

        # Detect and inject full-page images for pages where docling missed dominant images
        if get_config().DETECT_FULL_PAGE_IMAGES:
            images_meta, images_bytes, content_list, custom_md = ImageExtractor.inject_full_page_images(
                doc_json=doc_json,
                images_meta=images_meta,
                images_bytes=images_bytes,
                content_list=content_list,
                markdown=custom_md,
                output_prefix=output_prefix,
            )

        return ExtractionResult(
            md_content=custom_md,
            content_list=content_list,
            images=images_bytes,
            original_md_content=original_md,
            provider_json=doc_json,
        )
