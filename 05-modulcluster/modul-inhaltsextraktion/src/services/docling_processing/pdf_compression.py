# src/services/docling_processing/pdf_compression.py
"""
PDF image compression and rasterization activities.
"""

import asyncio
import io
import logging
import threading
from datetime import timedelta

import pikepdf
import pypdfium2 as pdfium
from pydantic import BaseModel
from temporal import Base64Bytes
from temporalio import activity, workflow
from temporalio.common import RetryPolicy

from src.config import get_config

logger = logging.getLogger(__name__)

# Lock to protect temporary mutation of PIL Image.MAX_IMAGE_PIXELS (process-global)
_pil_pixel_lock = threading.Lock()


# =============================================================================
# Pydantic I/O Models
# =============================================================================


class CompressPdfImagesInput(BaseModel):
    """Input for compress_pdf_images activity."""

    pdf_bytes: Base64Bytes
    file_size_mb: float


class CompressPdfImagesOutput(BaseModel):
    """Output from compress_pdf_images activity."""

    pdf_bytes: Base64Bytes
    file_size_mb: float
    was_compressed: bool


class RasterizeChunkInput(BaseModel):
    """Input for rasterize_chunk activity."""

    chunk_bytes: Base64Bytes
    chunk_index: int
    total_chunks: int


class RasterizeChunkOutput(BaseModel):
    """Output from rasterize_chunk activity."""

    rasterized_bytes: Base64Bytes
    original_size_mb: float
    rasterized_size_mb: float


# =============================================================================
# Helpers
# =============================================================================


def _pdf_has_oversized_images(pdf_bytes: bytes, max_pixels: int) -> bool:
    """Check if any embedded image exceeds the pixel limit by reading PDF metadata only (no decompression)."""
    pdf = pikepdf.open(io.BytesIO(pdf_bytes))
    try:
        for page in pdf.pages:
            resources = page.get("/Resources")
            if not resources:
                continue
            xobjects = resources.get("/XObject")
            if not xobjects:
                continue
            for key in xobjects.keys():
                obj = xobjects[key]
                if not isinstance(obj, pikepdf.Stream):
                    continue
                if obj.get("/Subtype") != pikepdf.Name.Image:
                    continue
                try:
                    pdfimage = pikepdf.PdfImage(obj)
                    if pdfimage.width * pdfimage.height > max_pixels:
                        return True
                except Exception:
                    logger.debug("Skipping unreadable image object during oversize check", exc_info=True)
                    continue
        return False
    finally:
        pdf.close()


