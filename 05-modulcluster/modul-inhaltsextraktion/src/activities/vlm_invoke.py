# src/activities/vlm_invoke.py
"""
Temporal activities for VLM (Visual Language Model) operations.

Following Temporal best practices, VLM API calls are Temporal activities,
providing independent retries, durability, and observability for each call.
"""

import asyncio
import base64
import hashlib
import io
import mimetypes
from collections import OrderedDict
from datetime import timedelta

import httpx
from openai import AsyncOpenAI

# Pillow for image processing (replaces pyvips to eliminate libvips CVEs)
from PIL import Image
from prompt_injection.prompt_defense import wrap_system_prompt
from pydantic import BaseModel
from temporal import Base64Bytes
from temporalio import activity, workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ApplicationError

from src.concurrency import get_model_throttle
from src.config import get_config
from src.env import ENV
from src.workflows.vlm_enhancement.prompt import (
    VLM_DESCRIPTION_PROMPT,
    VLM_EXTRACTION_PROMPT,
)

# --- Bounded Image Cache ---
# Caches compressed image bytes to avoid duplicate compression
# when extraction and description activities process the same image.
_IMAGE_CACHE_MAX_SIZE = 200
_image_cache: OrderedDict[str, tuple[bytes, str]] = OrderedDict()


def _image_cache_get(key: str) -> tuple[bytes, str] | None:
    """Get a cached compressed image, moving it to the end (most recently used)."""
    if key in _image_cache:
        _image_cache.move_to_end(key)
        return _image_cache[key]
    return None


def _image_cache_put(key: str, value: tuple[bytes, str]) -> None:
    """Store a compressed image in the cache, evicting oldest if at capacity."""
    if key in _image_cache:
        _image_cache.move_to_end(key)
    else:
        if len(_image_cache) >= _IMAGE_CACHE_MAX_SIZE:
            _image_cache.popitem(last=False)
    _image_cache[key] = value


# --- Image Compression Helper ---

# Maximum size for VLM images
# Base64 encoding adds ~33% overhead, plus JSON structure
# Cloud API limit is ~1MB payload, so: 1MB / 1.33 ≈ 750KB safe limit
VLM_IMAGE_MAX_BYTES = 750_000  # 750KB


def _compress_image_for_vlm(image_bytes: bytes, image_ref: str) -> tuple[bytes, str]:
    """
    Compress image to JPEG using Pillow with progressive quality/size reduction.

    Strategy:
    1. Start at Q=90, reduce by 5 until Q=75 if too large
    2. If still too large at Q=75, resize by 20% and restart quality loop
    3. Repeat until image fits under size limit

    Args:
        image_bytes: Original image bytes
        image_ref: Image reference for logging

    Returns:
        Tuple of (compressed_image_bytes, mime_type)
    """
    original_size = len(image_bytes)

    try:
        img = Image.open(io.BytesIO(image_bytes))
        original_width, original_height = img.size

        # Convert to RGB if necessary (handles RGBA, P, L modes)
        if img.mode in ("RGBA", "LA", "P"):
            # Create white background and paste image with alpha
            background = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            if img.mode in ("RGBA", "LA"):
                background.paste(img, mask=img.split()[-1])  # Use alpha as mask
            else:
                background.paste(img)
            img = background
        elif img.mode != "RGB":
            img = img.convert("RGB")

        original_img = img
        current_img = img
        current_width = original_width
        current_height = original_height
        scale_factor = 1.0
        compressed_bytes: bytes = b""

        # Loop: reduce quality, then resize if needed
        max_resize_iterations = 5  # Safety limit (0.8^5 = ~33% of original size)
        for _resize_iteration in range(max_resize_iterations):
            # Try quality levels: 90 -> 85 -> 80 -> 75
            for quality in [90, 85, 80, 75]:
                buffer = io.BytesIO()
                current_img.save(buffer, format="JPEG", quality=quality, optimize=True)
                compressed_bytes = buffer.getvalue()

                if len(compressed_bytes) <= VLM_IMAGE_MAX_BYTES:
                    activity.logger.info(
                        f"Image {image_ref}: {original_width}x{original_height}px -> "
                        f"{current_width}x{current_height}px, "
                        f"{original_size / 1024:.1f}KB -> {len(compressed_bytes) / 1024:.1f}KB "
                        f"(Q={quality}, scale={scale_factor:.0%})"
                    )
                    return compressed_bytes, "image/jpeg"

            # Quality reduction didn't help enough, resize by 20%
            scale_factor *= 0.8
            current_width = int(original_width * scale_factor)
            current_height = int(original_height * scale_factor)
            current_img = original_img.resize((current_width, current_height), Image.Resampling.LANCZOS)
            activity.logger.debug(
                f"Resizing {image_ref} to {current_width}x{current_height}px (scale={scale_factor:.0%})"
            )

        # If we get here, return the last compressed version anyway
        activity.logger.warning(
            f"Image {image_ref} still large after max compression: {len(compressed_bytes) / 1024:.1f}KB"
        )
        return compressed_bytes, "image/jpeg"

    except Exception as e:
        activity.logger.warning(f"Failed to compress image {image_ref}: {e}. Using original.")
        mime_type, _ = mimetypes.guess_type(image_ref)
        if mime_type is None:
            mime_type = "image/jpeg"
        return image_bytes, mime_type


# --- VLM Client Singleton ---
_vlm_client_instance: AsyncOpenAI | None = None
_async_client_lock = asyncio.Lock()


