from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config.settings import settings


def add_cors(app: FastAPI) -> None:
    """Adds CORS (Cross-Origin Resource Sharing) middleware to the FastAPI app."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=settings.ALLOWED_HTTP_METHODS,
        allow_headers=["*"],
    )