def _compress_pdf_images_sync(pdf_bytes: bytes) -> bytes:  # noqa: C901
    """
    Synchronous helper to downscale oversized embedded images in a PDF.

    Iterates all image XObjects in the PDF, downscales those exceeding
    PDF_COMPRESSION_MAX_IMAGE_DIMENSION using Pillow, and replaces the
    raw image stream in-place using pikepdf.

    Args:
        pdf_bytes: Raw PDF bytes

    Returns:
        Compressed PDF bytes, or original bytes if compression fails or produces a larger file
    """
    from PIL import Image

    pdf = pikepdf.open(io.BytesIO(pdf_bytes))
    try:
        cfg = get_config()
        max_dim = cfg.PDF_COMPRESSION_MAX_IMAGE_DIMENSION
        min_dim = cfg.PDF_COMPRESSION_MIN_IMAGE_DIMENSION
        max_pixels = cfg.PDF_COMPRESSION_MAX_IMAGE_PIXELS
        quality = cfg.PDF_COMPRESSION_JPEG_QUALITY

        # Collect unique image objects across all pages (deduplicate by objgen)
        seen_objgens: set[tuple[int, int]] = set()
        image_objects: list[pikepdf.Stream] = []
        for page in pdf.pages:
            resources = page.get("/Resources")
            if not resources:
                continue
            xobjects = resources.get("/XObject")
            if not xobjects:
                continue
            for key in xobjects.keys():
                obj = xobjects[key]
                if not isinstance(obj, pikepdf.Stream):
                    continue
                subtype = obj.get("/Subtype")
                if subtype != pikepdf.Name.Image:
                    continue
                objgen = obj.objgen
                if objgen in seen_objgens:
                    continue
                seen_objgens.add(objgen)
                image_objects.append(obj)

        logger.info(f"PDF compression: found {len(image_objects)} unique images across {len(pdf.pages)} pages")

        compressed_count = 0

        for obj in image_objects:
            try:
                pdfimage = pikepdf.PdfImage(obj)
                width = pdfimage.width
                height = pdfimage.height
                pixel_count = width * height

                # Skip small images (logos, icons)
                if width < min_dim and height < min_dim:
                    continue

                # Skip images that don't need downscaling (both dimensions safe AND pixel count safe)
                if width <= max_dim and height <= max_dim and pixel_count <= max_pixels:
                    continue

                # Temporarily raise PIL pixel limit so we can decompress oversized images for resizing.
                # Use a lock because Image.MAX_IMAGE_PIXELS is process-global and
                # multiple documents may be compressed concurrently via asyncio.to_thread().
                with _pil_pixel_lock:
                    original_max_pixels = Image.MAX_IMAGE_PIXELS
                    try:
                        Image.MAX_IMAGE_PIXELS = max(pixel_count + 1, original_max_pixels or 0)
                        img = pdfimage.as_pil_image()
                    finally:
                        Image.MAX_IMAGE_PIXELS = original_max_pixels
                if img.mode == "CMYK":
                    img = img.convert("RGB")
                elif img.mode in ("RGBA", "P", "LA"):
                    img = img.convert("RGB")

                scale = min(max_dim / width, max_dim / height)
                new_width = int(width * scale)
                new_height = int(height * scale)
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

                # Encode as JPEG and write back into the stream
                jpeg_buffer = io.BytesIO()
                img.save(jpeg_buffer, format="JPEG", quality=quality)
                jpeg_bytes = jpeg_buffer.getvalue()

                obj.write(jpeg_bytes, filter=pikepdf.Name.DCTDecode)
                obj["/Width"] = new_width
                obj["/Height"] = new_height
                obj["/ColorSpace"] = pikepdf.Name.DeviceRGB
                # Remove keys incompatible with DCTDecode
                for stale_key in ("/DecodeParms", "/BitsPerComponent"):
                    if stale_key in obj:
                        del obj[stale_key]

                compressed_count += 1

            except Exception:
                logger.warning("Skipping image that failed compression", exc_info=True)
                continue

        if compressed_count == 0:
            return pdf_bytes

        out_buf = io.BytesIO()
        pdf.save(out_buf, compress_streams=True)
        result = out_buf.getvalue()
    finally:
        pdf.close()

    # Graceful fallback: return original if compression made file larger
    if len(result) >= len(pdf_bytes):
        return pdf_bytes

    return result


