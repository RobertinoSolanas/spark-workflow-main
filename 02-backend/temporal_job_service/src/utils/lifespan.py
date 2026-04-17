from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.temporal.client import get_temporal_client
from src.utils.app_state import app_state


@asynccontextmanager
async def lifespan(app: FastAPI):
    await get_temporal_client()
    app_state.startup_complete = True
    yield
    app_state.startup_complete = False
