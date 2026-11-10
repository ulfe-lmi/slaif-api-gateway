"""Celery tasks for the admin GUI catalog-refresh bridge (217-a / G15).

ONE closed task family with an IDs-only broker payload: the single task
accepts exactly one custody job id; the job's sealed parameters live in
the operator custody record, never in the broker payload. Every family is
READ-ONLY; the mutating apply is composed directly by the web layer under
fresh HTTP authentication (reusing the Core one-transaction apply and its
durable outcome record) and is never a queued job.

Cancellation is cooperative at the shared application's phase
checkpoints (pre-baseline, pre-collect, per retrieval phase, pre-staging,
and immediately before the NEW-ONLY publication) plus a bounded
read-only time budget. An in-flight library operation may finish before
cancellation is observed: the custody record then shows the truthful
terminal state of the work that actually ran, and the pre-publication
gate ensures a canceled job never publishes ready output after the
cancellation was observed at the final checkpoint.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import httpx
import structlog

from slaif_gateway.config import Settings, get_settings
from slaif_gateway.services.admin_catalog_refresh import (
    CATALOG_JOB_FAMILIES,
    AdminCatalogRefreshError,
    CustodyCapacityError,
    CustodyJobError,
    _PROPOSAL_RESERVATION_BYTES,
    account_proposal_output,
    begin_job,
    cancel_check,
    finish_job,
    inspect_custody_setup,
    job_cancel_requested,
    open_proposal_dir,
    remove_proposal_dir,
    store_upload,
    upload_exists as custody_upload_exists,
)
from slaif_gateway.services.catalog_refresh.application import (
    PROFILE_STANDARD_V1,
    ApplicationDataError,
    ApplicationUsageError,
    CollectionCanceled,
    ReviewOutcome,
    check_key_containment,
    export_baseline_document,
    run_collect,
    run_review,
)
from slaif_gateway.services.catalog_refresh.baseline import MAX_BASELINE_BYTES
from slaif_gateway.services.catalog_refresh.filesystem import open_anchored_handle
from slaif_gateway.services.catalog_refresh.research import ResearchConfig
from slaif_gateway.services.catalog_refresh.source_transport import VettedHTTPTransport
from slaif_gateway.services.provider_catalog_proposal import (
    ProviderCatalogProposalSizeError,
    generate_provider_catalog_proposal,
)
from slaif_gateway.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)

_GENERATED_UPLOAD_NAME_RE = re.compile(r"^(bundle|baseline)-[0-9a-f]{32}$")
_JOB_ID_RE = re.compile(r"^[0-9a-f]{32}$")

# New GUI proposal network boundary: the EXISTING vetted transport
# (verified HTTPS, fixed official destinations enforced by the proposal
# service itself), redirect-following refused for this new surface,
# finite pool/timeout bounds. No new transport or resolver engine.
_PROPOSAL_HTTP_TIMEOUT = httpx.Timeout(120.0, connect=15.0)
_PROPOSAL_HTTP_LIMITS = httpx.Limits(
    max_connections=8, max_keepalive_connections=4
)
_PROPOSAL_MAX_MODELS = 500
_PROPOSAL_FETCH_DETAILS_LIMIT = 200
_PROPOSAL_MAX_WEB_CALLS = 10


# --- NEW GUI proposal network boundary --------------------------------------
# Fixed official host/path families for the EXISTING proposal service's
# fixed official destinations (an exact registry for this new surface; the
# service's own domain-suffix guard remains as defense in depth).
_OFFICIAL_HOST_PATH_FAMILIES: dict[str, tuple[str, ...]] = {
    "openrouter.ai": ("/api/v1/models", "/docs/"),
    # /v1/responses is the EXACT fixed endpoint of the operator-acknowledged
    # OpenAI-assisted catalog seam (openai_assisted_catalog posts it with the
    # SAME bridge client); it is gated upstream by the deployment-secret +
    # acknowledge-assisted-proposal-risk checks. No general passthrough.
    "api.openai.com": ("/v1/models", "/v1/responses"),
    "developers.openai.com": ("/api/docs/"),
}
# OpenRouter model-detail documents: the EXACT pinned service URL the
# proposal service derives from the official models payload's
# ``links.details`` (never browser/model-selected): the models LIST
# endpoint plus /api/v1/models/<vendor>/<model>/endpoints detail
# documents on the official host. No other /models/... passthrough.
_OPENROUTER_DETAIL_PATH_RE = re.compile(
    r"^/api/v1/models/[a-z0-9._~:-]+(?:/[a-z0-9._~:-]+){1,2}/endpoints$"
)
# Streamed bounds for one proposal job's bodies (finite, documented):
# per-body 16 MiB (the official models payload is a few MiB at most),
# aggregate 64 MiB across the whole job.
_PROPOSAL_MAX_BODY_BYTES = 16 * 1024 * 1024
_PROPOSAL_MAX_TOTAL_BYTES = 64 * 1024 * 1024


def _official_destination_allowed(url: str) -> bool:
    """Exact fixed host/path-family registry check for one request URL.
    Userinfo, query strings, fragments, non-443 ports, and non-https
    schemes are all refused - the service's own official URLs carry none
    of them, and a new browser-facing surface accepts none."""
    parsed = urlparse(url)
    if parsed.scheme != "https":
        return False
    if parsed.port not in (None, 443):
        return False
    if parsed.username is not None or parsed.password is not None:
        return False
    if parsed.query or parsed.fragment:
        return False
    host = (parsed.hostname or "").lower()
    families = _OFFICIAL_HOST_PATH_FAMILIES.get(host)
    if not families:
        return False
    path = parsed.path or "/"
    if not path.startswith("/") or "//" in path:
        return False
    # Raw dot segments (e.g. /models/x/../../etc/passwd) are refused
    # BEFORE any URL normalization can turn them into another family.
    if "/../" in path or path.endswith("/..") or "/./" in path or path.endswith("/."):
        return False
    for family in families:
        if family.endswith("/"):
            if path.startswith(family):
                return True
        elif path == family:
            return True
    if host == "openrouter.ai" and _OPENROUTER_DETAIL_PATH_RE.fullmatch(path):
        return True
    return False


class _ProposalBodyBudget:
    """Finite aggregate byte budget for ONE proposal job's source bodies.

    Every RETURNED raw chunk is debited during the bounded sync read -
    BEFORE any per-body/aggregate failure decision, and including
    overflow/failed captures (they were acquired from the network and
    are never refunded). A NEW acquisition is refused once the bound is
    FULLY SPENT (spent >= cap), so a request that would end exactly at
    the cap is never even sent; AFTER a debit, a body ending exactly at
    the cap remains allowed (overflow is spent > cap). Reused across all
    requests of the job's client."""

    def __init__(self, cap: int) -> None:
        self.cap = int(cap)
        self.spent = 0

    def debit(self, n: int) -> None:
        self.spent += int(n)

    def pre_acquisition_refused(self) -> bool:
        """Refuse a NEW acquisition once the bound is fully spent."""
        return self.spent >= self.cap

    def exhausted(self) -> bool:
        """Post-debit overflow: a body ending exactly at the cap is allowed."""
        return self.spent > self.cap


