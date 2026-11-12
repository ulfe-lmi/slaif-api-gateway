FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/app \
    HOME=/tmp

WORKDIR /app

RUN addgroup --system slaif && adduser --system --ingroup slaif slaif

COPY pyproject.toml README.md LICENSE alembic.ini ./
COPY app ./app
COPY migrations ./migrations
COPY deploy/production/load-secrets.sh /usr/local/bin/load-production-secrets

RUN python -m pip install --upgrade pip \
    && python -m pip install . \
    && chmod 0755 /usr/local/bin/load-production-secrets \
    && chown -R slaif:slaif /app

USER slaif

EXPOSE 8000

ENTRYPOINT ["/usr/local/bin/load-production-secrets"]

CMD ["gunicorn", "slaif_gateway.main:app", "--worker-class", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "120"]

# ---------------------------------------------------------------------------
# OPTIONAL worker-only target (objective 221): the default runtime target
# above must NOT gain PostgreSQL client tooling. This separate target adds
# the pinned PostgreSQL 16 clients (pg_dump/pg_restore/psql) needed by the
# bounded private demo snapshot worker. Build with:
#   docker build --target demo-snapshot-worker .
# Version proof: docker run --rm <image> pg_dump --version
# The inherited production secret-loading ENTRYPOINT is deliberately NOT
# used here: the demo worker receives credentials only through its
# operator-configured PGPASSFILE, so the entrypoint is cleared for this
# target and the worker command is a plain CMD.
# ---------------------------------------------------------------------------
FROM runtime AS demo-snapshot-worker

# The runtime target runs as the unprivileged slaif user; apt needs root,
# so switch back to root for the package install and revert afterwards.
USER root

# The pgdg repository must match the base distribution codename (the
# python:3.12-slim base is Debian 13/trixie, not bookworm); read it from
# /etc/os-release so the target stays correct if the base moves.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates wget gnupg \
    && install -d /usr/share/postgresql-common/pgdg \
    && wget -qO - https://www.postgresql.org/media/keys/ACCC4CF8.asc \
        | gpg --dearmor -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
    && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt $(. /etc/os-release && echo "${VERSION_CODENAME}-pgdg") main" \
        > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client-16=16.* \
    && apt-get remove -y --purge wget gnupg \
    && rm -rf /var/lib/apt/lists/*

# Revert to the unprivileged runtime user for the worker process itself.
USER slaif

# Clear the inherited production secret-loading entrypoint for this target.
ENTRYPOINT []

CMD ["slaif-gateway", "demo-snapshot-worker", "run"]
