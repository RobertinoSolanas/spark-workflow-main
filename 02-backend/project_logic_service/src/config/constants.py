"""Application constants shared across the service."""

# Paths excluded from security headers
SECURITY_HEADERS_EXCLUDED_PATHS = [
    "/",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/healthz",
    "/metrics",
]
