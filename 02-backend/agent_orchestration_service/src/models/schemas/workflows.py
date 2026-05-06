from pydantic import BaseModel

from src.models.schemas.config import CamelConfig


class WorkflowResponse(BaseModel, CamelConfig):
    parent_job_id: str


class CancelWorkflowResponse(BaseModel, CamelConfig):
    workflow_id: str
