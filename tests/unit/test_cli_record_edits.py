"""Owner/cohort partial-edit shared services and CLI surface (204-b).

Service level: honest fakes with locked-lookup call ordering, fresh merge
semantics, delegation to the shared complete-update helpers, exact
owner_updated/cohort_updated audits, and late-failure propagation.
CLI level: the actual Typer commands through a CliRunner with the private
async runners replaced (no database), covering the fixed no-echo error
law and safe resulting metadata output.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from typer.testing import CliRunner

from slaif_gateway.cli import cohorts as cohorts_cli
from slaif_gateway.cli import owners as owners_cli
from slaif_gateway.schemas.record_edits import (
    CohortUpdatePatch,
    OwnerUpdatePatch,
    parse_cohort_update_patch,
    parse_owner_update_patch,
)
from slaif_gateway.services.cohort_service import CohortService
from slaif_gateway.services.owner_service import OwnerService
from slaif_gateway.services.record_errors import (
    DuplicateRecordError,
    RecordNotFoundError,
    UnsupportedRecordOperationError,
)

CANARY = "sk-proj-canary204b0000000000000"
INST1 = uuid.uuid4()
INST2 = uuid.uuid4()
ACTOR = uuid.uuid4()
STAMP = datetime(2026, 10, 29, 12, 0, 0, tzinfo=UTC)

_runner = CliRunner()

# Renderer-stable terminal + ANSI/whitespace-independent assertions
# (established project pattern: tests/unit/test_cli.py,
# tests/unit/test_cli_key_batch.py).
_ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
TERM_ENV = {"COLUMNS": "220", "NO_COLOR": "1"}


def _plain(text: str) -> str:
    """ANSI-free, whitespace-normalized output for style-independent checks."""
    return " ".join(_ANSI_RE.sub("", text).split())


# --- honest fakes ----------------------------------------------------------


@dataclass
class _Row:
    id: uuid.UUID
    name: str
    surname: str | None = None
    email: str | None = None
    institution_id: uuid.UUID | None = None
    external_id: str | None = None
    notes: str | None = None
    is_active: bool = True
    description: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    created_at: datetime = STAMP
    updated_at: datetime = STAMP


class _FakeOwnersRepository:
    def __init__(self, owner: _Row | None) -> None:
        self.owner = owner
        self.calls: list[tuple[str, object]] = []
        self.by_email: dict[str, _Row] = {}
        self.update_kwargs: list[dict[str, object]] = []

    async def get_owner_by_id(self, owner_id: uuid.UUID) -> _Row | None:
        self.calls.append(("get_by_id", owner_id))
        return self.owner if self.owner and self.owner.id == owner_id else None

    async def get_owner_for_update(self, owner_id: uuid.UUID) -> _Row | None:
        self.calls.append(("get_for_update", owner_id))
        return self.owner if self.owner and self.owner.id == owner_id else None

    async def get_owner_by_email(self, email: str) -> _Row | None:
        return self.by_email.get(email)

    async def update_owner_metadata(self, owner_id: uuid.UUID, **kwargs: object) -> _Row | None:
        self.calls.append(("update", owner_id))
        self.update_kwargs.append(kwargs)
        if self.owner is None:
            return None
        self.owner = _Row(**{**self.owner.__dict__, **kwargs})
        return self.owner


class _FakeCohortsRepository:
    def __init__(self, cohort: _Row | None) -> None:
        self.cohort = cohort
        self.calls: list[tuple[str, object]] = []
        self.by_name: dict[str, _Row] = {}
        self.update_kwargs: list[dict[str, object]] = []

    async def get_cohort_by_id(self, cohort_id: uuid.UUID) -> _Row | None:
        self.calls.append(("get_by_id", cohort_id))
        return self.cohort if self.cohort and self.cohort.id == cohort_id else None

    async def get_cohort_for_update(self, cohort_id: uuid.UUID) -> _Row | None:
        self.calls.append(("get_for_update", cohort_id))
        return self.cohort if self.cohort and self.cohort.id == cohort_id else None

    async def get_cohort_by_name(self, name: str) -> _Row | None:
        return self.by_name.get(name)

    async def update_cohort_metadata(
        self, cohort_id: uuid.UUID, **kwargs: object
    ) -> _Row | None:
        self.calls.append(("update", cohort_id))
        self.update_kwargs.append(kwargs)
        if self.cohort is None:
            return None
        self.cohort = _Row(**{**self.cohort.__dict__, **kwargs})
        return self.cohort


class _FakeInstitutionsRepository:
    def __init__(self, institution_ids: set[uuid.UUID]) -> None:
        self.institution_ids = institution_ids

    async def get_institution_by_id(self, institution_id: uuid.UUID) -> object | None:
        return object() if institution_id in self.institution_ids else None


class _FakeAuditRepository:
    def __init__(self) -> None:
        self.audits: list[dict[str, object]] = []
        self.boom_at: int | None = None

    async def add_audit_log(self, **kwargs: object) -> None:
        if self.boom_at is not None and len(self.audits) + 1 == self.boom_at:
            raise RuntimeError("injected late audit failure (204b test)")
        self.audits.append(kwargs)


def _owner_service(owner: _Row | None, audit: _FakeAuditRepository | None = None) -> tuple[OwnerService, _FakeOwnersRepository, _FakeAuditRepository]:
    owners_repo = _FakeOwnersRepository(owner)
    if owner is not None:
        owners_repo.by_email[owner.email] = owner
    audit_repo = audit if audit is not None else _FakeAuditRepository()
    service = OwnerService(
        owners_repository=owners_repo,  # type: ignore[arg-type]
        institutions_repository=_FakeInstitutionsRepository({INST1, INST2}),  # type: ignore[arg-type]
        audit_repository=audit_repo,  # type: ignore[arg-type]
    )
    return service, owners_repo, audit_repo


def _cohort_service(cohort: _Row | None, audit: _FakeAuditRepository | None = None) -> tuple[CohortService, _FakeCohortsRepository, _FakeAuditRepository]:
    cohorts_repo = _FakeCohortsRepository(cohort)
    if cohort is not None:
        cohorts_repo.by_name[cohort.name] = cohort
    audit_repo = audit if audit is not None else _FakeAuditRepository()
    service = CohortService(
        cohorts_repository=cohorts_repo,  # type: ignore[arg-type]
        audit_repository=audit_repo,  # type: ignore[arg-type]
    )
    return service, cohorts_repo, audit_repo


def _async(coro):
    import asyncio

    return asyncio.run(coro)


def _owner_patch(**overrides) -> OwnerUpdatePatch:
    args: dict[str, object] = {
        "name": None, "surname": None, "email": None, "institution_id": None,
        "clear_institution": False, "external_id": None, "clear_external_id": False,
        "notes": None, "clear_notes": False, "active": False, "inactive": False,
        "actor_admin_id": None, "reason": "unit edit",
    }
    args.update(overrides)
    patch, _, _ = parse_owner_update_patch(**args)
    return patch


def _cohort_patch(**overrides) -> CohortUpdatePatch:
    args: dict[str, object] = {
        "name": None, "description": None, "clear_description": False,
        "starts_at": None, "clear_starts_at": False, "ends_at": None,
        "clear_ends_at": False, "actor_admin_id": None, "reason": "unit edit",
    }
    args.update(overrides)
    patch, _, _ = parse_cohort_update_patch(**args)
    return patch


# --- owner service ----------------------------------------------------------


def test_owner_partial_move_preserves_all_omitted_fields_and_locks_first() -> None:
    owner_id = uuid.uuid4()
    owner = _Row(
        id=owner_id, name="Ada", surname="L.", email="ada@example.org",
        institution_id=INST1, external_id="ext-orig", notes="orig note",
        is_active=False,
    )
    service, owners_repo, audit_repo = _owner_service(owner)

    updated = _async(
        service.update_owner_partial(
            owner_id, patch=_owner_patch(institution_id=str(INST2)),
            actor_admin_id=ACTOR, reason="move owner",
        )
    )

    # Lock FIRST, then write; the locked lookup is the fresh read.
    assert owners_repo.calls[0] == ("get_for_update", owner_id)
    assert ("get_for_update", owner_id) in owners_repo.calls
    assert owners_repo.calls[-1][0] == "update"

    kwargs = owners_repo.update_kwargs[0]
    # Provided field replaced, EVERY omitted field preserved (including
    # nullable values and is_active=False).
    assert kwargs["name"] == "Ada"
    assert kwargs["surname"] == "L."
    assert kwargs["email"] == "ada@example.org"
    assert kwargs["institution_id"] == INST2
    assert kwargs["external_id"] == "ext-orig"
    assert kwargs["notes"] == "orig note"
    assert kwargs["is_active"] is False
    assert updated.institution_id == INST2

    # Exactly one existing owner_updated audit with locked old/new,
    # reason, and actor.
    assert len(audit_repo.audits) == 1
    audit = audit_repo.audits[0]
    assert audit["action"] == "owner_updated"
    assert audit["entity_type"] == "owner"
    assert audit["entity_id"] == owner_id
    assert audit["admin_user_id"] == ACTOR
    assert audit["note"] == "move owner"
    assert audit["old_values"]["institution_id"] == str(INST1)
    assert audit["old_values"]["is_active"] is False
    assert audit["new_values"]["institution_id"] == str(INST2)
    assert audit["new_values"]["notes"] == "orig note"


def test_owner_partial_clears_only_nullable_fields() -> None:
    owner_id = uuid.uuid4()
    owner = _Row(
        id=owner_id, name="Ada", surname="L.", email="ada@example.org",
        institution_id=INST1, external_id="ext-orig", notes="orig note",
        is_active=True,
    )
    service, owners_repo, audit_repo = _owner_service(owner)
    _async(
        service.update_owner_partial(
            owner_id,
            patch=_owner_patch(
                clear_institution=True, clear_external_id=True, clear_notes=True
            ),
            reason="clear nullable fields",
        )
    )
    kwargs = owners_repo.update_kwargs[0]
    assert kwargs["institution_id"] is None
    assert kwargs["external_id"] is None
    assert kwargs["notes"] is None
    assert kwargs["is_active"] is True
    assert len(audit_repo.audits) == 1
    assert audit_repo.audits[0]["old_values"]["notes"] == "orig note"
    assert audit_repo.audits[0]["new_values"]["notes"] is None


def test_owner_partial_tri_state_active_inactive() -> None:
    owner_id = uuid.uuid4()
    owner = _Row(
        id=owner_id, name="Ada", surname="L.", email="ada@example.org",
        institution_id=None, external_id=None, notes=None, is_active=False,
    )
    service, owners_repo, _ = _owner_service(owner)
    _async(
        service.update_owner_partial(
            owner_id, patch=_owner_patch(active=True), reason="reactivate"
        )
    )
    assert owners_repo.update_kwargs[0]["is_active"] is True


def test_owner_partial_conflict_no_field_blank_reason_zero_access() -> None:
    owner_id = uuid.uuid4()
    owner = _Row(
        id=owner_id, name="Ada", surname="L.", email="ada@example.org",
        institution_id=INST1, external_id=None, notes=None, is_active=True,
    )
    service, owners_repo, audit_repo = _owner_service(owner)

    conflict = OwnerUpdatePatch(
        name=None, surname=None, email=None, institution_id=INST2,
        clear_institution=True, external_id=None, clear_external_id=False,
        notes=None, clear_notes=False, is_active=None,
    )
    with pytest.raises(ValueError, match="not both"):
        _async(service.update_owner_partial(owner_id, patch=conflict, reason="x"))
    no_field = OwnerUpdatePatch(
        name=None, surname=None, email=None, institution_id=None,
        clear_institution=False, external_id=None, clear_external_id=False,
        notes=None, clear_notes=False, is_active=None,
    )
    with pytest.raises(ValueError, match="at least one field"):
        _async(service.update_owner_partial(owner_id, patch=no_field, reason="x"))
    with pytest.raises(ValueError, match="audit reason"):
        _async(
            service.update_owner_partial(
                owner_id, patch=_owner_patch(external_id="e2"), reason="   "
            )
        )
    assert owners_repo.calls == []
    assert owners_repo.update_kwargs == []
    assert audit_repo.audits == []


def test_owner_partial_canary_reason_and_hand_built_field_refused_no_echo() -> None:
    owner_id = uuid.uuid4()
    owner = _Row(
        id=owner_id, name="Ada", surname="L.", email="ada@example.org",
        institution_id=INST1, external_id=None, notes=None, is_active=True,
    )
    service, owners_repo, audit_repo = _owner_service(owner)
    with pytest.raises(ValueError, match="secret-looking") as exc:
        _async(
            service.update_owner_partial(
                owner_id, patch=_owner_patch(external_id="e2"), reason=CANARY
            )
        )
    assert CANARY not in str(exc.value)
    bad = OwnerUpdatePatch(
        name=None, surname=None, email=None, institution_id=None,
        clear_institution=False, external_id=CANARY, clear_external_id=False,
        notes=None, clear_notes=False, is_active=None,
    )
    with pytest.raises(ValueError, match="secret-looking"):
        _async(service.update_owner_partial(owner_id, patch=bad, reason="ok"))
    assert owners_repo.update_kwargs == []
    assert audit_repo.audits == []


def test_owner_partial_hand_built_blank_replacements_refused() -> None:
    # 10b: a raw service caller may hand-build a patch with blank
    # nullable strings; the SHARED guard must refuse them (None=omit,
    # clear flags=clear) instead of silently clearing the stored field.
    owner_id = uuid.uuid4()
    owner = _Row(
        id=owner_id, name="Ada", surname="L.", email="ada@example.org",
        institution_id=INST1, external_id="ext-orig", notes="orig",
        is_active=True,
    )
    from dataclasses import replace

    for field in ("name", "surname", "email", "external_id", "notes"):
        service, owners_repo, audit_repo = _owner_service(owner)
        patch = replace(_owner_patch(institution_id=str(INST1)), **{field: "   "})
        with pytest.raises(ValueError, match="replacement cannot be empty") as exc:
            _async(
                service.update_owner_partial(
                    owner_id, patch=patch, reason="blank replacement"
                )
            )
        assert "   " not in str(exc.value)
        # the shared guard refuses BEFORE any repository access
        assert owners_repo.calls == []
        assert owners_repo.update_kwargs == []
        assert audit_repo.audits == []


def test_cohort_partial_hand_built_blank_replacements_refused() -> None:
    cohort_id = uuid.uuid4()
    cohort = _Row(id=cohort_id, name="C", description="keep",
                  starts_at=None, ends_at=None)
    from dataclasses import replace

    for field in ("name", "description"):
        service, cohorts_repo, audit_repo = _cohort_service(cohort)
        patch = replace(_cohort_patch(ends_at="2026-06-01T00:00:00Z"),
                        **{field: "  "})
        with pytest.raises(ValueError, match="replacement cannot be empty"):
            _async(
                service.update_cohort_partial(
                    cohort_id, patch=patch, reason="blank replacement"
                )
            )
        # the shared guard refuses BEFORE any repository access
        assert cohorts_repo.calls == []
        assert cohorts_repo.update_kwargs == []
        assert audit_repo.audits == []


def test_owner_partial_stored_canary_refused_on_unrelated_edit_and_clear() -> None:
    # Root item 8: an existing recognized-secret-shape value in the
    # SELECTED row must not pass into the new audit old/new snapshot or
    # the write, neither during an unrelated edit nor an explicit clear.
    for clear_notes in (False, True):
        owner_id = uuid.uuid4()
        owner = _Row(
            id=owner_id, name="Ada", surname="L.", email="ada@example.org",
            institution_id=INST1, external_id=None, notes=CANARY,
            is_active=True,
        )
        service, owners_repo, audit_repo = _owner_service(owner)
        patch = _owner_patch(
            clear_notes=clear_notes, external_id="new-ext"
        )
        with pytest.raises(ValueError, match="secret-looking") as exc:
            _async(
                service.update_owner_partial(
                    owner_id, patch=patch, reason="unrelated edit"
                )
            )
        assert CANARY not in str(exc.value)
        assert owners_repo.update_kwargs == []
        assert audit_repo.audits == []


def test_owner_partial_duplicate_email_and_unknown_institution() -> None:
    owner_id = uuid.uuid4()
    other_id = uuid.uuid4()
    owner = _Row(
        id=owner_id, name="Ada", surname="L.", email="ada@example.org",
        institution_id=INST1, external_id=None, notes=None, is_active=True,
    )
    service, owners_repo, audit_repo = _owner_service(owner)
    owners_repo.by_email["twin@example.org"] = _Row(
        id=other_id, name="Twin", email="twin@example.org",
    )
    with pytest.raises(DuplicateRecordError):
        _async(
            service.update_owner_partial(
                owner_id, patch=_owner_patch(email="Twin@example.org"),
                reason="take email",
            )
        )
    with pytest.raises(RecordNotFoundError):
        _async(
            service.update_owner_partial(
                owner_id, patch=_owner_patch(institution_id=str(uuid.uuid4())),
                reason="unknown institution",
            )
        )
    assert owners_repo.update_kwargs == []
    assert audit_repo.audits == []


def test_owner_partial_missing_row_and_late_audit_failure_propagate() -> None:
    service, _, audit_repo = _owner_service(None)
    with pytest.raises(RecordNotFoundError):
        _async(
            service.update_owner_partial(
                uuid.uuid4(), patch=_owner_patch(external_id="e"), reason="x"
            )
        )

    owner_id = uuid.uuid4()
    owner = _Row(
        id=owner_id, name="Ada", surname="L.", email="ada@example.org",
        institution_id=INST1, external_id=None, notes=None, is_active=True,
    )
    audit_repo.boom_at = 1
    service, owners_repo, _ = _owner_service(owner, audit_repo)
    with pytest.raises(RuntimeError, match="injected late audit failure"):
        _async(
            service.update_owner_partial(
                owner_id, patch=_owner_patch(external_id="e"), reason="late boom"
            )
        )
    # The write happened before the audit fault: the caller-owned
    # transaction rolls BOTH back (rollback proven at the PG layer).
    assert owners_repo.update_kwargs, "write must precede the audit fault"


def test_owner_complete_update_semantics_preserved() -> None:
    owner_id = uuid.uuid4()
    other_id = uuid.uuid4()
    owner = _Row(
        id=owner_id, name="Ada", surname="L.", email="ada@example.org",
        institution_id=INST1, external_id="ext", notes="n", is_active=True,
    )
    service, owners_repo, audit_repo = _owner_service(owner)
    updated = _async(
        service.update_owner(
            owner_id, name="Ada", surname="L.", email="ADA@Example.org",
            institution_id=INST2, external_id=None, notes=None,
            is_active=True, actor_admin_id=ACTOR, reason="full edit",
        )
    )
    assert updated.email == "ada@example.org"
    assert owners_repo.calls[0] == ("get_by_id", owner_id)
    assert ("get_for_update", owner_id) not in owners_repo.calls
    kwargs = owners_repo.update_kwargs[0]
    assert kwargs["institution_id"] == INST2
    assert kwargs["external_id"] is None
    assert len(audit_repo.audits) == 1
    assert audit_repo.audits[0]["note"] == "full edit"
    assert audit_repo.audits[0]["old_values"]["email"] == "ada@example.org"

    owners_repo.by_email["twin@example.org"] = _Row(
        id=other_id, name="Twin", email="twin@example.org",
    )
    with pytest.raises(DuplicateRecordError):
        _async(
            service.update_owner(
                owner_id, name="Ada", surname="L.", email="twin@example.org",
                institution_id=None,
            )
        )
    with pytest.raises(RecordNotFoundError):
        _async(
            service.update_owner(
                uuid.uuid4(), name="Ada", surname="L.", email="ada@example.org",
            )
        )


# --- cohort service ----------------------------------------------------------


def test_cohort_partial_rename_preserves_dates_and_description() -> None:
    cohort_id = uuid.uuid4()
    starts = datetime(2026, 1, 1, tzinfo=UTC)
    ends = datetime(2026, 12, 31, tzinfo=UTC)
    cohort = _Row(
        id=cohort_id, name="Old", description="keep me",
        starts_at=starts, ends_at=ends,
    )
    service, cohorts_repo, audit_repo = _cohort_service(cohort)
    _async(
        service.update_cohort_partial(
            cohort_id, patch=_cohort_patch(name="  New  "), reason="rename"
        )
    )
    assert cohorts_repo.calls[0] == ("get_for_update", cohort_id)
    kwargs = cohorts_repo.update_kwargs[0]
    assert kwargs["name"] == "New"
    assert kwargs["description"] == "keep me"
    assert kwargs["starts_at"] == starts
    assert kwargs["ends_at"] == ends
    assert len(audit_repo.audits) == 1
    audit = audit_repo.audits[0]
    assert audit["action"] == "cohort_updated"
    assert audit["old_values"]["name"] == "Old"
    assert audit["new_values"]["name"] == "New"
    assert audit["new_values"]["starts_at"] == starts.isoformat()


def test_cohort_partial_final_merged_window_refused() -> None:
    # Stored starts_at participates even when omitted: a one-field
    # ends_at patch below the stored start must refuse with zero
    # writes/audits.
    cohort_id = uuid.uuid4()
    cohort = _Row(
        id=cohort_id, name="C", description=None,
        starts_at=datetime(2026, 3, 1, tzinfo=UTC),
        ends_at=datetime(2026, 3, 31, tzinfo=UTC),
    )
    service, cohorts_repo, audit_repo = _cohort_service(cohort)
    with pytest.raises(ValueError, match="ends_at must be after starts_at"):
        _async(
            service.update_cohort_partial(
                cohort_id,
                patch=_cohort_patch(ends_at="2026-02-01T00:00:00Z"),
                reason="shrink window",
            )
        )
    assert cohorts_repo.update_kwargs == []
    assert audit_repo.audits == []


def test_cohort_partial_clears_and_member_relevant_fields() -> None:
    cohort_id = uuid.uuid4()
    cohort = _Row(
        id=cohort_id, name="C", description="d",
        starts_at=datetime(2026, 1, 1, tzinfo=UTC),
        ends_at=datetime(2026, 2, 1, tzinfo=UTC),
    )
    service, cohorts_repo, audit_repo = _cohort_service(cohort)
    _async(
        service.update_cohort_partial(
            cohort_id,
            patch=_cohort_patch(clear_starts_at=True, clear_ends_at=True,
                                 clear_description=True),
            reason="clear nullable window",
        )
    )
    kwargs = cohorts_repo.update_kwargs[0]
    assert kwargs["starts_at"] is None
    assert kwargs["ends_at"] is None
    assert kwargs["description"] is None
    assert kwargs["name"] == "C"
    assert audit_repo.audits[0]["old_values"]["ends_at"] is not None
    assert audit_repo.audits[0]["new_values"]["ends_at"] is None


def test_cohort_partial_duplicate_name_missing_and_late_audit_fault() -> None:
    cohort_id = uuid.uuid4()
    other_id = uuid.uuid4()
    cohort = _Row(id=cohort_id, name="Mine", description=None,
                  starts_at=None, ends_at=None)
    service, cohorts_repo, audit_repo = _cohort_service(cohort)
    cohorts_repo.by_name["Theirs"] = _Row(id=other_id, name="Theirs")
    with pytest.raises(DuplicateRecordError):
        _async(
            service.update_cohort_partial(
                cohort_id, patch=_cohort_patch(name="Theirs"), reason="steal"
            )
        )

    service_missing, _, _ = _cohort_service(None)
    with pytest.raises(RecordNotFoundError):
        _async(
            service_missing.update_cohort_partial(
                uuid.uuid4(), patch=_cohort_patch(description="x"), reason="x"
            )
        )

    audit_repo.boom_at = 1
    with pytest.raises(RuntimeError, match="injected late audit failure"):
        _async(
            service.update_cohort_partial(
                cohort_id, patch=_cohort_patch(description="x"), reason="boom"
            )
        )
    assert cohorts_repo.update_kwargs


def test_cohort_partial_stored_canary_refused_on_unrelated_edit_and_clear() -> None:
    for clear_description in (False, True):
        cohort_id = uuid.uuid4()
        cohort = _Row(id=cohort_id, name="C", description=CANARY,
                      starts_at=None, ends_at=None)
        service, cohorts_repo, audit_repo = _cohort_service(cohort)
        patch = _cohort_patch(
            clear_description=clear_description,
            ends_at="2026-06-01T00:00:00Z",
        )
        with pytest.raises(ValueError, match="secret-looking") as exc:
            _async(
                service.update_cohort_partial(
                    cohort_id, patch=patch, reason="unrelated edit"
                )
            )
        assert CANARY not in str(exc.value)
        assert cohorts_repo.update_kwargs == []
        assert audit_repo.audits == []


def test_cohort_complete_update_semantics_preserved() -> None:
    cohort_id = uuid.uuid4()
    cohort = _Row(id=cohort_id, name="C", description="d",
                  starts_at=None, ends_at=None)
    service, cohorts_repo, audit_repo = _cohort_service(cohort)
    with pytest.raises(UnsupportedRecordOperationError):
        _async(
            service.update_cohort(
                cohort_id, name="C", institution_id=uuid.uuid4()
            )
        )
    with pytest.raises(ValueError, match="ends_at must be after starts_at"):
        _async(
            service.update_cohort(
                cohort_id, name="C",
                starts_at=datetime(2026, 2, 1, tzinfo=UTC),
                ends_at=datetime(2026, 1, 1, tzinfo=UTC),
            )
        )
    updated = _async(
        service.update_cohort(
            cohort_id, name="  C2  ", description=None,
            actor_admin_id=ACTOR, reason="full edit",
        )
    )
    assert updated.name == "C2"
    assert cohorts_repo.calls[0] == ("get_by_id", cohort_id)
    assert ("get_for_update", cohort_id) not in cohorts_repo.calls
    assert len(audit_repo.audits) == 1
    assert audit_repo.audits[0]["note"] == "full edit"


# --- CLI surface (real Typer commands, runners replaced) --------------------


def _fake_owner() -> _Row:
    return _Row(
        id=uuid.uuid4(), name="Ada", surname="L.", email="ada@example.org",
        institution_id=INST2, external_id="ext-new", notes=None,
        is_active=False,
    )


def _fake_cohort() -> _Row:
    return _Row(
        id=uuid.uuid4(), name="Group", description="new",
        starts_at=None, ends_at=datetime(2026, 12, 31, tzinfo=UTC),
    )


def test_cli_owner_update_json_includes_external_id(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    async def _fake_update_owner(*, owner_id, patch, actor_admin_id, reason):
        captured.update(
            owner_id=owner_id, patch=patch, actor=actor_admin_id, reason=reason
        )
        return _fake_owner()

    monkeypatch.setattr(owners_cli, "_update_owner", _fake_update_owner)
    result = _runner.invoke(
        owners_cli.app,
        ["update", str(INST2), "--reason", "move owner",
         "--name", " Ada ", "--inactive",
         "--actor-admin-id", str(ACTOR), "--json"],
    )
    assert result.exit_code == 0, result.output
    payload = _json(result.stdout)
    assert payload["external_id"] == "ext-new"
    assert payload["institution_id"] == str(INST2)
    assert payload["is_active"] is False
    assert captured["owner_id"] == str(INST2)
    assert captured["reason"] == "move owner"
    assert captured["actor"] == ACTOR
    assert captured["patch"].name == "Ada"
    assert captured["patch"].is_active is False


def test_cli_owner_update_errors_are_fixed_and_no_echo(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _no_db(*, owner_id, patch, actor_admin_id, reason):
        raise AssertionError("database runner must not be reached")

    monkeypatch.setattr(owners_cli, "_update_owner", _no_db)

    base = ["update", str(uuid.uuid4())]
    cases = [
        (["--institution-id", str(INST1), "--clear-institution", "--reason", "x",
          "--json"],
         "invalid_value", "not both"),
        (["--reason", "x", "--json"], "invalid_value", "at least one field"),
        (["--notes", "  ", "--reason", "x", "--json"],
         "invalid_value", "cannot be empty"),
        (["--name", "n", "--reason", "  ", "--json"],
         "invalid_value", "audit reason"),
        (["--name", "n", "--actor-admin-id", "not-a-uuid", "--reason", "x",
          "--json"],
         "invalid_value", "valid UUID"),
        (["--name", "n", "--reason", CANARY, "--json"],
         "invalid_value", "secret-looking"),
    ]
    for extra, code, message in cases:
        result = _runner.invoke(owners_cli.app, base + extra, env={"NO_COLOR": "1"})
        assert result.exit_code == 1, (extra, result.output)
        payload = _json(result.stdout)
        assert payload["error"]["code"] == code, (extra, payload)
        assert message in payload["error"]["message"], (extra, payload)
    canary_result = _runner.invoke(
        owners_cli.app,
        base + ["--notes", CANARY, "--reason", "x"],
        env={"NO_COLOR": "1"},
    )
    assert CANARY not in canary_result.stdout
    assert CANARY not in (canary_result.stderr or "")


def test_cli_owner_update_reason_is_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # CI sets GITHUB_ACTIONS, so typer's rich console forces terminal
    # styling and interleaves per-segment ANSI codes inside the option
    # name (the literal flag is never contiguous in raw output). Force
    # the same ANSI-rich rendering test-locally and assert on the
    # ANSI/whitespace-independent form.
    import typer.rich_utils as _rich_utils

    monkeypatch.setattr(_rich_utils, "FORCE_TERMINAL", True)
    result = _runner.invoke(
        owners_cli.app,
        ["update", str(uuid.uuid4()), "--name", "n"],
        env=TERM_ENV,
    )
    # Typer missing-required-option error (click usage error), non-zero.
    assert result.exit_code != 0
    assert "--reason" in _plain(result.output or "")


def test_cli_cohort_update_json_and_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    async def _fake_update_cohort(*, cohort_id, patch, actor_admin_id, reason):
        captured.update(cohort_id=cohort_id, patch=patch, reason=reason)
        return _fake_cohort()

    monkeypatch.setattr(cohorts_cli, "_update_cohort", _fake_update_cohort)
    cohort_id = uuid.uuid4()
    result = _runner.invoke(
        cohorts_cli.app,
        ["update", str(cohort_id), "--reason", "extend window",
         "--ends-at", "2026-12-31T00:00:00Z", "--clear-starts-at", "--json"],
    )
    assert result.exit_code == 0, result.output
    payload = _json(result.stdout)
    assert payload["name"] == "Group"
    assert payload["ends_at"] == "2026-12-31T00:00:00+00:00"
    assert captured["patch"].clear_starts_at is True
    assert captured["reason"] == "extend window"

    async def _no_db(*, cohort_id, patch, actor_admin_id, reason):
        raise AssertionError("database runner must not be reached")

    monkeypatch.setattr(cohorts_cli, "_update_cohort", _no_db)
    base = ["update", str(cohort_id)]
    cases = [
        (["--description", "d", "--clear-description", "--reason", "x",
          "--json"],
         "not both"),
        (["--reason", "x", "--json"], "at least one field"),
        (["--starts-at", "nope", "--reason", "x", "--json"], "ISO datetime"),
        (["--name", "a", "--ends-at", "2026-01-01T00:00:00Z",
          "--starts-at", "2026-02-01T00:00:00Z", "--reason", "x",
          "--json"],
         "ends_at must be after starts_at"),
        (["--description", CANARY, "--reason", "x", "--json"],
         "secret-looking"),
    ]
    for extra, message in cases:
        result = _runner.invoke(
            cohorts_cli.app, base + extra, env={"NO_COLOR": "1"}
        )
        assert result.exit_code == 1, (extra, result.output)
        payload = _json(result.stdout)
        assert message in payload["error"]["message"], (extra, payload)


def _json(stdout: str) -> dict[str, object]:
    import json

    return json.loads(stdout)
