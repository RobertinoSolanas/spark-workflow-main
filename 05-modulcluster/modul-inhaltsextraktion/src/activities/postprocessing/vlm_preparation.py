# src/activities/postprocessing/vlm_preparation.py
"""
Temporal activities for VLM input preparation.
"""

from datetime import timedelta

from temporalio import activity, workflow
from temporalio.common import RetryPolicy

from src.activities.postprocessing.filtering import FilterEnhanceResult
from src.config import get_config
from src.utils.prepare_vlm_inputs import prepare_vlm_inputs
from src.workflows.vlm_enhancement.output_format import VLMWorkflowInput


@activity.defn(name="prepare_vlm_inputs")
async def _prepare_vlm_inputs_activity(
    input: FilterEnhanceResult,
) -> list[VLMWorkflowInput]:
    """Prepare VLM inputs from filtered extraction results."""
    return prepare_vlm_inputs(input)


async def prepare_vlm_inputs_wrapper(
    filtered_results: FilterEnhanceResult,
) -> list[VLMWorkflowInput]:
    """Workflow wrapper for prepare_vlm_inputs activity."""
    return await workflow.execute_activity(
        _prepare_vlm_inputs_activity,
        filtered_results,
        start_to_close_timeout=timedelta(minutes=5),
        retry_policy=RetryPolicy(maximum_attempts=get_config().TEMPORAL_PROCESSING_ACTIVITY_MAX_ATTEMPTS),
    )
