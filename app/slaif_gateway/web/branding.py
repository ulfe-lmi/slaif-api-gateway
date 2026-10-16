"""Bounded, read-only operator appearance overrides (187-a).

Adapted from the SLAIF Asset Reservation branding reference (revision
dad6e29d4f8e4fd941843b230474d35dafb69d1a, Apache License 2.0), from the Django
settings/views layer to explicit per-app values: every function receives the
``SLAIF_BRANDING_DIR`` value of the specific application instance, so
separately created apps (and unit-test instances) stay isolated. No ambient
settings are read at import time.

Optional by default: when the branding directory is unset/blank, or a slot
file is missing or invalid, the packaged defaults stand and the page is
unchanged. One invalid asset can never break another slot or any page: every
slot is discovered and validated independently, fail closed.

Security boundary
-----------------
Fixed slots are read relative to verified no-follow directory descriptors,
including each ancestor. Special files cannot block reads. Every resolution
reads and validates bounded bytes anew; operator assets are never cached.
CSS conservatively rejects escaped/resource-loading syntax. SVG has bounded,
namespace-aware inert validation; raster overrides support bounded RGB/RGBA
PNG only. Expected file/parse failures silently select packaged defaults.

The ``/admin/branding/`` endpoints are total: they serve the override bytes
when the slot is currently valid and the packaged fallback otherwise (empty
stylesheet for the CSS slot, the packaged logo for image slots), so a page
never references a broken subresource even if a file disappears between
render and request.
"""

from __future__ import annotations

import os
import re
import stat
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from slaif_gateway.web.branding_png import png_is_valid

STYLE_CSS = "style.css"
IMAGE_SLOTS = ("logo", "logo-compact", "favicon", "hero")
SLOTS = (STYLE_CSS, *IMAGE_SLOTS)
IMAGE_EXTENSIONS = (".svg", ".png")

MAX_CSS_BYTES = 256 * 1024
MAX_IMAGE_BYTES = 256 * 1024

_CONTENT_TYPES = {
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
}

SLOT_URLS = {
    STYLE_CSS: "/admin/branding/style.css",
    "logo": "/admin/branding/logo",
    "logo-compact": "/admin/branding/logo-compact",
    "favicon": "/admin/branding/favicon",
    "hero": "/admin/branding/hero",
}

# The packaged fallback identity asset (also the README brand asset since
# 186-a). Served locally by the admin static mount; no surface hotlinks it.
PACKAGED_LOGO_URL = "/admin/static/img/slaif-logo.svg"
_PACKAGED_LOGO_FILE = Path(__file__).resolve().parent / "static" / "img" / "slaif-logo.svg"

# --- content validation -----------------------------------------------------

_CSS_ACTIVE_MARKERS = (
    "@import",
    "@charset",
    "url(",
    "image-set(",
    "image(",
    "src(",
    "data:",
    "javascript:",
    "vbscript:",
    "expression(",
    "behavior:",
    "-moz-binding",
    "<",
)


def css_is_valid(data: bytes) -> bool:
    """Conservative CSS subset: no escapes, resource functions or imports.

    Remove complete comments then whitespace for token sensitivity. Rejecting
    escapes rather than decoding them also covers escaped keywords/strings,
    line continuations and alternate browser escape normalization.
    """
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    if "\\" in text or any(ord(char) < 32 and char not in "\t\r\n" for char in text):
        return False
    parts: list[str] = []
    cursor = 0
    while True:
        opening = text.find("/*", cursor)
        if opening == -1:
            parts.append(text[cursor:])
            break
        parts.append(text[cursor:opening])
        closing = text.find("*/", opening + 2)
        if closing == -1:
            return False
        cursor = closing + 2
    text = "".join(parts)
    if "*/" in text:
        return False
    normalized = re.sub(r"\s+", "", text).lower()
    return all(marker not in normalized for marker in _CSS_ACTIVE_MARKERS)


