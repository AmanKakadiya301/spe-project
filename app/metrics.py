"""
metrics.py
CREATE at app/metrics.py
Prometheus /metrics endpoint for Flask.
Add to main.py: from metrics import init_metrics; init_metrics(app)
"""
import time
import logging
from flask import request, Response

logger = logging.getLogger(__name__)


def init_metrics(app):
    try:
        from prometheus_client import (
            Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST,
        )

        REQUEST_COUNT = Counter(
            "flask_http_request_total", "Total HTTP requests",
            ["method", "path", "status"],
        )
        REQUEST_LATENCY = Histogram(
            "flask_http_request_duration_seconds", "Request latency",
            ["method", "path"],
            buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
        )

        @app.before_request
        def _before():
            request._prom_start = time.time()

        @app.after_request
        def _after(response):
            path = request.path
            # Collapse dynamic segments like /api/stock/AAPL → /api/stock/<sym>
            for seg in path.split("/"):
                if seg.isupper() and 1 < len(seg) <= 5:
                    path = path.replace(seg, "<sym>")
            latency = time.time() - getattr(request, "_prom_start", time.time())
            REQUEST_COUNT.labels(method=request.method, path=path, status=str(response.status_code)).inc()
            REQUEST_LATENCY.labels(method=request.method, path=path).observe(latency)
            return response

        @app.route("/metrics")
        def prometheus_metrics():
            return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)

        logger.info("Prometheus metrics enabled at /metrics")

    except ImportError:
        logger.warning("prometheus_client not installed — metrics disabled")

        @app.route("/metrics")
        def _no_metrics():
            return Response("# prometheus_client not installed\n", mimetype="text/plain")
