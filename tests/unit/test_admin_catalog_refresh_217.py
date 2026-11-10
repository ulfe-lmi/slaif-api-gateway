"""217-a: focused unit qualification of the admin GUI catalog-refresh bridge.

All synthetic, no network/DB/broker (root-qualified boundaries):

1. custody setup states (disabled/incomplete/unsafe/ready) and the
   feature-local optional research rule (incomplete config constructable);
2. the closed review token: build/verify round-trip + negatives
   (actor/session/expiry/tamper/run-id grammar);
3. upload bounds (exact Core caps, closed name shape, traversal, O_EXCL);
4. admission (active/retained/bytes/records + reservations + concurrency);
5. job lifecycle (terminal cancel recovery of a still-queued job, claim,
   late/duplicate refusal, cooperative running cancel, truthful re-reads);
6. canaries (secret absence in projections, task results, and logs);
7. the worker's DEFAULT composition: real ``run_collect`` (only the
   MockTransport bytes and a synthetic public resolver are synthetic)
   publishing a sealed run through ``_execute_job``;
8. the default proposal bridge (``_BoundedAsyncVettedTransport``) over a
   sync ``MockTransport``: destination families, identity encoding,
   per-body + aggregate budget incl. the equality edge and repeat refusal;
9. the GUI apply-flow helpers: sealed facts (canonical vs first-install),
   the two-step intent document builder, stale-binding predicate;
10. import boundary (router import never eagerly pulls the worker module).

Labeled seams: (7) replaces ``_collect_client_factory`` with a synthetic
official-source client and re-points the default resolver bindings to a
synthetic public answer - the REAL Core collection defaults, fetch bounds,
acquisition context, and sealing run unchanged; (8) drives the REAL bridge
class with a synthetic sync transport. Neither is an eager/mocked-broker
proof of worker assembly (that is the owned-Redis queued smoke in the
integration qualification).
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import socket
import stat
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace as _NS

import httpx
import pytest

from tests.unit.test_catalog_refresh_collection import World
from slaif_gateway.api import admin_catalog_refresh as router_mod
from slaif_gateway.api.admin_review_intent import (
    AdminReviewIntentError,
    build_catalog_refresh_review_token,
    verify_catalog_refresh_review_token,
)
from slaif_gateway.config import Settings
from slaif_gateway.services import admin_catalog_refresh as custody
from slaif_gateway.services.admin_catalog_refresh import (
    CustodyCapacityError,
    CustodyJobError,
)
from slaif_gateway.services.catalog_refresh import collection as coll
from slaif_gateway.services.catalog_refresh import sources as src
from slaif_gateway.services.catalog_refresh.bundle import MAX_BUNDLE_BYTES
from slaif_gateway.services.catalog_refresh.baseline import MAX_BASELINE_BYTES
from slaif_gateway.workers import tasks_catalog_refresh as worker

HEX64_A = "a" * 64
HEX64_B = "b" * 64
CANARY = "SLAIF217-SECRET-CANARY-9f31"


# --- fixtures ---------------------------------------------------------------


def _settings(custody: _NS, **overrides) -> Settings:
    values = {
        "APP_ENV": "test",
        "DATABASE_URL": None,
        "ADMIN_SESSION_SECRET": "s" * 40,
        "CATALOG_REFRESH_GUI_ENABLED": True,
        "CATALOG_REFRESH_ROOT": str(custody.root),
        "CATALOG_REFRESH_SEAL_KEY": str(custody.key),
    }
    values.update(overrides)
    return Settings(**values)


@pytest.fixture
def custody_root(tmp_path: Path) -> _NS:
    """Operator-owned 0700 custody root + EXISTING 0600 seal key (64 hex)."""
    root = tmp_path / "custody"
    root.mkdir(mode=0o700)
    key = tmp_path / "seal.hex"
    key.write_bytes(b"ab" * 32)
    os.chmod(key, stat.S_IRUSR | stat.S_IWUSR)  # 0600
    return _NS(root=root, key=key)


def _read_record(settings: Settings, job_id: str) -> dict:
    for row in custody.list_jobs(settings, limit=100):
        if row["job_id"] == job_id:
            return row
    raise AssertionError("job record missing from projection")


# --- 1. setup states ---------------------------------------------------------


def test_setup_disabled_never_creates(custody_root) -> None:
    settings = _settings(custody_root, CATALOG_REFRESH_GUI_ENABLED=False)
    result = custody.inspect_custody_setup(settings)
    assert result.state == "disabled"
    assert result.code == "catalog_refresh_gui_disabled"
    assert result.root is None and result.seal_key is None
    # ZERO mutation: the existing root stays empty, nothing is created.
    assert list(custody_root.root.iterdir()) == []


def test_setup_incomplete_configuration(custody_root) -> None:
    for override in (
        {"CATALOG_REFRESH_ROOT": None},
        {"CATALOG_REFRESH_SEAL_KEY": None},
        {"CATALOG_REFRESH_ROOT": None, "CATALOG_REFRESH_SEAL_KEY": None},
    ):
        settings = _settings(custody_root, **override)
        result = custody.inspect_custody_setup(settings)
        assert result.state == "unavailable"
        assert result.code == "catalog_refresh_setup_incomplete"
        assert result.help_lines
    assert list(custody_root.root.iterdir()) == []


def test_setup_root_missing(custody_root) -> None:
    settings = _settings(custody_root, CATALOG_REFRESH_ROOT=str(custody_root.root / "nope"))
    result = custody.inspect_custody_setup(settings)
    assert (result.state, result.code) == ("unavailable", "catalog_refresh_root_missing")


def test_setup_location_gate_refuses_repo_and_pgdata(custody_root) -> None:
    """Ordered location gate: custody root/key paths inside the gateway
    repository/source tree or a recognizable PGDATA (PG_VERSION
    ancestor) are refused BEFORE any layout creation; relative
    (ambiguous) paths are refused instead of CWD-resolved. Feature-local
    unavailable - no global startup failure, no repair, no create."""
    import slaif_gateway

    package_root = Path(slaif_gateway.__file__).resolve().parent
    # root inside the gateway source tree: refused, nothing created
    result = custody.inspect_custody_setup(
        _settings(custody_root, CATALOG_REFRESH_ROOT=str(package_root))
    )
    assert (result.state, result.code) == ("unavailable", "catalog_refresh_location_unsafe")
    assert result.root is None and result.seal_key is None
    # key inside the gateway source tree: refused
    result = custody.inspect_custody_setup(
        _settings(custody_root, CATALOG_REFRESH_SEAL_KEY=str(package_root / "x-seal.hex"))
    )
    assert (result.state, result.code) == ("unavailable", "catalog_refresh_location_unsafe")
    # inside a recognizable PostgreSQL data directory (PG_VERSION ancestor)
    pgdata = custody_root.root / "pgdata"
    pgdata.mkdir(mode=0o700)
    (pgdata / "PG_VERSION").write_bytes(b"16\n")
    result = custody.inspect_custody_setup(
        _settings(custody_root, CATALOG_REFRESH_ROOT=str(pgdata / "custody"))
    )
    assert (result.state, result.code) == ("unavailable", "catalog_refresh_location_unsafe")
    result = custody.inspect_custody_setup(
        _settings(custody_root, CATALOG_REFRESH_SEAL_KEY=str(pgdata / "seal2.hex"))
    )
    assert (result.state, result.code) == ("unavailable", "catalog_refresh_location_unsafe")
    # relative (ambiguous) configured paths: refused, not CWD-resolved
    for override in (
        {"CATALOG_REFRESH_ROOT": "relative/custody"},
        {"CATALOG_REFRESH_SEAL_KEY": "relative/seal.hex"},
    ):
        result = custody.inspect_custody_setup(_settings(custody_root, **override))
        assert (result.state, result.code) == ("unavailable", "catalog_refresh_location_unsafe")
    # NO layout mutation: the pre-existing root gained nothing and the
    # pgdata tree gained nothing beyond the marker itself.
    assert [p.name for p in custody_root.root.iterdir()] == ["pgdata"]
    assert [p.name for p in pgdata.iterdir()] == ["PG_VERSION"]


def test_setup_location_gate_installed_no_git(
    custody_root, monkeypatch, tmp_path: Path
) -> None:
    """INSTALLED package (site-packages, no ``.git`` ancestor): the
    location gate protects ONLY the actual package tree - never the
    filesystem root or every install ancestor - so a real external
    absolute custody path passes the location gate (and then fails on
    existence, not location). A real checkout case is covered by the
    repo/PGDATA test above."""
    import slaif_gateway

    fake_site = tmp_path / "site-packages"
    fake_pkg = fake_site / "slaif_gateway"
    fake_pkg.mkdir(parents=True)
    fake_init = fake_pkg / "__init__.py"
    fake_init.write_bytes(b"")
    monkeypatch.setattr(slaif_gateway, "__file__", str(fake_init))

    # the actual (fake) package tree itself is still refused
    result = custody.inspect_custody_setup(
        _settings(custody_root, CATALOG_REFRESH_ROOT=str(fake_pkg))
    )
    assert (result.state, result.code) == ("unavailable", "catalog_refresh_location_unsafe")

    # an EXTERNAL absolute custody path is NOT classified as source: the
    # location gate passes and it fails on existence instead (never
    # "location_unsafe" - the old defect refused ALL external absolute
    # custody because the filesystem root was a "known root").
    external = tmp_path / "var-lib-slaif" / "catalog-refresh"
    result = custody.inspect_custody_setup(
        _settings(custody_root, CATALOG_REFRESH_ROOT=str(external))
    )
    assert (result.state, result.code) == ("unavailable", "catalog_refresh_root_missing")


def test_setup_key_missing(custody_root) -> None:
    settings = _settings(custody_root, CATALOG_REFRESH_SEAL_KEY=str(custody_root.root.parent / "missing.hex"))
    result = custody.inspect_custody_setup(settings)
    assert (result.state, result.code) == ("unavailable", "catalog_refresh_custody_unsafe")
    assert any("seal key" in line for line in result.help_lines)


def test_setup_key_unsafe_mode(custody_root) -> None:
    os.chmod(custody_root.key, 0o644)
    settings = _settings(custody_root)
    result = custody.inspect_custody_setup(settings)
    assert (result.state, result.code) == ("unavailable", "catalog_refresh_custody_unsafe")
    # never repaired
    assert (custody_root.key.stat().st_mode & 0o777) == 0o644


def test_setup_root_group_writable_refused(custody_root) -> None:
    os.chmod(custody_root.root, 0o775)
    settings = _settings(custody_root)
    result = custody.inspect_custody_setup(settings)
    assert (result.state, result.code) == ("unavailable", "catalog_refresh_custody_unsafe")
    os.chmod(custody_root.root, 0o700)


def test_setup_ready_creates_only_private_subdirs(custody_root) -> None:
    settings = _settings(custody_root)
    result = custody.inspect_custody_setup(settings)
    assert result.state == "ready"
    assert result.code == "catalog_refresh_ready"
    assert result.root == custody_root.root and result.seal_key == custody_root.key
    names = {p.name for p in custody_root.root.iterdir()}
    assert names == {"runs", "jobs", "uploads", "proposals", "locks"}
    for name in names:
        mode = (custody_root.root / name).stat().st_mode & 0o777
        assert mode == 0o700


def test_research_partial_config_constructable(custody_root) -> None:
    """Incomplete optional research config NEVER raises globally and is
    unavailable at use (no unsandboxed fallback)."""
    for partial in (
        {"CATALOG_REFRESH_RESEARCH_MODEL": "synthetic-model"},
        {"CATALOG_REFRESH_RESEARCH_CLI_BIN": "/usr/bin/true",
         "CATALOG_REFRESH_RESEARCH_ENDPOINT": "https://example.test/v1",
         "CATALOG_REFRESH_RESEARCH_MODEL": "m"},
    ):
        settings = _settings(custody_root, **partial)  # must construct
        assert worker._research_config_from_settings(settings) is None
    # complete-but-unsafe variants
    settings = _settings(
        custody_root,
        CATALOG_REFRESH_RESEARCH_CLI_BIN="/usr/bin/true",
        CATALOG_REFRESH_RESEARCH_ENDPOINT="http://insecure.test/v1",  # not HTTPS
        CATALOG_REFRESH_RESEARCH_MODEL="m",
        CATALOG_REFRESH_RESEARCH_AUTH_ENV="SLAIF217_TEST_AUTH",
    )
    assert worker._research_config_from_settings(settings) is None
    os.environ["SLAIF217_TEST_AUTH"] = "secret-value"
    try:
        assert worker._research_config_from_settings(settings) is None
    finally:
        del os.environ["SLAIF217_TEST_AUTH"]


# --- 2. closed review token --------------------------------------------------

_SECRET = "t" * 48
_ACTOR = uuid.uuid4()
_SESSION = uuid.uuid4()


def _document(**overrides) -> dict:
    doc = {
        "run_id": "collect-20261110-000000-deadbeef01",
        "bundle_sha256": HEX64_A,
        "plan_sha256": HEX64_B,
        "target_database": "slaif_cat",
        "target_host": "db.internal",
        "target_port": 5433,
        "postgres_version": "16.4",
        "baseline_content_sha256": "d" * 64,
        "row_counts": {"providers": 2, "routes": 3},
        "ack_warning_codes": [],
        "reason": "monthly refresh",
        "nonce": uuid.uuid4().hex,
    }
    doc.update(overrides)
    return doc


def test_review_token_roundtrip() -> None:
    document = _document()
    token = build_catalog_refresh_review_token(
        admin_session_secret=_SECRET,
        admin_user_id=_ACTOR,
        admin_session_id=_SESSION,
        review_document=document,
        ttl_seconds=900,
    )
    parsed = verify_catalog_refresh_review_token(
        admin_session_secret=_SECRET,
        token=token,
        admin_user_id=_ACTOR,
        admin_session_id=_SESSION,
    )
    assert parsed == document


def test_review_token_wrong_actor_and_session() -> None:
    token = build_catalog_refresh_review_token(
        admin_session_secret=_SECRET,
        admin_user_id=_ACTOR,
        admin_session_id=_SESSION,
        review_document=_document(),
        ttl_seconds=900,
    )
    for kwargs in (
        {"admin_user_id": uuid.uuid4(), "admin_session_id": _SESSION},
        {"admin_user_id": _ACTOR, "admin_session_id": uuid.uuid4()},
    ):
        with pytest.raises(AdminReviewIntentError) as exc:
            verify_catalog_refresh_review_token(
                admin_session_secret=_SECRET, token=token, **kwargs
            )
        assert "not valid for this signed-in admin" in exc.value.message


def test_review_token_expiry() -> None:
    now = datetime(2026, 11, 10, 12, 0, 0, tzinfo=UTC)
    token = build_catalog_refresh_review_token(
        admin_session_secret=_SECRET,
        admin_user_id=_ACTOR,
        admin_session_id=_SESSION,
        review_document=_document(),
        ttl_seconds=900,
        now=now,
    )
    # one second before expiry: still valid
    verify_catalog_refresh_review_token(
        admin_session_secret=_SECRET,
        token=token,
        admin_user_id=_ACTOR,
        admin_session_id=_SESSION,
        now=now.fromtimestamp(now.timestamp() + 899, tz=UTC),
    )
    with pytest.raises(AdminReviewIntentError) as exc:
        verify_catalog_refresh_review_token(
            admin_session_secret=_SECRET,
            token=token,
            admin_user_id=_ACTOR,
            admin_session_id=_SESSION,
            now=now.fromtimestamp(now.timestamp() + 901, tz=UTC),
        )
    assert "expired" in exc.value.message


def test_review_token_tamper_and_wrong_secret() -> None:
    document = _document()
    token = build_catalog_refresh_review_token(
        admin_session_secret=_SECRET,
        admin_user_id=_ACTOR,
        admin_session_id=_SESSION,
        review_document=document,
        ttl_seconds=900,
    )
    body, dot, digest = token.rpartition(".")
    decoded = bytearray(base64.urlsafe_b64decode(body.encode("ascii")))
    decoded[10] ^= 0x01  # tamper one payload byte
    tampered = base64.urlsafe_b64encode(bytes(decoded)).decode("ascii") + dot + digest
    with pytest.raises(AdminReviewIntentError):
        verify_catalog_refresh_review_token(
            admin_session_secret=_SECRET,
            token=tampered,
            admin_user_id=_ACTOR,
            admin_session_id=_SESSION,
        )
    with pytest.raises(AdminReviewIntentError):
        verify_catalog_refresh_review_token(
            admin_session_secret="u" * 48,
            token=token,
            admin_user_id=_ACTOR,
            admin_session_id=_SESSION,
        )


def test_review_token_run_id_grammar() -> None:
    good = "a" * 64  # canonical Core run-id shape (64 chars)
    for run_id in (good, "collect-20261110-000000-deadbeef"):
        token = build_catalog_refresh_review_token(
            admin_session_secret=_SECRET,
            admin_user_id=_ACTOR,
            admin_session_id=_SESSION,
            review_document=_document(run_id=run_id),
            ttl_seconds=900,
        )
        assert isinstance(token, str) and token
    for run_id in ("Collect-20261110", "col.lect", "col/lect", "a" * 65, "", "-leading"):
        with pytest.raises(AdminReviewIntentError):
            build_catalog_refresh_review_token(
                admin_session_secret=_SECRET,
                admin_user_id=_ACTOR,
                admin_session_id=_SESSION,
                review_document=_document(run_id=run_id),
                ttl_seconds=900,
            )
    # empty reason is rejected by the strict closed document
    with pytest.raises(AdminReviewIntentError):
        build_catalog_refresh_review_token(
            admin_session_secret=_SECRET,
            admin_user_id=_ACTOR,
            admin_session_id=_SESSION,
            review_document=_document(reason="   "),
            ttl_seconds=900,
        )
    with pytest.raises(AdminReviewIntentError):
        build_catalog_refresh_review_token(
            admin_session_secret=_SECRET,
            admin_user_id=_ACTOR,
            admin_session_id=_SESSION,
            review_document=_document(reason="x" * 501),
            ttl_seconds=900,
        )


# --- 3. upload bounds ---------------------------------------------------------


@pytest.fixture
def ready_job(custody_root) -> _NS:
    settings = _settings(custody_root, CATALOG_REFRESH_MAX_TOTAL_BYTES=512 * 1024 * 1024)
    job_id = custody.create_job(settings, "review_supplied", {})
    return _NS(settings=settings, job_id=job_id)


def test_upload_exact_core_caps(ready_job) -> None:
    settings, job_id = ready_job.settings, ready_job.job_id
    # bundle cap: 8 MiB exactly OK, one byte over refused
    custody.store_upload(settings, job_id, "bundle", b"x" * MAX_BUNDLE_BYTES)
    with pytest.raises(CustodyJobError) as exc:
        custody.store_upload(settings, job_id, "bundle", b"x" * (MAX_BUNDLE_BYTES + 1))
    assert exc.value.code == "upload_too_large"
    # baseline cap: 32 MiB exactly OK, one byte over refused (separate job:
    # the active-slot bound is 1, so cancel the queued job first)
    custody.request_cancel(settings, job_id)
    job2 = custody.create_job(settings, "review_supplied", {})
    custody.store_upload(settings, job2, "baseline", b"y" * MAX_BASELINE_BYTES)
    with pytest.raises(CustodyJobError) as exc:
        custody.store_upload(settings, job2, "baseline", b"y" * (MAX_BASELINE_BYTES + 1))
    assert exc.value.code == "upload_too_large"
    with pytest.raises(CustodyJobError):
        custody.store_upload(settings, job2, "other", b"z")


def test_upload_closed_name_shape_and_new_only(ready_job) -> None:
    settings, job_id = ready_job.settings, ready_job.job_id
    # generated name
    name = custody.store_upload(settings, job_id, "bundle", b"payload-1")
    assert name.startswith("bundle-") and len(name) == len("bundle-") + 32
    # pre-allocated closed name
    pre = "baseline-" + "0" * 32
    assert custody.store_upload(settings, job_id, "baseline", b"payload-2", name=pre) == pre
    assert custody.upload_exists(settings, job_id, pre) is True
    # O_EXCL: the same pre-allocated name is never replaced
    with pytest.raises((FileExistsError, CustodyJobError)):
        custody.store_upload(settings, job_id, "baseline", b"other", name=pre)
    # closed shapes: wrong kind prefix / traversal / foreign names refused
    for bad in ("bundle-" + "g" * 32, "../../x", "bundle-../../x", "x" * 32, "bundle-short"):
        with pytest.raises(CustodyJobError) as exc:
            custody.store_upload(settings, job_id, "bundle", b"p", name=bad)
        assert exc.value.code in ("upload_name_invalid",)
    with pytest.raises(CustodyJobError):
        custody.upload_exists(settings, job_id, "../../x")
    assert custody.upload_exists(settings, job_id, "bundle-" + "f" * 32) is False


def test_upload_readback_and_non_served_names(ready_job) -> None:
    settings, job_id = ready_job.settings, ready_job.job_id
    name = custody.store_upload(settings, job_id, "baseline", b"canonical-bytes")
    assert custody.read_job_artifact(settings, job_id, name) == b"canonical-bytes"
    assert custody.read_job_artifact(settings, job_id, "bundle-" + "e" * 32) is None
    for bad in ("../seal.hex", "manifest.json", "x" * 100):
        with pytest.raises(CustodyJobError):
            custody.read_job_artifact(settings, job_id, bad)


# --- 4. admission -------------------------------------------------------------


def test_admission_unknown_family(custody_root) -> None:
    settings = _settings(custody_root)
    with pytest.raises(CustodyJobError) as exc:
        custody.create_job(settings, "apply", {})
    assert exc.value.code == "job_family_invalid"
    # mutating apply is NOT a queued family: the GUI composes Core directly
    assert "apply" not in custody.CATALOG_JOB_FAMILIES


def test_admission_active_capacity_and_recovery(custody_root) -> None:
    settings = _settings(custody_root, CATALOG_REFRESH_MAX_ACTIVE_JOBS=1)
    job1 = custody.create_job(settings, "collect", {"mode": "bootstrap"})
    with pytest.raises(CustodyCapacityError) as exc:
        custody.create_job(settings, "collect", {"mode": "bootstrap"})
    assert exc.value.code == "active_job_capacity"
    # claim + terminal finish releases the slot
    assert custody.begin_job(settings, job1) is not None
    with pytest.raises(CustodyCapacityError):
        custody.create_job(settings, "export_baseline", {})
    assert custody.finish_job(settings, job1, "ready", run_id="collect-20261110-000000-aa11") is True
    job2 = custody.create_job(settings, "collect", {"mode": "bootstrap"})
    assert job2 != job1


def test_admission_retained_runs_capacity(custody_root) -> None:
    settings = _settings(custody_root, CATALOG_REFRESH_MAX_RETAINED_RUNS=2)
    # the ready setup creates the private subdirectories (incl. runs/)
    assert custody.inspect_custody_setup(settings).state == "ready"
    # two published run directories (identity-checked cleanup shape: they do
    # NOT have to be sealed for the admission byte/slot accounting)
    for i in range(2):
        run_dir = custody_root.root / "runs" / f"collect-20261110-000000-{'00' * 8}{i:02x}"
        run_dir.mkdir(mode=0o700)
        (run_dir / "validation.json").write_bytes(b'{"result": {"state": "READY"}}')
    with pytest.raises(CustodyCapacityError) as exc:
        custody.create_job(settings, "review_supplied", {})
    assert exc.value.code == "retained_runs_capacity"
    # export_baseline reserves a slot too
    with pytest.raises(CustodyCapacityError):
        custody.create_job(settings, "export_baseline", {})


def test_admission_total_bytes_with_reservations(custody_root) -> None:
    # Each slot-reserving family reserves its full future ceiling at
    # admission (run ceiling + upload ceiling + record ~= 170 MiB for
    # collect/review). With a 256 MiB total bound, ONE job admits; after
    # its 32 MiB upload is stored, a second reserved job must refuse.
    # the active-job ceiling stays high so the BYTES gate is the one
    # under test (admission checks active capacity before total bytes)
    settings = _settings(
        custody_root,
        CATALOG_REFRESH_MAX_TOTAL_BYTES=256 * 1024 * 1024,
        CATALOG_REFRESH_MAX_ACTIVE_JOBS=4,
    )
    job = custody.create_job(settings, "review_supplied", {})
    custody.store_upload(settings, job, "baseline", b"z" * MAX_BASELINE_BYTES)
    _artifacts, _records, _active, total, reserved, _slots = custody._custody_usage(custody_root.root)
    assert total >= MAX_BASELINE_BYTES
    assert reserved > 0  # the admitted job's future ceiling is reserved
    with pytest.raises(CustodyCapacityError) as exc:
        custody.create_job(settings, "collect", {"mode": "bootstrap"})
    assert exc.value.code == "total_bytes_capacity"
    # the reservation releases on a terminal outcome, admitting the retry
    custody.begin_job(settings, job)
    custody.finish_job(settings, job, "ready")
    job2 = custody.create_job(settings, "collect", {"mode": "bootstrap"})
    assert job2 != job


def test_admission_job_record_capacity(custody_root) -> None:
    # MAX_RETAINED_RUNS=1 -> record cap 4; terminal records still count.
    settings = _settings(custody_root, CATALOG_REFRESH_MAX_RETAINED_RUNS=1)
    for _ in range(4):
        job = custody.create_job(settings, "export_baseline", {})
        custody.begin_job(settings, job)
        custody.finish_job(settings, job, "failed", error_code="database_url_missing")
    with pytest.raises(CustodyCapacityError) as exc:
        custody.create_job(settings, "export_baseline", {})
    assert exc.value.code == "job_record_capacity"


def test_admission_concurrent_race_single_winner(custody_root) -> None:
    """Under the existing admission lock, concurrent creators never both
    win the one active slot (thread stand-in for cross-process races)."""
    settings = _settings(custody_root, CATALOG_REFRESH_MAX_ACTIVE_JOBS=1)
    outcomes: list[str] = []
    errors: list[BaseException] = []
    lock = threading.Lock()

    def attempt() -> None:
        try:
            try:
                job_id = custody.create_job(settings, "collect", {"mode": "bootstrap"})
                result = "created:" + job_id
            except CustodyCapacityError:
                result = "capacity"
        except BaseException as exc:  # surface EVERY thread failure via the oracle
            with lock:
                errors.append(exc)
            return
        with lock:
            outcomes.append(result)

    threads = [threading.Thread(target=attempt) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    if errors:
        raise errors[0]
    assert len(outcomes) == 8
    assert sum(o.startswith("created:") for o in outcomes) == 1
    assert sum(o == "capacity" for o in outcomes) == 7


def _open_fd_count() -> int:
    return len(os.listdir("/proc/self/fd"))


def test_repeated_custody_operations_fd_stable(custody_root) -> None:
    """Bounded repeated-operation FD-stability check: a long sequence of
    setup inspects, admission-lifecycle, uploads, usage scans, job-file
    and run-directory reads must not grow the process descriptor table -
    every anchored handle and fd is closed EXACTLY ONCE on every path
    (no garbage-collected AnchoredDir chains leaking ancestor fds)."""
    import gc

    settings = _settings(custody_root)
    assert custody.inspect_custody_setup(settings).state == "ready"
    job = custody.create_job(settings, "review_supplied", {})
    upload_name = custody.store_upload(settings, job, "bundle", b"q" * 4096)
    custody.read_job_artifact(settings, job, upload_name)
    custody.begin_job(settings, job)
    custody.finish_job(settings, job, "failed", error_code="probe_done")
    gc.collect()
    baseline = _open_fd_count()
    for _ in range(50):
        assert custody.inspect_custody_setup(settings).state == "ready"
        custody.list_jobs(settings, limit=100)
        custody.list_runs(settings, limit=100)
        custody._custody_usage(custody_root.root)
        assert custody.upload_exists(settings, job, upload_name) is True
        assert custody.read_job_artifact(settings, job, upload_name) == b"q" * 4096
    gc.collect()
    after = _open_fd_count()
    # a 40+ fd leak per iteration (the AnchoredDir chains) would add
    # thousands; unrelated GC noise is bounded by a small margin.
    assert after - baseline <= 8, f"fd growth: baseline={baseline} after={after}"


# --- 5. job lifecycle + queued-cancel recovery --------------------------------


def test_begin_unknown_and_terminal_refused(custody_root) -> None:
    settings = _settings(custody_root)
    assert custody.begin_job(settings, "f" * 32) is None
    assert custody.finish_job(settings, "f" * 32, "ready") is False
    with pytest.raises(CustodyJobError):
        custody.request_cancel(settings, "f" * 32)


def test_claim_running_and_duplicate_delivery(custody_root) -> None:
    settings = _settings(custody_root)
    job = custody.create_job(settings, "export_baseline", {})
    record = custody.begin_job(settings, job)
    assert record is not None and record["status"] == "running"
    # duplicate/late delivery never re-executes
    assert custody.begin_job(settings, job) is None
    # terminal finish is NEW-ONLY
    assert custody.finish_job(settings, job, "ready", artifact_name="baseline-" + "1" * 32) is True
    assert custody.finish_job(settings, job, "failed", error_code="late") is False
    row = _read_record(settings, job)
    assert row["status"] == "ready"
    assert row["artifact_name"] == "baseline-" + "1" * 32
    assert row["error_code"] is None


def test_queued_cancel_is_terminal_and_releases_slot(custody_root) -> None:
    """broker-fail -> cancel -> retry (root 217-QUEUED-CANCEL-RECOVERY):
    a still-queued/unclaimed job is canceled terminally and its
    reservations release immediately; the slot is re-admissible."""
    settings = _settings(custody_root, CATALOG_REFRESH_MAX_ACTIVE_JOBS=1)
    job = custody.create_job(settings, "export_baseline", {})
    with pytest.raises(CustodyCapacityError):
        custody.create_job(settings, "export_baseline", {})
    # the dispatch was never acknowledged (lost/failed broker delivery)
    assert custody.note_dispatch(
        settings, job, dispatched=False, detail="broker dispatch unconfirmed: ConnectionError"
    ) is True
    row = _read_record(settings, job)
    assert row["dispatch"] == "unconfirmed"
    assert row["status"] == "queued"  # non-terminal metadata update
    assert "dispatch unconfirmed" in row["progress"]
    # terminal cancel of the still-queued job
    assert custody.request_cancel(settings, job) is True
    row = _read_record(settings, job)
    assert row["status"] == "canceled"
    assert row["cancel_requested"] is True
    _a, _r, active, _t, reserved, slots = custody._custody_usage(custody_root.root)
    assert active == 0 and reserved == 0 and slots == 0
    # retry is admissible
    job2 = custody.create_job(settings, "export_baseline", {})
    assert job2 != job
    # the LATE delivery of the lost message never executes
    assert custody.begin_job(settings, job) is None
    assert _read_record(settings, job)["status"] == "canceled"
    # canceling a terminal job is a no-op refusal
    assert custody.request_cancel(settings, job) is False


def test_dispatch_confirmed_persisted(ready_job) -> None:
    settings, job = ready_job.settings, ready_job.job_id
    assert custody.note_dispatch(
        settings, job, dispatched=True, detail="broker acknowledged"
    ) is True
    row = _read_record(settings, job)
    assert row["dispatch"] == "confirmed"
    assert row["status"] == "queued"
    # note_dispatch never touches terminal or unknown jobs
    custody.request_cancel(settings, job)  # -> terminal canceled
    assert custody.note_dispatch(settings, job, dispatched=True, detail="x") is False
    assert custody.note_dispatch(settings, "f" * 32, dispatched=True, detail="x") is False


def test_running_cancel_stays_cooperative(custody_root) -> None:
    settings = _settings(custody_root)
    job = custody.create_job(settings, "collect", {"mode": "bootstrap"})
    custody.begin_job(settings, job)
    assert custody.request_cancel(settings, job) is True
    row = _read_record(settings, job)
    assert row["status"] == "running" and row["cancel_requested"] is True
    # the live checkpoint re-read observes the flag (pre-publication gate)
    assert custody.cancel_check(settings, job)() is True
    # truthful terminal mapping: operator cancel -> canceled
    assert custody.job_cancel_requested(settings, job) is True
    assert custody.finish_job(settings, job, "canceled", error_code="cancel_requested") is True
    row = _read_record(settings, job)
    assert row["status"] == "canceled" and row["error_code"] == "cancel_requested"


def test_cancel_check_fails_closed_on_lost_custody(custody_root) -> None:
    settings = _settings(custody_root)
    job = custody.create_job(settings, "collect", {"mode": "bootstrap"})
    check = custody.cancel_check(settings, job)
    assert check() is False  # queued, no flag
    # operator removes the record out from under a running job: fail closed
    custody.begin_job(settings, job)
    os.unlink(custody_root.root / "jobs" / f"{job}.json")
    assert check() is True


def test_finish_releases_reservation(custody_root) -> None:
    settings = _settings(custody_root)
    job = custody.create_job(settings, "collect", {"mode": "bootstrap"})
    _a, _r, _active, _t, reserved, slots = custody._custody_usage(custody_root.root)
    assert reserved > 0 and slots == 1
    custody.begin_job(settings, job)
    custody.finish_job(settings, job, "ready", run_id="collect-20261110-000000-aa11")
    _a2, _r2, _a3, _t2, reserved2, slots2 = custody._custody_usage(custody_root.root)
    assert reserved2 == 0 and slots2 == 0


# --- 6. canaries ---------------------------------------------------------------


def test_canary_absent_from_projections_and_task_results(custody_root) -> None:
    settings = _settings(custody_root)
    job = custody.create_job(
        settings,
        "export_baseline",
        {"operator_note": CANARY, "reason": "refresh " + CANARY},
    )
    # projection never carries raw params
    for row in custody.list_jobs(settings):
        assert CANARY not in json.dumps(row)
    # the worker result for this job (database_url_missing -> failed)
    # carries no param content either
    result = asyncio.run(worker._execute_job(settings=settings, job_id=job))
    assert result["status"] == "failed"
    assert CANARY not in json.dumps(result)
    assert _read_record(settings, job)["status"] == "failed"


def test_canary_absent_from_unexpected_failure_log(custody_root, monkeypatch) -> None:
    settings = _settings(custody_root)
    job = custody.create_job(settings, "review_supplied", {"note": CANARY})
    captured: list[tuple[tuple, dict]] = []

    def _warn(*args, **kwargs):
        captured.append((args, kwargs))

    monkeypatch.setattr(worker.logger, "warning", _warn)

    def _boom(*args, **kwargs):
        raise RuntimeError(CANARY)

    monkeypatch.setattr(worker, "_run_review", _boom)
    result = asyncio.run(worker._execute_job(settings=settings, job_id=job))
    assert result["status"] == "failed"
    assert result["error_code"] == "internal_error"
    assert captured, "the unexpected failure must log exactly once"
    for args, kwargs in captured:
        blob = json.dumps([args, kwargs], default=repr)
        assert CANARY not in blob
        assert kwargs.get("error_class") == "RuntimeError"


# --- 7. worker default composition (real run_collect, synthetic sources) ------


def _synthetic_public_resolver(host, port, proto=None):
    """Synthetic public answer for the official registry hosts ONLY; any
    other host fails closed (no default DNS in this test)."""
    if host in ("openrouter.ai", "developers.openai.com", "www.ecb.europa.eu"):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", 443))
        ]
    raise OSError(f"no synthetic answer for {host}")


@pytest.fixture(autouse=True)
def _no_live_io(monkeypatch):
    """Fail-on-live-I/O guard: any default DNS or real socket connection
    inside this module is a test failure."""

    def _refuse(*args, **kwargs):
        raise AssertionError("focused test reached a live network seam")

    monkeypatch.setattr(socket, "getaddrinfo", _refuse)
    monkeypatch.setattr(socket.socket, "connect", _refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", _refuse)
    # the worker passes NO fetch/resolve: the REAL Core defaults are the
    # import-time bindings - re-point them to the synthetic public answer
    # (the only synthetic half of the default composition; the vetted
    # fetch bounds, ONE AcquisitionContext, sealing, and publication are
    # the real Core code paths).
    for fn in (src.fetch_source, src.fetch_sources, coll.collect_bundle):
        kwdefaults = dict(getattr(fn, "__kwdefaults__", None) or {})
        if "resolve" in kwdefaults:
            kwdefaults["resolve"] = _synthetic_public_resolver
            monkeypatch.setattr(fn, "__kwdefaults__", kwdefaults)
    yield


def test_worker_collect_default_composition_publishes_sealed_run(
    custody_root, monkeypatch, tmp_path: Path
) -> None:
    """The QUEUED collect family runs the REAL default composition
    (run_collect with default fetch/resolve/acquisition/sealing) end to
    end: only the official-source BYTES (MockTransport) and the public
    DNS answer are synthetic. The sealed run lands in operator custody."""
    settings = _settings(
        custody_root,
        CATALOG_REFRESH_MAX_TOTAL_BYTES=1024 * 1024 * 1024,
        CATALOG_REFRESH_READ_ONLY_TIMEOUT_SECONDS=120,
    )
    world = World()
    monkeypatch.setattr(worker, "_collect_client_factory", world.client)
    job = custody.create_job(
        settings,
        "collect",
        {"mode": "bootstrap", "providers": ["openai", "openrouter"]},
    )
    result = asyncio.run(worker._execute_job(settings=settings, job_id=job))
    assert result["executed"] is True
    # the synthetic world's new models are honest REVIEW-severity
    # new-model-exposure findings (no blockers): a sealed run publishes
    # as ready or ready-with-warnings - never a blocked/failed outcome
    assert result["status"] in ("ready", "warnings"), result
    run_id = result["run_id"]
    assert run_id and run_id.startswith("collect-")
    row = _read_record(settings, job)
    assert row["status"] == result["status"] and row["run_id"] == run_id
    # the sealed run is real custody: authenticated capture loads and the
    # sealed content is servable through the same held boundary
    capture, handle = custody.load_run_capture(settings, run_id)
    try:
        assert capture.result.valid is True
        assert capture.baseline is None  # bootstrap: no SQL observation
        content = capture.content["catalog-refresh.json"]
        assert isinstance(content, bytes) and content
        assert capture.content["catalog-baseline.json"]
    finally:
        handle.close()
    served = custody.read_run_artifact(settings, run_id, "catalog-refresh.json")
    assert served == capture.content["catalog-refresh.json"]
    # the custody run directory is exactly the sealed Core file set
    names = {p.name for p in (custody_root.root / "runs" / run_id).iterdir()}
    assert names == custody.CORE_RUN_FILE_SET
    # repeat delivery of the same (late) message: terminal, never re-runs
    result2 = asyncio.run(worker._execute_job(settings=settings, job_id=job))
    assert result2["executed"] is False and result2["error_code"] == "not_executed"


def test_worker_collect_refresh_uses_configured_db_refusal_offline(
    custody_root, monkeypatch
) -> None:
    """refresh WITHOUT an uploaded baseline consults the configured
    DATABASE_URL (legacy resolution point); offline (None) the exact
    legacy usage refusal fires BEFORE any retrieval - no
    blocked-by-network, no publication (the original CLI raised the
    '--refresh requires --baseline-file or --db-url (or DATABASE_URL)'
    BadParameter in this case, mapped to refresh_requires_baseline)."""
    settings = _settings(custody_root, DATABASE_URL=None)
    world = World()
    monkeypatch.setattr(worker, "_collect_client_factory", world.client)
    job = custody.create_job(
        settings,
        "collect",
        {"mode": "refresh", "providers": ["openrouter"]},
    )
    result = asyncio.run(worker._execute_job(settings=settings, job_id=job))
    assert result["status"] == "failed"
    assert result["error_code"] == "refresh_requires_baseline"
    # nothing was published: no run directories at all
    assert list((custody_root.root / "runs").iterdir()) == []


def test_worker_collect_cancel_before_retrieval(custody_root, monkeypatch) -> None:
    settings = _settings(
        custody_root,
        CATALOG_REFRESH_MAX_TOTAL_BYTES=1024 * 1024 * 1024,
        CATALOG_REFRESH_READ_ONLY_TIMEOUT_SECONDS=120,
    )
    world = World()
    monkeypatch.setattr(worker, "_collect_client_factory", world.client)
    job = custody.create_job(
        settings, "collect", {"mode": "bootstrap", "providers": ["openrouter"]}
    )
    # cancel while queued: the delivery never executes at all
    assert custody.request_cancel(settings, job) is True
    result = asyncio.run(worker._execute_job(settings=settings, job_id=job))
    assert result["executed"] is False
    assert _read_record(settings, job)["status"] == "canceled"
    assert list((custody_root.root / "runs").iterdir()) == []


# --- 8. default proposal bridge -------------------------------------------------


def _bridge(
    handler,
    *,
    per_body: int = worker._PROPOSAL_MAX_BODY_BYTES,
    total: int = worker._PROPOSAL_MAX_TOTAL_BYTES,
):
    sync = httpx.Client(
        transport=httpx.MockTransport(handler), follow_redirects=False, trust_env=False
    )
    transport = worker._BoundedAsyncVettedTransport(sync)
    transport._budget.cap = total  # focused bound for the probe
    return transport


def test_bridge_default_destination_families(monkeypatch) -> None:
    """The bridge enforces the fixed official host/path families, raw and
    normalized; everything else is refused before any network contact."""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, content=b"[]")

    transport = _bridge(handler)

    ok = [
        "https://openrouter.ai/api/v1/models",
        "https://openrouter.ai/docs/models",
        # the EXACT pinned OpenRouter detail service URL (vendor/model ids)
        "https://openrouter.ai/api/v1/models/synth/alpha/endpoints",
        "https://openrouter.ai/api/v1/models/vendor/model-2.1:free/endpoints",
        "https://api.openai.com/v1/models",
        # the exact fixed OpenAI-assisted seam endpoint (ack + secret gated)
        "https://api.openai.com/v1/responses",
        "https://developers.openai.com/api/docs/pricing.md",
    ]
    refused = [
        "https://openrouter.ai/api/v1/models/../docs",  # raw dot segment
        "https://openrouter.ai:8443/api/v1/models",  # non-443
        "https://user:pw@openrouter.ai/api/v1/models",  # userinfo
        "https://openrouter.ai/api/v1/models?x=1",  # query
        "https://openrouter.ai/api/v1/models#f",  # fragment
        "http://openrouter.ai/api/v1/models",  # not https
        "https://openrouter.ai/api/v1/models/../../etc",  # traversal
        # unrelated /models/... passthrough is NOT a pinned service URL
        "https://openrouter.ai/models/synth/alpha",
        "https://openrouter.ai/models/a/b/c/d",
        # detail family requires the exact /endpoints terminal + bounded id
        "https://openrouter.ai/api/v1/models/synth/alpha",
        "https://openrouter.ai/api/v1/models/a/b/c/d/e/endpoints",  # too deep
        "https://api.openai.com/v1/responses/extra",  # assisted is EXACT, no sub-path
        "https://api.openai.com/v1/chat/completions",  # unrelated endpoint refused
        "https://evil.example.com/api/v1/models",
        "ftp://openrouter.ai/api/v1/models",
    ]

    # RAW dot segments are refused on the raw string BEFORE httpx
    # normalization could turn them into another (pinned) family.
    assert not worker._official_destination_allowed(
        "https://openrouter.ai/api/v1/models/../models/synth/alpha/endpoints"
    )

    async def scenario():
        for url in ok:
            request = httpx.Request("GET", url)
            await transport.handle_async_request(request)
        for url in refused:
            request = httpx.Request("GET", url)
            with pytest.raises(ValueError):
                await transport.handle_async_request(request)

    asyncio.run(scenario())
    assert len(calls) == len(ok)


def test_bridge_identity_only_encoding() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            # stream= (not content=): construction must NOT decode the
            # declared gzip body - the bridge is what must refuse it
            200, stream=httpx.ByteStream(b"body"), headers={"Content-Encoding": "gzip"}
        )

    transport = _bridge(handler)

    async def scenario():
        request = httpx.Request("GET", "https://openrouter.ai/api/v1/models")
        request.headers["Accept-Encoding"] = "identity"  # the bridge forces this
        with pytest.raises(ValueError) as exc:
            await transport.handle_async_request(request)
        assert "non-identity encoding" in str(exc.value)

    asyncio.run(scenario())


def test_bridge_per_body_cap() -> None:
    overflow = b"x" * (worker._PROPOSAL_MAX_BODY_BYTES + 1)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=overflow)

    transport = _bridge(handler)

    async def scenario():
        request = httpx.Request("GET", "https://openrouter.ai/api/v1/models")
        with pytest.raises(ValueError) as exc:
            await transport.handle_async_request(request)
        assert "exceeds its bound" in str(exc.value)

    asyncio.run(scenario())


def test_bridge_aggregate_budget_overflow_and_repeat_refusal() -> None:
    """Debit DURING the sync read, never refund, refuse once exhausted:
    3-byte bodies under a 4-byte total: the first body (3 bytes) is
    delivered; the second is still acquired (spent was 3 < 4 pre-send)
    and its 3 bytes are debited BEFORE the failure decision - 6 > 4,
    so it is refused without refund; every later request is refused
    BEFORE any network contact (exactly two acquisitions)."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, content=b"abc")

    transport = _bridge(handler, total=4)

    outcomes: list[str] = []

    async def scenario():
        for _ in range(4):
            request = httpx.Request("GET", "https://openrouter.ai/api/v1/models")
            try:
                await transport.handle_async_request(request)
                outcomes.append("ok")
            except ValueError:
                outcomes.append("refused")

    asyncio.run(scenario())
    assert calls["n"] == 2  # only two bodies were ever acquired
    assert transport._budget.spent == 6  # overflow bytes are debited, never refunded
    assert outcomes == ["ok", "refused", "refused", "refused"]


