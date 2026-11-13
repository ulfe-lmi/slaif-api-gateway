"""Objective 224-a unit evidence: demo web-control state machine.

Database-independent: the service is driven through fake repositories
that simulate the reviewed database law (the 'pending' server_default,
the atomic guarded transitions, the copy-uniqueness and one-live-
session-per-copy constraints). Real role/grant/lock evidence lives in
tests/integration/test_demo_web_control_postgres.py.

Covers: state transitions, generation/revocation/zero-active-account
gates, token hashing/no echo, timeouts, idempotency, distinct
requests/copies across two logins, unknown-state refusal, the closed
identity grammars, the role grant matrix, and safe-error no-echo.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import IntegrityError

from slaif_gateway.db.repositories.fake_admin_accounts import FakeAdminAccountFacts
from slaif_gateway.services.demo_web_control import (
    CLAIM_LEASE,
    REQUEST_TTL,
    VERIFIED_COPY_STATE,
    DemoSessionIssuedResult,
    DemoSnapshotRequestProjection,
    DemoWebControlError,
    DemoWebControlService,
    VerifiedCopyBinding,
    generate_opaque_token,
    hash_opaque_token,
    web_role_grant_sql,
    worker_role_grant_sql,
)

# --- fakes ------------------------------------------------------------------------


class _Row:
    """Attribute view over a fake row dict."""

    def __init__(self, data: dict) -> None:
        object.__setattr__(self, "_data", data)

    def __getattr__(self, name: str):
        try:
            return self._data[name]
        except KeyError:
            raise AttributeError(name) from None


def _integrity_error(constraint_name: str) -> IntegrityError:
    orig = SimpleNamespace(constraint_name=constraint_name)
    return IntegrityError("UPDATE demo_control.demo_snapshot_requests", {}, orig)


class FakeRequestsRepo:
    """Simulates the demo request/session repository + database law."""

    def __init__(self) -> None:
        self.requests: dict[uuid.UUID, dict] = {}
        self.sessions: dict[uuid.UUID, dict] = {}

    # requests ----------------------------------------------------------------

    async def get_request(self, request_id: uuid.UUID, *, read_lock: bool = False):
        data = self.requests.get(request_id)
        return _Row(data) if data is not None else None

    async def create_request(
        self,
        *,
        account_id: uuid.UUID,
        credential_generation: int,
        created_at: object,
        deadline_at: object,
        expires_at: object,
    ) -> _Row:
        # The DB server_default applies: the web INSERT cannot name
        # state, so the row is born 'pending' with all worker-owned
        # columns NULL.
        rid = uuid.uuid4()
        data = {
            "id": rid,
            "account_id": account_id,
            "credential_generation": credential_generation,
            "state": "pending",
            "failure_code": None,
            "worker_job_id": None,
            "worker_target_db": None,
            "created_at": created_at,
            "claimed_at": None,
            "deadline_at": deadline_at,
            "expires_at": expires_at,
            "verified_at": None,
        }
        self.requests[rid] = data
        return _Row(data)

    async def count_requests(self, account_id: uuid.UUID, *, state: str | None = None) -> int:
        return sum(
            1
            for r in self.requests.values()
            if r["account_id"] == account_id and (state is None or r["state"] == state)
        )

    async def cas_transition(
        self,
        request_id: uuid.UUID,
        *,
        to_state: str,
        from_states: tuple[str, ...],
        failure_code: str | None = None,
        claimed_at: object = None,
        verified_at: object = None,
        worker_job_id: str | None = None,
        worker_target_db: str | None = None,
        account_gate: bool = False,
    ) -> bool:
        row = self.requests.get(request_id)
        if row is None or row["state"] not in from_states:
            return False
        # The database enforces account_gate statement-time inside the
        # guarded UPDATE (live account enabled + recorded generation).
        # This in-memory fake has no live-account state; the service's
        # own _load_account recheck covers the unit-level semantics, so
        # the flag is accepted and intentionally not evaluated here.
        # Database copy-uniqueness law (partial unique indexes).
        if worker_job_id is not None or worker_target_db is not None:
            for other in self.requests.values():
                if other is row:
                    continue
                if worker_job_id is not None and other["worker_job_id"] == worker_job_id:
                    raise _integrity_error("uq_demo_snapshot_requests_worker_job_id")
                if (
                    worker_target_db is not None
                    and other["worker_target_db"] == worker_target_db
                ):
                    raise _integrity_error("uq_demo_snapshot_requests_worker_target_db")
        row["state"] = to_state
        if failure_code is not None:
            row["failure_code"] = failure_code
        if claimed_at is not None:
            row["claimed_at"] = claimed_at
        if verified_at is not None:
            row["verified_at"] = verified_at
        if worker_job_id is not None:
            row["worker_job_id"] = worker_job_id
        if worker_target_db is not None:
            row["worker_target_db"] = worker_target_db
        return True

    async def list_expired_for_reap(self, *, limit: int) -> list[_Row]:
        now = datetime.now(timezone.utc)
        out = []
        for row in sorted(self.requests.values(), key=lambda r: r["created_at"]):
            if row["state"] == "pending" and row["deadline_at"] <= now:
                out.append(_Row(row))
            elif row["state"] == "claimed" and row["expires_at"] <= now:
                out.append(_Row(row))
            if len(out) >= limit:
                break
        return out

    async def flush(self) -> None:
        return None

    async def list_requests(self, account_id: uuid.UUID, *, limit: int, offset: int = 0):
        rows = [
            _Row(r)
            for r in sorted(
                (r for r in self.requests.values() if r["account_id"] == account_id),
                key=lambda r: r["created_at"],
                reverse=True,
            )
        ]
        return rows[offset : offset + limit]

    # sessions -----------------------------------------------------------------

    async def get_session_by_token_hash(self, token_hash: str, *, read_lock: bool = False):
        for data in self.sessions.values():
            if data["token_hash"] == token_hash:
                return _Row(data)
        return None

    async def count_active_sessions_for_request(self, request_id: uuid.UUID) -> int:
        return sum(
            1
            for s in self.sessions.values()
            if s["request_id"] == request_id and s["revoked_at"] is None
        )

    async def create_session(
        self,
        *,
        token_hash: str,
        account_id: uuid.UUID,
        credential_generation: int,
        request_id: uuid.UUID,
        created_at: object,
        expires_at: object,
    ) -> _Row:
        # Database law: token hash unique; at most one LIVE session per
        # request (partial unique index).
        if any(s["token_hash"] == token_hash for s in self.sessions.values()):
            raise _integrity_error("ix_demo_web_sessions_token_hash")
        if any(
            s["request_id"] == request_id and s["revoked_at"] is None
            for s in self.sessions.values()
        ):
            raise _integrity_error("uq_demo_web_sessions_one_active_per_request")
        sid = uuid.uuid4()
        data = {
            "id": sid,
            "token_hash": token_hash,
            "account_id": account_id,
            "credential_generation": credential_generation,
            "request_id": request_id,
            "created_at": created_at,
            "expires_at": expires_at,
            "revoked_at": None,
        }
        self.sessions[sid] = data
        return _Row(data)

    async def cas_revoke_session(self, session_id: uuid.UUID, revoked_at: object) -> bool:
        data = self.sessions.get(session_id)
        if data is None or data["revoked_at"] is not None:
            return False
        data["revoked_at"] = revoked_at
        return True


class FakeAccountsRepo:
    def __init__(self, accounts: dict[uuid.UUID, tuple[bool, int]]) -> None:
        self.accounts = accounts  # id -> (is_enabled, credential_generation)
        self.force_count: int | None = None  # test hook for the count gate

    async def get_account_facts(self, account_id: uuid.UUID, *, read_lock: bool = True):
        value = self.accounts.get(account_id)
        if value is None:
            return None
        return FakeAdminAccountFacts(
            id=account_id, is_enabled=value[0], credential_generation=value[1]
        )

    async def count_active_accounts(self) -> int:
        if self.force_count is not None:
            return self.force_count
        return sum(1 for enabled, _ in self.accounts.values() if enabled)

    # The real repository also exposes full-row helpers used by the CLI
    # path; the demo control service must never call them.
    async def get_account_by_id(self, account_id: uuid.UUID, *, for_update: bool = False):
        raise AssertionError("demo control service must use facts-only reads")


# --- harness ------------------------------------------------------------------------


ACCOUNT = uuid.uuid4()
ACCOUNT2 = uuid.uuid4()


def _svc(*, accounts=None):
    req = FakeRequestsRepo()
    acc = FakeAccountsRepo(accounts if accounts is not None else {ACCOUNT: (True, 0)})
    svc = DemoWebControlService(None, requests_repository=req, accounts_repository=acc)  # type: ignore[arg-type]
    return svc, req, acc


def _binding(job: str | None = None, target: str | None = None, state: str = VERIFIED_COPY_STATE):
    return VerifiedCopyBinding(
        worker_job_id=job or f"snap-{uuid.uuid4().hex}",
        worker_target_db=target or f"demo_snap_{uuid.uuid4().hex[:20]}",
        manifest_state=state,
    )


def _job_id(i: int = 0) -> str:
    return "snap-" + format(i, "032x")


def _target(i: int = 0) -> str:
    return "demo_snap_" + format(i, "020x")


async def _full_cycle(svc, *, account=ACCOUNT, job=0, target=0):
    """create -> claim -> verify; returns the verified request projection."""
    created = await svc.create_request(account_id=account)
    claimed = await svc.claim_request(request_id=created.id)
    assert claimed.state == "claimed"
    verified = await svc.record_verified_handoff(
        request_id=created.id, binding=_binding(_job_id(job), _target(target))
    )
    assert verified.state == "verified_unpublished"
    return verified


def _age_request(req_repo: FakeRequestsRepo, request_id: uuid.UUID, *, deadline=None, expires=None):
    """Simulate wall-clock passing by moving the row's times into the past."""
    row = req_repo.requests[request_id]
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    if deadline is not None:
        row["deadline_at"] = deadline
    if expires is not None:
        row["expires_at"] = expires
    if deadline is None and expires is None:
        row["deadline_at"] = past
        row["expires_at"] = past + timedelta(minutes=1)


