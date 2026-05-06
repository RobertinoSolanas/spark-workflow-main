from datetime import timedelta

from temporalio import activity, workflow
from temporalio.common import RetryPolicy

from src.models.schemas.temporal.fvp import (
    SendFVPResultsActivityArgs,
    SendPlausibilityResultsActivityArgs,
)
from src.models.schemas.temporal.fvp import SendTOCMatchingResultsActivityArgs
from src.services.api_clients import FVPClient, PlausibilityClient

_retry_policy = RetryPolicy(maximum_attempts=5, maximum_interval=timedelta(minutes=1))
_timeout = timedelta(minutes=10)


async def _execute_activity(activity_fn, args) -> dict:
    return await workflow.execute_activity(
        activity_fn,
        args,
        start_to_close_timeout=_timeout,
        retry_policy=_retry_policy,
    )


@activity.defn(name="send_fvp_results")
async def _send_fvp_results(args: SendFVPResultsActivityArgs) -> dict:
    return await FVPClient.send_fvp_results(args.project_id, args.file_id)


async def send_fvp_results(project_id: str, file_id: str) -> dict:
    return await _execute_activity(
        _send_fvp_results, SendFVPResultsActivityArgs(project_id=project_id, file_id=file_id)
    )


@activity.defn(name="send_plausibility_results")
async def _send_plausibility_results(args: SendPlausibilityResultsActivityArgs) -> dict:
    return await PlausibilityClient.send_plausibility_results(args.project_id, args.file_id)


async def send_plausibility_results(project_id: str, file_id: str) -> dict:
    return await _execute_activity(
        _send_plausibility_results, SendPlausibilityResultsActivityArgs(project_id=project_id, file_id=file_id)
    )


@activity.defn(name="send_toc_matching_results")
async def _send_toc_matching_results(args: SendTOCMatchingResultsActivityArgs) -> dict:
    return await FVPClient.send_toc_matching_results(args.project_id, args.file_id)


async def send_toc_matching_results(project_id: str, file_id: str) -> dict:
    return await _execute_activity(
        _send_toc_matching_results, SendTOCMatchingResultsActivityArgs(project_id=project_id, file_id=file_id)
    )