class _BoundedAsyncVettedTransport(httpx.AsyncBaseTransport):
    """THIN async bridge over the EXISTING vetted synchronous transport
    (the sync client executes in a worker thread - no new DNS/TLS
    resolver engine; certificate verification is exactly the vetted
    transport's). Every request is checked against the fixed official
    host/path family BEFORE any network contact; redirects are refused
    by the client; bodies stream under per-body/aggregate bounds."""

    def __init__(
        self,
        sync_client: httpx.Client,
        checkpoint: Callable[[], bool] | None = None,
    ) -> None:
        self._client = sync_client
        self._budget = _ProposalBodyBudget(_PROPOSAL_MAX_TOTAL_BYTES)
        # Optional cooperative job checkpoint (the job's _Checkpoint):
        # consulted between acquisitions and between returned raw chunks
        # so a long source loop never ignores a cancel/deadline. No
        # custom DNS/deadline engine - the existing job checkpoint,
        # passed through the factory seam.
        self.checkpoint = checkpoint

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if not _official_destination_allowed(str(request.url)):
            # Per-request refusal: the job's client stays usable for its
            # remaining requests and is closed by the job's own finally.
            raise ValueError(
                "destination is outside the fixed official source set"
            )
        # Identity-only bodies: force the request encoding and REJECT a
        # non-identity response encoding BEFORE any decoding.
        request.headers["Accept-Encoding"] = "identity"

        def _send_and_read() -> tuple[int, list[tuple[bytes, bytes]], bytes]:
            """One network round-trip in a worker thread.

            Every returned raw chunk is debited against the job's
            AGGREGATE budget WHILE the body is read - before any
            per-body/aggregate failure decision; overflow and failed
            captures are never refunded. A new acquisition is refused
            once the budget is exhausted. Allocation stays bounded for
            both buffered and streamed sync transports, the sync
            response is always closed, and the identity encoding is
            verified before the body is captured."""
            if self._budget.pre_acquisition_refused():
                raise ValueError(
                    "proposal job bodies exhausted their aggregate bound"
                )
            if self.checkpoint is not None and self.checkpoint():
                raise CollectionCanceled(
                    "proposal checkpoint reached: cancellation requested "
                    "or the bounded read-only time budget was used up"
                )
            sync_response = self._client.send(request, stream=True)
            try:
                encoding = (
                    sync_response.headers.get("content-encoding") or ""
                ).lower().strip()
                if encoding and encoding != "identity":
                    raise ValueError(
                        "proposal source response uses a non-identity encoding"
                    )
                if sync_response.is_stream_consumed:
                    # Buffered transport response (content already held).
                    body = sync_response.read()
                    self._budget.debit(len(body))
                    if len(body) > _PROPOSAL_MAX_BODY_BYTES:
                        raise ValueError("proposal source body exceeds its bound")
                    if self._budget.exhausted():
                        raise ValueError(
                            "proposal job bodies exceeded their aggregate bound"
                        )
                    if self.checkpoint is not None and self.checkpoint():
                        raise CollectionCanceled(
                            "proposal checkpoint reached: cancellation "
                            "requested or the bounded read-only time "
                            "budget was used up"
                        )
                else:
                    parts: list[bytes] = []
                    total = 0
                    for chunk in sync_response.iter_raw():
                        total += len(chunk)
                        # Debit each returned raw chunk BEFORE the
                        # per-body/total failure checks (no refunds).
                        self._budget.debit(len(chunk))
                        if total > _PROPOSAL_MAX_BODY_BYTES:
                            raise ValueError("proposal source body exceeds its bound")
                        if self._budget.exhausted():
                            raise ValueError(
                                "proposal job bodies exceeded their aggregate bound"
                            )
                        parts.append(chunk)
                        # Cooperative checkpoint BETWEEN returned raw
                        # chunks (the long source loop seam).
                        if self.checkpoint is not None and self.checkpoint():
                            raise CollectionCanceled(
                                "proposal checkpoint reached: cancellation "
                                "requested or the bounded read-only time "
                                "budget was used up"
                            )
                    body = b"".join(parts)
                return sync_response.status_code, list(sync_response.headers.raw), body
            finally:
                if not sync_response.is_closed:
                    sync_response.close()

        status_code, headers, body = await asyncio.to_thread(_send_and_read)
        # The body was already captured under the bounds, so delivery is
        # a plain buffered response (no second counting layer).
        return httpx.Response(
            status_code,
            headers=headers,
            content=body,
            request=request,
        )

    async def aclose(self) -> None:
        await asyncio.to_thread(self._client.close)


