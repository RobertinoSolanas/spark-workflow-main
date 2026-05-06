# Observability Stack

Configuration files for the local observability stack (traces, logs, metrics, dashboards). All services are started via `docker compose up -d` from the repository root.

## Components

| Service | Image | Port | Purpose |
|---------|-------|------|---------|
| **OTel Collector** | `otel/opentelemetry-collector-contrib` | `4317` (gRPC), `4318` (HTTP) | Receives OTLP traces and logs, enriches Temporal spans, forwards to Tempo and Loki |
| **Tempo** | `grafana/tempo` | `3200` | Distributed tracing backend |
| **Loki** | `grafana/loki` | `3100` | Log aggregation backend |
| **Prometheus** | `prom/prometheus` | `9090` | Metrics collection (scrapes LiteLLM proxy) |
| **Grafana** | `grafana/grafana-oss` | `3000` | Dashboards and data exploration UI |

## Configuration Files

```
docker/observability/
├── otel-collector.yaml          # OTel Collector pipeline config
├── prometheus.yaml              # Prometheus scrape targets
├── tempo.yaml                   # Tempo storage and ingestion config
├── dashboards/
│   ├── provider.yaml            # Grafana dashboard provisioning
│   └── litellm-metrics.json     # Pre-built LiteLLM metrics dashboard
└── datasources/
    └── datasources.yaml         # Grafana datasource provisioning (Tempo, Loki, Prometheus)
```

## How It Works

### OTel Collector Pipeline

The collector receives OTLP data from all services and applies custom processing for Temporal spans:

1. **Groups spans** by `temporal.context` attribute
2. **Remaps `service.name`** to the Temporal context value for visual separation of workflows vs. activities in Grafana
3. **Adds Temporal UI links** to each span for direct navigation to workflow executions
4. **Prefixes span names** with the originating service name (e.g. `[inhaltsextraktion] StartWorkflow`)

Traces are exported to Tempo, logs to Loki via OTLP.

### Grafana

Grafana starts with anonymous admin access enabled (local dev only) and auto-provisions:

- **Datasources**: Tempo (default, with trace-to-log correlation), Loki, Prometheus
- **Dashboards**: LiteLLM proxy metrics

### Prometheus

Scrapes the LiteLLM proxy at `litellm-proxy:4000/metrics` every 10 seconds.

## Accessing the UIs

| UI | URL |
|----|-----|
| Grafana | http://localhost:3000 |
| Tempo API | http://localhost:3200 |
| Prometheus | http://localhost:9090 |
| Loki API | http://localhost:3100 |

## Customization

- **Add scrape targets**: Edit `prometheus.yaml`
- **Add dashboards**: Place JSON files in `dashboards/`
- **Add datasources**: Edit `datasources/datasources.yaml`
- **Modify trace processing**: Edit `otel-collector.yaml` pipeline processors