# --- create_request -------------------------------------------------------------------


def test_create_request_gates_and_distinct_requests() -> None:
    async def run():
        svc, req, _ = _svc()
        first = await svc.create_request(account_id=ACCOUNT)
        second = await svc.create_request(account_id=ACCOUNT)
        assert first.id != second.id, "two logins must get distinct requests"
        assert first.state == "pending"
        assert first.failure_code is None
        assert first.worker_job_id is None and first.worker_target_db is None
        assert first.credential_generation == 0
        assert first.deadline_at - first.created_at == CLAIM_LEASE
        assert first.expires_at - first.created_at == REQUEST_TTL
        # The DB default applied: the fake (like the DB) stored pending.
        assert req.requests[first.id]["state"] == "pending"

    asyncio.run(run())


def test_create_request_refusals() -> None:
    async def run():
        # missing account
        svc, _, _ = _svc()
        with pytest.raises(DemoWebControlError) as exc:
            await svc.create_request(account_id=uuid.uuid4())
        assert exc.value.code == "web_account_not_found"
        # disabled account
        svc, _, _ = _svc(accounts={ACCOUNT: (False, 0)})
        with pytest.raises(DemoWebControlError) as exc:
            await svc.create_request(account_id=ACCOUNT)
        assert exc.value.code == "web_account_disabled"
        # zero active accounts: the account reads enabled but the
        # database-side active count is zero (defense-in-depth gate)
        svc, _, acc = _svc(accounts={ACCOUNT: (True, 0)})
        acc.force_count = 0
        with pytest.raises(DemoWebControlError) as exc:
            await svc.create_request(account_id=ACCOUNT)
        assert exc.value.code == "web_no_active_accounts"

    asyncio.run(run())


