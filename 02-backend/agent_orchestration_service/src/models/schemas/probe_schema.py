from typing import Literal

from pydantic import BaseModel, Field


class HealthStatus(BaseModel):
    """Base model for health status"""

    status: str = Field(..., description="Overall status")
    reason: str | None = Field(None, description="Failure reason if not ok")


class CheckResponse(HealthStatus):
    """Response model for health checks"""

    status: Literal["ok"] = "ok"
