#!/usr/bin/env python3
"""Fail-closed static and optional Compose validation for the production appliance."""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise RuntimeError(f"{label}: missing required contract")


def service_block(compose: str, service: str) -> str:
    lines = compose.splitlines()
    marker = f"  {service}:"
    try:
        start = lines.index(marker)
    except ValueError:
        raise RuntimeError(f"service {service} missing")
    end = len(lines)
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if line.startswith("  ") and not line.startswith("    "):
            end = index
            break
    return "\n".join(lines[start:end])


def validate_static() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.production.yml").read_text(encoding="utf-8")
    nginx = (ROOT / "nginx/production.conf").read_text(encoding="utf-8")
    loader = (ROOT / "deploy/production/load-secrets.sh").read_text(encoding="utf-8")

    require(dockerfile, "AS runtime", "Dockerfile runtime stage")
    require(dockerfile, "COPY app ./app", "Dockerfile application")
    require(dockerfile, "COPY migrations ./migrations", "Dockerfile migrations")
    require(dockerfile, "load-production-secrets", "Dockerfile secret entrypoint")
    require(dockerfile, 'ENTRYPOINT ["/usr/local/bin/load-production-secrets"]', "Dockerfile entrypoint")

    for needle, label in (
        ("POSTGRES_USER: slaif", "PostgreSQL user"),
        ("POSTGRES_DB: slaif_gateway", "PostgreSQL database"),
        ("postgres_data:/var/lib/postgresql/data", "PostgreSQL persistence"),
        ("SLAIF_DATABASE_URL_FILE", "database secret override"),
        ("REDIS_URL_FILE", "authenticated Redis URL secret"),
        ("redis_password", "Redis password secret"),
        ("--requirepass", "Redis authentication"),
        ("SLAIF_TLS_DIR", "TLS directory override"),
        ('ENABLE_REDIS_RATE_LIMITS: "true"', "Redis rate-limit enablement"),
        ('RATE_LIMIT_FAIL_CLOSED: "true"', "Redis fail-closed policy"),
        ("slaif_gateway.workers.celery_app:celery_app", "Celery application object"),
        ("egress", "provider egress network"),
    ):
        require(compose, needle, label)

    postgres = service_block(compose, "postgres")
    redis = service_block(compose, "redis")
    if "ports:" in postgres or "ports:" in redis:
        raise RuntimeError("PostgreSQL and Redis must not publish host ports")
    api = service_block(compose, "api")
    if "networks: [internal, egress]" not in api:
        raise RuntimeError("API must be attached to private and egress networks")
    for service in ("migrations", "api", "worker", "scheduler"):
        if "user: root" not in service_block(compose, service):
            raise RuntimeError(f"{service} must start the secret loader as root")

    for needle, label in (
        ("proxy_buffering off;", "Nginx streaming buffering"),
        ("proxy_cache off;", "Nginx streaming cache"),
        ("proxy_read_timeout 3600s;", "Nginx streaming read timeout"),
        ("proxy_send_timeout 3600s;", "Nginx streaming send timeout"),
        ("proxy_set_header X-Forwarded-Proto", "Nginx forwarded scheme"),
    ):
        require(nginx, needle, label)

    for needle, label in (
        ("DATABASE_URL_FILE", "database allowlist"),
        ("TOKEN_HMAC_SECRET_V1_FILE", "HMAC allowlist"),
        ("ADMIN_SESSION_SECRET_FILE", "admin-session allowlist"),
        ("ONE_TIME_SECRET_ENCRYPTION_KEY_FILE", "one-time-secret allowlist"),
        ("OPENAI_UPSTREAM_API_KEY_FILE", "OpenAI allowlist"),
        ("OPENROUTER_API_KEY_FILE", "OpenRouter allowlist"),
        ("exec \"$@\"", "secret-loader exec"),
    ):
        require(loader, needle, label)


def validate_compose() -> None:
    env = os.environ.copy()
    result = subprocess.run(
        ["docker", "compose", "-f", "docker-compose.production.yml", "config", "--quiet"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("docker compose config failed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compose", action="store_true", help="also run docker compose config")
    args = parser.parse_args()
    try:
        validate_static()
        if args.compose:
            validate_compose()
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"RESULT=FAIL reason={exc}")
        return 1
    print(f"RESULT=OK static=true compose={str(bool(args.compose)).lower()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
