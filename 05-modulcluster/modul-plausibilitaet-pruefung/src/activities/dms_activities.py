"""Temporal activities for DMS (Document Management Service) operations."""

import asyncio
from typing import Any

from pydantic import BaseModel
from temporalio import activity

from src.dms.schemas import DMSFileResponse
from src.workflows.clients import dms_client


class UploadTemporalCheckpointInput(BaseModel):
    """Input parameters for the upload_temporal_checkpoint activity."""

    project_id: str
    workflow_id: str
    run_id: str
    filename: str
    payload: dict[str, Any]


class AggregateCheckpointsInput(BaseModel):
    """Input parameters for aggregating multiple files into one."""

    project_id: str
    workflow_id: str
    run_id: str
    filename: str
    file_ids: list[str]


@activity.defn
async def fetch_erlauterungsbericht_document_ids(classification_file_id: str | None) -> list[str]:
    """Fetches and extracts Erläuterungsbericht document IDs from DMS classification output."""
    if not classification_file_id:
        return []
    return await dms_client.fetch_erlauterungsbericht_document_ids(classification_file_id)


@activity.defn
async def upload_temporal_checkpoint(
    params: UploadTemporalCheckpointInput,
) -> DMSFileResponse:
    """Temporal activity to upload a checkpoint to the DMS."""
    return await dms_client.upload_temporal_checkpoint(
        project_id=params.project_id,
        workflow_id=params.workflow_id,
        run_id=params.run_id,
        filename=params.filename,
        payload=params.payload,
    )


@activity.defn
async def aggregate_and_upload_checkpoints(
    params: AggregateCheckpointsInput,
) -> DMSFileResponse:
    """Downloads multiple JSON files, aggregates contradictions, and uploads the result."""
    download_tasks = [dms_client.download_json(file_id=fid) for fid in params.file_ids]
    async with asyncio.TaskGroup() as tg:
        task_objs = [tg.create_task(t) for t in download_tasks]
    raw_results = [t.result() for t in task_objs]

    all_contradictions: list[dict[str, Any]] = []
    for doc_result in raw_results:
        if "contradictions" in doc_result:
            all_contradictions.extend(doc_result["contradictions"])

    final_payload = {"contradictions": all_contradictions}

    return await dms_client.upload_temporal_checkpoint(
        project_id=params.project_id,
        workflow_id=params.workflow_id,
        run_id=params.run_id,
        filename=params.filename,
        payload=final_payload,
    )
