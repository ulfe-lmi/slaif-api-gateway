"""217-a: disposable application Celery worker driver (queued smoke).

Runs the REAL application Celery worker in this process:

- real task registration (``slaif_gateway.catalog_refresh.execute_job``);
- real broker consumption from the owned Redis (IDS-only payload);
- real ``_execute_job`` -> real custody lifecycle -> real Core
  composition, sealing, and publication.

Labeled synthetic seams (identical to the focused unit suite - the ONLY
synthetic parts): the collect client factory returns a synthetic
OFFICIAL-source ``World()`` MockTransport client and the default public
resolver bindings are re-pointed to a synthetic answer.
The proposal transport is re-pointed (``worker.VettedHTTPTransport``) to
a synthetic OFFICIAL-source sync MockTransport, exactly as the accepted
default-factory unit seam: the REAL ``_build_proposal_client`` factory
composes the production fixed registry guard, the sync-to-async bounded
bridge, checkpoint and body budgets, and the real ``_run_proposal``
generation/custody composition - only the source BYTES are synthetic,
never physical upstream network.

Network gate (test-only assembly, no production policy relaxation): the
driver allows ONLY the exact fixture-owned numeric loopback host+port
targets derived from the controlled broker (``REDIS_URL``) and database
(``DATABASE_URL``) URLs - the real owned Redis broker and the real owned
PostgreSQL export. Every other DNS answer or socket endpoint is a hard
failure. The effective Celery broker is asserted to be EXACTLY the
owned Redis before the worker starts, and the result backend must stay
unset (result-backend-optional behavior is preserved). No physical
upstream network, no ambient broker, no eager execution.
"""

from __future__ import annotations

import ipaddress
import os
import socket
import sys
from pathlib import Path
from urllib.parse import urlparse

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _owned_loopback_targets() -> dict[tuple[str, int], str]:
    """The EXACT fixture-owned loopback targets derived from the
    controlled URLs. Anything not in this map may never be reached."""
    allowed: dict[tuple[str, int], str] = {}
    for label, url in (
        ("broker", os.environ.get("REDIS_URL", "")),
        ("database", os.environ.get("DATABASE_URL", "")),
    ):
        if not url:
            raise SystemExit(f"driver: {label} URL is not configured (test-only gate)")
        parsed = urlparse(url)
        host = parsed.hostname or ""
        port = parsed.port
        if not host or not port:
            raise SystemExit(f"driver: {label} URL lacks an explicit host:port")
        try:
            is_loopback = ipaddress.ip_address(host) == ipaddress.ip_address("127.0.0.1")
        except ValueError:
            is_loopback = False
        if not is_loopback:
            raise SystemExit(f"driver: {label} URL is not loopback-bound (test-only gate)")
        allowed[(host, int(port))] = label
    return allowed


_ALLOWED_TARGETS = _owned_loopback_targets()
if not _ALLOWED_TARGETS:
    raise SystemExit("driver: no owned loopback targets configured (test-only gate)")

_original_getaddrinfo = socket.getaddrinfo
_original_connect = socket.socket.connect
_original_connect_ex = socket.socket.connect_ex


def _endpoint_allowed(address: object) -> bool:
    if isinstance(address, tuple) and address and isinstance(address[0], str) and len(address) >= 2:
        return (address[0], int(address[1])) in _ALLOWED_TARGETS
    return False


def _guarded_getaddrinfo(host, port, *args, **kwargs):
    # The owned targets are numeric loopback: no DNS is ever needed for
    # them. Every other host/port fails closed BEFORE any resolver call.
    if not (isinstance(host, str) and isinstance(port, int) and (host, port) in _ALLOWED_TARGETS):
        raise AssertionError(f"queued smoke reached an unmapped network endpoint: {host}:{port}")
    return _original_getaddrinfo(host, port, *args, **kwargs)


def _guarded_connect(self, address):  # noqa: ANN001 - socket API signature
    if not _endpoint_allowed(address):
        raise AssertionError(f"queued smoke reached an unmapped socket endpoint: {address!r}")
    return _original_connect(self, address)


def _guarded_connect_ex(self, address):  # noqa: ANN001 - socket API signature
    if not _endpoint_allowed(address):
        raise AssertionError(f"queued smoke reached an unmapped socket endpoint: {address!r}")
    return _original_connect_ex(self, address)


def _synthetic_public_resolver(host: str, port: int, proto: int | None = None) -> list:
    """Synthetic public answer for the official registry hosts ONLY; any
    other host fails closed (no default DNS in this test)."""
    if host in ("openrouter.ai", "developers.openai.com", "www.ecb.europa.eu"):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", 443))
        ]
    raise OSError(f"no synthetic answer for {host}")


