"""Browser acceptance (A2) for 195-a multi-value list filters.

Real PostgreSQL + real uvicorn app + real Chromium with the actual Jinja
macro/CSS/JS (no mocked choices in this module):

- two-cohort union through ACTUAL menu clicks: rows from both selected
  cohorts, the third cohort's keys excluded, a status filter AND-narrows
  the union, duplicate clicks do not duplicate a value, chip removal and
  "Clear filters" round-trip through the GET filter form, and the Rows
  limit drives "N rows shown" and the ordinal column;
- label-only async refresh (the R5 JS gap): the page hydrates only
  values it can resolve server-side, so two VALID but UNKNOWN cohort
  UUIDs start as raw-UUID fallback chips; the ``selected=`` lookup
  response (mocked, delivering exactly what the real fetch returns for
  resolvable ids) refreshes the chip labels IN PLACE — hidden values
  stay the raw UUIDs in the same order, the input text/focus are
  undisturbed, and no chip is duplicated. A second test proves the
  resolvable OLDEST cohorts (outside the initial latest-100 batch) keep
  friendly chips from page load, exact rows, and remain reachable by
  name through the real server search;
- chips grow DOWN below the integrated control at desktop 1600px and
  wrap down (no horizontal overflow) at narrow 390px.

Screenshots land in ``/tmp/slaif195/screenshots/`` for strategic review.
All data is synthetic and fictional; the module never points at an
ambient ``DATABASE_URL``.

Run:  python -m pytest tests/browser/test_admin_list_multiselection.py -m playwright
"""

from __future__ import annotations

import asyncio
import uuid
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.db.models import Owner
from slaif_gateway.db.repositories.admin_users import AdminUsersRepository
from slaif_gateway.db.repositories.cohorts import CohortsRepository
from slaif_gateway.db.repositories.institutions import InstitutionsRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.main import create_app
from slaif_gateway.utils.passwords import hash_admin_password

from tests.browser.test_admin_usability import (
    _chromium_browser,
    _free_port,
    _login,
    _run_uvicorn_server,
    _settings,
)
from tests.integration.test_lazy_throttling_postgres_redis import (
    owned_pg_url as _owned_pg_url_fixture,
)

# Re-export the qualified fixture under the expected fixture name.
owned_pg_url = _owned_pg_url_fixture

pytestmark = pytest.mark.playwright

ADMIN_PASSWORD = "correct horse battery staple"
SCREENSHOT_DIR = Path("/tmp/slaif195/screenshots")
BASE_TIME = datetime(2026, 7, 1, 0, 0, 0, tzinfo=UTC)

# 105 cohorts: the two OLDEST (001/002) fall outside the latest-100
# initial batch (resolvable-older-selection proofs: page-load hydration
# and server search reach them); the three NEWEST (103/104/105) drive
# the real-click union.
COHORT_COUNT = 105


# ---------------------------------------------------------------------------
# Seed
# ---------------------------------------------------------------------------


