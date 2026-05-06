from event_logging.middleware import EventLoggingMiddleware
from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from src.api.middlewares.security_headers import SecurityHeadersMiddleware
from src.api.routes.job_service import router as job_router
from src.api.routes.probe_router import probe_router
from src.config.settings import settings
from src.utils.lifespan import lifespan

app = FastAPI(lifespan=lifespan)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    EventLoggingMiddleware,
    service_name=settings.SERVICE_NAME,
    skip_paths=["/healthz", "/metrics"],
)

Instrumentator().instrument(app).expose(app)

app.include_router(job_router)
app.include_router(probe_router)


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}