def _rasterize_chunk_sync(chunk_bytes: bytes) -> bytes:
    """
    Synchronous helper to rasterize each page of a PDF chunk into a JPEG image.

    Renders each page at RASTER_FALLBACK_DPI using pypdfium2 and builds a new
    image-only PDF using pikepdf. This strips all complex vector/embedded-image
    content that causes docling-serve to crash.

    Args:
        chunk_bytes: Raw PDF bytes of the chunk

    Returns:
        Rasterized PDF bytes
    """
    cfg = get_config()
    dpi = cfg.RASTER_FALLBACK_DPI
    quality = cfg.RASTER_FALLBACK_JPEG_QUALITY
    scale = dpi / 72.0

    src_doc = pdfium.PdfDocument(chunk_bytes)
    dst_pdf = pikepdf.Pdf.new()
    try:
        for page_idx in range(len(src_doc)):
            page = src_doc[page_idx]
            page_width = page.get_width()
            page_height = page.get_height()

            # Render page to PIL Image, then encode as JPEG
            bitmap = page.render(scale=scale)
            pil_image = bitmap.to_pil()
            jpeg_buf = io.BytesIO()
            pil_image.save(jpeg_buf, format="JPEG", quality=quality)
            jpeg_bytes = jpeg_buf.getvalue()

            # Build a single-image PDF page via pikepdf
            image_stream = pikepdf.Stream(dst_pdf, jpeg_bytes)
            image_stream["/Type"] = pikepdf.Name.XObject
            image_stream["/Subtype"] = pikepdf.Name.Image
            image_stream["/Width"] = pil_image.width
            image_stream["/Height"] = pil_image.height
            image_stream["/ColorSpace"] = pikepdf.Name.DeviceRGB
            image_stream["/BitsPerComponent"] = 8
            image_stream["/Filter"] = pikepdf.Name.DCTDecode

            # Content stream: scale image to fill the page
            content = f"q {page_width} 0 0 {page_height} 0 0 cm /Im0 Do Q"
            content_stream = pikepdf.Stream(dst_pdf, content.encode())

            new_page = pikepdf.Dictionary(
                Type=pikepdf.Name.Page,
                MediaBox=[0, 0, page_width, page_height],
                Contents=dst_pdf.make_indirect(content_stream),
                Resources=pikepdf.Dictionary(
                    XObject=pikepdf.Dictionary(Im0=dst_pdf.make_indirect(image_stream)),
                ),
            )
            dst_pdf.pages.append(pikepdf.Page(dst_pdf.make_indirect(new_page)))

        out_buf = io.BytesIO()
        dst_pdf.save(out_buf, compress_streams=True)
        result = out_buf.getvalue()
    finally:
        src_doc.close()
        dst_pdf.close()

    return result


# =============================================================================
# Activity Definitions
# =============================================================================


@activity.defn(name="compress_pdf_images")
async def _compress_pdf_images(
    input: CompressPdfImagesInput,
) -> CompressPdfImagesOutput:
    """
    Compress oversized embedded images in a PDF to reduce memory pressure on docling-serve.

    Skips compression if disabled by config or if the PDF is below the size threshold.
    Runs CPU-intensive work in asyncio.to_thread().

    Args:
        input: CompressPdfImagesInput with pdf_bytes and file_size_mb

    Returns:
        CompressPdfImagesOutput with (possibly compressed) PDF bytes and updated size
    """
    pdf_bytes = input.pdf_bytes
    file_size_mb = input.file_size_mb

    cfg = get_config()

    # Skip if compression is disabled
    if not cfg.ENABLE_PDF_COMPRESSION:
        activity.logger.info("PDF compression disabled by config")
        return CompressPdfImagesOutput(
            pdf_bytes=pdf_bytes,
            file_size_mb=file_size_mb,
            was_compressed=False,
        )

    # For small PDFs, run a lightweight pixel-count scan to catch images that
    # would trigger PIL DecompressionBombWarning in docling-serve (limit ~89M pixels).
    if file_size_mb < cfg.PDF_COMPRESSION_THRESHOLD_MB:
        if not await asyncio.to_thread(_pdf_has_oversized_images, pdf_bytes, cfg.PDF_COMPRESSION_MAX_IMAGE_PIXELS):
            activity.logger.info(
                f"PDF size {file_size_mb:.2f}MB < threshold {cfg.PDF_COMPRESSION_THRESHOLD_MB}MB "
                "and no oversized images found, skipping compression"
            )
            return CompressPdfImagesOutput(
                pdf_bytes=pdf_bytes,
                file_size_mb=file_size_mb,
                was_compressed=False,
            )
        activity.logger.info(
            f"PDF size {file_size_mb:.2f}MB < threshold but oversized images detected, "
            "running compression for pixel safety"
        )

    activity.logger.info(f"Compressing PDF images ({file_size_mb:.2f}MB)")

    try:
        result_bytes = await asyncio.to_thread(_compress_pdf_images_sync, pdf_bytes)
    except Exception as e:
        activity.logger.warning(f"PDF compression failed, using original: {e}")
        return CompressPdfImagesOutput(
            pdf_bytes=pdf_bytes,
            file_size_mb=file_size_mb,
            was_compressed=False,
        )

    new_size_mb = len(result_bytes) / (1024 * 1024)
    was_compressed = len(result_bytes) < len(pdf_bytes)

    if was_compressed:
        activity.logger.info(
            f"PDF compressed: {file_size_mb:.2f}MB -> {new_size_mb:.2f}MB "
            f"({(1 - new_size_mb / file_size_mb) * 100:.1f}% reduction)"
        )
    else:
        activity.logger.info("Compression did not reduce file size, using original")

    return CompressPdfImagesOutput(
        pdf_bytes=result_bytes,
        file_size_mb=new_size_mb,
        was_compressed=was_compressed,
    )