def test_create_request_records_live_generation() -> None:
    async def run():
        svc, _, _ = _svc(accounts={ACCOUNT: (True, 7)})
        created = await svc.create_request(account_id=ACCOUNT)
        assert created.credential_generation == 7

    asyncio.run(run())


# --- claim ---------------------------------------------------------------------------


def test_claim_lifecycle_and_replay_refusal() -> None:
    async def run():
        svc, req, _ = _svc()
        created = await svc.create_request(account_id=ACCOUNT)
        claimed = await svc.claim_request(request_id=created.id)
        assert claimed.state == "claimed"
        # claimed_at is worker metadata on the stored row (not on the
        # public projection)
        assert req.requests[created.id]["claimed_at"] is not None
        # replayed/duplicate claim refused
        with pytest.raises(DemoWebControlError) as exc:
            await svc.claim_request(request_id=created.id)
        assert exc.value.code == "web_request_not_pending"
        # unknown request
        with pytest.raises(DemoWebControlError) as exc:
            await svc.claim_request(request_id=uuid.uuid4())
        assert exc.value.code == "web_request_not_found"

    asyncio.run(run())


def test_claim_expired_lease_fails_claim_expired() -> None:
    async def run():
        svc, req, _ = _svc()
        created = await svc.create_request(account_id=ACCOUNT)
        _age_request(req, created.id, deadline=datetime.now(timezone.utc) - timedelta(seconds=1))
        result = await svc.claim_request(request_id=created.id)
        assert result.state == "failed"
        assert result.failure_code == "claim_expired"

    asyncio.run(run())


