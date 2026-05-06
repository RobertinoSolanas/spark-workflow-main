import asyncio

from temporal.workflows.formale_pruefung import InhaltsverzeichnisMatchingParams, LLMMatchingParams
from temporal.workflows.formale_pruefung.inhaltsverzeichnis_matching import (
    execute_inhaltsverzeichnis_matching_workflow,
)
from temporal.workflows.formale_pruefung.llm_matching import execute_llm_matching_workflow
from temporal.workflows.formale_pruefung.types import DMSFileResponse
from temporal.workflows.inhaltsextraktion.process_documents import (
    ProcessDocumentsWorkflowInput,
    execute_process_documents_workflow,
)
from temporal.workflows.plausibilitaet_pruefung import (
    PlausibilityOrchestratorInput,
    execute_plausibility_orchestrator_workflow,
)
from temporalio import workflow
from temporalio.exceptions import ApplicationError

from src.models.schemas.temporal.fvp import (
    FullFVPWorkflowInput,
    FVPExtractionWorkflowResult,
    FVPExtractionWorkflowResultItem,
)


def _get_result_id(result: object) -> str | None:
    return DMSFileResponse.model_validate(result, from_attributes=True).id


async def run_fvp_workflow(
    args: FullFVPWorkflowInput,
) -> FVPExtractionWorkflowResult:
    if not args.file_ids:
        raise ApplicationError("No files provided", non_retryable=True)

    await execute_process_documents_workflow(
        ProcessDocumentsWorkflowInput(project_id=args.project_id, file_ids=args.file_ids),
        project_id=args.project_id,
    )

    formalpruefung_result, inhaltsverzeichnismatching_result = await asyncio.gather(
        execute_llm_matching_workflow(
            LLMMatchingParams(
                project_id=args.project_id,
                document_types=[dt.model_dump(mode="json") for dt in args.document_types],
            ),
            project_id=args.project_id,
        ),
        execute_inhaltsverzeichnis_matching_workflow(
            InhaltsverzeichnisMatchingParams(
                project_id=args.project_id,
                document_types=[dt.model_dump(mode="json") for dt in args.document_types],
            ),
            project_id=args.project_id,
        ),
        return_exceptions=True,
    )

    classification_file_id = None
    if not isinstance(formalpruefung_result, BaseException):
        classification_file_id = _get_result_id(formalpruefung_result)

    try:
        plausibility_result = await execute_plausibility_orchestrator_workflow(
            PlausibilityOrchestratorInput(
                project_id=args.project_id,
                document_ids=args.file_ids,
                classification_file_id=classification_file_id,
            ),
            project_id=args.project_id,
        )
    except Exception as e:
        plausibility_result = e

    def _to_result_item(name: str, result: object) -> FVPExtractionWorkflowResultItem:
        return FVPExtractionWorkflowResultItem(
            workflow_type=name,
            result=result if not isinstance(result, BaseException) else None,
            error=str(result) if isinstance(result, BaseException) else None,
        )

    return FVPExtractionWorkflowResult(
        results=[
            _to_result_item("formalpruefung", formalpruefung_result),
            _to_result_item("plausibilitaetspruefung", plausibility_result),
            _to_result_item("inhaltsverzeichnismatching", inhaltsverzeichnismatching_result),
        ]
    )


@workflow.defn()
class IsolatedFVPWorkflow:
    """
    Only used for E2E testing. Started via UI
    """

    @workflow.run
    async def run(self, args: FullFVPWorkflowInput) -> FVPExtractionWorkflowResult:
        return await run_fvp_workflow(args)
