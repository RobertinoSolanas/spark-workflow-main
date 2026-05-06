from datetime import timedelta
from pathlib import Path

from pydantic import BaseModel
from temporalio import activity, workflow
from temporalio.common import RetryPolicy

from src.activities.dms_activities import DmsFileInfo
from src.config import get_config
from src.processors.preprocessor import Preprocessor
from src.utils.dms_utils import (
    download_file,
)


class ConvertToPdfIfNeededInput(BaseModel):
    file_info: DmsFileInfo


@activity.defn(name="convert_to_pdf_if_needed")
async def _convert_to_pdf_if_needed(
    input: ConvertToPdfIfNeededInput,
) -> bytes:
    """
    Download a file from DMS, convert to PDF if needed.
    """
    filename = input.file_info.filename
    file_id = input.file_info.file_id

    activity.logger.info(f"Starting document processing: {Path(filename).stem}")

    file_bytes = await download_file(file_id)
    pdf_bytes, _ = await Preprocessor.convert_to_pdf_if_needed(filename, file_bytes)
    return pdf_bytes


async def convert_to_pdf_if_needed(
    input: ConvertToPdfIfNeededInput,
) -> bytes:
    """Workflow wrapper for DMS PDF conversion."""
    return await workflow.execute_activity(
        _convert_to_pdf_if_needed,
        input,
        start_to_close_timeout=timedelta(minutes=10),
        retry_policy=RetryPolicy(maximum_attempts=get_config().TEMPORAL_PREPROCESSING_ACTIVITY_MAX_ATTEMPTS),
    )