def main() -> int:
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))

    socket.getaddrinfo = _guarded_getaddrinfo
    socket.socket.connect = _guarded_connect
    socket.socket.connect_ex = _guarded_connect_ex

    # 219-a test-only seam: the installed worker venv deliberately has no
    # pytest. The synthetic ``World`` fixture is imported FROM SOURCE (test
    # fixtures may be source; product imports stay installed) and needs only
    # pytest's IMPORT-time decorator surface (fixture/parametrize). Provide
    # that minimal stub ONLY when the real pytest is absent; no test runs in
    # this process and no product behavior changes.
    try:
        import pytest  # noqa: F401
    except ModuleNotFoundError:
        import types

        def _decorator_identity(*args, **kwargs):
            if len(args) == 1 and callable(args[0]) and not kwargs:
                return args[0]

            def _keep(func):
                return func

            return _keep

        _pytest_stub = types.ModuleType("pytest")
        _pytest_stub.fixture = _decorator_identity
        _pytest_stub.mark = types.SimpleNamespace(parametrize=_decorator_identity)
        sys.modules["pytest"] = _pytest_stub

    from tests.unit.test_catalog_refresh_collection import World
    from slaif_gateway.services.catalog_refresh import collection as coll
    from slaif_gateway.services.catalog_refresh import sources as src
    from slaif_gateway.workers import tasks_catalog_refresh as worker
    from slaif_gateway.workers.celery_app import create_celery_app

    # 219-a test-only seam (env-gated, driver-level, no product behavior
    # change): report where the PRODUCT imports actually resolve so the
    # installed workflow can prove API+worker origins are the installed
    # wheel, not the source checkout.
    _origin_report = os.environ.get("SLAIF219_WORKER_ORIGIN_REPORT", "").strip()
    if _origin_report:
        import json as _json
        import slaif_gateway as _sl
        Path(_origin_report).write_text(
            _json.dumps(
                {
                    "package": _sl.__file__,
                    "worker_module": worker.__file__,
                }
            )
        )

    world = World()
    worker._collect_client_factory = lambda: world.client()

    # 219-a test-only seam (env-gated, no product behavior change): the
    # product task wrapper classifies unhandled execution exceptions as the
    # fixed ``internal_error`` code and never logs raw text. When the
    # workflow parent sets SLAIF219_WORKER_ERROR_REPORT, record the
    # exception class/message/traceback of the collect/export execution to
    # that file for failure diagnosis (the parent owns the file; nothing
    # is printed to the worker stdout).
    _error_report = os.environ.get("SLAIF219_WORKER_ERROR_REPORT", "").strip()
    if _error_report:
        import traceback as _traceback

        def _report_execution_error(stage: str, exc: BaseException) -> None:
            try:
                with open(_error_report, "a", encoding="utf-8") as _fh:
                    _fh.write(f"STAGE={stage} {type(exc).__name__}: {exc}\n")
                    _fh.write("".join(_traceback.format_exception(exc))[:8000])
                    _fh.write("\n")
            except Exception:  # noqa: BLE001 - diagnostics never mask the fault
                pass

        _orig_run_collect = worker._run_collect

        async def _run_collect_reported(*args, **kwargs):
            try:
                return await _orig_run_collect(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001 - record, then re-raise
                _report_execution_error("collect", exc)
                raise

        worker._run_collect = _run_collect_reported

        _orig_run_export = worker._run_export

        async def _run_export_reported(*args, **kwargs):
            try:
                return await _orig_run_export(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001 - record, then re-raise
                _report_execution_error("export", exc)
                raise

        worker._run_export = _run_export_reported

    # Labeled synthetic proposal transport seam (queued proposal job):
    # only the transport is replaced; the real factory/registry/bridge
    # run unchanged. The payload row shape is the SAME official
    # models-API fixture the collect World uses.
    import httpx

    _OR_DOCS_URL = "https://openrouter.ai/docs/guides/overview/models.md"
    _OR_API_URL = "https://openrouter.ai/api/v1/models"

    def _proposal_sync_handler(request: "httpx.Request") -> "httpx.Response":
        url = str(request.url)
        if url == _OR_API_URL:
            return httpx.Response(200, json={"data": world.or_rows[:3]})
        if url == _OR_DOCS_URL:
            return httpx.Response(
                200,
                text="All pricing values are in USD per token/request/unit.\n",
            )
        return httpx.Response(404, text="not found")

    worker.VettedHTTPTransport = lambda: httpx.MockTransport(_proposal_sync_handler)

    for fn in (src.fetch_source, src.fetch_sources, coll.collect_bundle):
        kwdefaults = dict(getattr(fn, "__kwdefaults__", None) or {})
        if "resolve" in kwdefaults:
            kwdefaults["resolve"] = _synthetic_public_resolver
            fn.__kwdefaults__ = kwdefaults

    app = create_celery_app()
    # Assert the effective broker is EXACTLY the owned Redis before the
    # worker starts (inherited CELERY_BROKER_URL/result backend are
    # sanitized by the spawner; never print credentials - compare and
    # fail closed on mismatch).
    expected_broker = os.environ["REDIS_URL"]
    if app.conf.broker_url != expected_broker:
        raise SystemExit("driver: effective Celery broker is not the exact owned Redis")
    if app.conf.result_backend:
        raise SystemExit("driver: the result backend must stay unset (optional behavior)")

    # 219-a test-only seam: readiness line BEFORE the blocking worker loop
    # so an installed-workflow parent can drain it and then wait on the
    # sealed job results (the 217 flow polls custody and needs no line).
    print("WORKER_READY", flush=True)

    app.worker_main(
        [
            "worker",
            "--pool=solo",
            "--concurrency=1",
            "--loglevel=error",
            "--without-heartbeat",
            "--without-mingle",
            "--without-gossip",
        ]
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
