from pydantic import BaseModel


class NodeSummaryResponse(BaseModel):
    summary: str


class RecursiveSummaryResponse(BaseModel):
    summary: str
