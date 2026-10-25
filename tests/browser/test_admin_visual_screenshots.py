"""A1 visual acceptance screenshots for objective 193-a.

Real rendered, authenticated dashboard + keys list on the already-qualified
owned PostgreSQL fixture (shared module-scoped fixtures from
``tests/browser/test_admin_usability.py``: owned PG16, seeded synthetic
data, real uvicorn app, real Chromium). For each viewport this suite

- logs in through the real admin login form;
- renders the actual dashboard and the keys list;
- asserts the R1 dashboard contract (product heading inside the dashboard
  body, Administration eyebrow, the three destination groups, and no
  implementation-oriented "Dashboard Foundation" prose);
- asserts the A2 unified control geometry on the real keys filter bar
  (native filter selects and integrated record-choice boxes share
  14px/400 value typography, 13px/600 muted labels, 42px height and the
  shared control radius);
- asserts A3 header controls are ``a.ts-link`` hyperlinks, never buttons;
- asserts no horizontal overflow and that the CONTENT PANEL
  (``.dashboard-shell``) stays top-anchored below the shared header for
  both the short dashboard and the long keys list - measuring the panel,
  not the ``#admin-main`` flex container, so a resurrected
  ``justify-content: safe center`` on ``.page-shell`` would fail;
- proves the R2 grow-down behavior on the real keys page: selecting a
  known synthetic owner chip (real mouse selection, no forced clicks)
  adds the chip row BELOW the primary controls - panel top, control top,
  and Filter button top stay unchanged while the table moves DOWN - and
  removing the chip restores the layout;
- captures full-page screenshots (including the selected-chip state)
  into ``/tmp/slaif193/screenshots/`` for strategic review (the directory
  is a local review-artifact location; the test never fails a run because
  of screenshot review).

Safety: the keys list displays only ``key_prefix`` + opaque public key id
and synthetic owner metadata; one-time plaintext key cells, CSRF values,
session cookies, and real personal data are never read, logged, or
screenshotted.

Run:  python -m pytest tests/browser/test_admin_visual_screenshots.py -m playwright
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.browser.test_admin_usability import (
    _login,
    chromium,  # noqa: F401  (pytest fixture, bound via test parameters below)
    owned_pg_url,  # noqa: F401  (fixture dependency of usab_env)
    usab_env,  # noqa: F401  (pytest fixture, bound via test parameters below)
)

pytestmark = pytest.mark.playwright

SCREENSHOT_DIR = Path("/tmp/slaif193/screenshots")

GROUP_HEADINGS = ("Access management", "Providers and models", "Usage and operations")

# (name, width, height): desktop 1440/1600 and narrow 390/768 per order A1.
VIEWPORTS = (
    ("desktop-1440", 1440, 900),
    ("desktop-1600", 1600, 1000),
    ("tablet-768", 768, 1024),
    ("narrow-390", 390, 844),
)


def _assert_no_horizontal_overflow(page: object) -> None:
    metrics = page.evaluate(  # type: ignore[attr-defined]
        "() => ({scrollWidth: document.documentElement.scrollWidth,"
        " innerWidth: window.innerWidth})"
    )
    assert metrics["scrollWidth"] <= metrics["innerWidth"] + 1, (
        f"horizontal overflow: scrollWidth={metrics['scrollWidth']} "
        f"innerWidth={metrics['innerWidth']}"
    )


def _assert_top_anchored(page: object) -> None:
    """The CONTENT PANEL starts directly below the shared header (the
    ``.page-shell`` padding), never vertically centered. Measuring
    ``.dashboard-shell`` (not ``#admin-main``) is deliberate: the flex
    container always starts below the header, so only the panel proves
    the top-anchoring of the visible content (R2)."""
    layout = page.evaluate(  # type: ignore[attr-defined]
        """() => {
            const header = document.querySelector('.admin-header');
            const panel = document.querySelector('.dashboard-shell');
            return {
                headerBottom: header.getBoundingClientRect().bottom,
                panelTop: panel.getBoundingClientRect().top,
            };
        }"""
    )
    gap = layout["panelTop"] - layout["headerBottom"]
    assert 0 <= gap <= 60, (
        f"admin content panel must stay top-anchored below the header, "
        f"got gap={gap}px"
    )


def _capture(page: object, name: str) -> Path:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SCREENSHOT_DIR / f"{name}.png"
    page.screenshot(path=str(path), full_page=True)  # type: ignore[attr-defined]
    assert path.stat().st_size > 10_000, f"screenshot {path} looks empty"
    return path


@pytest.mark.parametrize("name,width,height", VIEWPORTS)
def test_dashboard_visual(chromium, usab_env, name: str, width: int, height: int) -> None:  # noqa: F811
    env: dict[str, Any] = usab_env
    with chromium.new_context(  # type: ignore[attr-defined]
        base_url=env["base_url"], viewport={"width": width, "height": height}
    ) as context:
        page = context.new_page()
        _login(page, env)
        page.goto("/admin")

        # R1: product heading inside the dashboard body + eyebrow/purpose;
        # the three destination groups; no foundation prose.
        assert page.locator("h1#dashboard-heading").inner_text() == "SLAIF API Gateway"
        # DOM text: .eyebrow is CSS uppercased, so the rendered text is
        # "ADMINISTRATION" while the markup content is "Administration".
        assert (page.locator(".eyebrow").first.text_content() or "").strip() == "Administration"
        for heading in GROUP_HEADINGS:
            assert page.locator(f".dash-group h2:has-text('{heading}')").count() == 1, heading
        assert page.get_by_role("link", name="Create gateway key").count() == 1
        assert "Dashboard Foundation" not in page.locator("body").inner_text()

        _assert_no_horizontal_overflow(page)
        _assert_top_anchored(page)
        _capture(page, f"dashboard-{name}")


@pytest.mark.parametrize("name,width,height", VIEWPORTS)
def test_keys_list_visual(chromium, usab_env, name: str, width: int, height: int) -> None:  # noqa: F811
    env: dict[str, Any] = usab_env
    with chromium.new_context(  # type: ignore[attr-defined]
        base_url=env["base_url"], viewport={"width": width, "height": height}
    ) as context:
        page = context.new_page()
        _login(page, env)
        page.goto("/admin/keys?limit=50")

        # A2: native filter selects and integrated record-choice entry
        # fields share one value typography/geometry; labels are unified.
        styles = page.evaluate(  # type: ignore[attr-defined]
            """() => {
                const prop = (sel, name) => {
                    const el = document.querySelector(sel);
                    return el ? getComputedStyle(el)[name] : null;
                };
                return {
                    selectFontSize: prop('.filter-bar select', 'fontSize'),
                    selectFontWeight: prop('.filter-bar select', 'fontWeight'),
                    selectHeight: prop('.filter-bar select', 'height'),
                    selectRadius: prop('.filter-bar select', 'borderTopLeftRadius'),
                    rcFontSize: prop('.rc-main:not(.rc-main-multi) .rc-input', 'fontSize'),
                    rcFontWeight: prop('.rc-main:not(.rc-main-multi) .rc-input', 'fontWeight'),
                    rcHeight: prop('.rc-main:not(.rc-main-multi)', 'height'),
                    rcRadius: prop('.rc-main:not(.rc-main-multi)', 'borderTopLeftRadius'),
                    rcLabelSize: prop('.rc-name', 'fontSize'),
                    rcLabelWeight: prop('.rc-name', 'fontWeight'),
                    plainLabelSize: prop('.filter-bar label:not(.rc-field)', 'fontSize'),
                    plainLabelWeight: prop('.filter-bar label:not(.rc-field)', 'fontWeight'),
                };
            }"""
        )
        assert styles["selectFontSize"] == "14px", styles
        assert styles["selectFontWeight"] == "400", styles
        assert styles["selectHeight"] == "42px", styles
        assert styles["selectRadius"] == "6px", styles
        assert styles["rcFontSize"] == "14px", styles
        assert styles["rcFontWeight"] == "400", styles
        assert styles["rcHeight"] == "42px", styles
        assert styles["rcRadius"] == "6px", styles
        assert styles["rcLabelSize"] == "13px", styles
        assert styles["rcLabelWeight"] == "600", styles
        assert styles["plainLabelSize"] == "13px", styles
        assert styles["plainLabelWeight"] == "600", styles

        # 193-a default prompt: blank integrated boxes read as searchable
        # (the caller-supplied placeholders on other pages still win).
        for rc_id in ("keys-owner-email", "keys-public-key-id", "keys-cohort"):
            ph = page.locator(f'.rc[data-rc-id="{rc_id}"] .rc-input').get_attribute("placeholder")
            assert ph and ph.strip(), f"blank box for {rc_id} has no visible prompt"

        # A3: sortable headers are hyperlinks, not buttons.
        table = page.locator("table[data-sortable]")
        assert table.count() == 1
        assert table.locator("thead th a.ts-link").count() == 6
        assert table.locator("thead th button").count() == 0

        # The keys table holds the full seeded page: exactly the 12
        # synthetic keys (10 for one owner + 2 for another); opaque
        # prefix + public id only, never a one-time plaintext cell.
        assert table.locator("tbody tr").count() == 12

        _assert_no_horizontal_overflow(page)
        _assert_top_anchored(page)
        _capture(page, f"keys-{name}")


def _layout_tops(page: object) -> dict[str, float]:
    return page.evaluate(  # type: ignore[attr-defined]
        """() => {
            const top = (sel) => {
                const el = document.querySelector(sel);
                return el ? el.getBoundingClientRect().top : null;
            };
            return {
                panel: top('.dashboard-shell'),
                control: top('.rc[data-rc-id="keys-owner-email"] .rc-main'),
                filter: top('.filter-bar > button[type="submit"]'),
                table: top('.table-wrap'),
            };
        }"""
    )


def test_keys_chip_grow_down(chromium, usab_env) -> None:  # noqa: F811
    """R2 grow-down proof on the real keys page: a selected chip row
    appears BELOW the primary controls - panel top, control top, and
    Filter button top stay unchanged while the table moves DOWN;
    removing the chip restores the original layout exactly."""
    env: dict[str, Any] = usab_env
    # Owner 105 is the newest seeded, non-anonymized owner, so it is in
    # the initial latest-100 batch (email label, owner name as sub).
    owner_email = f"u105-{env['suffix']}@example.org"
    with chromium.new_context(  # type: ignore[attr-defined]
        base_url=env["base_url"], viewport={"width": 1440, "height": 900}
    ) as context:
        page = context.new_page()
        _login(page, env)
        page.goto("/admin/keys?limit=50")

        rc = page.locator('.rc[data-rc-id="keys-owner-email"]')
        before = _layout_tops(page)

        # Real mouse selection: open the integrated control, pick the
        # known synthetic owner from the rendered menu.
        rc.locator(".rc-open").click()
        option = rc.locator(".rc-option", has_text=owner_email)
        option.wait_for(state="visible")
        option.click()

        # Selection state: menu closed, chip below the box, ONE managed
        # hidden field carrying the submitted id (email).
        assert not rc.locator(".rc-menu").is_visible()
        assert rc.locator(".rc-chip", has_text=owner_email).count() == 1
        hidden = rc.locator(".rc-value")
        assert hidden.count() == 1
        assert hidden.first.input_value() == owner_email

        after = _layout_tops(page)
        assert abs(after["panel"] - before["panel"]) <= 1, (before, after)
        assert abs(after["control"] - before["control"]) <= 1, (before, after)
        assert abs(after["filter"] - before["filter"]) <= 1, (before, after)
        assert after["table"] - before["table"] >= 8, (before, after)
        _capture(page, "keys-chips-selected-desktop-1440")

        # Chip removal restores the exact pre-selection layout. The
        # managed field always exists (writeHidden keeps one empty field
        # for no-JS/server form parity), so cleared = empty value.
        rc.locator(".rc-chip-remove").click()
        assert rc.locator(".rc-chip").count() == 0
        assert rc.locator(".rc-value").count() == 1
        assert rc.locator(".rc-value").first.input_value() == ""
        restored = _layout_tops(page)
        assert abs(restored["panel"] - before["panel"]) <= 1, (before, restored)
        assert abs(restored["control"] - before["control"]) <= 1, (before, restored)
        assert abs(restored["filter"] - before["filter"]) <= 1, (before, restored)
        assert abs(restored["table"] - before["table"]) <= 1, (before, restored)