def test_claim_stale_account_fails_state_conflict() -> None:
    async def run():
        # account disabled AFTER the request existed (mid-flight)
        svc, _, _ = _svc(accounts={ACCOUNT: (True, 0)})
        created = await svc.create_request(account_id=ACCOUNT)
        svc._accounts.accounts[ACCOUNT] = (False, 0)  # type: ignore[attr-defined]
        result = await svc.claim_request(request_id=created.id)
        assert result.state == "failed"
        assert result.failure_code == "state_conflict"

    asyncio.run(run())

    async def run2():
        # generation moved AFTER the request existed
        svc, _, _ = _svc(accounts={ACCOUNT: (True, 0)})
        created = await svc.create_request(account_id=ACCOUNT)
        svc._accounts.accounts[ACCOUNT] = (True, 1)  # type: ignore[attr-defined]
        result = await svc.claim_request(request_id=created.id)
        assert result.state == "failed"
        assert result.failure_code == "state_conflict"

    asyncio.run(run2())


# --- verified handoff ------------------------------------------------------------------


def test_verified_handoff_happy_path() -> None:
    async def run():
        svc, req, _ = _svc()
        verified = await _full_cycle(svc, job=1, target=2)
        assert verified.worker_job_id == _job_id(1)
        assert verified.worker_target_db == _target(2)
        # verified_at is worker metadata: asserted on the stored row, not
        # exposed on the public projection
        assert req.requests[verified.id]["verified_at"] is not None
        assert req.requests[verified.id]["state"] == "verified_unpublished"
        assert "verified_at" not in verified.to_safe_dict()

    asyncio.run(run())


def test_verified_handoff_refusals() -> None:
    async def run():
        svc, req, _ = _svc()
        created = await svc.create_request(account_id=ACCOUNT)
        # not claimed yet
        with pytest.raises(DemoWebControlError) as exc:
            await svc.record_verified_handoff(
                request_id=created.id, binding=_binding()
            )
        assert exc.value.code == "web_request_not_claimed"
        await svc.claim_request(request_id=created.id)
        # wrong manifest state -> failed/verification_failed
        bad = await svc.record_verified_handoff(
            request_id=created.id, binding=_binding(state="RAW_UNVERIFIED")
        )
        assert bad.state == "failed"
        assert bad.failure_code == "verification_failed"

    asyncio.run(run())


def test_verified_handoff_late_completion() -> None:
    async def run():
        svc, req, _ = _svc()
        created = await svc.create_request(account_id=ACCOUNT)
        await svc.claim_request(request_id=created.id)
        _age_request(req, created.id, expires=datetime.now(timezone.utc) - timedelta(seconds=1))
        result = await svc.record_verified_handoff(
            request_id=created.id, binding=_binding()
        )
        assert result.state == "failed"
        assert result.failure_code == "late_completion"

    asyncio.run(run())


def test_verified_handoff_stale_account() -> None:
    async def run():
        svc, _, _ = _svc(accounts={ACCOUNT: (True, 0)})
        created = await svc.create_request(account_id=ACCOUNT)
        await svc.claim_request(request_id=created.id)
        # generation moved mid-job
        svc._accounts.accounts[ACCOUNT] = (True, 1)  # type: ignore[attr-defined]
        result = await svc.record_verified_handoff(
            request_id=created.id, binding=_binding()
        )
        assert result.state == "failed"
        assert result.failure_code == "state_conflict"

    asyncio.run(run())


def test_verified_handoff_grammar_refusal_no_echo() -> None:
    canary = "snap-SECRET000000000000000000000000000"
    async def run():
        svc, _, _ = _svc()
        created = await svc.create_request(account_id=ACCOUNT)
        await svc.claim_request(request_id=created.id)
        with pytest.raises(DemoWebControlError) as exc:
            await svc.record_verified_handoff(
                request_id=created.id, binding=_binding(job=canary)
            )
        assert exc.value.code == "web_invalid_job_identity"
        assert canary not in exc.value.safe_message
        with pytest.raises(DemoWebControlError) as exc:
            await svc.record_verified_handoff(
                request_id=created.id,
                binding=_binding(target="demo_snap_" + "G" * 20),
            )
        assert exc.value.code == "web_invalid_target_identity"

    asyncio.run(run())


def test_verified_handoff_copy_conflict_refused_safely() -> None:
    async def run():
        svc, req, _ = _svc()
        first = await _full_cycle(svc, job=1, target=1)
        # a second request tries to bind the SAME copy
        created2 = await svc.create_request(account_id=ACCOUNT)
        await svc.claim_request(request_id=created2.id)
        with pytest.raises(DemoWebControlError) as exc:
            await svc.record_verified_handoff(
                request_id=created2.id,
                binding=_binding(_job_id(1), _target(1)),
            )
        assert exc.value.code == "web_request_copy_reused"
        # the second request stays claimed (aborted transaction)
        assert req.requests[created2.id]["state"] == "claimed"
        assert req.requests[created2.id]["worker_job_id"] is None
        _ = first

    asyncio.run(run())


# --- sessions --------------------------------------------------------------------------


