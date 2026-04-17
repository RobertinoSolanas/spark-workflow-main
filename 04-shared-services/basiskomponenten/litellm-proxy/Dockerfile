FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir --upgrade pip wheel setuptools && \
    pip install --no-cache-dir \
    "setuptools>=82.0.1" \
    "litellm[proxy]==1.82.6" \
    "google-cloud-aiplatform>=1.133.0,<2.0.0" \
    "google-auth>=2.41.1" \
    "prometheus_client==0.24.1"

COPY entrypoint.py /app/entrypoint.py
RUN chmod +x /app/entrypoint.py

COPY config.yaml /app/config.yaml

RUN chown -R 65532:65532 /app

# UID 65532 -> non-root, this also works with distroless images
USER 65532

ENTRYPOINT ["/app/entrypoint.py"]