def test_bridge_aggregate_budget_exact_cap_equality() -> None:
    """The exact-edge predicate split: two 2-byte bodies fill the 4-byte
    total; the third request is refused BEFORE reaching the transport
    (pre-acquisition spent >= cap) while a body ending exactly at the cap
    after its debit remains allowed (post-debit spent > cap)."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, content=b"ab")

    transport = _bridge(handler, total=4)

    outcomes: list[str] = []

    async def scenario():
        for _ in range(3):
            request = httpx.Request("GET", "https://openrouter.ai/api/v1/models")
            try:
                await transport.handle_async_request(request)
                outcomes.append("ok")
            except ValueError:
                outcomes.append("refused")

    asyncio.run(scenario())
    assert calls["n"] == 2
    assert transport._budget.spent == 4
    assert outcomes == ["ok", "ok", "refused"]


def test_registry_guarded_client_raw_traversal_refusal() -> None:
    """The client guard validates the RAW url string before httpx
    normalization can turn a traversal into another family."""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, content=b"[]")

    async def scenario():
        async with worker._RegistryGuardedClient(
            # this httpx build's MockTransport is BOTH BaseTransport and
            # AsyncBaseTransport: no adapter layer needed
            transport=httpx.MockTransport(handler)
        ) as client:
            response = await client.get("https://openrouter.ai/api/v1/models")
            assert response.status_code == 200 and len(calls) == 1
            with pytest.raises(ValueError):
                await client.get("https://openrouter.ai/api/v1/models/../../docs/anything")
            assert len(calls) == 1  # refused BEFORE any network contact

    asyncio.run(scenario())


def test_proposal_default_factory_composition_and_checkpoint(monkeypatch) -> None:
    """DEFAULT factory composition: the REAL ``_build_proposal_client``
    (registry guard + bounded async bridge + budget), with ONLY the
    vetted sync transport replaced by a sync MockTransport (labeled -
    the whole async factory is NOT replaced). The cooperative job
    checkpoint is wired through the factory seam and honored between
    returned raw chunks (a mid-body cancel never refunds debited
    bytes)."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"payload-bytes")

    monkeypatch.setattr(
        worker, "VettedHTTPTransport", lambda: httpx.MockTransport(handler)
    )
    client = worker._build_proposal_client()

    async def scenario_ok():
        try:
            response = await client.get("https://openrouter.ai/api/v1/models")
            assert response.status_code == 200
            assert response.content == b"payload-bytes"
        finally:
            await client.aclose()

    asyncio.run(scenario_ok())

    # mid-body checkpoint trip across a streamed sync body: every
    # returned chunk is debited BEFORE the per-chunk failure decision
    class _ChunkedStream(httpx.SyncByteStream):
        """A real (multi-chunk) sync response stream for the bounded
        bridge; a plain ``iter([...])`` is not a ``SyncByteStream`` and
        is rejected by the sync client's single-request path."""

        def __init__(self, chunks: list[bytes]) -> None:
            self._chunks = list(chunks)

        def __iter__(self):
            for chunk in self._chunks:
                yield chunk

        def close(self) -> None:
            pass

    def streamed(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, stream=_ChunkedStream([b"012", b"345", b"678", b"901"])
        )

    monkeypatch.setattr(
        worker, "VettedHTTPTransport", lambda: httpx.MockTransport(streamed)
    )
    trips = {"n": 0}

    def checkpoint() -> bool:
        trips["n"] += 1
        return trips["n"] > 4

    client2 = worker._build_proposal_client(checkpoint=checkpoint)

    async def scenario_cancel():
        try:
            with pytest.raises(worker.CollectionCanceled):
                await client2.get("https://openrouter.ai/api/v1/models")
        finally:
            await client2.aclose()

    asyncio.run(scenario_cancel())
    assert client2._transport._budget.spent == 12  # no refunds

