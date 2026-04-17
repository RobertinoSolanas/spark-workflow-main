"""Unit tests for job service workflow querying."""

from uuid import uuid4

import pytest

from src.models.schemas.job_service_schemas import ExecutionStatus
from src.services.job_service_service import JobServiceService


class FakeTemporalClient:
    def __init__(self) -> None:
        self.queries: list[str] = []

    async def _iter_workflows(self):
        for _ in ():
            yield None

    def list_workflows(self, query: str):
        self.queries.append(query)
        return self._iter_workflows()


@pytest.mark.asyncio
async def test_get_workflows_filters_out_child_workflows() -> None:
    temporal_client = FakeTemporalClient()
    project_id = uuid4()

    response = await JobServiceService.get_workflows(
        execution_status=ExecutionStatus.ALL,
        project_id=project_id,
        temporal_client=temporal_client,  # type: ignore[arg-type]
    )

    assert temporal_client.queries == [
        f'`ParentWorkflowId` IS null AND `ProjectId` = "{project_id}"'
    ]
    assert response.retrieved_workflows == 0


@pytest.mark.asyncio
async def test_get_workflows_combines_parent_filter_with_other_filters() -> None:
    temporal_client = FakeTemporalClient()
    project_id = uuid4()

    await JobServiceService.get_workflows(
        execution_status=ExecutionStatus.RUNNING,
        project_id=project_id,
        temporal_client=temporal_client,  # type: ignore[arg-type]
    )

    assert temporal_client.queries == [
        '`ParentWorkflowId` IS null AND `ExecutionStatus` = "Running" '
        f'AND `ProjectId` = "{project_id}"'
    ]
