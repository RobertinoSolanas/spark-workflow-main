import ssl
from collections.abc import AsyncIterable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from io import BytesIO
from typing import Any
from uuid import UUID

import httpx
from event_logging.enums import (
    EventAction,
    EventCategory,
    EventOutcome,
)

from src.config.settings import settings
from src.models.schemas.files import FileObject, FileUploadArgs
from src.models.schemas.temporal.fvp import TemplateDocumentTypeResponse
from src.utils.logger import logger


class ApiClient:
    timeout = settings.api.timeout

    @classmethod
    async def _request(
        cls,
        method: str,
        url: str,
        action: EventAction,
        **kwargs: Any,
    ) -> httpx.Response:
        async with httpx.AsyncClient(timeout=cls.timeout) as client:
            try:
                response = await client.request(method, url, **kwargs)
                response.raise_for_status()
            except httpx.HTTPStatusError:
                try:
                    body = response.json()
                except (ValueError, UnicodeDecodeError):
                    body = response.text
                logger.error(
                    action=action,
                    outcome=EventOutcome.FAILURE,
                    category=EventCategory.FILE,
                    message=f"Failed {method} {response.status_code} {url}: {body}",
                )
                raise
            except httpx.RequestError as e:
                logger.error(
                    action=action,
                    outcome=EventOutcome.FAILURE,
                    category=EventCategory.FILE,
                    message=f"Failed {method} {url}: {e}",
                )
                raise
            return response

    @classmethod
    async def get(
        cls, url: str, params: dict | None = None, headers: dict | None = None
    ) -> httpx.Response:
        return await cls._request("GET", url, EventAction.DOWNLOAD, params=params, headers=headers)

    @classmethod
    @asynccontextmanager
    async def get_stream(
        cls,
        url: str,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        verify_ssl: bool = True,
    ) -> AbstractAsyncContextManager[httpx.Response]:
        default_headers = {"Accept": "*/*"}

        if headers:
            default_headers.update(headers)

        ssl_context = None
        if not verify_ssl:
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

        async with httpx.AsyncClient(
            headers=default_headers,
            verify=ssl_context,
            timeout=httpx.Timeout(300, connect=10),
        ) as client:
            async with client.stream("GET", url, params=params) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    logger.error(
                        action=EventAction.DOWNLOAD,
                        outcome=EventOutcome.FAILURE,
                        category=EventCategory.FILE,
                        message=f"Failed GET {resp.status_code} {url}: {body[:500]}",
                    )
                    raise httpx.HTTPStatusError(
                        "Streaming request failed",
                        request=resp.request,
                        response=resp,
                    )
                yield resp

    @classmethod
    async def post(
        cls, url: str, data: dict | None = None, json: dict | None = None, headers: dict | None = None
    ) -> httpx.Response:
        return await cls._request("POST", url, EventAction.UPLOAD, data=data, json=json, headers=headers)

    @classmethod
    async def put(
        cls, url: str, content: AsyncIterable[bytes] | bytes = None, headers: dict | None = None
    ) -> httpx.Response:
        return await cls._request("PUT", url, EventAction.UPLOAD, content=content, headers=headers)


class FilesApiClient(ApiClient):
    BASE_URL = settings.api.dms_base_url

    @classmethod
    async def get_file(cls, file_name: str, project_id: str) -> FileObject:
        params = {
            # DMS binds the project filter only from query alias `projectId`
            # (FastAPI `Query(alias="projectId")`), so snake_case `project_id`
            # would be ignored and project scoping would not be applied.
            "projectId": project_id,
            "file_type": "document",
            "name": file_name,
        }
        response = await cls.get(f"{cls.BASE_URL}/v2/files", params=params)
        files = response.json()
        if not files:
            logger.error(
                action=EventAction.DOWNLOAD,
                outcome=EventOutcome.FAILURE,
                category=EventCategory.FILE,
                message=f"File {file_name} for project {project_id} not found.",
            )
            raise FileNotFoundError(
                f"File {file_name} for project {project_id} not found."
            )
        return FileObject(**files[0])

    @classmethod
    async def list_files(
        cls, project_id: str, file_type: str = "document"
    ) -> list[FileObject]:
        # DMS reads the project filter via query alias `projectId` (camelCase).
        # Sending `project_id` would skip the project filter and return
        # files outside the requested project scope.
        all_files: list[FileObject] = []
        page_size = 500  # DMS maximum allowed value

        page = 1
        has_next_page = True

        while has_next_page:
            params = {
                "projectId": project_id,
                "file_type": file_type,
                "page": page,
                "page_size": page_size,
            }
            response = await cls.get(f"{cls.BASE_URL}/v2/files", params=params)
            batch = response.json()
            if not isinstance(batch, list):
                raise TypeError(
                    f"Expected a list from DMS /v2/files (page {page}), "
                    f"got {type(batch).__name__}: {batch!r}"
                )
            all_files.extend(FileObject(**f) for f in batch)

            has_next_page = len(batch) >= page_size
            page += 1

        return all_files

    @classmethod
    async def download_file(cls, file_id: UUID) -> BytesIO:
        resp = await cls.get(f"{cls.BASE_URL}/v2/files/{file_id}/generate-download-url")
        download_url = resp.json()["downloadUrl"]
        response = await cls.get(download_url)
        return BytesIO(response.content)

    @classmethod
    async def upload_file(
        cls, file_data: FileUploadArgs, file_content: httpx.Response
    ) -> FileObject:
        data = file_data.model_dump(by_alias=True, exclude_none=True)
        response = await cls.post(
            f"{cls.BASE_URL}/v2/files/generate-upload-url", json=data
        )
        response_data = response.json()
        if settings.USE_TRANSFER_ENCODING_CHUNKED:
            await cls.put(
                url=response_data["uploadUrl"],
                content=file_content.aiter_bytes(),
                headers={
                    "Content-Type": response_data["mimeType"],
                    "Transfer-Encoding": "chunked",
                },
            )
        else:
            file_bytes = b"".join([chunk async for chunk in file_content.aiter_bytes()])
            await cls.put(
                url=response_data["uploadUrl"],
                content=file_bytes,
                headers={
                    "Content-Type": response_data["mimeType"],
                },
            )
        response = await cls.post(
            url=f"{cls.BASE_URL}/v2/files/confirm-upload", json=data
        )
        return FileObject(**response.json())


class FVPClient(ApiClient):
    BASE_URL = settings.api.fvp_base_url

    @classmethod
    async def send_fvp_results(cls, project_id: str, file_id: str) -> dict:
        return (
            await cls.post(
                f"{cls.BASE_URL}/{project_id}/results",
                json={"file_id": file_id},
            )
        ).json()

    @classmethod
    async def get_template_document_types(
        cls, project_id: str
    ) -> list[TemplateDocumentTypeResponse]:
        response = await cls.get(f"{cls.BASE_URL}/{project_id}/template-document-types")
        response.raise_for_status()
        return [
            TemplateDocumentTypeResponse.model_validate(item)
            for item in response.json()
        ]

    @classmethod
    async def send_toc_matching_results(cls, project_id: str, file_id: str) -> dict:
        return (
            await cls.post(
                f"{cls.BASE_URL}/{project_id}/toc-notes/results",
                json={"file_id": file_id},
            )
        ).json()


class PlausibilityClient(ApiClient):
    BASE_URL = settings.api.plausibility_notes_base_url

    @classmethod
    async def send_plausibility_results(cls, project_id: str, file_id: str) -> dict:
        return (
            await cls.post(
                f"{cls.BASE_URL}/plausibility-notes/{project_id}/job-done",
                json={"fileId": file_id},
            )
        ).json()