# --- 9. GUI apply-flow helpers ---------------------------------------------------


class _Warn:
    def __init__(self, code: str) -> None:
        self.code = code


def _fake_capture(
    *, baseline, warnings=(), state="READY", bundle_sha: str = HEX64_A, plan_sha: str = HEX64_B
):
    validation = {
        "state": state,
        "apply_plan": {"operations": [{"op": "upsert"}], "plan_sha256": plan_sha},
        "baseline": {"target": "declared-not-truth"},
    }
    first_install_doc = b'{"note": "first install", "schema_version": "first-install"}\n'
    return _NS(
        result=_NS(state=state, valid=True),
        content={
            "validation.json": json.dumps(validation).encode(),
            "catalog-baseline.json": first_install_doc,
        },
        receipt={"semantic_bundle_sha256": bundle_sha, "hmac_sha256": "c" * 64},
        baseline=baseline,
        report=_NS(warnings=list(warnings)),
    )


def _observed_baseline():
    """Canonical document shape (the fields the facts helper reads)."""
    return _NS(
        target=_NS(
            server_host="db.internal", server_port=5433,
            database="slaif_cat", postgres_version="16.4",
        ),
        counts=_NS(providers=2, routes=132, pricing_rules=140, fx_rates=6),
        content_sha256="d" * 64,
    )


