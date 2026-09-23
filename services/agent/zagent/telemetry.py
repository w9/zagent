import os

from opentelemetry import trace
from opentelemetry.propagate import inject

_configured = False


def configure_telemetry(service: str, app=None) -> None:
    global _configured
    if not os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        return
    if not _configured:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider = TracerProvider(
            resource=Resource.create({"service.name": os.environ.get("OTEL_SERVICE_NAME", service)})
        )
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        trace.set_tracer_provider(provider)
        HTTPXClientInstrumentor().instrument()
        AsyncPGInstrumentor().instrument()
        _configured = True
    if app is not None:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app, excluded_urls="health,session-list/events")


def carrier() -> dict[str, str]:
    context: dict[str, str] = {}
    inject(context)
    return context
