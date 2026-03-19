"""
tracing/otel.py
CREATE at app/tracing/otel.py
OpenTelemetry → Jaeger distributed tracing.
Add to main.py:
    from tracing.otel import init_tracing
    init_tracing(app)
"""
import os
import logging

logger = logging.getLogger(__name__)


def init_tracing(app):
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.instrumentation.flask import FlaskInstrumentor
        from opentelemetry.instrumentation.requests import RequestsInstrumentor
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://jaeger:4317")
        resource = Resource.create({
            "service.name":    "fintech-stock-app",
            "service.version": os.getenv("APP_VERSION", "2.0.0"),
            "deployment.env":  os.getenv("FLASK_ENV", "production"),
        })
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True))
        )
        trace.set_tracer_provider(provider)
        FlaskInstrumentor().instrument_app(app)
        RequestsInstrumentor().instrument()
        SQLAlchemyInstrumentor().instrument()
        logger.info(f"OpenTelemetry tracing → {endpoint}")
    except ImportError as exc:
        logger.warning(f"OTel not installed — tracing disabled: {exc}")
    except Exception as exc:
        logger.warning(f"Tracing init failed (non-fatal): {exc}")
