"""HTTP client for docling-serve API communication.

Prefers the async endpoint (/v1/convert/file/async) which processes conversions
in a background worker, keeping docling-serve's health endpoint responsive.
Falls back to the sync endpoint (/v1/convert/file) if the async endpoint is
not available (HTTP 404/405).
"""

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any

import httpx

from src.config import get_config

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 3
MAX_NETWORK_ERRORS = 20
MAX_SUBMIT_RETRIES = 3
SUBMIT_RETRY_DELAY = 10
_RETRYABLE_STATUS_CODES = {502, 503, 504}

# Poll/fetch requests must complete well within the 2-minute heartbeat timeout.
# The 300s client-level timeout is for large file uploads (submit); polls and
# fetches should never take that long.
_SHORT_TIMEOUT = httpx.Timeout(90.0, connect=30.0)


class DoclingApiClient:
    """Handles HTTP communication with docling-serve API."""

    def __init__(self, base_url: str, timeout: int) -> None:
        self.base_url = base_url
        self.timeout = timeout

    def _form_data(self) -> dict[str, Any]:
        """Shared form data for both sync and async endpoints."""
        return {
            "to_formats": ["md", "json"],
            "image_export_mode": "embedded",
            "do_ocr": "true",
            "ocr_engine": get_config().DOCLING_OCR_ENGINE,
            "ocr_lang": get_config().DOCLING_OCR_LANG,
            "table_mode": "accurate",
            "document_timeout": str(self.timeout),
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def convert_document(
        self,
        pdf_bytes: bytes,
        pdf_filename: str,
        heartbeat_fn: Callable[[str], None] | None = None,
        log_fn: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        """
        Convert a PDF document via docling-serve.

        Tries the async endpoint first (submit/poll/fetch). If the async
        endpoint is not available (404/405), falls back to the blocking
        sync endpoint transparently.

        Args:
            pdf_bytes: Raw PDF file bytes
            pdf_filename: Original filename of the PDF
            heartbeat_fn: Called each poll iteration (e.g. activity.heartbeat)
            log_fn: Called for key status messages (e.g. activity.logger.info)

        Returns:
            API response dict with document JSON and markdown content

        Raises:
            RuntimeError: If conversion fails, times out, or the task is lost
        """

        def _log(msg: str) -> None:
            logger.info(msg)
            if log_fn:
                log_fn(msg)

        # Timeout for async requests: 5 min read allows large file uploads
        # on submit and large result downloads on fetch; poll responses are tiny.
        async_timeout = httpx.Timeout(300.0, connect=30.0)

        async with httpx.AsyncClient(
            timeout=async_timeout,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=5),
        ) as client:
            # Try async endpoint first, with retries for transient errors
            task_id = await self._submit_with_retries(client, pdf_bytes, pdf_filename, _log, heartbeat_fn)
            if task_id is None:
                # Fallback to sync was triggered
                return await self._convert_sync(pdf_bytes, pdf_filename, _log, heartbeat_fn)

            # Poll until task completes
            await self._poll_until_done(client, task_id, heartbeat_fn, _log)

            # Fetch result
            return await self._fetch_result(client, task_id)

    # ------------------------------------------------------------------
    # Async path: submit → poll → fetch
    # ------------------------------------------------------------------

    async def _submit_with_retries(
        self,
        client: httpx.AsyncClient,
        pdf_bytes: bytes,
        pdf_filename: str,
        log_fn: Callable[[str], None],
        heartbeat_fn: Callable[[str], None] | None,
    ) -> str | None:
        """Submit with retries for transient errors.

        Returns task_id on success, None if sync fallback should be used.
        Raises RuntimeError (with concise message) if all retries fail.
        """
        last_error: Exception | None = None

        for attempt in range(1, MAX_SUBMIT_RETRIES + 1):
            if heartbeat_fn:
                heartbeat_fn(f"submitting to docling (attempt {attempt})")
            try:
                task_id = await self._submit_async(client, pdf_bytes, pdf_filename)
                log_fn(f"Async docling task submitted: {task_id}")
                return task_id
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (404, 405):
                    log_fn("Async endpoint not available, falling back to sync endpoint")
                    return None
                if e.response.status_code in _RETRYABLE_STATUS_CODES:
                    last_error = e
                    log_fn(
                        f"Submit attempt {attempt}/{MAX_SUBMIT_RETRIES} "
                        f"got HTTP {e.response.status_code} "
                        f"for '{pdf_filename}'"
                    )
                    if attempt < MAX_SUBMIT_RETRIES:
                        await asyncio.sleep(SUBMIT_RETRY_DELAY)
                    continue
                raise RuntimeError(
                    f"docling-serve submit failed: HTTP {e.response.status_code} for {pdf_filename}"
                ) from None
            except httpx.TransportError as e:
                last_error = e
                log_fn(
                    f"Submit attempt {attempt}/{MAX_SUBMIT_RETRIES} failed "
                    f"for '{pdf_filename}': {type(e).__name__}: {e}"
                )
                if attempt < MAX_SUBMIT_RETRIES:
                    await asyncio.sleep(SUBMIT_RETRY_DELAY)

        raise RuntimeError(
            f"docling-serve submit failed after {MAX_SUBMIT_RETRIES} attempts "
            f"for '{pdf_filename}': {type(last_error).__name__}"
        )

    async def _submit_async(
        self,
        client: httpx.AsyncClient,
        pdf_bytes: bytes,
        pdf_filename: str,
    ) -> str:
        """Submit a document for async conversion. Returns the task_id."""
        response = await client.post(
            f"{self.base_url}/v1/convert/file/async",
            files={"files": (pdf_filename, pdf_bytes, "application/pdf")},
            data=self._form_data(),
        )
        response.raise_for_status()
        data = response.json()
        task_id = data.get("task_id")
        if not task_id:
            raise RuntimeError(f"docling-serve did not return a task_id (keys: {list(data.keys())})")
        return task_id

    async def _poll_until_done(
        self,
        client: httpx.AsyncClient,
        task_id: str,
        heartbeat_fn: Callable[[str], None] | None,
        log_fn: Callable[[str], None],
    ) -> None:
        """Poll the task status until success or failure.

        Two retry strategies:
        - Network errors (ReadTimeout, ConnectError): server may be dead.
          Give up after MAX_NETWORK_ERRORS consecutive failures.
        - HTTP 502/503/504: server IS alive, just overloaded.
          Keep polling until the overall deadline — the task is still processing.
        """
        deadline = time.monotonic() + self.timeout
        consecutive_network_errors = 0
        consecutive_http_errors = 0

        while True:
            if time.monotonic() >= deadline:
                raise RuntimeError(f"docling-serve conversion timed out after {self.timeout}s (task_id={task_id})")

            if heartbeat_fn:
                heartbeat_fn(f"polling docling task {task_id}")

            try:
                response = await client.get(
                    f"{self.base_url}/v1/status/poll/{task_id}",
                    timeout=_SHORT_TIMEOUT,
                )
            except httpx.TransportError as e:
                consecutive_network_errors += 1
                log_fn(f"Network error polling task {task_id} ({consecutive_network_errors}/{MAX_NETWORK_ERRORS}): {e}")
                if consecutive_network_errors >= MAX_NETWORK_ERRORS:
                    raise RuntimeError(
                        f"docling-serve unreachable after {MAX_NETWORK_ERRORS} "
                        f"consecutive network errors (task_id={task_id}): {e}"
                    ) from e
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
                continue

            consecutive_network_errors = 0

            if response.status_code in _RETRYABLE_STATUS_CODES:
                consecutive_http_errors += 1
                if consecutive_http_errors % 20 == 1:
                    log_fn(
                        f"docling-serve busy (HTTP {response.status_code}), "
                        f"still polling task {task_id} "
                        f"({consecutive_http_errors} retries, "
                        f"{int(deadline - time.monotonic())}s remaining)"
                    )
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
                continue

            consecutive_http_errors = 0

            if response.status_code == 404:
                raise RuntimeError(f"docling-serve task lost — pod likely restarted (task_id={task_id})")
            response.raise_for_status()

            data = response.json()
            if not isinstance(data, dict):
                raise RuntimeError(f"docling-serve returned non-dict poll response: {type(data).__name__}")
            status = data.get("task_status", "")
            log_fn(f"Docling task {task_id} status: {status}")

            if status == "success":
                return
            if status == "failure":
                raise RuntimeError(f"docling-serve async conversion failed (task_id={task_id})")
            # "pending" / "started" → sleep and continue polling
            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    async def _fetch_result(
        self,
        client: httpx.AsyncClient,
        task_id: str,
    ) -> dict[str, Any]:
        """Fetch the conversion result for a completed task.

        Retries on transient errors to avoid re-submitting the entire
        document just because the result download failed once.
        """
        last_error: Exception | None = None

        for attempt in range(1, MAX_SUBMIT_RETRIES + 1):
            try:
                response = await client.get(
                    f"{self.base_url}/v1/result/{task_id}",
                    timeout=_SHORT_TIMEOUT,
                )
                if response.status_code in _RETRYABLE_STATUS_CODES:
                    last_error = RuntimeError(f"HTTP {response.status_code}")
                    logger.warning(
                        f"Fetch attempt {attempt}/{MAX_SUBMIT_RETRIES} "
                        f"got HTTP {response.status_code} for task {task_id}"
                    )
                    if attempt < MAX_SUBMIT_RETRIES:
                        await asyncio.sleep(SUBMIT_RETRY_DELAY)
                    continue
                response.raise_for_status()
                return self._validate_result(response.json())
            except httpx.TransportError as e:
                last_error = e
                logger.warning(
                    f"Fetch attempt {attempt}/{MAX_SUBMIT_RETRIES} failed for task {task_id}: {type(e).__name__}: {e}"
                )
                if attempt < MAX_SUBMIT_RETRIES:
                    await asyncio.sleep(SUBMIT_RETRY_DELAY)

        raise RuntimeError(
            f"docling-serve fetch failed after {MAX_SUBMIT_RETRIES} attempts "
            f"(task_id={task_id}): {type(last_error).__name__}"
        )

    # ------------------------------------------------------------------
    # Sync fallback: single blocking POST
    # ------------------------------------------------------------------

    async def _convert_sync(
        self,
        pdf_bytes: bytes,
        pdf_filename: str,
        log_fn: Callable[[str], None],
        heartbeat_fn: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        """Blocking sync conversion — used when async endpoint is unavailable.

        Fires heartbeats concurrently so Temporal doesn't kill the activity
        during long-running conversions.
        """
        log_fn(f"Sync docling conversion for '{pdf_filename}' (timeout: {self.timeout}s)")
        timeout = httpx.Timeout(float(self.timeout), connect=30.0)

        async def _do_post() -> httpx.Response:
            async with httpx.AsyncClient(
                timeout=timeout,
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=5),
            ) as client:
                response = await client.post(
                    f"{self.base_url}/v1/convert/file",
                    files={"files": (pdf_filename, pdf_bytes, "application/pdf")},
                    data=self._form_data(),
                )
                response.raise_for_status()
                return response

        if heartbeat_fn:
            # Run POST and heartbeat loop concurrently so Temporal doesn't
            # cancel the activity during a multi-minute sync conversion.
            post_task = asyncio.create_task(_do_post())
            try:
                while not post_task.done():
                    heartbeat_fn("sync docling conversion in progress")
                    await asyncio.sleep(POLL_INTERVAL_SECONDS)
                response = await post_task
            except BaseException:
                post_task.cancel()
                raise
        else:
            response = await _do_post()

        return self._validate_result(response.json())

    # ------------------------------------------------------------------
    # Shared validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_result(result: dict[str, Any]) -> dict[str, Any]:
        """Validate the conversion result, raise on failure/skipped."""
        status = result.get("status", "")
        if status == "failure":
            errors = result.get("errors", [])
            raise RuntimeError(f"docling-serve conversion failed: {errors}")
        if status == "skipped":
            raise RuntimeError("docling-serve skipped document processing")
        return result