def test_session_token_law_and_no_echo() -> None:
    token_a = generate_opaque_token()
    token_b = generate_opaque_token()
    assert token_a != token_b
    assert re.fullmatch(r"[A-Za-z0-9_-]{43}", token_a)
    h = hash_opaque_token(token_a)
    assert re.fullmatch(r"[0-9a-f]{64}", h)
    assert h == hashlib.sha256(token_a.encode()).hexdigest()
    # safe projection never carries the token or its hash
    async def run():
        svc, _, _ = _svc()
        verified = await _full_cycle(svc, job=3, target=3)
        issued_result = await svc.create_session(
            account_id=ACCOUNT, request_id=verified.id
        )
        return issued_result

    issued = asyncio.run(run())
    assert isinstance(issued, DemoSessionIssuedResult)
    safe = issued.session.to_safe_dict()
    assert "token" not in safe and "token_hash" not in safe
    assert issued.token not in str(safe)


def test_session_lifecycle_validate_revoke() -> None:
    async def run():
        svc, req, _ = _svc()
        verified = await _full_cycle(svc, job=4, target=4)
        # only verified-unpublished may issue
        issued = await svc.create_session(account_id=ACCOUNT, request_id=verified.id)
        ok = await svc.validate_session(account_id=ACCOUNT, token=issued.token)
        assert ok.id == issued.session.id
        # wrong account refused
        with pytest.raises(DemoWebControlError) as exc:
            await svc.validate_session(account_id=ACCOUNT2, token=issued.token)
        assert exc.value.code == "web_session_not_found"
        # copy reuse refused while a session is live
        with pytest.raises(DemoWebControlError) as exc:
            await svc.create_session(account_id=ACCOUNT, request_id=verified.id)
        assert exc.value.code == "web_request_copy_reused"
        # worker cleanup refused while a live session binds the copy
        with pytest.raises(DemoWebControlError) as exc:
            await svc.mark_cleanup_pending(request_id=verified.id)
        assert exc.value.code == "web_cleanup_refused_live_session"
        # revoke (web) - idempotent, no request mutation by the web path
        proj = await svc.revoke_session(account_id=ACCOUNT, token=issued.token)
        assert proj is not None and proj.revoked_at is not None
        again = await svc.revoke_session(account_id=ACCOUNT, token=issued.token)
        assert again is not None and again.revoked_at == proj.revoked_at
        assert req.requests[verified.id]["state"] == "verified_unpublished"
        # validate after revocation refused
        with pytest.raises(DemoWebControlError) as exc:
            await svc.validate_session(account_id=ACCOUNT, token=issued.token)
        assert exc.value.code == "web_session_revoked"
        # after revocation (and BEFORE the worker starts cleanup) the
        # still-verified copy may receive exactly one new session
        issued2 = await svc.create_session(account_id=ACCOUNT, request_id=verified.id)
        assert issued2.session.id != issued.session.id
        # the worker cleanup path proceeds once no live session remains
        # after the new one is revoked too... (one live at a time)
        with pytest.raises(DemoWebControlError) as exc:
            await svc.mark_cleanup_pending(request_id=verified.id)
        assert exc.value.code == "web_cleanup_refused_live_session"
        await svc.revoke_session(account_id=ACCOUNT, token=issued2.token)
        cleaned_pending = await svc.mark_cleanup_pending(request_id=verified.id)
        assert cleaned_pending.state == "cleanup_pending"
        # the cleanup tail blocks NEW sessions on the dying copy: a new
        # login must take a NEW snapshot request
        with pytest.raises(DemoWebControlError) as exc:
            await svc.create_session(account_id=ACCOUNT, request_id=verified.id)
        assert exc.value.code == "web_request_not_verified"

    asyncio.run(run())


def test_session_gates() -> None:
    async def run():
        # unverified request refused
        svc, _, _ = _svc()
        created = await svc.create_request(account_id=ACCOUNT)
        with pytest.raises(DemoWebControlError) as exc:
            await svc.create_session(account_id=ACCOUNT, request_id=created.id)
        assert exc.value.code == "web_request_not_verified"
        # wrong-account request refused
        svc, _, _ = _svc(accounts={ACCOUNT: (True, 0), ACCOUNT2: (True, 0)})
        created = await svc.create_request(account_id=ACCOUNT)
        with pytest.raises(DemoWebControlError) as exc:
            await svc.create_session(account_id=ACCOUNT2, request_id=created.id)
        assert exc.value.code == "web_request_not_owned"
        # generation mismatch refused
        svc, _, _ = _svc(accounts={ACCOUNT: (True, 0)})
        verified = await _full_cycle(svc, job=5, target=5)
        svc._accounts.accounts[ACCOUNT] = (True, 1)  # type: ignore[attr-defined]
        with pytest.raises(DemoWebControlError) as exc:
            await svc.create_session(account_id=ACCOUNT, request_id=verified.id)
        assert exc.value.code == "web_account_generation_mismatch"
        # disabled account refused
        svc, _, _ = _svc(accounts={ACCOUNT: (True, 0)})
        verified = await _full_cycle(svc, job=6, target=6)
        svc._accounts.accounts[ACCOUNT] = (False, 0)  # type: ignore[attr-defined]
        with pytest.raises(DemoWebControlError) as exc:
            await svc.validate_session(account_id=ACCOUNT, token="whatever")
        assert exc.value.code in {"web_session_not_found", "web_account_disabled"}

    asyncio.run(run())