_SVG_NS = "http://www.w3.org/2000/svg"
_SVG_ALLOWED_TAGS = frozenset(
    {
        "svg",
        "g",
        "rect",
        "circle",
        "ellipse",
        "line",
        "polyline",
        "polygon",
        "path",
        "text",
        "tspan",
        "title",
        "desc",
        "defs",
        "linearGradient",
        "radialGradient",
        "stop",
        "clipPath",
        "mask",
        "pattern",
    }
)
_SVG_ALLOWED_ATTRS = frozenset(
    {
        "id",
        "class",
        "xmlns",
        "x",
        "y",
        "cx",
        "cy",
        "r",
        "rx",
        "ry",
        "width",
        "height",
        "x1",
        "y1",
        "x2",
        "y2",
        "points",
        "d",
        "transform",
        "fill",
        "fill-opacity",
        "fill-rule",
        "stroke",
        "stroke-width",
        "stroke-opacity",
        "stroke-linecap",
        "stroke-linejoin",
        "stroke-dasharray",
        "stroke-dashoffset",
        "opacity",
        "viewBox",
        "gradientUnits",
        "gradientTransform",
        "offset",
        "stop-color",
        "stop-opacity",
        "maskUnits",
        "maskContentUnits",
        "patternUnits",
        "patternContentUnits",
        "text-anchor",
        "font-family",
        "font-size",
        "font-weight",
        "letter-spacing",
        "display",
    }
)
_SVG_ALLOWED_TAG_SET = frozenset(f"{{{_SVG_NS}}}{tag}" for tag in _SVG_ALLOWED_TAGS)
_SVG_URL_FRAGMENT_RE = re.compile(r"^url\(\s*#[^)\s#]*\s*\)$", re.IGNORECASE)
# Raw substrings that only occur in markup (a literal '<' cannot appear in
# well-formed text content), checked before parsing as a fast rejection.
_SVG_RAW_REJECT_MARKERS = (
    "<script",
    "<iframe",
    "<object",
    "<embed",
    "<image",
    "<use",
    "<style",
    "<foreignobject",
    "<animate",
    "<set",
    "<a ",
    "<a>",
    "<!doctype",
    "<!--",
    "<![",
    "xlink:href",
    "javascript:",
    "data:",
    "@import",
)

MAX_SVG_DEPTH = 32
MAX_SVG_NODES = 2048
MAX_SVG_ATTRIBUTES = 64


def svg_is_valid(data: bytes) -> bool:
    """Bounded inert SVG in the actual SVG namespace; no recursive walk."""
    try:
        text = data.decode("utf-8")
        if any(marker in text.lower() for marker in _SVG_RAW_REJECT_MARKERS):
            return False
        declaration_free = re.sub(r"^\s*<\?xml\s+[^?]*\?>", "", text, count=1)
        if "<?" in declaration_free:
            return False
        root = ET.fromstring(text)
    except (UnicodeDecodeError, ET.ParseError, ValueError, RecursionError):
        return False
    if root.tag != f"{{{_SVG_NS}}}svg":
        return False
    stack = [(root, 1)]
    count = 0
    while stack:
        node, depth = stack.pop()
        count += 1
        if depth > MAX_SVG_DEPTH or count > MAX_SVG_NODES:
            return False
        if node.tag not in _SVG_ALLOWED_TAG_SET:
            return False
        if len(node.attrib) > MAX_SVG_ATTRIBUTES:
            return False
        for name, value in node.attrib.items():
            if not (name in _SVG_ALLOWED_ATTRS or name.startswith("data-")):
                return False
            if "{" in name or len(value) > 8192:
                return False
            normalized = value.strip().lower()
            if any(marker in normalized for marker in ("\\", "data:", "javascript:", "@import")):
                return False
            if "url" in normalized and not _SVG_URL_FRAGMENT_RE.fullmatch(normalized):
                return False
        stack.extend((child, depth + 1) for child in node)
    return True


def image_is_valid(data: bytes, extension: str) -> bool:
    if extension == ".svg":
        return svg_is_valid(data)
    return extension == ".png" and png_is_valid(data)


# --- bounded reads ----------------------------------------------------------


