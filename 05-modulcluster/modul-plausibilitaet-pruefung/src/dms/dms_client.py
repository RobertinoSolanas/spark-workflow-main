import json
import logging
import tempfile
from typing import Any

import httpx

from src.config.config import config
from src.config.env import ENV
from src.dms.schemas import (
    BaseMetadata,
    DMSDocument,
    DMSFileResponse,
    DocDataResult,
    DocumentDetailsResponse,
    DocumentMetadata,
    ProjectBaseMetadataStatus,
)

logger = logging.getLogger(__name__)

_ERLAUTERUNGSBERICHT_TYPE = "Erläuterungsbericht"

class DMSClient:
    """
    General client for the Document Management System (DMS) with
    Inhaltsextraktion mapping logic.
    This client provides methods for interacting with the DMS API to list files,
    retrieve download URLs, and process JSON files via temporary storage. It
    also contains specialized methods to map storage files to Inhaltsextraktion
    domain models using file_id as the primary identifier.
    """

    def __init__(self, timeout: int = 120) -> None:
        """
        Initializes the DMS client.
        Args:
            timeout (int): Request timeout in seconds. Defaults to 60.
        """
        self.base_url = ENV.DMS_BASE_URL.rstrip("/")
        self.timeout = timeout
        self.headers = {"Content-Type": "application/json"}

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        """
        Internal helper for making authenticated requests to DMS.
        Args:
            method (str): HTTP method (e.g., "GET", "POST").
            path (str): Endpoint path relative to the base URL.
            **kwargs: Additional arguments passed to the httpx request.
        Returns:
            Any: The parsed JSON response body.
        Raises:
            httpx.HTTPStatusError: If the request returns an error status.
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            url = f"{self.base_url}{path}"
            resp = await client.request(method, url, headers=self.headers, **kwargs)
            resp.raise_for_status()
            return resp.json()

    async def list_files(
        self, project_id: str, file_type: str = "document"
    ) -> list[DMSFileResponse]:
        """
        Lists files for a project, optionally filtered by type.
        Args:
            project_id (str): The unique identifier of the project.
            file_type (Optional[str]): Filter by file type (e.g., "document").
        Returns:
            List[DMSFileResponse]: A list of file metadata objects.
        """
        all_files = []
        page = 1
        # Safety limit to prevent infinite loops (100k files)
        while page <= config.DMS.MAX_PAGES:
            params = {
                "projectId": project_id,
                "page_size": config.DMS.PAGE_SIZE,
                "file_type": file_type,
                "page": page,
            }
            data = await self._request("GET", "/v2/files", params=params)
            if not data:
                break
            all_files.extend([DMSFileResponse(**item) for item in data])
            if len(data) < config.DMS.PAGE_SIZE:
                break
            page += 1
        return all_files

    async def get_dms_documents(self, project_id: str) -> list[DMSDocument]:
        docs = await self.list_files(project_id, file_type="document")
        extraction_docs = await self.list_files(
            project_id, file_type="content_extraction"
        )
        ext_map = {d.filename: d.id for d in extraction_docs}
        results = []
        for d in docs:
            base_path = d.filename.rsplit(".", 1)[0]
            file_name = base_path.split("/")[-1]
            target_path = f"{base_path}/{file_name}_processed.json"
            if target_path in ext_map:
                results.append(
                    DMSDocument(
                        project_id=project_id,
                        document_name=d.filename,
                        document_id=d.id,
                        content_extraction_id=ext_map[target_path],
                    )
                )
        return results

    async def get_download_url(self, file_id: str) -> str:
        """
        Retrieves a signed download URL for a file.
        Args:
            file_id (str): The unique identifier (UUID) of the file.
        Returns:
            str: The signed URL used to download the file.
        """
        data = await self._request("GET", f"/v2/files/{file_id}/generate-download-url")
        return data["downloadUrl"]

    async def download_json(self, file_id: str) -> Any:
        """
        Downloads a JSON file from DMS and parses it using a temporary file.

        Args:
            file_id (str): The unique identifier of the file to download.

        Returns:
            Any: The parsed JSON content of the file.

        Raises:
            httpx.HTTPStatusError: If the download request fails.
        """
        download_url = await self.get_download_url(file_id)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(download_url)
            resp.raise_for_status()
            with tempfile.NamedTemporaryFile(
                mode="w+", delete=True, suffix=".json", encoding="utf-8"
            ) as tmp:
                tmp.write(resp.text)
                tmp.seek(0)
                return json.load(tmp)

    async def get_extraction_data(
        self,
        dms_document: DMSDocument,
        n_pages: int | None = None,
        include_summary: bool = False,
    ) -> DocDataResult:
        """
        Retrieves and filters subchunks based on page numbers using file_id.
        Args:
            dms_document: The document object containing the file identifier and metadata.
            n_pages (Optional[int]): Filter for subchunks with page <= n_pages.
            include_summary (bool): Whether to include the summary.
        Returns:
            DocDataResult: Filtered subchunks and optional summary.
        """
        f_id = dms_document.content_extraction_id
        data = await self.download_json(f_id)
        details = DocumentDetailsResponse(**data)

        filtered_chunks = [
            sub_chunk
            for chunk in details.chunks
            for sub_chunk in (chunk.sub_chunks or [])
            if n_pages is None or any(p <= n_pages for p in sub_chunk.metadata.page_numbers)
        ]

        return DocDataResult(
            dms_document=dms_document,
            title=details.metadata.title,
            chunks=filtered_chunks,
            summary=details.metadata.summary if include_summary else None,
        )

    async def get_project_base_metadata(
        self,
        project_id: str,
    ) -> tuple[BaseMetadata, ProjectBaseMetadataStatus]:
        extraction_files = await self.list_files(project_id=project_id, file_type="content_extraction")

        summary_candidates = [extr_file for extr_file in extraction_files if extr_file.filename == "summary.json"]

        if len(summary_candidates) != 1:
            raise ValueError(f"Found {len(summary_candidates)} summary files for project {project_id}")

        summary_extraction_id = summary_candidates[0].id

        summary_json = await self.download_json(summary_extraction_id)
        raw_base_metadata = summary_json.get("base_metadata")
        if raw_base_metadata is None:
            logger.warning(
                "Project %s has summary.json without base_metadata. Using explicit unknown fallback.",
                project_id,
            )
            return (
                BaseMetadata.fallback_unknown(project_id),
                ProjectBaseMetadataStatus.FALLBACK_MISSING,
            )

        base_metadata = BaseMetadata.model_validate(raw_base_metadata)

        return base_metadata, ProjectBaseMetadataStatus.COMPLETE

    async def upload_file(
        self,
        project_id: str,
        filename: str,
        payload: Any,
        file_type: str = "document",
        extra_params: dict[str, Any] | None = None,
    ) -> DMSFileResponse:
        """Uploads a JSON payload to the DMS via signed URL and confirms it.
        Args:
            project_id: The unique identifier of the project.
            filename: The target path/name for the file in storage.
            payload: The JSON-serializable data to be uploaded.
            file_type: The DMS file category (e.g., 'content_extraction').
            extra_params: Optional additional metadata fields (e.g., workflow_id, run_id).
        Returns:
            The metadata of the confirmed file.
        Raises:
            httpx.HTTPStatusError: If the URL generation, upload, or confirmation fails.
        """
        params = {
            "filename": filename,
            "projectId": project_id,
            "type": file_type,
            "createNewVersion": True,
            **(extra_params or {}),
        }
        meta = await self._request("POST", "/v2/files/generate-upload-url", json=params)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.put(
                meta["uploadUrl"],
                content=json.dumps(payload),
                headers={"Content-Type": str(meta.get("mimeType", "application/json"))},
                timeout=self.timeout,
            )
            resp.raise_for_status()
        # TODO There might be a need to add a wait for DMS upload delay
        data = await self._request("POST", "/v2/files/confirm-upload", json=params)
        return DMSFileResponse(**data)

    async def upload_temporal_checkpoint(
        self,
        project_id: str,
        workflow_id: str,
        run_id: str,
        filename: str,
        payload: Any,
    ) -> DMSFileResponse:
        """Specific helper to upload temporal checkpoints.
        Args:
            project_id: The unique identifier of the project.
            workflow_id: The temporal workflow identifier.
            run_id: The temporal run identifier.
            filename: The target filename in storage.
            payload: The JSON-serializable state to save.
        Returns:
            The metadata of the confirmed checkpoint file.
        """
        extra = {"workflow_id": workflow_id, "run_id": run_id}
        return await self.upload_file(
            project_id=project_id,
            filename=filename,
            payload=payload,
            file_type="temporal_checkpoint",
            extra_params=extra,
        )

    async def fetch_erlauterungsbericht_document_ids(self, classification_file_id: str) -> list[str]:
        """Fetches and extracts Erläuterungsbericht document IDs from DMS classification output."""
        if not classification_file_id:
            logger.warning("No classification file ID provided, skipping Erläuterungsbericht document fetch.")
            return []
        classification_data = await self.download_json(classification_file_id)
        for entry in classification_data.get("matched_document_types", []):
            if entry.get("required_document_type", {}).get("document_type_name") == _ERLAUTERUNGSBERICHT_TYPE:
                ids = [doc["document_id"] for doc in entry.get("assigned_documents", []) if doc.get("document_id")]
                logger.info(f"Found {len(ids)} {_ERLAUTERUNGSBERICHT_TYPE} documents.")
                return ids
        logger.info(f"No {_ERLAUTERUNGSBERICHT_TYPE} documents found.")
        return []

    async def get_document_metadata(self, project_id: str, document_id: str) -> DocumentMetadata:
        """Fetches document metadata from DMS for a given project and document ID."""
        files = await self.list_files(project_id=project_id, file_type="document")
        for f in files:
            if f.id == document_id:
                return DocumentMetadata(
                    project_id=project_id,
                    document_id=document_id,
                    title=f.filename,
                )
        raise ValueError(f"Document with ID {document_id} not found in project {project_id}")