class _RegistryGuardedClient(httpx.AsyncClient):
    """Thin client guard: the RAW url string is validated against the
    fixed official registry BEFORE httpx's dot-segment normalization
    (which could otherwise turn a traversal into another family), then
    the request is delegated. The transport re-checks the normalized
    URL as defense in depth."""

    def request(self, method: str, url: Any, **kwargs: Any) -> httpx.Response:
        if not _official_destination_allowed(str(url)):
            raise ValueError(
                "destination is outside the fixed official source set"
            )
        return super().request(method, url, **kwargs)


def _build_proposal_client(
    *, checkpoint: Callable[[], bool] | None = None
) -> httpx.AsyncClient:
    """The NEW GUI proposal network boundary: bounded async client over
    the EXISTING vetted sync transport, redirects refused, fixed official
    host/path families enforced on raw and normalized URLs. Qualification
    may replace this factory with a synthetic-source client (labeled).
    The optional cooperative job checkpoint is wired into the bounded
    bridge through this seam (never through a client .transport
    attribute - this httpx version exposes no such public attribute)."""
    sync_client = httpx.Client(
        transport=VettedHTTPTransport(),
        follow_redirects=False,
        trust_env=False,
        timeout=httpx.Timeout(60.0, connect=15.0),
        limits=httpx.Limits(max_connections=4, max_keepalive_connections=2),
    )
    try:
        return _RegistryGuardedClient(
            transport=_BoundedAsyncVettedTransport(sync_client, checkpoint=checkpoint),
            follow_redirects=False,
            trust_env=False,
            timeout=_PROPOSAL_HTTP_TIMEOUT,
            limits=_PROPOSAL_HTTP_LIMITS,
        )
    except BaseException:
        # setup failure must not leak the sync client
        sync_client.close()
        raise