def test_session_race_integrity_error_safe() -> None:
    async def run():
        svc, req, _ = _svc()
        verified = await _full_cycle(svc, job=7, target=7)

        real_create = req.create_session

        async def racing_create(**kwargs):
            raise _integrity_error("uq_demo_web_sessions_one_active_per_request")

        req.create_session = racing_create  # type: ignore[method-assign]
        try:
            with pytest.raises(DemoWebControlError) as exc:
                await svc.create_session(account_id=ACCOUNT, request_id=verified.id)
            assert exc.value.code == "web_request_copy_reused"
        finally:
            req.create_session = real_create  # type: ignore[method-assign]

    asyncio.run(run())


# --- worker failure + cleanup tail -------------------------------------------------------


def test_worker_failure_law() -> None:
    async def run():
        svc, _, _ = _svc()
        created = await svc.create_request(account_id=ACCOUNT)
        failed = await svc.record_worker_failure(request_id=created.id, code="worker_failed")
        assert failed.state == "failed"
        assert failed.failure_code == "worker_failed"
        # invalid code refused
        with pytest.raises(DemoWebControlError) as exc:
            await svc.record_worker_failure(request_id=created.id, code="whatever")
        assert exc.value.code == "web_failure_code_invalid"
        # verified requests cannot be failed by the generic path
        svc2, _, _ = _svc()
        verified = await _full_cycle(svc2, job=8, target=8)
        with pytest.raises(DemoWebControlError) as exc:
            await svc2.record_worker_failure(request_id=verified.id, code="worker_failed")
        assert exc.value.code == "web_state_conflict"

    asyncio.run(run())


def test_cleanup_tail_law_and_idempotency() -> None:
    async def run():
        svc, _, _ = _svc()
        # failed -> cleanup_pending -> cleaned
        created = await svc.create_request(account_id=ACCOUNT)
        await svc.record_worker_failure(request_id=created.id, code="internal_error")
        cp = await svc.mark_cleanup_pending(request_id=created.id)
        assert cp.state == "cleanup_pending"
        again = await svc.mark_cleanup_pending(request_id=created.id)
        assert again.state == "cleanup_pending"
        cleaned = await svc.mark_cleaned(request_id=created.id)
        assert cleaned.state == "cleaned"
        assert (await svc.mark_cleaned(request_id=created.id)).state == "cleaned"
        # pending cannot enter cleanup
        created2 = await svc.create_request(account_id=ACCOUNT)
        with pytest.raises(DemoWebControlError) as exc:
            await svc.mark_cleanup_pending(request_id=created2.id)
        assert exc.value.code == "web_state_conflict"
        # cleaned-from-wrong-state refused
        created3 = await svc.create_request(account_id=ACCOUNT)
        with pytest.raises(DemoWebControlError) as exc:
            await svc.mark_cleaned(request_id=created3.id)
        assert exc.value.code == "web_state_conflict"

    asyncio.run(run())


def test_verified_with_live_session_blocks_cleanup_until_revoked() -> None:
    async def run():
        svc, _, _ = _svc()
        verified = await _full_cycle(svc, job=9, target=9)
        issued = await svc.create_session(account_id=ACCOUNT, request_id=verified.id)
        with pytest.raises(DemoWebControlError) as exc:
            await svc.mark_cleanup_pending(request_id=verified.id)
        assert exc.value.code == "web_cleanup_refused_live_session"
        await svc.revoke_session(account_id=ACCOUNT, token=issued.token)
        cp = await svc.mark_cleanup_pending(request_id=verified.id)
        assert cp.state == "cleanup_pending"

    asyncio.run(run())


