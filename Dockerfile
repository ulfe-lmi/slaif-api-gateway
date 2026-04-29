FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN addgroup --system slaif && adduser --system --ingroup slaif slaif

COPY pyproject.toml README.md LICENSE alembic.ini ./
COPY app ./app
COPY migrations ./migrations

RUN python -m pip install --upgrade pip \
    && python -m pip install . \
    && chown -R slaif:slaif /app

USER slaif

EXPOSE 8000

CMD ["gunicorn", "slaif_gateway.main:app", "--worker-class", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "120"]
