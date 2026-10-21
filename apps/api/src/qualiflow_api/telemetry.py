from opentelemetry import metrics
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource


def configure_telemetry(service_name: str, otlp_endpoint: str) -> None:
    """Metrics only — no TracerProvider configured. Traces would just be
    received and dropped by the collector right now (its pipeline only
    exports to Prometheus, which understands metrics, not spans), so
    there's no point sending them until there's a real destination."""
    resource = Resource.create({"service.name": service_name})
    exporter = OTLPMetricExporter(endpoint=f"{otlp_endpoint}/v1/metrics")
    reader = PeriodicExportingMetricReader(exporter, export_interval_millis=5000)
    provider = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(provider)