def _collect_client_factory() -> httpx.Client | None:
    """Client seam for the collect family.

    The default returns None so the shared application composes the
    production vetted official transport (real fetch_sources /
    getaddrinfo / default acquisition context). Focused qualification may
    replace this factory with a synthetic-official-source client to
    exercise the REAL default composition path - never a fake
    collect_bundle.
    """
    return None


class _Checkpoint:
    """Cooperative cancel + bounded read-only time budget for ONE job.

    ``cancel`` is the live custody re-read (operator flag, terminal
    status, or lost custody -> fail closed). Once the configured
    read-only deadline passes, the checkpoint is truthy; the terminal
    mapping distinguishes ``canceled`` from a ``read_only_timeout``
    failure truthfully.
    """

    def __init__(self, cancel: Callable[[], bool], timeout_seconds: int) -> None:
        self._cancel = cancel
        self._deadline = time.monotonic() + float(max(1, timeout_seconds))
        self.timed_out = False

    def __call__(self) -> bool:
        if self._cancel():
            return True
        if time.monotonic() >= self._deadline:
            self.timed_out = True
            return True
        return False


def _gate(checkpoint: _Checkpoint) -> None:
    """Phase checkpoint: interrupted work raises the shared canceled
    classification (timeout vs cancel is resolved truthfully at finish)."""
    if checkpoint():
        raise CollectionCanceled(
            "read-only checkpoint reached: cancellation requested or the "
            "bounded read-only time budget was used up"
        )


def _interrupted_terminal(
    settings: Settings, job_id: str, checkpoint: _Checkpoint
) -> tuple[str, str]:
    """Truthful (status, error_code) for checkpoint-interrupted work:
    operator cancellation -> ``canceled``; time budget -> ``failed`` +
    ``read_only_timeout``; custody lost/terminal elsewhere -> ``failed``
    + ``custody_unavailable`` (never a success claim)."""
    if job_cancel_requested(settings, job_id):
        return "canceled", "cancel_requested"
    if checkpoint.timed_out:
        return "failed", "read_only_timeout"
    return "failed", "custody_unavailable"


def _require_ready(settings: Settings):
    setup = inspect_custody_setup(settings)
    if setup.state != "ready" or setup.root is None or setup.seal_key is None:
        raise AdminCatalogRefreshError(
            setup.code, "catalog refresh custody is not usable: " + setup.code
        )
    return setup


