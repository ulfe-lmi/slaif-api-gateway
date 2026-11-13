"""224-k unit evidence (pure): the demo-only catalog index projection.

Database-independent: ``_project_catalog_index`` is tested directly on
synthetic leaf rows shaped exactly like the verified target-only
``demo_display`` index (remapped names, closed kinds, byte counts,
capture times). Every display value that fails the closed remapped
name law, the bounded kind/size law or the finite representable-time
law must fail the WHOLE page safely (ValueError -> fixed safe
unavailable note upstream) instead of being rendered.
"""

from __future__ import annotations

import pytest

from slaif_gateway.api.demo_admin_catalog import _project_catalog_index

RUN_ID = "demo-run-" + "a1" * 12  # worker _demo_run_id shape (24 hex)
JOB_ID = "b2" * 16  # worker _demo_job_id shape (32 hex)


def _leaf(name: str, kind: str = "refresh_bundle", size: int = 1, at: float = 1750000000.0):
    return {
        "logical_name": name,
        "kind": kind,
        "byte_count": size,
        "captured_at": at,
    }


def test_project_canonical_catalog_areas():
    rows = _project_catalog_index(
        [
            _leaf(f"catalog/runs/{RUN_ID}/catalog-refresh.json", "refresh_bundle", 1234567, 1750000000.0),
            _leaf(f"catalog/jobs/{JOB_ID}.json", "job_record", 42, 1750000010.0),
            _leaf(f"catalog/uploads/{JOB_ID}/bundle-{JOB_ID}", "refresh_bundle", 12, 1750000020.0),
            _leaf(
                f"catalog/proposals/{JOB_ID}/packages/openrouter-chat-text/routes-proposal.tsv",
                "route_tsv",
                88,
                1750000030.0,
            ),
            # Non-catalog leaves share the verified target table but
            # are NOT catalog artifacts: silently skipped, not shown.
            _leaf("branding/logo", "branding", 9, 1750000000.0),
            _leaf("profiles/upstream-llm.json", "upstream_llm_profiles", 9, 1750000000.0),
        ]
    )
    assert len(rows) == 4
    assert [r["area"] for r in rows] == ["runs", "jobs", "uploads", "proposals"]
    run_row = rows[0]
    assert run_row["demo_id"] == RUN_ID
    assert run_row["artifact"] == "catalog-refresh.json"
    assert run_row["kind"] == "refresh_bundle"
    assert run_row["byte_count"] == 1234567
    assert run_row["captured_utc"] == "2025-06-15 15:06:40 UTC"
    assert run_row["captured_sort"] == "2025-06-15T15:06:40+00:00"
    assert rows[1]["demo_id"] == JOB_ID
    assert rows[1]["artifact"] == f"{JOB_ID}.json"
    assert rows[2]["artifact"] == f"bundle-{JOB_ID}"
    assert rows[3]["artifact"] == "packages/openrouter-chat-text/routes-proposal.tsv"
    # No raw composite name ever survives into a row.
    for r in rows:
        assert "logical_name" not in r


def test_project_empty_and_noncatalog_only():
    assert _project_catalog_index([]) == []
    assert _project_catalog_index([_leaf("branding/logo", "branding")]) == []


def test_project_rejects_source_like_run_id():
    # An ORIGINAL (non-remapped) run id is source-shaped and must fail
    # the whole index, never render.
    with pytest.raises(ValueError):
        _project_catalog_index([_leaf(f"catalog/runs/{JOB_ID}/catalog-refresh.json")])
    with pytest.raises(ValueError):
        _project_catalog_index(
            [_leaf(f"catalog/runs/demo-run-{JOB_ID}/catalog-refresh.json")]  # 32 hex, not 24
        )
    with pytest.raises(ValueError):
        _project_catalog_index([_leaf(f"catalog/runs/{RUN_ID}/../../secret.txt")])


def test_project_rejects_bad_areas_and_traversal():
    for bad in (
        f"catalog/other/{JOB_ID}",
        f"catalog/runs/{RUN_ID}",
        f"catalog/jobs/{JOB_ID}.json/extra",
        f"catalog/jobs/{JOB_ID[:-1]}x.json",
        f"catalog/uploads/{JOB_ID}",
        f"catalog/proposals/{JOB_ID}",
        "catalog/../../../etc/passwd",
        f"catalog/proposals/{JOB_ID}/packages/x/y/../../z",
        "catalog/runs/demo-run-a1/short-hex",
    ):
        with pytest.raises(ValueError):
            _project_catalog_index([_leaf(bad)])


def test_project_rejects_overlong_name():
    # Worker display-name ceiling (200): a corrupted target row with an
    # enormous catalog name fails the whole page safely.
    ok = f"catalog/jobs/{JOB_ID}.json"
    assert len(ok) <= 200
    with pytest.raises(ValueError):
        _project_catalog_index([_leaf(ok + "x" * 200)])


def test_project_rejects_bad_kind_size_time():
    good = f"catalog/jobs/{JOB_ID}.json"
    cases = [
        _leaf(good, kind="Refresh_Bundle"),   # uppercase kind
        _leaf(good, kind="a" * 65),           # unbounded kind length
        _leaf(good, size=-1),                 # negative size
        _leaf(good, size=True),               # bool is not a size
        _leaf(good, size=2**31 + 1),           # above the size bound
        _leaf(good, size="12"),               # not an int
        _leaf(good, at=float("nan")),         # non-finite time
        _leaf(good, at=float("inf")),
        _leaf(good, at=True),                 # bool is not a time
        _leaf(good, at=9.0e15),               # finite, unrepresentable
        _leaf(good, at=-1),                   # negative epoch
    ]
    for bad in cases:
        with pytest.raises(ValueError):
            _project_catalog_index([bad])


def test_project_rejects_malformed_container_and_leaf():
    with pytest.raises(ValueError):
        _project_catalog_index("not-a-list")
    with pytest.raises(ValueError):
        _project_catalog_index([["catalog/jobs"], {"not": "a leaf"}])
    with pytest.raises(ValueError):
        _project_catalog_index(
            [_leaf(f"catalog/jobs/{JOB_ID}.json")] * 4097  # above the row bound
        )
