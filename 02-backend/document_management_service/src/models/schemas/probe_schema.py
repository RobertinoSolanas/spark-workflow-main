from typing import Literal

from pydantic import BaseModel, Field


class HealthStatus(BaseModel):
    status: str = Field(..., description="Overall status")
    reason: str | None = Field(None, description="Failure reason if not ok")


class CheckResponse(HealthStatus):
    """Used for /ready and /healthz"""

    status: Literal["ok"] = "ok"