def _str_list(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    out: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip() and item not in out:
            out.append(item)
    return tuple(out)


def _int_param(value: Any, default: int, low: int, high: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise ApplicationUsageError("param_invalid", "integer parameter expected")
    if not low <= value <= high:
        raise ApplicationUsageError("param_out_of_range", "parameter out of range")
    return value


def _research_config_from_settings(settings: Settings) -> ResearchConfig | None:
    """Strict AT USE: the FULL existing isolated-runner configuration must
    be verified safe (all values present, HTTPS endpoint, finite 10..600s
    timeout, readable executable, non-empty credential-ENV-NAME value) or
    research is unavailable. Never a partial configuration, never an
    unsandboxed fallback or call."""
    cli_bin = (settings.CATALOG_REFRESH_RESEARCH_CLI_BIN or "").strip()
    endpoint = (settings.CATALOG_REFRESH_RESEARCH_ENDPOINT or "").strip()
    model = (settings.CATALOG_REFRESH_RESEARCH_MODEL or "").strip()
    auth_env = (settings.CATALOG_REFRESH_RESEARCH_AUTH_ENV or "").strip()
    timeout = settings.CATALOG_REFRESH_RESEARCH_TIMEOUT_SECONDS
    if not (cli_bin and endpoint and model and auth_env):
        return None
    if not endpoint.lower().startswith("https://"):
        return None
    if not 10 <= timeout <= 600:
        return None
    if not os.environ.get(auth_env):
        return None
    cli_path = Path(cli_bin).expanduser().absolute()
    if not cli_path.is_file():
        return None
    return ResearchConfig(
        enabled=True,
        cli_bin=str(cli_path),
        model_endpoint=endpoint,
        model_name=model,
        model_auth_env=auth_env,
        timeout_seconds=timeout,
    )


def _held_operation_handles(settings: Settings):
    """Retain the EXISTING anchored run-root and key-parent lifecycle
    handles for the whole operation (create_missing=False: setup already
    verified them, the GUI never triggers Core create-missing defaults).
    Containment is re-verified on the held descriptors; the caller owns
    and closes both handles."""
    setup = inspect_custody_setup(settings)
    if setup.state != "ready" or setup.root is None or setup.seal_key is None:
        raise AdminCatalogRefreshError(
            setup.code, "catalog refresh custody is not usable: " + setup.code
        )
    run_root = setup.root / "runs"
    run_handle = open_anchored_handle(run_root, create_missing=False)
    try:
        key_handle = open_anchored_handle(setup.seal_key.parent, create_missing=False)
    except BaseException:
        run_handle.close()
        raise
    try:
        check_key_containment(run_root, setup.seal_key, run_handle, key_handle)
    except BaseException:
        run_handle.close()
        key_handle.close()
        raise
    return run_handle, key_handle


def _settings_database_url_lazy(settings: Settings) -> Callable[[], str | None]:
    """Lazy configured-URL getter (the bundle's validated baseline.mode
    decides whether it is ever consulted; bootstrap/exported/offline
    reviews never read settings)."""

    def _get() -> str | None:
        return (settings.DATABASE_URL or "").strip() or None

    return _get


def _outcome_terminal(outcome: ReviewOutcome) -> tuple[str, str | None, str | None, str]:
    """(status, run_id, error_code, progress) from one sealed outcome.
    BLOCKED keeps a CLOSED error classification - the exact blocked code
    is part of the sealed run and is surfaced by the admin rendering."""
    if outcome.state == "READY":
        return (
            "ready",
            outcome.run_id,
            None,
            f"ready: {outcome.changed} changed, {outcome.warnings} warning(s)",
        )
    if outcome.state == "READY_WITH_WARNINGS":
        return (
            "warnings",
            outcome.run_id,
            None,
            f"ready with {outcome.warnings} warning(s), {outcome.changed} changed",
        )
    return (
        "blocked",
        outcome.run_id,
        outcome.exit_class,
        f"blocked at stage {outcome.stage}",
    )


def _generated_upload_path(setup_root: Path, job_id: str, name: Any) -> Path | None:
    if not isinstance(name, str) or not _GENERATED_UPLOAD_NAME_RE.fullmatch(name):
        raise ApplicationUsageError(
            "upload_ref_invalid", "the job references an unknown uploaded artifact"
        )
    return setup_root / "uploads" / job_id / name


async def _run_collect(
    settings: Settings, job_id: str, params: dict[str, Any], checkpoint: _Checkpoint
) -> tuple[str, str | None, str | None, str]:
    setup = _require_ready(settings)
    mode = str(params.get("mode") or "")
    if mode == "bootstrap":
        bootstrap, refresh = True, False
    elif mode == "refresh":
        bootstrap, refresh = False, True
    else:
        raise ApplicationUsageError(
            "collect_mode_invalid", "collect mode must be bootstrap or refresh"
        )
    providers = _str_list(params.get("providers"))
    models = _str_list(params.get("models"))
    baseline_upload = params.get("baseline_upload")
    baseline_file = (
        _generated_upload_path(setup.root, job_id, baseline_upload)
        if baseline_upload is not None
        else None
    )
    # Exact legacy rule: refresh WITHOUT an uploaded exported baseline
    # falls back to the configured DATABASE_URL; bootstrap and
    # exported-baseline refreshes never consult settings.
    settings_database_url: str | None = None
    if refresh and baseline_file is None:
        settings_database_url = (settings.DATABASE_URL or "").strip() or None
    research: ResearchConfig | None = None
    if params.get("research"):
        research = _research_config_from_settings(settings)
        if research is None:
            raise ApplicationUsageError(
                "research_unavailable",
                "assisted research is not fully configured on this deployment",
            )
    if baseline_file is not None and not custody_upload_exists(settings, job_id, str(baseline_file.name)):
        raise ApplicationDataError(
            "upload_missing", "the uploaded baseline artifact is missing from custody"
        )
    run_handle, key_handle = _held_operation_handles(settings)
    try:
        outcome = await asyncio.to_thread(
            run_collect,
            bootstrap=bootstrap,
            refresh=refresh,
            profile=PROFILE_STANDARD_V1,
            providers=providers,
            model_include=models,
            baseline_file=baseline_file,
            db_url=None,
            run_root=setup.root / "runs",
            seal_key_path=setup.seal_key,
            run_root_handle=run_handle,
            key_handle=key_handle,
            research=research,
            existing_key_only=True,
            cancel=checkpoint,
            client=_collect_client_factory(),
            settings_database_url=settings_database_url,
        )
    finally:
        run_handle.close()
        key_handle.close()
    return _outcome_terminal(outcome)


async def _run_review(
    settings: Settings, job_id: str, params: dict[str, Any], checkpoint: _Checkpoint
) -> tuple[str, str | None, str | None, str]:
    setup = _require_ready(settings)
    bundle_path = _generated_upload_path(setup.root, job_id, params.get("bundle_name"))
    assert bundle_path is not None
    baseline_name = params.get("baseline_name")
    baseline_file = (
        _generated_upload_path(setup.root, job_id, baseline_name)
        if baseline_name
        else None
    )
    if not custody_upload_exists(settings, job_id, str(bundle_path.name)):
        raise ApplicationDataError(
            "upload_missing", "the uploaded bundle artifact is missing from custody"
        )
    if baseline_file is not None and not custody_upload_exists(
        settings, job_id, str(baseline_file.name)
    ):
        raise ApplicationDataError(
            "upload_missing", "the uploaded baseline artifact is missing from custody"
        )
    run_handle, key_handle = _held_operation_handles(settings)
    try:
        outcome = await asyncio.to_thread(
            run_review,
            bundle_path=bundle_path,
            baseline_file=baseline_file,
            first_install=bool(params.get("first_install")),
            db_url=None,
            run_root=setup.root / "runs",
            seal_key_path=setup.seal_key,
            run_root_handle=run_handle,
            key_handle=key_handle,
            existing_key_only=True,
            cancel=checkpoint,
            settings_database_url=_settings_database_url_lazy(settings),
        )
    finally:
        run_handle.close()
        key_handle.close()
    return _outcome_terminal(outcome)


async def _run_export(
    settings: Settings, job_id: str, params: dict[str, Any], checkpoint: _Checkpoint
) -> tuple[tuple[str, str | None, str | None, str], str]:
    _require_ready(settings)
    db_url = (settings.DATABASE_URL or "").strip()
    if not db_url:
        raise ApplicationDataError(
            "database_url_missing",
            "DATABASE_URL is not configured; the export baseline needs a "
            "read-only database connection",
        )
    _gate(checkpoint)
    doc = await asyncio.to_thread(export_baseline_document, db_url=db_url)
    _gate(checkpoint)
    # SAME canonical serialization the CLI export publishes.
    payload = (json.dumps(doc.model_dump(mode="json"), sort_keys=True, indent=1) + "\n").encode(
        "utf-8"
    )
    if len(payload) > MAX_BASELINE_BYTES:
        raise CustodyCapacityError(
            "export_too_large", "the exported baseline document exceeds its bound"
        )
    name = store_upload(settings, job_id, "baseline", payload)
    _gate(checkpoint)
    return ("ready", None, None, f"baseline exported: {name}"), name


async def _run_proposal(
    settings: Settings, job_id: str, params: dict[str, Any], checkpoint: _Checkpoint
) -> tuple[str, str | None, str | None, str]:
    _require_ready(settings)
    _gate(checkpoint)
    output_dir = open_proposal_dir(settings, job_id)
    scope = str(params.get("provider_scope") or "openai")
    if scope not in ("openai", "openrouter", "all"):
        raise ApplicationUsageError(
            "proposal_scope_invalid", "provider scope must be openai, openrouter, or all"
        )
    source_methods = _str_list(params.get("source_methods"))
    if not source_methods:
        source_methods = ("docs",)
    if any(method not in ("docs", "api", "assisted") for method in source_methods):
        raise ApplicationUsageError(
            "source_method_invalid", "unknown proposal source method"
        )
    # The job's existing cooperative checkpoint is wired through the
    # factory seam: cancel/deadline is honored between acquisitions and
    # between returned raw chunks across the whole source loop (the
    # before/after gates alone are not a bound for a long generator).
    client = _build_proposal_client(checkpoint=checkpoint)
    try:
        generation = generate_provider_catalog_proposal(
            provider_scope=scope,  # type: ignore[arg-type]
            output_dir=output_dir,
            endpoint_scopes=_str_list(params.get("endpoint_scopes")),
            include_models=_str_list(params.get("include_models")),
            exclude_models=_str_list(params.get("exclude_models")),
            currency=str(params.get("currency") or "USD"),
            source_methods=source_methods,  # type: ignore[arg-type]
            max_models=_int_param(
                params.get("max_models"), _PROPOSAL_MAX_MODELS, 1, _PROPOSAL_MAX_MODELS
            ),
            fetch_details_limit=_int_param(
                params.get("fetch_details_limit"),
                50,
                0,
                _PROPOSAL_FETCH_DETAILS_LIMIT,
            ),
            include_api_models=bool(params.get("include_api_models")),
            max_web_calls=_int_param(
                params.get("max_web_calls"), 3, 1, _PROPOSAL_MAX_WEB_CALLS
            ),
            save_source_snapshots=bool(params.get("save_source_snapshots")),
            acknowledge_assisted_proposal_risk=bool(
                params.get("acknowledge_assisted_proposal_risk")
            ),
            allow_zero_prices=bool(params.get("allow_zero_prices")),
            paired_ready_only=bool(params.get("paired_ready_only")),
            ordinary_chat_only=bool(params.get("ordinary_chat_only", True)),
            all_packages=bool(params.get("all_packages")),
            package_names=_str_list(params.get("package_names")),
            include_deprecated=bool(params.get("include_deprecated")),
            include_ambiguous_capabilities=bool(
                params.get("include_ambiguous_capabilities")
            ),
            http_client=client,
            max_output_bytes=_PROPOSAL_RESERVATION_BYTES,
        )
        try:
            await generation
        except ProviderCatalogProposalSizeError:
            # Enforced ceiling breached mid-generation: the over-ceiling
            # payload was never written, but earlier files are; retract the
            # partial output and refuse (never leave an over-bound artifact).
            remove_proposal_dir(settings, job_id)
            raise CustodyCapacityError(
                "proposal_output_capacity",
                "the proposal output exceeded its enforced byte ceiling "
                "before generation completed; no complete proposal was "
                "published",
            )
    finally:
        await client.aclose()
    # Post-generation custody gate (actual bytes, retract+refuse over cap)
    # and the cancel gate BEFORE any ready claim: a canceled job retracts
    # its output and never publishes ready after the cancellation.
    try:
        _gate(checkpoint)
        account_proposal_output(settings, job_id)
        _gate(checkpoint)
    except CollectionCanceled:
        remove_proposal_dir(settings, job_id)
        raise
    return "ready", None, None, "proposal artifacts generated"


async def _execute_job(*, settings: Settings, job_id: str) -> dict[str, object]:
    if not isinstance(job_id, str) or not _JOB_ID_RE.fullmatch(job_id):
        return {"job_id": None, "executed": False, "error_code": "job_id_invalid"}
    record = begin_job(settings, job_id)
    if record is None:
        # Unknown, already terminal, duplicate delivery, or a
        # cancel-requested queued job (never executes).
        return {"job_id": job_id, "executed": False, "error_code": "not_executed"}
    family = str(record.get("family") or "")
    params = record.get("params")
    if not isinstance(params, dict):
        params = {}
    if family not in CATALOG_JOB_FAMILIES:
        finish_job(settings, job_id, "failed", error_code="job_family_invalid")
        return {
            "job_id": job_id,
            "executed": True,
            "status": "failed",
            "error_code": "job_family_invalid",
        }
    checkpoint = _Checkpoint(
        cancel_check(settings, job_id),
        settings.CATALOG_REFRESH_READ_ONLY_TIMEOUT_SECONDS,
    )
    artifact_name: str | None = None
    try:
        if family == "collect":
            result = await _run_collect(settings, job_id, params, checkpoint)
        elif family == "review_supplied":
            result = await _run_review(settings, job_id, params, checkpoint)
        elif family == "export_baseline":
            result, artifact_name = await _run_export(
                settings, job_id, params, checkpoint
            )
        else:  # proposal
            result = await _run_proposal(settings, job_id, params, checkpoint)
    except CollectionCanceled:
        status, code = _interrupted_terminal(settings, job_id, checkpoint)
        finish_job(settings, job_id, status, error_code=code)
        return {
            "job_id": job_id,
            "executed": True,
            "status": status,
            "error_code": code,
        }
    except (ApplicationUsageError, ApplicationDataError) as exc:
        finish_job(settings, job_id, "failed", error_code=exc.code)
        return {
            "job_id": job_id,
            "executed": True,
            "status": "failed",
            "error_code": exc.code,
        }
    except (CustodyCapacityError, CustodyJobError, AdminCatalogRefreshError) as exc:
        finish_job(
            settings, job_id, "failed", error_code=getattr(exc, "code", None) or "custody_error"
        )
        return {
            "job_id": job_id,
            "executed": True,
            "status": "failed",
            "error_code": getattr(exc, "code", None) or "custody_error",
        }
    except Exception as exc:  # noqa: BLE001 - closed safe classification
        # Fixed safe code/class only: raw exception text (which may carry
        # untrusted source/filename/error content) never reaches logs.
        logger.warning(
            "catalog refresh job failed",
            job_id=job_id,
            family=family,
            error_class=type(exc).__name__,
        )
        finish_job(settings, job_id, "failed", error_code="internal_error")
        return {
            "job_id": job_id,
            "executed": True,
            "status": "failed",
            "error_code": "internal_error",
        }
    status, run_id, error_code, progress = result
    finished = finish_job(
        settings,
        job_id,
        status,
        run_id=run_id,
        progress=progress,
        error_code=error_code,
        artifact_name=artifact_name,
    )
    if not finished:
        # A terminal state was already recorded (late/duplicate delivery
        # race): that state wins, and this delivery claims nothing.
        return {
            "job_id": job_id,
            "executed": True,
            "status": "unconfirmed",
            "error_code": "finish_refused",
        }
    return {
        "job_id": job_id,
        "executed": True,
        "status": status,
        "run_id": run_id,
        "error_code": error_code,
    }


@celery_app.task(name="slaif_gateway.catalog_refresh.execute_job")
def catalog_refresh_execute_job(job_id: str) -> dict[str, object]:
    """ONE closed read-only family, IDs-only broker payload."""
    return asyncio.run(_execute_job(settings=get_settings(), job_id=job_id))
