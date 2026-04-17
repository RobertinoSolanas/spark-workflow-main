"""
Temporal activities for interacting with the DMS API.
"""

import json
from typing import Any

from temporal.workflows.formale_pruefung import DMSFileResponse
from temporalio import activity

from src.schemas.dms_schemas import (
    DMSDocument,
    DMSInhaltsExtraction,
    DownloadJsonFromDmsInput,
    InhaltsExtraktionChunksActivityParams,
    UploadTemporalCheckpointInput,
)
from src.services.dms_client import DMSClient


@activity.defn
async def get_inhalts_extraktion_docs(project_id: str) -> list[DMSDocument]:
    """Retrieves all documents associated with a project for table of contents extraction.

    This activity interfaces with the DMS API to fetch a list of document metadata
    required for the subsequent identification of the Inhaltsverzeichnis.

    Args:
        project_id: The unique identifier of the project whose documents
            need to be retrieved.

    Returns:
        A list of DMSDocument objects containing IDs and names for all
        files in the project.
    """
    client = DMSClient()
    return await client.get_dms_documents(project_id)


@activity.defn
async def get_inhalts_extraktion_doc_chunks(
    params: InhaltsExtraktionChunksActivityParams,
) -> DMSInhaltsExtraction:
    """
    Activity to retrieve filtered document chunks from DMS using file_id.

    Args:
        params (InhaltsExtraktionChunksActivityParams): Parameters including
            file_id (main identifier), project_id, and page filters.

    Returns:
        DMSInhaltsExtraction: The chunks and summmary for the requested file.

    Raises:
        RuntimeError: If there is an error retrieving or processing the file.
    """
    client = DMSClient()
    return await client.get_extraction_data(
        dms_document=params.dms_document,
        n_pages=params.n_pages,
        include_summary=params.include_summary,
    )


@activity.defn
async def upload_temporal_checkpoint(
    params: UploadTemporalCheckpointInput,
) -> DMSFileResponse:
    """Uploads an intermediate workflow state as a checkpoint to the DMS.

    This activity persists a JSON-serializable payload to the Document Management
    System, allowing Temporal workflows to track progress or store results
    outside of the Temporal history. It is intended for smaller payloads
    (typically under 2MB).

    Args:
        params: An object containing the project, workflow, and run identifiers,
            as well as the target filename and the data payload to be stored.

    Returns:
        A DMSFileResponse containing the metadata of the successfully
        uploaded checkpoint.
    """
    # Our files are far below 2MB for larger files it needs to be done unsafe in the
    # workflow
    if isinstance(params.payload, str):
        final_payload = params.payload
    else:
        final_payload = json.dumps(params.payload)
    client = DMSClient()
    return await client.upload_temporal_checkpoint(
        project_id=params.project_id,
        workflow_id=params.workflow_id,
        run_id=params.run_id,
        filename=params.filename,
        payload=final_payload,
    )


@activity.defn
async def download_json_from_dms(params: DownloadJsonFromDmsInput) -> Any:
    """Downloads a JSON file from the DMS using its file ID.

    This activity retrieves the file content from the Document Management System
    and returns it as a parsed JSON object (dict or list).

    Args:
        params (DownloadJsonFromDmsInput): The input parameters containing the file ID.

    Returns:
        Any: The parsed JSON content of the file.
    """
    client = DMSClient()
    json_data = await client.download_json(file_id=params.file_id)

    activity.logger.info(f"Successfully downloaded JSON for file_id: {params.file_id}")
    return json_data