# 224-b: the cleanup gate is account-aware - a live session makes the
# copy usable ONLY while the bound account is still enabled with the
# recorded generation (the per-use recheck law).
def test_cleanup_gate_released_by_account_disable_and_reset() -> None:
    async def run():
        # Disable: live session present but unusable at next use.
        svc, _, acc = _svc()
        verified = await _full_cycle(svc, job=11, target=11)
        await svc.create_session(account_id=ACCOUNT, request_id=verified.id)
        with pytest.raises(DemoWebControlError) as exc:
            await svc.mark_cleanup_pending(request_id=verified.id)
        assert exc.value.code == "web_cleanup_refused_live_session"
        acc.accounts[ACCOUNT] = (False, 0)
        cp = await svc.mark_cleanup_pending(request_id=verified.id)
        assert cp.state == "cleanup_pending"

        # Reset (generation change): same release.
        svc2, _, acc2 = _svc()
        verified2 = await _full_cycle(svc2, job=12, target=12)
        await svc2.create_session(account_id=ACCOUNT, request_id=verified2.id)
        acc2.accounts[ACCOUNT] = (True, 1)
        cp2 = await svc2.mark_cleanup_pending(request_id=verified2.id)
        assert cp2.state == "cleanup_pending"

    asyncio.run(run())


# 224-b residual race: a session INSERTED in the window between the
# worker's live-session count and its cleanup CAS is invalidated early -
# its first use is refused (bound copy no longer verified_unpublished)
# before any physical removal.
def test_session_inserted_in_cleanup_window_invalidated_at_first_use() -> None:
    async def run():
        svc, req, _ = _svc()
        verified = await _full_cycle(svc, job=13, target=13)
        # A prior session exists and is revoked (count now sees 0) -
        # the worker's cleanup count passes...
        prior = await svc.create_session(account_id=ACCOUNT, request_id=verified.id)
        await svc.revoke_session(account_id=ACCOUNT, token=prior.token)
        # ...and a concurrent web issuance lands its row in the window
        # (the account-aware gate refuses cleanup when a live session
        # exists AT GATE TIME - covered by the live-session tests above;
        # here the gate's count already ran and saw 0, so bind that
        # stale result, then insert the concurrent row directly after
        # the count and before the cleanup CAS completes).
        async def stale_zero(_request_id):
            return 0

        req.count_active_sessions_for_request = stale_zero
        late_token = generate_opaque_token()
        await req.create_session(
            token_hash=hash_opaque_token(late_token),
            account_id=ACCOUNT,
            credential_generation=0,
            request_id=verified.id,
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + REQUEST_TTL,
        )
        cp = await svc.mark_cleanup_pending(request_id=verified.id)
        assert cp.state == "cleanup_pending"
        # The window session is unusable at its FIRST use: the bound
        # copy is no longer verified_unpublished, so the browser can
        # never touch a copy cleanup is about to remove.
        with pytest.raises(DemoWebControlError) as exc:
            await svc.validate_session(account_id=ACCOUNT, token=late_token)
        assert exc.value.code == "web_request_not_verified"
        # A fresh issuance on the dying copy is refused too.
        with pytest.raises(DemoWebControlError) as exc:
            await svc.create_session(account_id=ACCOUNT, request_id=verified.id)
        assert exc.value.code == "web_request_not_verified"

    asyncio.run(run())


# --- unknown state + reap ------------------------------------------------------------------


def test_unknown_state_refused_everywhere() -> None:
    async def run():
        svc, req, _ = _svc()
        created = await svc.create_request(account_id=ACCOUNT)
        req.requests[created.id]["state"] = "bogus"
        for coro in (
            svc.claim_request(request_id=created.id),
            svc.record_verified_handoff(request_id=created.id, binding=_binding()),
            svc.record_worker_failure(request_id=created.id, code="worker_failed"),
            svc.mark_cleanup_pending(request_id=created.id),
            svc.mark_cleaned(request_id=created.id),
        ):
            with pytest.raises(DemoWebControlError) as exc:
                await coro
            assert exc.value.code == "web_unknown_state"
        # untouched
        assert req.requests[created.id]["state"] == "bogus"

    asyncio.run(run())


def test_reap_expired_bounded_recovery() -> None:
    async def run():
        svc, req, _ = _svc()
        fresh = await svc.create_request(account_id=ACCOUNT)
        stale_pending = await svc.create_request(account_id=ACCOUNT)
        await svc.claim_request(request_id=fresh.id)
        stale_claimed = fresh  # claimed, will age past expiry
        _age_request(req, stale_pending.id)  # both times past
        _age_request(req, stale_claimed.id)  # both times past
        reaped = await svc.reap_expired()
        assert reaped == 2
        # a fresh pending request (created after aging) is untouched
        await svc.create_request(account_id=ACCOUNT)
        assert await svc.reap_expired() == 0
        rows = {r["id"]: (r["state"], r["failure_code"]) for r in req.requests.values()}
        assert rows[stale_pending.id] == ("failed", "claim_expired")
        assert rows[stale_claimed.id] == ("failed", "late_completion")

    asyncio.run(run())