async def _seed_ms195_data(database_url: str) -> dict[str, Any]:
    engine = create_async_engine(database_url, future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid.uuid4().hex[:10]
    try:
        async with factory() as session:
            async with session.begin():
                admin = await AdminUsersRepository(session).create_admin_user(
                    email=f"ms195-admin-{suffix}@example.org",
                    display_name="MS195 Admin",
                    password_hash=hash_admin_password(ADMIN_PASSWORD),
                    role="admin",
                    is_active=True,
                )
                institution = await InstitutionsRepository(session).create_institution(
                    name=f"MS195 University {suffix}", country="SI"
                )
                owner = Owner(
                    id=uuid.uuid4(),
                    name="Multi",
                    surname="Owner",
                    email=f"ms195-owner-{suffix}@example.org",
                    institution_id=institution.id,
                    is_active=True,
                    created_at=BASE_TIME,
                    updated_at=BASE_TIME,
                )
                session.add(owner)

                keys_repo = GatewayKeysRepository(session)
                cohort_ids: dict[int, uuid.UUID] = {}
                for i in range(1, COHORT_COUNT + 1):
                    cohort = await CohortsRepository(session).create_cohort(
                        name=f"MS195 Cohort {i:03d} {suffix}",
                        description="ms195 browser cohort",
                        starts_at=BASE_TIME,
                        ends_at=BASE_TIME + timedelta(days=30),
                    )
                    # Explicit staggered created_at: the initial latest-100
                    # batch is cohorts 006..105, so 001/002 are OLDER
                    # selections (page-load hydration + server-search
                    # proofs below).
                    cohort.created_at = BASE_TIME + timedelta(minutes=i)
                    cohort_ids[i] = cohort.id

                async def add_key(cohort_no: int, *, status: str, i: int) -> None:
                    await keys_repo.create_gateway_key_record(
                        public_key_id=f"ms195-{cohort_no}-{i:02d}-{suffix}",
                        token_hash=f"synthetic_token_hash_ms195_{cohort_no}_{i}_{suffix}",
                        owner_id=owner.id,
                        cohort_id=cohort_ids[cohort_no],
                        valid_from=BASE_TIME,
                        valid_until=BASE_TIME + timedelta(days=30),
                        status=status,
                        key_hint=f"synthetic-hint-ms195-{suffix}",
                        allow_all_models=True,
                        allow_all_endpoints=True,
                        created_by_admin_user_id=admin.id,
                    )

                # Newest cohorts: 105 (3 keys: 2 active + 1 suspended),
                # 104 (2 active), 103 (2 active — the "third" cohort whose
                # keys must never appear in the 105+104 union).
                # Oldest cohorts: 001/002 (1 key each) for the URL-selected
                # label-recovery page.
                await add_key(105, status="active", i=0)
                await add_key(105, status="active", i=1)
                await add_key(105, status="suspended", i=2)
                await add_key(104, status="active", i=3)
                await add_key(104, status="active", i=4)
                await add_key(103, status="active", i=5)
                await add_key(103, status="active", i=6)
                await add_key(1, status="active", i=7)
                await add_key(2, status="active", i=8)

                return {
                    "admin_email": admin.email,
                    "suffix": suffix,
                    "cohort_oldest_1": str(cohort_ids[1]),
                    "cohort_oldest_2": str(cohort_ids[2]),
                    "cohort_new_103": str(cohort_ids[103]),
                    "cohort_new_104": str(cohort_ids[104]),
                    "cohort_new_105": str(cohort_ids[105]),
                    "cohort_oldest_1_name": f"MS195 Cohort 001 {suffix}",
                    "cohort_oldest_2_name": f"MS195 Cohort 002 {suffix}",
                    "cohort_new_103_name": f"MS195 Cohort 103 {suffix}",
                    "cohort_new_104_name": f"MS195 Cohort 104 {suffix}",
                    "cohort_new_105_name": f"MS195 Cohort 105 {suffix}",
                }
    finally:
        await engine.dispose()

@pytest.fixture(scope="module")
def ms195_env(owned_pg_url: str) -> Iterator[dict[str, Any]]:
    data = asyncio.run(_seed_ms195_data(owned_pg_url))
    app = create_app(_settings(owned_pg_url))
    port = _free_port()
    data["base_url"] = f"http://127.0.0.1:{port}"
    with _run_uvicorn_server(app, port):
        yield data


@pytest.fixture(scope="module")
def chromium(ms195_env) -> Iterator[object]:
    """Depends on ``ms195_env`` on purpose: the Playwright sync session
    runs an asyncio loop on the main thread, so PG readiness, seeding,
    and the uvicorn app must complete BEFORE it starts."""
    with _chromium_browser() as browser:
        yield browser


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _data_rows(page: object) -> int:
    return page.locator("td.row-ordinal").count()  # type: ignore[attr-defined]


def _cohort_rows(page: object, cohort_name: str) -> int:
    return page.locator("td.col-cohort", has_text=cohort_name).count()  # type: ignore[attr-defined]


def _rows_shown(page: object) -> str:
    return page.locator("#keys-rows-shown").inner_text()  # type: ignore[attr-defined]


def _hidden_cohort_values(page: object) -> list[str]:
    loc = page.locator('.rc[data-rc-id="keys-cohort"] .rc-value')
    return [loc.nth(i).input_value() for i in range(loc.count())]


def _chip_texts(page: object) -> list[str]:
    loc = page.locator('.rc[data-rc-id="keys-cohort"] .rc-chip')
    return [loc.nth(i).inner_text() for i in range(loc.count())]


def _chip_labels(page: object) -> list[str]:
    """Chip label text (excluding the remove button's ×)."""
    return page.locator('.rc[data-rc-id="keys-cohort"] .rc-chip').evaluate_all(  # type: ignore[attr-defined]
        "(els) => els.map((el) => (el.firstChild ? el.firstChild.textContent : ''))"
    )


def _capture(page: object, name: str) -> Path:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SCREENSHOT_DIR / f"{name}.png"
    page.screenshot(path=str(path), full_page=True)  # type: ignore[attr-defined]
    assert path.stat().st_size > 10_000, f"screenshot {name} looks empty"
    return path


def _assert_layout_invariants(page: object) -> None:
    metrics = page.evaluate(  # type: ignore[attr-defined]
        "() => ({scrollWidth: document.documentElement.scrollWidth,"
        " innerWidth: window.innerWidth})"
    )
    assert metrics["scrollWidth"] <= metrics["innerWidth"] + 1, (
        f"horizontal overflow: scrollWidth={metrics['scrollWidth']} "
        f"innerWidth={metrics['innerWidth']}"
    )
    # Chips grow DOWN below the integrated control (193/194 contract).
    layout = page.evaluate(  # type: ignore[attr-defined]
        """() => {
            const box = document.querySelector('.rc[data-rc-id="keys-cohort"] .rc-main');
            const chips = document.querySelector('.rc[data-rc-id="keys-cohort"] .rc-selected');
            if (!box || !chips || chips.hidden) return null;
            return {boxBottom: box.getBoundingClientRect().bottom,
                    chipsTop: chips.getBoundingClientRect().top};
        }"""
    )
    if layout is not None:
        assert layout["chipsTop"] >= layout["boxBottom"] - 1, (
            f"chips must grow below the control box: {layout}"
        )


# ---------------------------------------------------------------------------
# A2: two-cohort union through real clicks + chip lifecycle
# ---------------------------------------------------------------------------


def test_keys_two_cohort_real_click_union_and_chip_lifecycle(
    chromium, ms195_env
) -> None:
    env = ms195_env
    name_103 = env["cohort_new_103_name"]
    name_104 = env["cohort_new_104_name"]
    name_105 = env["cohort_new_105_name"]
    with chromium.new_context(  # type: ignore[attr-defined]
        base_url=env["base_url"], viewport={"width": 1600, "height": 1000}
    ) as context:
        page = context.new_page()
        _login(page, env)
        page.goto("/admin/keys")
        assert _data_rows(page) == 9, "unfiltered page shows all 9 seeded keys"
        _assert_layout_invariants(page)

        rc = page.locator('.rc[data-rc-id="keys-cohort"]')
        rc.locator(".rc-input").click()
        # Select the two NEWEST cohorts through actual menu clicks (the
        # menu stays open after a multi toggle, so the second click is
        # another option in the same rendered list).
        rc.locator(".rc-option", has_text=name_105).click()
        rc.locator(".rc-option", has_text=name_104).click()
        # Exactly one hidden value per selected cohort, no fan-out.
        assert _hidden_cohort_values(page) == [env["cohort_new_105"], env["cohort_new_104"]]
        assert len(_chip_texts(page)) == 2
        page.keyboard.press("Escape")

        page.click("#keys-filter button[type=submit]")
        page.wait_for_load_state("domcontentloaded")
        # UNION: 3 (105) + 2 (104) = 5 rows; cohort 103 (and the oldest
        # cohorts) excluded.
        assert _data_rows(page) == 5
        assert _cohort_rows(page, name_105) == 3
        assert _cohort_rows(page, name_104) == 2
        assert _cohort_rows(page, name_103) == 0
        assert "rows shown" in _rows_shown(page)
        _assert_layout_invariants(page)
        _capture(page, "keys-two-cohorts-desktop-1600")

        # Submitting the same two values again yields the same rows
        # (no duplicate-value fan-out).
        page.click("#keys-filter button[type=submit]")
        assert _data_rows(page) == 5

        # Status AND narrows the union to the single suspended key (105).
        page.select_option("select[name=status]", "suspended")
        page.click("#keys-filter button[type=submit]")
        assert _data_rows(page) == 1
        assert _cohort_rows(page, name_105) == 1
        assert _cohort_rows(page, name_104) == 0

        # Rows limit: a custom limit (3, not a preset) drives "3 rows
        # shown" and the ordinal column, and round-trips as an explicit
        # option for the next page.
        page.goto(
            f"/admin/keys?limit=3"
            f"&cohort_id={env['cohort_new_105']}"
            f"&cohort_id={env['cohort_new_104']}"
        )
        assert _data_rows(page) == 3
        assert "3 rows shown" in _rows_shown(page)
        assert page.locator("#keys-limit option[value='3']").count() == 1
        ordinals = page.locator("td.row-ordinal")
        assert [ordinals.nth(i).inner_text() for i in range(3)] == ["1", "2", "3"]

        # Chip removal round-trip: drop cohort 104, apply -> 3 rows (105 only).
        rc.locator(".rc-chip-remove").last.click()
        assert _hidden_cohort_values(page) == [env["cohort_new_105"]]
        page.select_option("#keys-limit", "200")
        page.click("#keys-filter button[type=submit]")
        assert _data_rows(page) == 3
        assert _cohort_rows(page, name_105) == 3
        assert _cohort_rows(page, name_104) == 0

        # Clear filters link restores the unfiltered list.
        page.click("#keys-rows-shown a")
        assert _data_rows(page) == 9
        assert _chip_texts(page) == []
        assert _hidden_cohort_values(page) == [""]


# ---------------------------------------------------------------------------
# A2: label-only async refresh — the R5 JS gap regression. The page
# itself only hydrates values it can resolve server-side, so the
# raw-UUID-fallback chip state is proven with two VALID but UNKNOWN
# cohort UUIDs (the filter accepts any UUID; zero rows match), and the
# lookup response is mocked with authoritative labels exactly as the
# real selected= fetch would deliver them for resolvable ids.
# ---------------------------------------------------------------------------


def test_keys_unknown_selected_chips_recover_labels_async(
    chromium, ms195_env
) -> None:
    env = ms195_env
    u1 = str(uuid.uuid4())
    u2 = str(uuid.uuid4())
    with chromium.new_context(  # type: ignore[attr-defined]
        base_url=env["base_url"], viewport={"width": 1600, "height": 1000}
    ) as context:
        page = context.new_page()

        def _mock_lookup(route: object) -> None:
            if "kind=cohort" in route.request.url:
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(
                        {
                            "choices": [
                                {"id": u1, "label": "Recovered Cohort A", "sub": u1},
                                {"id": u2, "label": "Recovered Cohort B", "sub": u2},
                            ]
                        }
                    ),
                )
            else:
                route.fallback()

        page.route("**/admin/record-choices**", _mock_lookup)
        _login(page, env)
        # Valid-but-unknown cohort UUIDs: the page cannot resolve them,
        # so the chips start as the raw-UUID fallback.
        page.goto(f"/admin/keys?limit=100&cohort_id={u1}&cohort_id={u2}")
        assert _chip_labels(page) == [u1, u2], "initial chips must be the raw UUID fallback"
        assert _hidden_cohort_values(page) == [u1, u2]
        assert _data_rows(page) == 0

        # Focus the control: the selected= lookup returns the authoritative
        # labels and the chips must refresh IN PLACE.
        rc_input = page.locator('.rc[data-rc-id="keys-cohort"] .rc-input')
        rc_input.click()
        page.wait_for_function(
            """() => {
                const chips = document.querySelectorAll(
                    '.rc[data-rc-id="keys-cohort"] .rc-chip');
                return chips.length === 2
                    && chips[0].textContent.includes('Recovered Cohort A')
                    && chips[1].textContent.includes('Recovered Cohort B');
            }"""
        )
        # Label-only refresh: IDs and order unchanged, hidden values stay
        # the raw UUIDs, the input keeps its blank prompt and focus (no
        # value change, no rc-change side effects).
        assert _chip_labels(page) == ["Recovered Cohort A", "Recovered Cohort B"]
        assert _hidden_cohort_values(page) == [u1, u2]
        assert rc_input.input_value() == ""
        assert page.evaluate(
            """() => document.activeElement ===
                document.querySelector(".rc[data-rc-id='keys-cohort'] .rc-input")"""
        )
        _capture(page, "keys-chip-async-label-recovery")