async def get_async_vlm_client() -> AsyncOpenAI:
    """
    Lazy initialization of the Async VLM client.
    All requests are routed through the LiteLLM proxy.
    """
    global _vlm_client_instance
    async with _async_client_lock:
        if _vlm_client_instance is None:
            timeout_seconds = float(get_config().VLM_TIMEOUT_SECONDS)
            http_client = httpx.AsyncClient(
                limits=httpx.Limits(
                    max_connections=200,
                    max_keepalive_connections=50,
                ),
                timeout=httpx.Timeout(timeout_seconds),
            )
            activity.logger.info("VLM client initialized: LiteLLM proxy")
            _vlm_client_instance = AsyncOpenAI(
                api_key=ENV.LITELLM_MASTER_KEY.get_secret_value(),
                base_url=ENV.LITELLM_BASE_URL,
                timeout=timeout_seconds,
                http_client=http_client,
            )
    return _vlm_client_instance


# --- VLM Activities ---


class VLMInvokeInput(BaseModel):
    image_data: Base64Bytes
    image_ref: str
    prompt: str
    task_name: str
    element_type: str = "image"


@activity.defn(name="vlm_invoke")
async def _vlm_invoke(
    input: VLMInvokeInput,
) -> str:
    """
    VLM invocation activity that receives image bytes directly.
    """
    image_bytes = bytes(input.image_data)
    image_ref = input.image_ref
    prompt = input.prompt
    task_name = input.task_name
    element_type = input.element_type
    model_name = ENV.VLLM_MODEL

    activity.logger.info(f"VLM {task_name}: {image_ref} ({element_type})")

    # Cache key: hash of image content + prompt + model
    image_hash = hashlib.sha256(image_bytes).hexdigest()

    # Resize and encode image (prevents 413 errors from cloud APIs)
    # Use in-memory cache to avoid re-compressing the same image
    # when extraction and description activities process the same image.
    image_cache_key = image_hash
    cached_image = _image_cache_get(image_cache_key)
    if cached_image is not None:
        processed_bytes, mime_type = cached_image
        activity.logger.info(f"Image cache hit for {image_ref}")
    else:
        try:
            loop = asyncio.get_running_loop()
            processed_bytes, mime_type = await loop.run_in_executor(
                None, _compress_image_for_vlm, image_bytes, image_ref
            )
        except Exception as e:
            activity.logger.error(f"Failed to encode {element_type} {image_ref}: {e}")
            raise RuntimeError(f"Failed to prepare {element_type} for VLM: {e}") from e
        _image_cache_put(image_cache_key, (processed_bytes, mime_type))

    base64_image = base64.b64encode(processed_bytes).decode("utf-8")
    image_url_payload = f"data:{mime_type};base64,{base64_image}"

    # Single VLM API call — throttle handles rate limiting, Temporal handles retries.
    # No in-app retry loop: it compounded with Temporal retries causing 42+ min hangs.
    async_client = await get_async_vlm_client()

    # Throttle: rate limiter (outside) then semaphore (inside)
    async with get_model_throttle("vlm").acquire():
        response = await async_client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": wrap_system_prompt(prompt, lang="vlm_de")},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": image_url_payload},
                        },
                    ],
                },
            ],
            max_tokens=get_config().VLM_MAX_TOKENS,
            temperature=0,
        )

    activity.logger.debug(f"VLM done: {image_ref}")
    result = response.choices[0].message.content

    # The OpenAI API defines `content` as Optional[str].  When the model
    # returns no content (e.g. refusal, empty response, image not visible),
    # we get None.  Raise a retryable error so Temporal retries the activity
    # — these failures are typically transient (VLM infra issues).
    if result is None or not result.strip():
        raise ApplicationError(
            f"VLM returned empty response for {task_name}: {image_ref} ({element_type})",
            type="VLMEmptyResponse",
            non_retryable=False,
        )

    return result


# --- Workflow-Facing Wrappers ---


async def vlm_extract_content(
    image_data: bytes,
    image_ref: str,
    element_type: str,
) -> str:
    """
    Workflow wrapper for VLM content extraction.

    Extracts text and table content from an image using VLM.
    """
    return await workflow.execute_activity(
        _vlm_invoke,
        VLMInvokeInput(
            image_data=image_data,
            image_ref=image_ref,
            prompt=VLM_EXTRACTION_PROMPT,
            task_name="vlm_extract",
            element_type=element_type,
        ),
        start_to_close_timeout=timedelta(minutes=get_config().VLM_ACTIVITY_TIMEOUT_MINUTES),
        retry_policy=RetryPolicy(
            maximum_attempts=get_config().TEMPORAL_VLM_ACTIVITY_MAX_ATTEMPTS,
            initial_interval=timedelta(seconds=10),
            backoff_coefficient=2,
            maximum_interval=timedelta(seconds=60),
        ),
    )


async def vlm_describe_image(
    image_data: bytes,
    image_ref: str,
) -> str:
    """
    Workflow wrapper for VLM image description.

    Generates a brief visual description of an image using VLM.

    NOTE: Always uses default VLM (Nanonets), not table-specific model.
    This ensures visual descriptions are consistent regardless of element type.
    """
    return await workflow.execute_activity(
        _vlm_invoke,
        VLMInvokeInput(
            image_data=image_data,
            image_ref=image_ref,
            prompt=VLM_DESCRIPTION_PROMPT,
            task_name="vlm_describe",
            element_type="image",  # Force "image" type
        ),
        start_to_close_timeout=timedelta(minutes=get_config().VLM_ACTIVITY_TIMEOUT_MINUTES),
        retry_policy=RetryPolicy(
            maximum_attempts=get_config().TEMPORAL_VLM_ACTIVITY_MAX_ATTEMPTS,
            initial_interval=timedelta(seconds=10),
            backoff_coefficient=2,
            maximum_interval=timedelta(seconds=60),
        ),
    )
