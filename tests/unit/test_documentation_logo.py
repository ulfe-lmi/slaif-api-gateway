"""Focused regression for the README brand logo local-asset contract (186-a).

The README must reference the tracked repository SVG by repository-relative
path; the asset must exist, be nonempty, and be an SVG document. A missing
logo or broken src reference must fail clearly.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check_documentation.py"

_SPEC = importlib.util.spec_from_file_location("check_documentation_logo", SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_CHECKER = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_CHECKER)

LOGO_REL = "app/slaif_gateway/web/static/img/slaif-logo.svg"


def _good_readme() -> str:
    return (
        '<div align="center">\n'
        '  <a href="https://www.slaif.si">\n'
        f'    <img src="{LOGO_REL}" width="320" alt="SLAIF">\n'
        "  </a>\n"
        "</div>\n"
        "\n"
        "# SLAIF API Gateway\n"
        "\n"
        "See [scope](docs/product-scope.md) and [docs](docs/README.md).\n"
    )


def _logo_in(root: Path, text: str) -> None:
    path = root / LOGO_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_tracked_logo_is_a_nonempty_svg() -> None:
    logo = (ROOT / LOGO_REL).read_text(encoding="utf-8")
    assert logo.strip()
    assert "<svg" in logo


def test_real_readme_brand_block_passes() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert _CHECKER.brand_block_errors(readme, ROOT) == []


def test_broken_src_reference_fails(tmp_path: Path) -> None:
    broken = _good_readme().replace(f'src="{LOGO_REL}"', 'src="img/missing-logo.svg"')
    errors = _CHECKER.brand_block_errors(broken, ROOT)
    assert any("missing required brand/navigation fragment" in e for e in errors), errors


def test_missing_logo_file_fails(tmp_path: Path) -> None:
    errors = _CHECKER.brand_block_errors(_good_readme(), tmp_path)
    assert any(f"brand logo file missing at {LOGO_REL}" in e for e in errors), errors


def test_empty_logo_file_fails(tmp_path: Path) -> None:
    _logo_in(tmp_path, "   \n")
    errors = _CHECKER.brand_block_errors(_good_readme(), tmp_path)
    assert any("brand logo file is empty" in e for e in errors), errors


def test_non_svg_logo_file_fails(tmp_path: Path) -> None:
    _logo_in(tmp_path, "<html><body>not an svg</body></html>")
    errors = _CHECKER.brand_block_errors(_good_readme(), tmp_path)
    assert any("not an SVG document" in e for e in errors), errors
