"""Unit qualification for optional operator branding (187-a).

Real temporary files and real FD IO; security negatives exercise the real
no-follow reader (patching is limited to injecting a swap at a precise
moment, never replacing the reader with a fake implementation). Branding is
resolved per application instance from ``request.app.state.settings``, so
every test builds isolated ``create_app(Settings(...))`` instances.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from slaif_gateway.config import Settings
from slaif_gateway.main import create_app
from slaif_gateway.web import branding

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "branding"
CUSTOM = FIXTURES / "custom"
PACKAGED_LOGO = (ROOT / "app" / "slaif_gateway" / "web" / "static" / "img" / "slaif-logo.svg").read_bytes()

VALID_CSS = b"body { color: blue; }"
VALID_SVG = (
    b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
    b'<rect x="0" y="0" width="10" height="10" fill="#000"/></svg>'
)


def _settings(branding_dir: str | None = None) -> Settings:
    return Settings(
        ADMIN_SESSION_SECRET="k" * 32,
        SLAIF_BRANDING_DIR=branding_dir if branding_dir is not None else "",
        ENABLE_REDIS_RATE_LIMITS=False,
    )


def _app(branding_dir: str | None = None):
    return create_app(_settings(branding_dir))


def _write_dir(root: Path, files: dict[str, bytes]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        (root / name).write_bytes(data)
    return root


BRANDING_HEADERS = {
    "cache-control": "no-cache",
    "x-content-type-options": "nosniff",
}


def _assert_branding_headers(response) -> None:
    for name, value in BRANDING_HEADERS.items():
        assert response.headers[name] == value, response.headers


# --- disabled / missing / total endpoints -------------------------------------


def test_disabled_defaults_and_total_endpoints() -> None:
    app = _app()
    with TestClient(app) as client:
        for slot in ("style.css", "logo", "logo-compact", "favicon", "hero"):
            response = client.get(f"/admin/branding/{slot}")
            assert response.status_code == 200
            _assert_branding_headers(response)
        css = client.get("/admin/branding/style.css")
        assert css.headers["content-type"] == "text/css; charset=utf-8"
        assert css.content == b""
        for slot in ("logo", "logo-compact", "favicon", "hero"):
            response = client.get(f"/admin/branding/{slot}")
            assert response.headers["content-type"] == "image/svg+xml"
            assert response.content == PACKAGED_LOGO
        # Unknown paths keep the normal 404; only fixed literals exist.
        assert client.get("/admin/branding/unknown").status_code == 404
        assert client.get("/admin/branding/logo.svg").status_code == 404
        assert client.get("/admin/branding/style.css/extra").status_code == 404
        # No authentication rights or session side effects from asset requests.
        response = client.get("/admin/branding/logo")
        assert "set-cookie" not in response.headers
        assert response.status_code == 200
        html = client.get("/admin/login").text
        assert 'src="/admin/static/img/slaif-logo.svg"' in html
        assert "brand-logo-compact" not in html
        assert "/admin/branding/style.css" not in html
        assert "branding-active" not in html


def test_missing_and_empty_directories_fall_back(tmp_path: Path) -> None:
    for directory in (tmp_path / "nope", tmp_path / "empty"):
        if directory.name == "empty":
            directory.mkdir()
        assert branding.resolve_slot("style.css", str(directory)) is None
    app = _app(str(tmp_path / "nope"))
    with TestClient(app) as client:
        assert client.get("/admin/branding/style.css").content == b""
        assert client.get("/admin/branding/logo").content == PACKAGED_LOGO


def test_custom_fixtures_serve_exact_bytes_with_mime() -> None:
    app = _app(str(CUSTOM))
    with TestClient(app) as client:
        css = client.get("/admin/branding/style.css")
        assert css.status_code == 200
        assert css.content == (CUSTOM / "style.css").read_bytes()
        assert css.headers["content-type"] == "text/css; charset=utf-8"
        _assert_branding_headers(css)
        logo = client.get("/admin/branding/logo")
        assert logo.content == (CUSTOM / "logo.svg").read_bytes()
        assert logo.headers["content-type"] == "image/svg+xml"
        compact = client.get("/admin/branding/logo-compact")
        assert compact.content == (CUSTOM / "logo-compact.png").read_bytes()
        assert compact.headers["content-type"] == "image/png"
        favicon = client.get("/admin/branding/favicon")
        assert favicon.content == (CUSTOM / "favicon.png").read_bytes()
        assert favicon.headers["content-type"] == "image/png"
        hero = client.get("/admin/branding/hero")
        assert hero.content == (CUSTOM / "hero.svg").read_bytes()


def test_login_references_overrides_with_css_after_packaged() -> None:
    app = _app(str(CUSTOM))
    with TestClient(app) as client:
        html = client.get("/admin/login").text
        assert (
            html.index('/admin/static/css/admin.css')
            < html.index("/admin/branding/style.css")
        )
        assert '<link rel="stylesheet" href="/admin/branding/style.css">' in html
        assert '<link rel="icon" type="image/png" href="/admin/branding/favicon">' in html
        assert 'src="/admin/branding/logo"' in html
        assert 'src="/admin/branding/logo-compact"' in html
        assert "class=\"brand-lockup admin-brand branding-active\"" in html
        assert "src=\"/admin/branding/hero\"" in html
        assert "alt=\"SLAIF Slovenian AI Factory\"" in html


# --- per-slot fallbacks, ambiguity, unknown files -----------------------------


def test_invalid_css_falls_back_without_breaking_other_slots(tmp_path: Path) -> None:
    directory = _write_dir(
        tmp_path / "b",
        {
            "style.css": b"body { background: url(http://evil.example/x.png); }",
            "logo.svg": VALID_SVG,
        },
    )
    assert branding.resolve_slot("style.css", str(directory)) is None
    assert branding.resolve_slot("logo", str(directory)) is not None
    app = _app(str(directory))
    with TestClient(app) as client:
        assert client.get("/admin/branding/style.css").content == b""
        assert client.get("/admin/branding/logo").content == VALID_SVG
        html = client.get("/admin/login").text
        assert "/admin/branding/style.css" not in html
        assert 'src="/admin/branding/logo"' in html


def test_invalid_svg_falls_back_to_packaged_default(tmp_path: Path) -> None:
    directory = _write_dir(tmp_path / "s", {"logo.svg": b"<svg xmlns='http://www.w3.org/2000/svg'><script>x</script></svg>"})
    assert branding.resolve_slot("logo", str(directory)) is None
    app = _app(str(directory))
    with TestClient(app) as client:
        response = client.get("/admin/branding/logo")
        assert response.status_code == 200
        assert response.content == PACKAGED_LOGO


def test_ambiguous_slot_and_unknown_entries(tmp_path: Path) -> None:
    directory = tmp_path / "amb"
    directory.mkdir()
    (directory / "logo.svg").write_bytes(VALID_SVG)
    (directory / "logo.png").write_bytes((CUSTOM / "logo-compact.png").read_bytes())
    (directory / "style.css").write_bytes(VALID_CSS)
    (directory / "robots.txt").write_bytes(b"User-agent: *")
    assert branding.resolve_slot("logo", str(directory)) is None
    assert branding.resolve_slot("style.css", str(directory)) is not None


def test_unknown_slot_and_non_branding_directories_refused(tmp_path: Path) -> None:
    assert branding.resolve_slot("not-a-slot", str(CUSTOM)) is None
    assert branding.resolve_slot("logo", None) is None
    assert branding.resolve_slot("logo", "   ") is None
    assert branding.resolve_slot("logo", str(ROOT / "app")) is None


def test_css_at_exact_cap_is_valid_and_over_cap_falls_back(tmp_path: Path) -> None:
    cap = branding.MAX_CSS_BYTES
    payload = b"/*" + b"a" * (cap - 4) + b"*/"
    assert len(payload) == cap
    directory = _write_dir(tmp_path / "cap", {"style.css": payload})
    resolved = branding.resolve_slot("style.css", str(directory))
    assert resolved is not None and resolved.data == payload
    over = b"body { color: red; }" + b" " * (cap - len(b"body { color: red; }") + 1)
    assert len(over) == cap + 1
    (tmp_path / "cap" / "style.css").write_bytes(over)
    assert branding.resolve_slot("style.css", str(tmp_path / "cap")) is None


# --- security negatives (real reader, real FDs) ---------------------------------


def test_symlink_file_and_directory_rejected(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    (real / "style.css").write_bytes(VALID_CSS)
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    assert branding.resolve_slot("style.css", str(link)) is None
    # A symlinked slot leaf is refused even inside a real directory.
    (tmp_path / "leaf.css").write_bytes(VALID_CSS)
    (tmp_path / "style.css").symlink_to(tmp_path / "leaf.css")
    assert branding.resolve_slot("style.css", str(tmp_path)) is None


def test_ancestor_symlink_refused(tmp_path: Path) -> None:
    actual = tmp_path / "actual" / "branding"
    actual.mkdir(parents=True)
    (actual / "style.css").write_bytes(VALID_CSS)
    link = tmp_path / "link"
    link.symlink_to(tmp_path / "actual", target_is_directory=True)
    assert branding.resolve_slot("style.css", str(link / "branding")) is None


def test_fifo_slot_file_refused_without_open(tmp_path: Path) -> None:
    (tmp_path / "style.css")  # placeholder to keep tmp_path used
    os.mkfifo(tmp_path / "style.css")
    assert branding.resolve_slot("style.css", str(tmp_path)) is None


def test_root_directory_swap_cannot_read_outside(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "branding"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    original = b"body { color: blue; }"
    (root / "style.css").write_bytes(original)
    (outside / "style.css").write_bytes(b"body { color: red; }")
    real_open = os.open
    state = {"swapped": False}

    def swap(path, flags, *args, **kwargs):
        if pathlib.Path(path).name == "style.css" and not state["swapped"]:
            state["swapped"] = True
            root.rename(tmp_path / "original")
            root.symlink_to(outside, target_is_directory=True)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(branding.os, "open", swap)
    result = branding.resolve_slot("style.css", str(root))
    assert state["swapped"]
    assert result is None or result.data == original


def test_regular_file_swapped_to_fifo_is_nonblocking(tmp_path: Path, monkeypatch) -> None:
    slot = tmp_path / "style.css"
    slot.write_bytes(VALID_CSS)
    real_open = os.open

    def swap(path, flags, *args, **kwargs):
        if pathlib.Path(path).name == "style.css":
            slot.unlink()
            os.mkfifo(slot)
            assert flags & os.O_NONBLOCK, "special-file opens must not block"
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(branding.os, "open", swap)
    assert branding.resolve_slot("style.css", str(tmp_path)) is None


def test_fifo_swap_finishes_in_real_bounded_child(tmp_path: Path) -> None:
    (tmp_path / "style.css").write_bytes(VALID_CSS)
    code = (
        "import os, pathlib, sys\n"
        f"sys.path.insert(0, {str(ROOT / 'app')!r})\n"
        "from slaif_gateway.web import branding\n"
        "root = pathlib.Path(sys.argv[1]); slot = root / 'style.css'\n"
        "original = os.open\n"
        "def swap(path, flags, *args, **kwargs):\n"
        "    if pathlib.Path(path).name == 'style.css':\n"
        "        slot.unlink(); os.mkfifo(slot)\n"
        "    return original(path, flags, *args, **kwargs)\n"
        "branding.os.open = swap\n"
        "assert branding.resolve_slot('style.css', str(root)) is None\n"
        "print('FIFO-REFUSED-OK')\n"
    )
    environment = {key: value for key, value in os.environ.items() if key in ("PATH",)}
    environment["APP_ENV"] = "development"
    try:
        result = subprocess.run(
            [sys.executable, "-c", code, str(tmp_path)],
            env=environment,
            capture_output=True,
            timeout=10,
        )
    except subprocess.TimeoutExpired:
        pytest.fail("FIFO replacement blocked the owned child")
    assert result.returncode == 0, result.stderr.decode()
    assert b"FIFO-REFUSED-OK" in result.stdout


def test_read_error_does_not_break_login_or_errors(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "style.css").write_bytes(VALID_CSS)

    # Build the genuine app first: startup performs the Codex profile
    # bootstrap read of the packaged DATA. Only the subsequent branding
    # request reads get the synthetic os.read failure injected.
    app = _app(str(tmp_path))

    def failed_read(*args):
        raise OSError("synthetic read failure")

    monkeypatch.setattr(branding.os, "read", failed_read)
    with TestClient(app) as client:
        assert client.get("/admin/branding/style.css").content == b""
        assert client.get("/admin/login").status_code == 200
        assert client.get("/admin/no-such-page").status_code == 404


def test_identity_change_during_read_falls_back(tmp_path: Path, monkeypatch) -> None:
    directory = _write_dir(tmp_path / "id", {"style.css": VALID_CSS})
    real_fstat = os.fstat
    calls = {"n": 0}

    def fake_fstat(descriptor, *args, **kwargs):
        status = real_fstat(descriptor, *args, **kwargs)
        calls["n"] += 1
        if calls["n"] >= 3:  # the after-read identity check only
            return os.stat_result(
                (status.st_mode, status.st_ino + 1, status.st_dev, status.st_nlink,
                 status.st_uid, status.st_gid, status.st_size, status.st_atime,
                 status.st_mtime, status.st_ctime)
            )
        return status

    monkeypatch.setattr(branding.os, "fstat", fake_fstat)
    assert branding.resolve_slot("style.css", str(directory)) is None
    assert calls["n"] >= 3


def test_no_fd_leak_across_repeated_resolutions(tmp_path: Path) -> None:
    directory = _write_dir(tmp_path / "fd", {"style.css": VALID_CSS, "logo.svg": VALID_SVG})
    before = len(os.listdir("/proc/self/fd"))
    for _ in range(200):
        assert branding.resolve_slot("style.css", str(directory)) is not None
        assert branding.resolve_slot("logo", str(directory)) is not None
        assert branding.resolve_slot("style.css", str(tmp_path / "missing")) is None
        assert branding.resolve_slot("style.css", None) is None
    after = len(os.listdir("/proc/self/fd"))
    assert after <= before + 2, (before, after)


# --- refresh semantics -----------------------------------------------------------


def test_file_change_picked_up_on_next_request(tmp_path: Path) -> None:
    slot = tmp_path / "style.css"
    slot.write_bytes(b"body { color: blue; }")
    first = branding.resolve_slot("style.css", str(tmp_path)).data
    slot.write_bytes(b"body { color: green; }")
    second = branding.resolve_slot("style.css", str(tmp_path)).data
    assert first == b"body { color: blue; }"
    assert second == b"body { color: green; }"


def test_same_size_and_mtime_replacement_revalidates(tmp_path: Path) -> None:
    slot = tmp_path / "style.css"
    first = b"body { color: blue; }"
    second = b"body { color: pink; }"
    assert len(first) == len(second)
    slot.write_bytes(first)
    stamp = slot.stat().st_mtime_ns
    assert branding.resolve_slot("style.css", str(tmp_path)).data == first
    replacement = tmp_path / "replacement"
    replacement.write_bytes(second)
    os.utime(replacement, ns=(stamp, stamp))
    replacement.replace(slot)
    assert branding.resolve_slot("style.css", str(tmp_path)).data == second
    slot.write_bytes(b'@import "x";')
    os.utime(slot, ns=(stamp, stamp))
    assert branding.resolve_slot("style.css", str(tmp_path)) is None


def test_removed_file_after_render_serves_safe_fallback(tmp_path: Path) -> None:
    (tmp_path / "style.css").write_bytes(VALID_CSS)
    app = _app(str(tmp_path))
    with TestClient(app) as client:
        html = client.get("/admin/login").text
        assert "/admin/branding/style.css" in html
        (tmp_path / "style.css").unlink()
        response = client.get("/admin/branding/style.css")
        assert response.status_code == 200
        assert response.content == b""


def test_path_traversal_and_foreign_names_cannot_leak(tmp_path: Path) -> None:
    (tmp_path / "style.css").write_bytes(VALID_CSS)
    app = _app(str(tmp_path))
    with TestClient(app) as client:
        for path in (
            "/admin/branding/../../etc/passwd",
            "/admin/branding/style.css/..",
            "/admin/branding/%2e%2e/%2e%2e/etc/passwd",
        ):
            response = client.get(path)
            assert response.status_code in {404, 405}
            assert b"root:" not in response.content


# --- app-instance isolation --------------------------------------------------------


def test_two_app_instances_stay_isolated(tmp_path: Path) -> None:
    directory = _write_dir(tmp_path / "iso", {"style.css": VALID_CSS})
    branded = _app(str(directory))
    plain = _app()
    with TestClient(branded) as client_branded, TestClient(plain) as client_plain:
        assert client_branded.get("/admin/branding/style.css").content == VALID_CSS
        assert client_plain.get("/admin/branding/style.css").content == b""
        assert "/admin/branding/style.css" in client_branded.get("/admin/login").text
        assert "/admin/branding/style.css" not in client_plain.get("/admin/login").text


def test_api_json_contract_unchanged() -> None:
    app = _app(str(CUSTOM))
    with TestClient(app) as client:
        response = client.get("/v1/models")
        assert response.status_code == 401
        body = response.json()
        assert "error" in body
        assert response.headers["content-type"].startswith("application/json")
