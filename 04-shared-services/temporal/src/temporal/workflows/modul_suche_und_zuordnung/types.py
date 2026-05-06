from typing import Any

from pydantic import BaseModel


class NormOrchestratorWorkflowInput(BaseModel):
    data: dict[str, Any]
    project_id: str
    normdetail_id: str


class PageIndexSVMWorkflowOutput(BaseModel):
    result: dict[str, Any] | None


class SatzResult(BaseModel):
    satz_key: str
    child_workflow_id: str | None
    research_report: str | None
    svm_outputs: list[PageIndexSVMWorkflowOutput]


class NormOrchestratorWorkflowOutput(BaseModel):
    norm: str
    satz_results: list[SatzResult]