def _db_settings(db_url: str | None) -> _NS:
    return _NS(DATABASE_URL=db_url)


def test_sealed_facts_canonical_document() -> None:
    capture = _fake_capture(baseline=_observed_baseline())
    facts, refusal = router_mod._sealed_apply_facts(
        capture, _db_settings("postgresql+asyncpg://op:s@db.internal:5433/slaif_cat")
    )
    assert refusal is None
    assert facts["target_database"] == "slaif_cat"
    assert facts["target_host"] == "db.internal"
    assert facts["target_port"] == 5433
    assert facts["postgres_version"] == "16.4"
    assert facts["row_counts"] == {"providers": 2, "routes": 132, "pricing_rules": 140, "fx_rates": 6}
    assert facts["baseline_content_sha256"] == "d" * 64
    assert facts["bundle_sha256"] == HEX64_A and facts["plan_sha256"] == HEX64_B
    # the display validation.baseline ('target' key) is NOT a source of truth
    assert facts["target_database"] != "declared-not-truth"


def test_sealed_facts_first_install_honest_semantics() -> None:
    import hashlib

    capture = _fake_capture(baseline=None)
    facts, refusal = router_mod._sealed_apply_facts(
        capture, _db_settings("postgresql+asyncpg://op:s@db.internal:5433/slaif_cat")
    )
    assert refusal is None
    assert (facts["target_database"], facts["target_host"], facts["target_port"]) == (
        "slaif_cat", "db.internal", 5433
    )
    assert facts["postgres_version"] == "unknown"  # honest marker, no SQL fact
    assert facts["row_counts"] == {}  # nothing observed
    doc = capture.content["catalog-baseline.json"]
    assert facts["baseline_content_sha256"] == hashlib.sha256(doc).hexdigest()
    # bootstrap without a configured DB: explicit refusal, no facts
    facts2, refusal2 = router_mod._sealed_apply_facts(capture, _db_settings(None))
    assert facts2 is None and "DATABASE_URL" in refusal2
    # blocked state refuses
    capture_b = _fake_capture(baseline=_observed_baseline(), state="BLOCKED")
    facts3, refusal3 = router_mod._sealed_apply_facts(capture_b, _db_settings("x"))
    assert facts3 is None and "BLOCKED" in refusal3


