# LiteLLM Proxy

A containerized LiteLLM proxy service that provides a unified OpenAI-compatible API gateway in front of a vLLM backend. It routes model requests, handles authentication, and exposes Prometheus metrics.

## Overview

The *LiteLLM Proxy* is responsible for:

- **Model routing**: Mapping model aliases to vLLM-hosted models via a single OpenAI-compatible API
- **Authentication**: Securing access with a master API key
- **Monitoring**: Exposing Prometheus metrics for LLM usage tracking
- **Config templating**: Substituting environment variables into `config.yaml` at startup

## Available Models

| Model Alias                  | Backend Model                              |
| ---------------------------- | ------------------------------------------ |
| `gpt-oss-120b`              | `openai/openai/gpt-oss-120b`              |
| `mistral-small-24b-instruct`| `openai/mistralai/Mistral-Small-24B-Instruct` |
| `BAAI/bge-m3`               | `openai/BAAI/bge-m3`                      |

Models are configured in `config.yaml` and can be modified or extended by adding entries to the `model_list`.

## Configuration

Clients authenticate against the proxy with `LITELLM_MASTER_KEY` (sent as `Bearer` token). The proxy then forwards requests to the vLLM backend using `VLLM_API_KEY` internally.

| Variable             | Description                              |
| -------------------- | ---------------------------------------- |
| `VLLM_URL`           | Base URL of the vLLM backend             |
| `VLLM_API_KEY`       | API key for the vLLM backend (server-side only, not exposed to clients) |
| `LITELLM_MASTER_KEY` | API key that clients send as `Bearer` token to authenticate against the proxy |

## Docker

```bash
docker build -t litellm-proxy .
docker run -p 4000:4000 \
  -e VLLM_URL=http://vllm:8000 \
  -e VLLM_API_KEY=<your-key> \
  -e LITELLM_MASTER_KEY=<your-master-key> \
  litellm-proxy
```

The proxy will be available at:

- API: http://localhost:4000
- UI: http://localhost:4000/ui
- Prometheus Metrics: via `prometheus` callback

## How It Works

The `entrypoint.py` script processes `config.yaml` at startup, replacing `${VAR_NAME}` placeholders with the corresponding environment variables. The processed config is written to `/app/config_processed.yaml` and passed to LiteLLM, which starts a proxy server on port 4000.
