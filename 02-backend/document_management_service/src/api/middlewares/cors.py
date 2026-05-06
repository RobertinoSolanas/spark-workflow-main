from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config.settings import settings


def add_cors(app: FastAPI) -> None:
    """
    Adds CORS (Cross-Origin Resource Sharing) middleware to the FastAPI app.

    This middleware allows the FastAPI backend to accept requests from
    specified frontend origins defined in the application settings.

    Args:
        app (FastAPI): The FastAPI application instance to which CORS
            middleware will be added.

    Returns:
        None
    """

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=settings.ALLOWED_HTTP_METHODS,
        allow_headers=["*"],
    )