@activity.defn(name="rasterize_chunk_for_fallback")
async def _rasterize_chunk(input: RasterizeChunkInput) -> RasterizeChunkOutput:
    """
    Rasterize a PDF chunk by rendering each page as a JPEG image.

    This activity is used as a fallback when docling-serve crashes on a chunk
    due to huge embedded images. The rasterized PDF is much lighter and can
    usually be processed successfully.

    Args:
        input: RasterizeChunkInput with chunk bytes and metadata

    Returns:
        RasterizeChunkOutput with rasterized bytes and size info
    """
    if not input.chunk_bytes:
        raise RuntimeError(f"Chunk {input.chunk_index + 1}/{input.total_chunks} has empty bytes, cannot rasterize")

    chunk_num = input.chunk_index + 1
    original_size_mb = len(input.chunk_bytes) / (1024 * 1024)

    activity.logger.info(
        f"Rasterizing chunk {chunk_num}/{input.total_chunks} "
        f"({original_size_mb:.2f}MB) at {get_config().RASTER_FALLBACK_DPI} DPI"
    )

    rasterized_bytes = await asyncio.to_thread(_rasterize_chunk_sync, input.chunk_bytes)
    rasterized_size_mb = len(rasterized_bytes) / (1024 * 1024)

    activity.logger.info(
        f"Rasterized chunk {chunk_num}: {original_size_mb:.2f}MB -> "
        f"{rasterized_size_mb:.2f}MB "
        f"({(1 - rasterized_size_mb / max(original_size_mb, 0.001)) * 100:.1f}% reduction)"
    )

    return RasterizeChunkOutput(
        rasterized_bytes=rasterized_bytes,
        original_size_mb=original_size_mb,
        rasterized_size_mb=rasterized_size_mb,
    )


# =============================================================================
# Workflow Wrappers
# =============================================================================


async def compress_pdf_images(
    pdf_bytes: bytes,
    file_size_mb: float,
) -> CompressPdfImagesOutput:
    """Workflow wrapper for compress_pdf_images activity."""
    return await workflow.execute_activity(
        _compress_pdf_images,
        CompressPdfImagesInput(pdf_bytes=pdf_bytes, file_size_mb=file_size_mb),
        start_to_close_timeout=timedelta(minutes=15),
        retry_policy=RetryPolicy(maximum_attempts=get_config().TEMPORAL_PROCESSING_ACTIVITY_MAX_ATTEMPTS),
    )


async def rasterize_chunk(
    chunk_bytes: bytes,
    chunk_index: int,
    total_chunks: int,
) -> RasterizeChunkOutput:
    """Workflow wrapper for rasterize_chunk activity."""
    return await workflow.execute_activity(
        _rasterize_chunk,
        RasterizeChunkInput(
            chunk_bytes=chunk_bytes,
            chunk_index=chunk_index,
            total_chunks=total_chunks,
        ),
        start_to_close_timeout=timedelta(minutes=10),
        retry_policy=RetryPolicy(maximum_attempts=get_config().TEMPORAL_PROCESSING_ACTIVITY_MAX_ATTEMPTS),
    )
