# ruff: noqa: E402
from temporal.observability import ObservabilityConfig, setup_observability

from src.config.settings import settings

setup_observability(
    ObservabilityConfig(
        service_name=settings.OTEL_SERVICE_NAME,
        otel_endpoint=settings.OTEL_ENDPOINT,
    )
)

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from src.api.middlewares.cors import add_cors
from src.api.middlewares.security_headers import SecurityHeadersMiddleware
from src.api.routes.probes_routes import probe_router
from src.api.routes.workflows_api import router as workflows_router
from src.exceptions.exception_handlers import register_exception_handlers
from src.lifespan import lifespan

app = FastAPI(lifespan=lifespan)
Instrumentator().instrument(app).expose(app)
register_exception_handlers(app)
add_cors(app)

app.add_middleware(SecurityHeadersMiddleware)
app.include_router(workflows_router)
app.include_router(probe_router)


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}
