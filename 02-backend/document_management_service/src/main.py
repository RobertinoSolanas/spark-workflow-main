from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from src.api.middlewares.cors import add_cors
from src.api.middlewares.http_method_restrictions import (
    HTTPMethodRestrictionsMiddleware,
)
from src.api.middlewares.security_headers import SecurityHeadersMiddleware
from src.api.middlewares.utf8_enforcement import UTF8EnforcementMiddleware
from src.api.routers import api_router
from src.api.routes.probe_router import probe_router
from src.config.handlers import register_exception_handlers
from src.lifespan import lifespan

app = FastAPI(lifespan=lifespan)

# Middlewares are executed in LIFO order
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(UTF8EnforcementMiddleware)
app.add_middleware(HTTPMethodRestrictionsMiddleware)
add_cors(app)

# Exception Handlers
register_exception_handlers(app=app)

# adds /metrics endpoint for Prometheus to scrape
Instrumentator().instrument(app).expose(app)

app.include_router(api_router)
app.include_router(probe_router)


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}