class _StubHandle:
    def close(self) -> None:
        return None


def _stub_capture(monkeypatch, capture) -> None:
    """Point the custody seam at ONE synthetic authenticated capture."""
    load = lambda settings, run_id: (capture, _StubHandle())  # noqa: E731
    monkeypatch.setattr(router_mod.custody, "load_run_capture", load)
    monkeypatch.setattr(custody, "load_run_capture", load)


def test_apply_review_document_two_step_intent(monkeypatch) -> None:
    settings = _db_settings("postgresql+asyncpg://op:s@db.internal:5433/slaif_cat")
    capture = _fake_capture(
        baseline=_observed_baseline(),
        warnings=(_Warn("gate:pricing"), _Warn("gate:routes")),
    )
    _stub_capture(monkeypatch, capture)
    run_id = "collect-20261110-000000-deadbeef"
    # exact sealed acknowledgement set + reason -> signed document
    built, refusal = router_mod._apply_review_document(
        settings, run_id, reason="monthly refresh", ack_codes=["gate:routes", "gate:pricing"]
    )
    assert refusal is None and built is not None
    document, codes = built
    assert document["run_id"] == run_id
    assert document["reason"] == "monthly refresh"
    assert document["ack_warning_codes"] == ["gate:pricing", "gate:routes"]
    assert codes == ["gate:pricing", "gate:routes"]
    # missing acknowledgement refused
    built2, refusal2 = router_mod._apply_review_document(
        settings, run_id, reason="monthly refresh", ack_codes=["gate:routes"]
    )
    assert built2 is None and "gate:pricing" in refusal2
    # a code outside the sealed set refused
    built3, refusal3 = router_mod._apply_review_document(
        settings, run_id,
        reason="monthly refresh",
        ack_codes=["gate:pricing", "gate:routes", "invented:code"],
    )
    assert built3 is None and "invented:code" in refusal3
    # READY (no warnings) requires an EMPTY acknowledgement set
    capture_ready = _fake_capture(baseline=_observed_baseline())
    _stub_capture(monkeypatch, capture_ready)
    built4, refusal4 = router_mod._apply_review_document(
        settings, run_id, reason="monthly refresh", ack_codes=[]
    )
    assert built4 is not None
    built5, refusal5 = router_mod._apply_review_document(
        settings, run_id, reason="monthly refresh", ack_codes=["gate:pricing"]
    )
    assert built5 is None