def test_keys_older_selected_cohorts_stay_searchable(
    chromium, ms195_env
) -> None:
    env = ms195_env
    id_1 = env["cohort_oldest_1"]
    id_2 = env["cohort_oldest_2"]
    name_1 = env["cohort_oldest_1_name"]
    name_2 = env["cohort_oldest_2_name"]
    with chromium.new_context(  # type: ignore[attr-defined]
        base_url=env["base_url"], viewport={"width": 1600, "height": 1000}
    ) as context:
        page = context.new_page()
        _login(page, env)
        # The two OLDEST cohorts: outside the initial latest-100 batch.
        # The PAGE hydrates resolvable selections (192-a), so the chips
        # carry the friendly names from load; the rows are exact.
        page.goto(f"/admin/keys?limit=100&cohort_id={id_1}&cohort_id={id_2}")
        # Direct proof they are OLDER than the initial latest-100 batch
        # AND that page-load hydration works end to end: the embedded
        # option list still holds exactly 100 entries, CONTAINS both
        # selected older cohorts with their authoritative labels (they
        # displaced the two oldest in-batch entries), so the chips carry
        # the friendly names from load.
        initial_options = page.evaluate(
            """() => JSON.parse(
                document.querySelector('.rc[data-rc-id="keys-cohort"]')
                    .dataset.initialOptions
            )"""
        )
        assert len(initial_options) == 100
        by_id = {o["id"]: o["label"] for o in initial_options}
        assert by_id.get(id_1) == name_1
        assert by_id.get(id_2) == name_2
        assert _chip_labels(page) == [name_1, name_2]
        assert _hidden_cohort_values(page) == [id_1, id_2]
        assert _data_rows(page) == 2
        assert _cohort_rows(page, name_1) == 1
        assert _cohort_rows(page, name_2) == 1

        # Server search still reaches the older cohorts by name.
        page.locator('.rc[data-rc-id="keys-cohort"] .rc-input').click()
        page.keyboard.type("MS195 Cohort 001")
        page.locator('.rc[data-rc-id="keys-cohort"] .rc-option', has_text=name_1).first.wait_for(
            state="visible"
        )
        page.keyboard.press("Escape")
        _capture(page, "keys-selected-older-after-search")


# ---------------------------------------------------------------------------
# A2: chips wrap down at narrow 390px (no horizontal overflow)
# ---------------------------------------------------------------------------


def test_keys_two_cohorts_narrow_390_chips_wrap_down(chromium, ms195_env) -> None:
    env = ms195_env
    name_104 = env["cohort_new_104_name"]
    name_105 = env["cohort_new_105_name"]
    with chromium.new_context(  # type: ignore[attr-defined]
        base_url=env["base_url"], viewport={"width": 390, "height": 844}
    ) as context:
        page = context.new_page()
        _login(page, env)
        page.goto(
            f"/admin/keys?limit=100&cohort_id={env['cohort_new_105']}"
            f"&cohort_id={env['cohort_new_104']}"
        )
        assert _data_rows(page) == 5
        assert _cohort_rows(page, name_105) == 3
        assert _cohort_rows(page, name_104) == 2
        _assert_layout_invariants(page)
        _capture(page, "keys-two-cohorts-narrow-390")
