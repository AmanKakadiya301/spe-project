# ─────────────────────────────────────────────────────────────────────────────
# AutoDevOps FinTech Stock App — Multi-Stage Dockerfile
#   Stage 1 (builder) : python:3.11-slim → installs all dependencies
#   Stage 2 (runtime) : python:3.11-slim → copies only what is needed
#
# Result: lean, secure production image (~150 MB vs ~900 MB naïve build)
# Non-root user: uid/gid 1001 (appuser)
# WSGI server: gunicorn with 4 workers
# ─────────────────────────────────────────────────────────────────────────────

# ── STAGE 1: Builder ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# Install compilers needed by some Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy only the requirements file first — maximises layer caching
COPY app/requirements.txt .

# Install to a directory that will be copied to the runtime stage
RUN pip install --upgrade pip \
 && pip install --no-cache-dir --target=/install -r requirements.txt


# ── STAGE 2: Runtime ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# Create non-root user/group
RUN groupadd --gid 1001 appuser \
 && useradd  --uid 1001 --gid 1001 \
             -s /bin/false --no-create-home appuser

# Upgrade known vulnerable base OS python packages
RUN pip install --no-cache-dir --upgrade setuptools wheel jaraco.context

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local/lib/python3.11/site-packages

# Copy application source
COPY app/ .

# Fix ownership
RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 5000

# Docker-daemon health check (Kubernetes also has its own probes)
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD python -c \
        "import urllib.request; urllib.request.urlopen('http://localhost:5000/health')"

# Runtime defaults (override via --env-file or K8s Secret/ConfigMap)
ENV FLASK_ENV=production \
    PORT=5000 \
    APP_VERSION=1.0.0 \
    PATH="/usr/local/lib/python3.11/site-packages/bin:/usr/local/bin:$PATH"

# Gunicorn: 4 workers, all interfaces, structured logging to stdout
CMD ["gunicorn", \
     "--workers",      "4", \
     "--bind",         "0.0.0.0:5000", \
     "--access-logfile", "-", \
     "--error-logfile",  "-", \
     "--log-level",    "info", \
     "--timeout",      "120", \
     "main:app"]