def test_stale_binding_field_by_field(monkeypatch) -> None:
    """The apply re-check compares EVERY signed fact against the CURRENT
    capture; any drift (digest, target, counts, warning set) is stale."""
    settings = _db_settings("postgresql+asyncpg://op:s@db.internal:5433/slaif_cat")
    base = _fake_capture(baseline=_observed_baseline())
    facts, _refusal = router_mod._sealed_apply_facts(base, settings)
    signed = {
        "run_id": "collect-20261110-000000-deadbeef",
        **facts,
        "ack_warning_codes": [],
        "reason": "monthly refresh",
        "nonce": uuid.uuid4().hex,
    }

    def matches(drifted_capture, drifted_document) -> bool:
        current, refusal = router_mod._sealed_apply_facts(drifted_capture, settings)
        assert refusal is None
        return (
            drifted_document["bundle_sha256"] == current["bundle_sha256"]
            and drifted_document["plan_sha256"] == current["plan_sha256"]
            and drifted_document["target_database"] == current["target_database"]
            and drifted_document["target_host"] == current["target_host"]
            and drifted_document["target_port"] == current["target_port"]
            and drifted_document["postgres_version"] == current["postgres_version"]
            and drifted_document["baseline_content_sha256"] == current["baseline_content_sha256"]
            and dict(drifted_document["row_counts"]) == dict(current["row_counts"])
            and sorted(drifted_document["ack_warning_codes"])
            == router_mod._sealed_warning_codes(drifted_capture)
        )

    # untouched: every signed fact matches the current capture
    assert matches(base, dict(signed)) is True
    # each drift dimension is detected
    drifted = _fake_capture(baseline=_observed_baseline(), bundle_sha="e" * 64)
    assert matches(drifted, dict(signed)) is False
    doc = dict(signed)
    doc["target_port"] = 5434
    assert matches(base, doc) is False
    doc = dict(signed)
    doc["row_counts"] = {"providers": 3, "routes": 132, "pricing_rules": 140, "fx_rates": 6}
    assert matches(base, doc) is False
    doc = dict(signed)
    doc["ack_warning_codes"] = ["gate:pricing"]
    assert matches(base, doc) is False


# --- 11. custody storage/cleanup regressions -----------------------------------


def _fill(path: Path, nbytes: int) -> None:
    """Create a file whose st_size is exactly ``nbytes`` (sparse - the
    custody byte accounting reads st_size, not allocated blocks, so this
    is fast and writes almost no real disk)."""
    with path.open("wb") as fh:
        fh.truncate(nbytes)


def test_proposal_output_budget_refuses_overcap_never_written(tmp_path: Path) -> None:
    """The enforced generation ceiling is a BEFORE-GROWTH write admission
    (O(1), no tree rescan): an over-cap payload is refused and NEVER
    written (not merely removed later); a payload ending exactly at the
    cap is allowed; the default (None) budget leaves CLI behavior
    unchanged."""
    from slaif_gateway.services import provider_catalog_proposal as pm

    token = pm._PROPOSAL_OUTPUT_BUDGET.set(pm._ProposalOutputBudget(1000))
    try:
        ok = tmp_path / "ok.bin"
        pm._emit(ok, b"y" * 900)  # 900 <= 1000
        assert ok.read_bytes() == b"y" * 900
        over = tmp_path / "over.bin"
        with pytest.raises(pm.ProviderCatalogProposalSizeError):
            pm._emit(over, b"z" * 200)  # 900 + 200 > 1000
        assert not over.exists()  # refused payload was NEVER written
        exact = tmp_path / "exact.bin"
        pm._emit(exact, b"e" * 100)  # 900 + 100 == 1000 (exact cap)
        assert exact.read_bytes() == b"e" * 100
    finally:
        pm._PROPOSAL_OUTPUT_BUDGET.reset(token)
    # default budget (None): writes freely (CLI unchanged)
    free = tmp_path / "free.bin"
    pm._emit(free, b"q" * 5000)
    assert free.read_bytes() == b"q" * 5000


def test_proposal_output_budget_charges_failed_write_conservatively(
    tmp_path: Path, monkeypatch
) -> None:
    """A write that raises (a source-details helper may catch the error
    and continue) STILL conservatively consumes the budget - no automatic
    refund - so a later payload is admitted against the charged (not the
    on-disk) total."""
    from slaif_gateway.services import provider_catalog_proposal as pm

    budget = pm._ProposalOutputBudget(100)
    token = pm._PROPOSAL_OUTPUT_BUDGET.set(budget)
    real_write = Path.write_bytes
    calls = {"n": 0}

    def boom(self, data):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("simulated partial/failed write")
        return real_write(self, data)

    monkeypatch.setattr(Path, "write_bytes", boom)
    try:
        try:
            pm._emit(tmp_path / "a.bin", b"x" * 60)  # 0+60<=100: charge, then raise
        except OSError:
            pass  # an upstream source-details helper would catch and continue
        assert budget.committed == 60  # charged even though the write failed
        # a 40-byte payload now fits exactly at the cap (60+40)
        pm._emit(tmp_path / "b.bin", b"y" * 40)
        assert (tmp_path / "b.bin").read_bytes() == b"y" * 40
        # and a further over-cap payload is refused (never written)
        with pytest.raises(pm.ProviderCatalogProposalSizeError):
            pm._emit(tmp_path / "c.bin", b"z" * 1)
        assert not (tmp_path / "c.bin").exists()
    finally:
        pm._PROPOSAL_OUTPUT_BUDGET.reset(token)
        monkeypatch.undo()


def test_account_proposal_output_arithmetic_corrected(custody_root) -> None:
    """The post-generation gate compares the AT-REST total_bytes (which
    ALREADY includes the actual proposal output on disk and EXCLUDES the
    virtual admission reservation) to the bound. A proposal output that
    the old 'total_bytes - reserved + actual' formula would wrongly
    retract (it subtracted the 32 MiB reservation) is correctly kept
    under the corrected arithmetic; only a genuinely over-cap output is
    retracted."""
    MiB = 1024 * 1024
    # CATALOG_REFRESH_MAX_TOTAL_BYTES has a 64 MiB settings floor, and the
    # proposal admission reservation is fixed at 33 MiB (32 MiB + job file).
    settings = _settings(
        custody_root, CATALOG_REFRESH_MAX_TOTAL_BYTES=64 * MiB
    )
    job = custody.create_job(settings, "proposal", {"provider_scope": "openrouter"})
    outdir = custody_root.root / "proposals" / job
    outdir.mkdir()
    os.chmod(outdir, 0o700)
    blob = outdir / "provider-catalog-normalized.json"
    # 63 MiB actual output: at-rest total_bytes (~63 MiB + tiny jobfile)
    # is under the 64 MiB cap -> NOT retracted. The OLD formula
    # (total_bytes - reserved + actual = 2*S - 33 MiB) would have
    # retracted this (2*63 - 33 = 93 MiB > 64 MiB), so this case
    # distinguishes the corrected arithmetic.
    _fill(blob, 63 * MiB)
    custody.account_proposal_output(settings, job)
    assert blob.exists()
    # push past the cap: 64.5 MiB output -> total_bytes > 64 MiB ->
    # retract + refuse.
    _fill(blob, 64 * MiB + 512 * 1024)
    with pytest.raises(custody.CustodyCapacityError) as exc:
        custody.account_proposal_output(settings, job)
    assert exc.value.code == "proposal_output_capacity"
    assert not outdir.exists()  # partial output retracted


def _seed_run_dir(custody_root, settings, run_id: str) -> Path:
    custody.inspect_custody_setup(settings)  # ready -> creates subdirs
    run_dir = custody_root.root / "runs" / run_id
    run_dir.mkdir(mode=0o700)
    for name in custody.CORE_RUN_FILE_SET:
        (run_dir / name).write_bytes(b"{}")
    return run_dir


def test_remove_terminal_run_refuses_extra_hidden_entry(custody_root) -> None:
    """An EXTRA hidden entry (staging leftover) refuses BEFORE any unlink:
    all 9 core files AND the hidden entry stay untouched (the old defect
    deleted the 9 expected files, then failed on the final rmdir)."""
    settings = _settings(custody_root)
    run_id = "collect-20261110-000000-deadbeef"
    run_dir = _seed_run_dir(custody_root, settings, run_id)
    (run_dir / ".operator-note").write_bytes(b"note")
    with pytest.raises(custody.CustodyJobError) as exc:
        custody.remove_terminal_run(settings, run_id)
    assert exc.value.code == "run_cleanup_refused"
    assert {p.name for p in run_dir.iterdir()} == (
        custody.CORE_RUN_FILE_SET | {".operator-note"}
    )


