# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --upgrade pip wheel \
    && pip wheel --no-deps -w /wheels .

FROM python:3.12-slim AS runtime

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

RUN apt-get update \
    && apt-get install -y --no-install-recommends tini libpq5 ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && python -m venv /opt/venv \
    && groupadd -r cti && useradd -r -g cti -d /home/cti -m cti

COPY pyproject.toml README.md /app/
COPY src /app/src
COPY migrations /app/migrations
COPY alembic.ini /app/
COPY config /app/config
COPY --from=builder /wheels /wheels

RUN /opt/venv/bin/pip install --upgrade pip wheel \
    && /opt/venv/bin/pip install /wheels/*.whl \
    && /opt/venv/bin/pip install \
        "alembic>=1.13" \
        "psycopg2-binary>=2.9" \
        "uvicorn>=0.30" \
    && rm -rf /wheels

WORKDIR /app
RUN mkdir -p /var/lib/cti/raw && chown -R cti:cti /var/lib/cti /app
USER cti

ENTRYPOINT ["tini", "--"]
CMD ["cti", "--help"]
