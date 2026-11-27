"""Subprocess driver for the rev16/rev17 GUI Codex-create evidence (229-a).

Runs in a FRESH process so the one-shot Codex profile bootstrap can bind a
validated non-default DATA revision (in-process rebinds fail closed by
design). Seeds a ready QWEN38 route, creates the app bound to the given
profile file, drives the authenticated GUI create with
``client_use_codex=true`` and prints one JSON line with the safe outcome.
No provider traffic, no email delivery.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from pathlib import Path

REPO_ROOT = str(Path(__file__).resolve().parents[2])

def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(json.dumps({"error": "usage: db_url profile_path"}))
        return 2
    database_url, profile_path = argv
    sys.path.insert(0, REPO_ROOT)

    from fastapi.testclient import TestClient
    from sqlalchemy import func, select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from slaif_gateway.config import Settings
    from slaif_gateway.db.models import GatewayKey, ModelRoute, PricingRule, ProviderConfig
    from slaif_gateway.db.repositories.admin_users import AdminUsersRepository
    from slaif_gateway.db.repositories.cohorts import CohortsRepository
    from slaif_gateway.db.repositories.institutions import InstitutionsRepository
    from slaif_gateway.db.repositories.owners import OwnersRepository
    from slaif_gateway.main import create_app
    from slaif_gateway.services.codex_profile_registry import (
        QWEN38_CODEX_PROFILE_ID,
        build_codex_profile_declaration,
        get_codex_profile,
    )
    from slaif_gateway.utils.passwords import hash_admin_password
    from slaif_gateway.utils.secrets import generate_secret_key

    suffix = uuid.uuid4().hex[:8]
    profile = get_codex_profile(QWEN38_CODEX_PROFILE_ID)
    assert profile is not None

    async def seed() -> dict[str, object]:
        engine = create_async_engine(database_url, future=True)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        now = datetime.now(UTC)
        try:
            async with session_factory() as session:
                async with session.begin():
                    admin = await AdminUsersRepository(session).create_admin_user(
                        email=f"admin-{uuid.uuid4()}@example.org",
                        display_name="Rev16 GUI Admin",
                        password_hash=hash_admin_password("pw-rev16-229"),
                        role="admin",
                        is_active=True,
                    )
                    institution = await InstitutionsRepository(session).create_institution(
                        name=f"Inst {uuid.uuid4()}", country="SI"
                    )
                    cohort = await CohortsRepository(session).create_cohort(
                        name=f"Cohort {uuid.uuid4()}",
                        starts_at=now - timedelta(days=1),
                        ends_at=now + timedelta(days=30),
                    )
                    owner = await OwnersRepository(session).create_owner(
                        name="Ada",
                        surname="L",
                        email=f"owner-{uuid.uuid4()}@example.org",
                        institution_id=institution.id,
                    )
                    provider = ProviderConfig(
                        provider=f"syn229rev-{suffix}",
                        display_name="Syn 229 Rev Provider",
                        kind="openai_compatible",
                        base_url="https://syn229rev.example/v1",
                        api_key_env_var="GUI229_REV_KEY",
                        enabled=True,
                    )
                    session.add(provider)
                    await session.flush()
                    session.add(
                        ModelRoute(
                            requested_model=profile.public_model,
                            provider=provider.provider,
                            upstream_model=profile.upstream_model,
                            match_type="exact",
                            endpoint="/v1/responses",
                            priority=1,
                            enabled=True,
                            visible_in_models=True,
                            supports_streaming=True,
                            capabilities={
                                "responses": {
                                    "text": True,
                                    "stateless": True,
                                    "streaming": True,
                                    "codex_request_envelope": True,
                                    "codex_client_tools": True,
                                    "codex_streaming_tool_events": True,
                                    "codex_encrypted_reasoning_replay": True,
                                },
                                "codex_limits": {
                                    "context_window_tokens": profile.context_window_tokens,
                                    "default_max_output_tokens": profile.default_max_output_tokens,
                                    "max_output_tokens": profile.max_output_tokens,
                                },
                                "codex_profile": build_codex_profile_declaration(
                                    QWEN38_CODEX_PROFILE_ID
                                ),
                            },
                        )
                    )
                    session.add(
                        PricingRule(
                            provider=provider.provider,
                            upstream_model=profile.upstream_model,
                            endpoint="/v1/responses",
                            input_price_per_1m=Decimal("1.000000000"),
                            cached_input_price_per_1m=Decimal("0.250000000"),
                            output_price_per_1m=Decimal("1.000000000"),
                            reasoning_price_per_1m=Decimal("2.000000000"),
                            request_price=Decimal("0.000000000"),
                            currency="EUR",
                            valid_from=now - timedelta(days=1),
                            enabled=True,
                            pricing_metadata={
                                "codex_accounting": {
                                    "long_context_threshold_tokens": 98304,
                                    "long_context_input_multiplier": "2",
                                    "long_context_output_multiplier": "2",
                                    "cache_write_input_multiplier": "1",
                                }
                            },
                        )
                    )
                    return {
                        "admin_email": admin.email,
                        "owner_id": owner.id,
                        "cohort_id": cohort.id,
                        "provider": provider.provider,
                    }
        finally:
            await engine.dispose()

    data = asyncio.run(seed())

    async def inspect_key() -> tuple[int, dict[str, object] | None]:
        engine = create_async_engine(database_url, future=True)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with session_factory() as session:
                count = int(
                    (
                        await session.execute(
                            select(func.count())
                            .select_from(GatewayKey)
                            .where(GatewayKey.owner_id == data["owner_id"])
                        )
                    ).scalar_one()
                )
                rows = (
                    (
                        await session.execute(
                            select(GatewayKey).where(
                                GatewayKey.owner_id == data["owner_id"]
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                policy = rows[-1].metadata_json.get("responses_policy") if rows else None
                return count, policy
        finally:
            await engine.dispose()

    settings = Settings(
        APP_ENV="test",
        DATABASE_URL=database_url,
        ADMIN_SESSION_SECRET="s" * 40,
        TOKEN_HMAC_SECRET="hmac-rev16-gui-229",
        ONE_TIME_SECRET_ENCRYPTION_KEY=generate_secret_key(),
        OPENAI_UPSTREAM_API_KEY="sk-provider-secret-placeholder",
        OPENROUTER_API_KEY="sk-or-provider-secret-placeholder",
        CODEX_COMPATIBILITY_PROFILE_FILE=profile_path,
    )
    app = create_app(settings)
    outcome: dict[str, object] = {"status": None, "key_count": 0, "responses_policy": None}
    try:
        with TestClient(app) as client:
            login_page = client.get("/admin/login")
            csrf_match = re.search(r'name="csrf_token" value="([^"]+)"', login_page.text)
            assert csrf_match is not None
            client.post(
                "/admin/login",
                data={
                    "email": data["admin_email"],
                    "password": "pw-rev16-229",
                    "csrf_token": csrf_match.group(1),
                },
                follow_redirects=False,
            )
            create_page = client.get("/admin/keys/create")
            assert create_page.status_code == 200
            csrf = re.search(r'name="csrf_token" value="([^"]+)"', create_page.text)
            assert csrf is not None
            response = client.post(
                "/admin/keys/create",
                data={
                    "csrf_token": csrf.group(1),
                    "owner_id": str(data["owner_id"]),
                    "cohort_id": str(data["cohort_id"]),
                    "valid_days": "30",
                    "reason": "rev-gui codex create",
                    "rate_limit_requests_per_minute": "60",
                    "rate_limit_tokens_per_minute": "12000",
                    "rate_limit_concurrent_requests": "4",
                    "rate_limit_window_seconds": "30",
                    "client_use_codex": "true",
                    "allowed_providers": str(data["provider"]),
                    "allowed_models": profile.public_model,
                    "allowed_endpoints": "/v1/models\n/v1/responses",
                },
            )
            outcome["status"] = response.status_code
            count, policy = asyncio.run(inspect_key())
            outcome["key_count"] = count
            outcome["responses_policy"] = policy
            if response.status_code != 200:
                flash = re.search(
                    r'admin-flash-error[^>]*>(.*?)</div>', response.text, re.S
                )
                if flash:
                    outcome["error_flash"] = re.sub(
                        r"<[^>]+>", " ", flash.group(1)
                    ).strip()[:400]
    finally:
        pass
    print(json.dumps(outcome))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