def test_remove_terminal_run_refuses_nonregular_entry(custody_root) -> None:
    """A symlink (a non-regular entry) in the run refuses before any
    unlink; the entry is neither followed nor removed."""
    settings = _settings(custody_root)
    run_id = "collect-20261110-000000-deadbeef"
    run_dir = _seed_run_dir(custody_root, settings, run_id)
    target = run_dir / "catalog-refresh.json"
    target.unlink()
    target.symlink_to("/etc/hostname")
    with pytest.raises(custody.CustodyJobError) as exc:
        custody.remove_terminal_run(settings, run_id)
    assert exc.value.code == "run_cleanup_refused"
    assert target.is_symlink()  # symlink refused, not followed/removed


# --- 10. import boundary ----------------------------------------------------------


def test_router_import_does_not_eagerly_import_worker_or_celery() -> None:
    """The web router must stay broker-free at import time: the worker
    module is imported ONLY inside the dispatch helper (lazy)."""
    import inspect

    source = Path(router_mod.__file__).read_text(encoding="utf-8")
    for line in source.splitlines():
        if line.startswith(("import ", "from ")):
            assert "workers" not in line, f"eager worker import: {line}"
    body = inspect.getsource(router_mod._dispatch_job)
    assert "from slaif_gateway.workers.tasks_catalog_refresh import" in body
    assert "catalog_refresh_execute_job.delay(job_id)" in body


# --- 11. 217-a resume corrections ----------------------------------------------


def test_bounded_form_preserves_repeated_keys() -> None:
    """A native <select multiple> submits one key per selection: the
    bounded form projection must keep ALL values (dict would drop all
    but the last)."""
    form = router_mod._BoundedForm(
        [("providers", "openai"), ("providers", "openrouter"), ("mode", "bootstrap")]
    )
    assert form.getlist("providers") == ["openai", "openrouter"]
    assert form.get("mode") == "bootstrap"
    assert form.get("missing", "default") == "default"
    assert len(form) == 2
    assert sorted(form.keys()) == ["mode", "providers"]


def test_parse_provider_choices_closed_set() -> None:
    assert (
        router_mod._parse_provider_choices(
            ["openrouter", "openai", "openai", " evil "]
        )
        == ["openai", "openrouter"]
    )
    assert router_mod._parse_provider_choices(["evil"]) == []
    assert router_mod._parse_provider_choices([]) == []


def test_parse_model_choices_newline_comma_and_cap() -> None:
    # blank = all eligible
    assert router_mod._parse_model_choices("") == []
    assert router_mod._parse_model_choices(None) == []
    # comma- AND newline-separated (record-choice multi serialization),
    # de-duplicated, order-preserving
    assert router_mod._parse_model_choices("a, b\nb\nc") == ["a", "b", "c"]
    # the cap boundary: exactly 200 is allowed, 201 is refused (None)
    assert router_mod._parse_model_choices(",".join(f"m{i}" for i in range(200))) is not None
    assert router_mod._parse_model_choices(",".join(f"m{i}" for i in range(201))) is None


def _multipart_request(body: bytes, content_type: str):
    from starlette.requests import Request

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/",
        "query_string": b"",
        "headers": [
            (b"content-type", content_type.encode()),
            (b"content-length", str(len(body)).encode()),
        ],
    }
    return Request(scope, receive)


def _multipart_body(boundary: str, parts: list[bytes]) -> bytes:
    return b"".join(
        [f"--{boundary}\r\n".encode() + part for part in parts]
        + [f"--{boundary}--\r\n".encode()]
    )


def test_review_upload_envelope_headroom_accepts_max_files() -> None:
    """The supported SIMULTANEOUS maximum files (exact 8 MiB bundle +
    32 MiB baseline) plus finite multipart overhead fit the finite
    envelope cap (the old cap left ZERO overhead and rejected them)."""
    boundary = "----slaif217resume"
    bundle = b"x" * MAX_BUNDLE_BYTES
    baseline = b"y" * MAX_BASELINE_BYTES
    parts = [
        b'Content-Disposition: form-data; name="csrf_token"\r\n\r\ntok\r\n',
        (
            b'Content-Disposition: form-data; name="bundle"; filename="bundle.json"\r\n'
            b"Content-Type: application/json\r\n\r\n" + bundle + b"\r\n"
        ),
        (
            b'Content-Disposition: form-data; name="baseline"; filename="baseline.json"\r\n'
            b"Content-Type: application/json\r\n\r\n" + baseline + b"\r\n"
        ),
    ]
    request = _multipart_request(
        _multipart_body(boundary, parts), f"multipart/form-data; boundary={boundary}"
    )
    form, files = asyncio.run(
        router_mod._bounded_multipart(
            request,
            cap_bytes=router_mod._REVIEW_UPLOAD_CAP,
            max_files=2,
            max_fields=16,
        )
    )
    assert form.get("csrf_token") == "tok"
    assert files["bundle"] == bundle
    assert files["baseline"] == baseline


def test_review_upload_envelope_overflow_refused() -> None:
    """Beyond the finite envelope (per-file caps + headroom) the total
    byte cap refuses BEFORE unbounded allocation."""
    boundary = "----slaif217resume"
    bundle = b"x" * MAX_BUNDLE_BYTES
    baseline = b"y" * MAX_BASELINE_BYTES
    # padding field pushes the total past cap (envelope headroom is 1 MiB)
    padding = b"p" * (router_mod._REVIEW_UPLOAD_HEADROOM_BYTES + 1)
    parts = [
        b'Content-Disposition: form-data; name="csrf_token"\r\n\r\ntok\r\n',
        (
            b'Content-Disposition: form-data; name="bundle"; filename="bundle.json"\r\n'
            b"Content-Type: application/json\r\n\r\n" + bundle + b"\r\n"
        ),
        (
            b'Content-Disposition: form-data; name="baseline"; filename="baseline.json"\r\n'
            b"Content-Type: application/json\r\n\r\n" + baseline + b"\r\n"
        ),
        b'Content-Disposition: form-data; name="padding"\r\n\r\n' + padding + b"\r\n",
    ]
    request = _multipart_request(
        _multipart_body(boundary, parts), f"multipart/form-data; boundary={boundary}"
    )
    with pytest.raises(router_mod._UploadTooLarge):
        asyncio.run(
            router_mod._bounded_multipart(
                request,
                cap_bytes=router_mod._REVIEW_UPLOAD_CAP,
                max_files=2,
                max_fields=16,
            )
        )


def test_collect_multipart_ignores_unselected_optional_file() -> None:
    """A real browser form with an UNSELECTED optional file input submits the
    native no-file sentinel File(filename="", size=0). The bounded parser must
    ignore ONLY that sentinel, so a bootstrap collect sees NO baseline (a pure
    urlencoded form could never hide this broken browser flow)."""
    boundary = "----slaif217sentinel"
    parts = [
        b'Content-Disposition: form-data; name="csrf_token"\r\n\r\ntok\r\n',
        b'Content-Disposition: form-data; name="mode"\r\n\r\nbootstrap\r\n',
        b'Content-Disposition: form-data; name="providers"\r\n\r\nopenai\r\n',
        # unselected optional baseline: filename="" and a ZERO-byte payload
        # (headers CRLF CRLF, empty payload, then the payload-terminator CRLF)
        (
            b'Content-Disposition: form-data; name="baseline"; filename=""\r\n'
            b"Content-Type: application/octet-stream\r\n\r\n"
            b"\r\n"
        ),
    ]
    request = _multipart_request(
        _multipart_body(boundary, parts), f"multipart/form-data; boundary={boundary}"
    )
    form, files = asyncio.run(
        router_mod._bounded_multipart(
            request,
            cap_bytes=router_mod._REVIEW_UPLOAD_CAP,
            max_files=4,
            max_fields=16,
        )
    )
    assert form.get("csrf_token") == "tok"
    assert form.get("mode") == "bootstrap"
    # the empty optional-file sentinel is ignored -> no baseline key at all
    assert "baseline" not in files


def test_multipart_preserves_named_empty_file() -> None:
    """A NAMED zero-byte file is NOT the no-file sentinel: it is preserved so
    downstream strict validation can refuse it (not silently dropped)."""
    boundary = "----slaif217named"
    parts = [
        (
            b'Content-Disposition: form-data; name="baseline"; filename="empty.json"\r\n'
            b"Content-Type: application/json\r\n\r\n"
            b"\r\n"
        ),
    ]
    request = _multipart_request(
        _multipart_body(boundary, parts), f"multipart/form-data; boundary={boundary}"
    )
    _form, files = asyncio.run(
        router_mod._bounded_multipart(
            request,
            cap_bytes=router_mod._REVIEW_UPLOAD_CAP,
            max_files=4,
            max_fields=16,
        )
    )
    assert files.get("baseline") == b""


def _plain_request(headers: list[tuple[bytes, bytes]]):
    from starlette.requests import Request

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/",
        "query_string": b"",
        "headers": list(headers),
    }
    return Request(scope, receive)


def test_secret_form_and_upload_refusal_pure(monkeypatch) -> None:
    """The same pure known-incoming-secret / credential-shaped guards
    refuse secret-bearing values BEFORE custody persistence: opaque
    incoming aliases (bearer/cookie) and credential-shaped content in
    uploads, fail closed; clean content passes."""
    settings = _settings(_NS(root=Path("/tmp/never"), key=Path("/tmp/never")))
    monkeypatch.setattr(router_mod, "_settings", lambda request: settings)
    canary = "SLAIF217-INCOMING-CANARY-9f31"
    request = _plain_request(
        [
            (b"authorization", f"Bearer {canary}".encode()),
            (b"cookie", b"sessionid=abc123"),
        ]
    )
    # opaque incoming alias in a form value
    assert router_mod._known_alias(request, canary) is True
    assert router_mod._secret_form_refusal(request, [canary]) is True
    assert router_mod._secret_form_refusal(request, ["plain operator text"]) is False
    # opaque alias embedded in upload bytes
    assert (
        router_mod._secret_upload_refusal(request, f'{{"note": "leak {canary}"}}'.encode())
        is True
    )
    # credential-shaped (gateway-key prefix) content in upload bytes
    shaped = b'{"route": {"upstream_key": "sk-slaif-0123456789abcdef0123456789abcdef"}}'
    assert router_mod._secret_upload_refusal(request, shaped) is True
    # clean content passes
    assert router_mod._secret_upload_refusal(request, b'{"providers": []}') is False
    # a cookie value alias in a form value
    assert router_mod._known_alias(request, "sessionid=abc123") is True