def test_reap_limit_validation() -> None:
    async def run():
        svc, _, _ = _svc()
        with pytest.raises(DemoWebControlError) as exc:
            await svc.reap_expired(limit=0)
        assert exc.value.code == "web_reap_limit_invalid"
        with pytest.raises(DemoWebControlError) as exc:
            await svc.reap_expired(limit=1001)
        assert exc.value.code == "web_reap_limit_invalid"

    asyncio.run(run())


# --- grant matrix -----------------------------------------------------------------------


def test_role_grant_matrix_law() -> None:
    web = web_role_grant_sql("slaif_demo_web")
    worker = worker_role_grant_sql("slaif_demo_worker")

    web_joined = " || ".join(web)
    worker_joined = " || ".join(worker)

    # web: column-limited request INSERT; state and worker columns excluded
    request_insert = next(
        g for g in web if "INSERT" in g and "demo_snapshot_requests" in g
    )
    assert "INSERT (id, account_id, credential_generation, created_at," in request_insert
    for forbidden in ("state", "claimed_at", "failure_code", "worker_job_id", "worker_target_db", "verified_at"):
        assert forbidden not in request_insert.split("ON", 1)[0], forbidden
    # web: NO UPDATE grant on requests at all
    assert not any(
        "UPDATE" in g and "demo_snapshot_requests" in g for g in web
    ), "web role must hold no UPDATE on demo_snapshot_requests"
    # web: session write surface is INSERT + UPDATE(revoked_at) only
    session_updates = [g for g in web if "UPDATE" in g and "demo_web_sessions" in g]
    assert len(session_updates) == 1
    assert "UPDATE (revoked_at)" in session_updates[0]
    # web: account SELECT is column-scoped (no timestamps)
    web_accounts = next(g for g in web if "fake_admin_accounts" in g)
    assert "created_at" not in web_accounts and "updated_at" not in web_accounts

    # worker: facts-only account SELECT (never username/password_hash)
    worker_accounts = next(g for g in worker if "fake_admin_accounts" in g)
    assert "username" not in worker_accounts
    assert "password_hash" not in worker_accounts
    # worker: session facts only (never token_hash/account/generation)
    worker_sessions = next(g for g in worker if "demo_web_sessions" in g)
    assert "SELECT (id, request_id, expires_at, revoked_at)" in worker_sessions
    assert "token_hash" not in worker_sessions.split("ON", 1)[0]
    # worker: no INSERT anywhere
    assert "INSERT" not in worker_joined
    # worker: request UPDATE is exactly the worker-owned column set
    worker_request_update = next(g for g in worker if "UPDATE" in g)
    assert (
        "UPDATE (state, failure_code, claimed_at, worker_job_id, "
        "worker_target_db, verified_at)" in worker_request_update
    )
    # neither role touches business tables
    assert "public." not in web_joined and "public." not in worker_joined


def test_role_name_refusal_no_echo() -> None:
    canary = "evil; DROP TABLE demo_control.demo_web_sessions;--"
    with pytest.raises(DemoWebControlError) as exc:
        web_role_grant_sql(canary)
    assert exc.value.code == "web_role_name_invalid"
    assert canary not in exc.value.safe_message
    with pytest.raises(DemoWebControlError):
        worker_role_grant_sql("UPPER")
    with pytest.raises(DemoWebControlError):
        worker_role_grant_sql(None)  # type: ignore[arg-type]


# --- safe projection --------------------------------------------------------------


def test_request_safe_dict_omits_private_copy_locators() -> None:
    verified: DemoSnapshotRequestProjection

    async def run():
        svc, _, _ = _svc()
        return await _full_cycle(svc, job=11, target=11)

    verified = asyncio.run(run())
    safe = verified.to_safe_dict()
    assert "worker_job_id" not in safe
    assert "worker_target_db" not in safe
    assert safe["state"] == "verified_unpublished"
    # internal fields still available to the worker control path
    assert verified.worker_job_id == _job_id(11)
    assert verified.worker_target_db == _target(11)


# --- two logins: distinct requests and copies ------------------------------------------


def test_two_logins_distinct_requests_and_copies() -> None:
    async def run():
        svc, req, _ = _svc()
        first = await _full_cycle(svc, job=21, target=21)
        second = await _full_cycle(svc, job=22, target=22)
        assert first.id != second.id
        assert first.worker_job_id != second.worker_job_id
        assert first.worker_target_db != second.worker_target_db
        # exactly two bound copies exist
        bound = [r for r in req.requests.values() if r["worker_job_id"] is not None]
        assert len(bound) == 2

    asyncio.run(run())