def _open_root(root: Path) -> int | None:
    """Walk each directory component from /, refusing symlinks atomically."""
    descriptor: int | None = None
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
    try:
        absolute = Path(os.path.abspath(root))
        descriptor = os.open("/", flags)
        for component in absolute.parts[1:]:
            child = os.open(component, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
            os.close(descriptor)
            return None
        return descriptor
    except (OSError, ValueError):
        if descriptor is not None:
            os.close(descriptor)
        return None


def _read_bounded(root_fd: int, name: str, cap: int) -> bytes | None:
    """No path re-resolution, no blocking FIFO opens, no unbounded reads."""
    descriptor: int | None = None
    try:
        descriptor = os.open(
            name,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
            dir_fd=root_fd,
        )
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size > cap:
            return None
        chunks = bytearray()
        while len(chunks) <= cap:
            chunk = os.read(descriptor, cap + 1 - len(chunks))
            if not chunk:
                break
            chunks.extend(chunk)
        after = os.fstat(descriptor)
        if len(chunks) > cap or _stat_identity(before) != _stat_identity(after):
            return None
        return bytes(chunks)
    except OSError:
        return None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _stat_identity(status: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        status.st_dev,
        status.st_ino,
        status.st_size,
        status.st_mtime_ns,
        status.st_ctime_ns,
    )


# --- resolution -------------------------------------------------------------


@dataclass(frozen=True)
class ResolvedAsset:
    slot: str
    file_name: str
    content_type: str
    data: bytes


def branding_root(branding_dir: str | None) -> Path | None:
    """The configured branding directory, or None when unset/blank."""
    if not isinstance(branding_dir, str):
        return None
    raw = branding_dir.strip()
    return Path(raw) if raw else None


def branding_enabled(branding_dir: str | None) -> bool:
    return branding_root(branding_dir) is not None


def _slot_file_name(root_fd: int, slot: str) -> str | None:
    """Bounded fixed-name discovery relative to the anchored directory."""
    names = [STYLE_CSS] if slot == STYLE_CSS else [slot + ext for ext in IMAGE_EXTENSIONS]
    candidates = []
    for name in names:
        try:
            status = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
        except OSError:
            continue
        if stat.S_ISREG(status.st_mode):
            candidates.append(name)
    return candidates[0] if len(candidates) == 1 else None


def _validate_slot_data(slot: str, file_name: str, data: bytes) -> str | None:
    """Return the response content type, or None when the content is invalid."""
    if slot == STYLE_CSS:
        return _CONTENT_TYPES[".css"] if css_is_valid(data) else None
    extension = "." + file_name.rsplit(".", 1)[-1]
    return _CONTENT_TYPES.get(extension) if image_is_valid(data, extension) else None


def resolve_slot(slot: str, branding_dir: str | None) -> ResolvedAsset | None:
    if slot not in SLOT_URLS:
        return None
    root = branding_root(branding_dir)
    if root is None:
        return None
    root_fd = _open_root(root)
    if root_fd is None:
        return None
    try:
        file_name = _slot_file_name(root_fd, slot)
        if file_name is None:
            return None
        cap = MAX_CSS_BYTES if slot == STYLE_CSS else MAX_IMAGE_BYTES
        data = _read_bounded(root_fd, file_name, cap)
        if data is None:
            return None
        content_type = _validate_slot_data(slot, file_name, data)
        if content_type is None:
            return None
        return ResolvedAsset(slot, file_name, content_type, data)
    finally:
        os.close(root_fd)


def asset_url(slot: str) -> str:
    return SLOT_URLS[slot]


@lru_cache(maxsize=1)
def _packaged_logo_bytes() -> bytes:
    return _PACKAGED_LOGO_FILE.read_bytes()


def fallback_asset(slot: str) -> tuple[bytes, str]:
    """The total-endpoint fallback: empty stylesheet or the packaged logo."""
    if slot == STYLE_CSS:
        return b"", _CONTENT_TYPES[".css"]
    return _packaged_logo_bytes(), _CONTENT_TYPES[".svg"]


# --- presentation helpers ---------------------------------------------------


def branding_src(slot: str, branding_dir: str | None) -> str:
    """Image ``src`` for a slot: the override URL or the packaged default."""
    return asset_url(slot) if resolve_slot(slot, branding_dir) is not None else PACKAGED_LOGO_URL


def branding_css_link_html(branding_dir: str | None) -> str:
    """The override stylesheet link, emitted only when the slot is valid."""
    if resolve_slot(STYLE_CSS, branding_dir) is not None:
        return f'<link rel="stylesheet" href="{asset_url(STYLE_CSS)}">'
    return ""


def branding_icon_link_html(branding_dir: str | None) -> str:
    """The ``<link rel="icon">`` element, always emitted so every browser
    page carries a local favicon: the override when the favicon slot is
    valid, otherwise the packaged logo."""
    resolved = resolve_slot("favicon", branding_dir)
    if resolved is not None:
        mime = resolved.content_type.split(";", 1)[0]
        return f'<link rel="icon" type="{mime}" href="{asset_url("favicon")}">'
    return f'<link rel="icon" type="image/svg+xml" href="{PACKAGED_LOGO_URL}">'


def branding_hero_src(branding_dir: str | None) -> str:
    """The login hero override URL, empty when the slot is not valid."""
    return asset_url("hero") if resolve_slot("hero", branding_dir) is not None else ""
