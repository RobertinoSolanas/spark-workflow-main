ARG INCLUDE_DEPENDENCIES=prod
ARG BASE_IMAGE_DEV=python:3.13-slim
ARG BASE_IMAGE=python:3.13-slim

FROM ${BASE_IMAGE_DEV} AS builder

ENV DEBIAN_FRONTEND=noninteractive
# some apt packages usually needed in Python projects
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    apt-get update && apt-get install -y git curl gcc libpq-dev

# install uv via pip
RUN pip install uv==0.5.27

# UV_PROJECT_ENVIRONMENT configures the environment for the uv project interface
# UV_PYTHON configures the python executable for the uv pip interface
ENV UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_PYTHON=3.13 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_FROZEN=1

# -------------------------------------------------------------
FROM builder AS deps-prod

WORKDIR /src

COPY pyproject.toml uv.lock  ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-install-workspace --all-extras --no-dev --package document-management-service

FROM deps-prod AS deps-dev

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-install-workspace --only-group dev --inexact

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-install-workspace --all-extras --inexact --package document-management-service -v

# -------------------------------------------------------------
FROM deps-${INCLUDE_DEPENDENCIES} AS selected-deps

WORKDIR /src

# Copy all the rest of the code
COPY . .

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --all-extras --inexact --package document-management-service

FROM ${BASE_IMAGE} AS final

WORKDIR /src

ENV VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH" \
    SKIP_DOTENV=true


COPY --from=selected-deps /app/.venv /app/.venv
COPY . .

WORKDIR /src/02-backend/document_management_service

EXPOSE 8000

# UID 65532 -> non-root, this also works with distroless images
USER 65532

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