def test_list_runs_reads_top_level_state(custody_root) -> None:
    """The sealed ValidationReport document carries the review state at
    the TOP level (report.to_dict): list_runs must read it there (the old
    code read document.result.state, so every sealed run rendered
    unreadable)."""
    settings = _settings(custody_root)
    custody.inspect_custody_setup(settings)
    run_dir = custody_root.root / "runs" / "collect-20261110-000000-deadbeef"
    run_dir.mkdir(mode=0o700)
    (run_dir / "validation.json").write_text(
        json.dumps({"state": "READY", "generated_at": "2026-11-10T00:00:00Z"})
    )
    rows = custody.list_runs(settings, limit=100)
    assert len(rows) == 1
    assert rows[0]["state"] == "READY"
    assert rows[0]["generated_at"] == "2026-11-10T00:00:00Z"
    assert rows[0]["readable"] is True


def test_remove_terminal_job_cleans_job_artifacts(custody_root) -> None:
    """Terminal job cleanup removes the record AND the job's OWN
    generated upload/proposal subtrees (the old cleanup deleted only the
    JSON, silently retaining the bytes)."""
    settings = _settings(custody_root)
    custody.inspect_custody_setup(settings)
    job_id = custody.create_job(settings, "collect", {"mode": "bootstrap"})
    custody.store_upload(settings, job_id, "baseline", b"b" * 64)
    outdir = custody.open_proposal_dir(settings, job_id)
    (outdir / "nested").mkdir()
    (outdir / "nested" / "pkg").mkdir()
    (outdir / "nested" / "pkg" / "routes-proposal.tsv").write_text("a\tb\n")
    (outdir / "routes-proposal.tsv").write_text("a\tb\n")
    custody.finish_job(settings, job_id, "ready")
    custody.remove_terminal_job(settings, job_id)
    # record gone, both owned subtrees gone
    assert all(row["job_id"] != job_id for row in custody.list_jobs(settings))
    assert not (custody_root.root / "uploads" / job_id).exists()
    assert not (custody_root.root / "proposals" / job_id).exists()


def test_remove_terminal_job_refuses_nonterminal_untouched(custody_root) -> None:
    """A still-queued job refuses cleanup BEFORE any artifact is removed
    (record and both subtrees stay exactly as they were)."""
    settings = _settings(custody_root)
    custody.inspect_custody_setup(settings)
    job_id = custody.create_job(settings, "collect", {"mode": "bootstrap"})
    custody.store_upload(settings, job_id, "baseline", b"b" * 64)
    custody.open_proposal_dir(settings, job_id)
    with pytest.raises(custody.CustodyJobError) as exc:
        custody.remove_terminal_job(settings, job_id)
    assert exc.value.code == "job_cleanup_refused"
    record = _read_record(settings, job_id)
    assert record["status"] == "queued"
    assert any((custody_root.root / "uploads" / job_id).iterdir())
    assert (custody_root.root / "proposals" / job_id).exists()


# --- generated package usability (closed known presets) ----------------------


def _seed_package(settings: Settings, job_id: str, preset: str, **files: bytes) -> Path:
    outdir = custody.open_proposal_dir(settings, job_id)
    pkg = outdir / "packages" / preset
    pkg.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (pkg / name).write_bytes(content)
    return pkg


def test_list_proposal_packages_closed_known_presets_only(custody_root) -> None:
    """Listing is the CLOSED known-preset enumeration: only generated
    OPENROUTER_PACKAGE_ORDER directories appear (in preset order), a
    rogue directory outside the closed set is never reported, and a
    SYMLINKED preset is refused by the no-follow component open."""
    order = custody.OPENROUTER_PACKAGE_ORDER
    settings = _settings(custody_root)
    custody.inspect_custody_setup(settings)
    job_id = custody.create_job(settings, "proposal", {"provider_scope": "openrouter"})
    outdir = custody.open_proposal_dir(settings, job_id)
    # generate two closed presets (first and last of the closed order)
    _seed_package(settings, job_id, order[0], **{"routes-proposal.tsv": b"a\tb\n"})
    _seed_package(settings, job_id, order[-1], **{"package-manifest.json": b"{}\n"})
    # a rogue preset OUTSIDE the closed set + a symlinked preset
    (outdir / "packages" / "rogue-preset").mkdir()
    target = custody_root.root / "symlink-target"
    target.mkdir()
    os.symlink(target, outdir / "packages" / order[1])
    listed = custody.list_proposal_packages(settings, job_id)
    assert listed == [order[0], order[-1]]
    # no job directory at all -> empty (no error)
    missing = custody.list_proposal_packages(settings, "0" * 32)
    assert missing == []
    # malformed job ids refuse
    with pytest.raises(custody.CustodyJobError) as exc:
        custody.list_proposal_packages(settings, "../jobs")
    assert exc.value.code == "job_unknown"


def test_read_proposal_package_artifact_closed_set_and_bounds(custody_root) -> None:
    """Package reads accept ONLY the closed preset + closed file set
    through the held anchored handles; unknown presets/files and
    traversal-shaped names refuse; the cap is the enforced 32 MiB
    proposal output ceiling."""
    order = custody.OPENROUTER_PACKAGE_ORDER
    settings = _settings(custody_root)
    custody.inspect_custody_setup(settings)
    job_id = custody.create_job(settings, "proposal", {"provider_scope": "openrouter"})
    payload = b"requested_model\tsynth/alpha\n"
    _seed_package(settings, job_id, order[0], **{"routes-proposal.tsv": payload})
    content = custody.read_proposal_package_artifact(
        settings, job_id, order[0], "routes-proposal.tsv"
    )
    assert content == payload
    # closed-set refusals (no filesystem walk needed - the name is refused)
    for preset, name in (
        ("rogue-preset", "routes-proposal.tsv"),
        (order[0], "rogue.txt"),
        (order[0], "../routes-proposal.tsv"),
        (order[0], "packages/routes-proposal.tsv"),
    ):
        with pytest.raises(custody.CustodyJobError) as exc:
            custody.read_proposal_package_artifact(settings, job_id, preset, name)
        assert exc.value.code == "artifact_not_served"
    # missing file inside a generated package -> None (not an error)
    assert (
        custody.read_proposal_package_artifact(
            settings, job_id, order[0], "package-report.md"
        )
        is None
    )
    # cap is the 32 MiB enforced proposal ceiling, not the 8 MiB bundle cap:
    # a 9 MiB root artifact is served...
    MiB = 1024 * 1024
    outdir = custody.open_proposal_dir(settings, job_id)
    _fill(outdir / "provider-catalog-report.md", 9 * MiB)
    big = custody.read_proposal_artifact(settings, job_id, "provider-catalog-report.md")
    assert big is not None and len(big) == 9 * MiB
    # ...and a 33 MiB package file is refused at the ceiling
    _seed_package(
        settings, job_id, order[0], **{"model-review.md": b"x" * (33 * MiB)}
    )
    assert (
        custody.read_proposal_package_artifact(settings, job_id, order[0], "model-review.md")
        is None
    )


# --- 11. job-result binding (exact-id, no latest substitution) ----------------


def _fake_request(job: str | None) -> _NS:
    """Query-param surface the API binding helpers consume."""
    return _NS(query_params={} if job is None else {"job": job})


def test_bound_job_exact_id_and_refusals(custody_root) -> None:
    settings = _settings(custody_root, CATALOG_REFRESH_MAX_ACTIVE_JOBS=4)
    job_a = custody.create_job(settings, "collect", {"mode": "bootstrap"})
    job_b = custody.create_job(settings, "proposal", {"provider_scope": "openrouter"})
    # exact id, correct family -> the exact safe projection
    job = router_mod._bound_job(settings, job_a, "collect")
    assert job is not None and job["job_id"] == job_a and job["family"] == "collect"
    assert "params" not in job  # projection never leaks raw params
    # foreign family is refused, never substituted (both directions)
    assert router_mod._bound_job(settings, job_a, "proposal") is None
    assert router_mod._bound_job(settings, job_b, "collect") is None
    # unknown / malformed / non-hex / path-bearing ids all resolve to None
    for bad in ("f" * 32, job_a.upper(), job_a[:16], f"/{job_a}", "g" * 32, None, ""):
        assert router_mod._bound_job(settings, bad, "collect") is None
    assert router_mod._bound_job(settings, None, "collect") is None


def test_resolve_bound_view_three_states(custody_root) -> None:
    settings = _settings(custody_root, CATALOG_REFRESH_MAX_ACTIVE_JOBS=4)
    job_a = custody.create_job(settings, "collect", {"mode": "bootstrap"})
    job_b = custody.create_job(settings, "collect", {"mode": "refresh"})
    jobs = custody.list_jobs(settings)
    assert [j["job_id"] for j in jobs] == [job_b, job_a]  # newest first
    # ABSENT (or empty) param -> latest-global view (the NEWEST job)
    for request in (_fake_request(None), _fake_request("")):
        last, refusal = router_mod._resolve_bound_view(request, settings, "collect", jobs)
        assert last is not None and last["job_id"] == job_b
        assert refusal is None
    # EXPLICIT bound id -> the EXACT job even though it is not the newest
    last, refusal = router_mod._resolve_bound_view(_fake_request(job_a), settings, "collect", jobs)
    assert last is not None and last["job_id"] == job_a and refusal is None
    # EXPLICIT unknown / invalid / foreign-family ids -> refusal, and the
    # newest job is NEVER substituted for them
    for bad in ("f" * 32, "z" * 32, job_a[:20], job_b.upper()):
        last, refusal = router_mod._resolve_bound_view(_fake_request(bad), settings, "collect", jobs)
        assert last is None and refusal
        assert "unknown" in refusal
    # foreign family for an existing valid id -> refusal
    last, refusal = router_mod._resolve_bound_view(_fake_request(job_b), settings, "review_supplied", jobs)
    assert last is None and refusal
    # deleted terminal job -> refusal (cleanup can never resurrect a view)
    custody.finish_job(settings, job_b, "failed", error_code="probe")
    custody.remove_terminal_job(settings, job_b)
    last, refusal = router_mod._resolve_bound_view(_fake_request(job_b), settings, "collect", jobs)
    assert last is None and refusal


def test_job_provider_scope_closed_access(custody_root) -> None:
    settings = _settings(custody_root, CATALOG_REFRESH_MAX_ACTIVE_JOBS=4)
    job_p = custody.create_job(settings, "proposal", {"provider_scope": "openrouter"})
    job_c = custody.create_job(settings, "collect", {"provider_scope": "openrouter"})
    assert custody.job_provider_scope(settings, job_p) == "openrouter"
    # non-proposal families and malformed ids never echo a scope
    assert custody.job_provider_scope(settings, job_c) is None
    assert custody.job_provider_scope(settings, "f" * 32) is None
    assert custody.job_provider_scope(settings, job_p.upper()) is None
    # values outside the closed scope vocabulary are withheld
    job_bad = custody.create_job(settings, "proposal", {"provider_scope": "anthropic"})
    assert custody.job_provider_scope(settings, job_bad) is None
