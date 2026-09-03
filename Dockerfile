FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FASTDPS_PORT=5024 \
    FASTDPS_DATA_DIR=/data \
    FASTDPS_DB=/data/fastdps.sqlite

WORKDIR /app
RUN apt-get update \
    && apt-get install --no-install-recommends -y curl \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml README.md LICENSE THIRD_PARTY_NOTICES.md ./
COPY fastdps ./fastdps
COPY migrations ./migrations
COPY static ./static
COPY web_app.py seed.py VERSION ./
RUN python -m pip install --no-cache-dir .

RUN useradd --create-home --uid 10001 fastdps && mkdir -p /data && chown -R fastdps:fastdps /data /app
USER fastdps
EXPOSE 5024
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5024/healthz', timeout=3)"
CMD ["python", "web_app.py"]
