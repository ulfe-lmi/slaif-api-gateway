"""Bounded image-header inspection for operator-configured admission estimates.

No network access, image decompression, pixel allocation, or persistent cache.
Unknown, animated, malformed, and overly long headers retain the route budget.
"""

from __future__ import annotations

import base64
import binascii
from collections.abc import Mapping
from dataclasses import dataclass
import math
import struct
import zlib

_HEADER_BYTES = 65_536
_MAX_DIMENSION = 1_000_000
_GEOMETRY_FIELDS = frozenset(
    {"method", "patch_size", "spatial_merge_size", "min_tokens", "overhead_tokens"}
)


@dataclass(frozen=True, slots=True)
class ImageGeometry:
    patch_size: int
    spatial_merge_size: int
    min_tokens: int
    overhead_tokens: int

    def estimate(self, url: str, fallback_tokens: int) -> int:
        size = _image_dimensions(url)
        if size is None:
            return fallback_tokens
        width, height = size
        stride = self.patch_size * self.spatial_merge_size
        grid = ((width + stride - 1) // stride) * ((height + stride - 1) // stride)
        # Bound aspect-preserving minimum-size upscaling as well as patch
        # alignment. max(min_tokens, grid) alone undercounts thin small images.
        minimum_grid = _ceil_sqrt_ratio(self.min_tokens * width, height) * (
            _ceil_sqrt_ratio(self.min_tokens * height, width)
        )
        return min(fallback_tokens, max(grid, minimum_grid) + self.overhead_tokens)


def parse_image_geometry(raw: object, fallback_tokens: int | None) -> ImageGeometry:
    """Validate data-only patch geometry; no implicit per-model defaults."""
    if (
        not isinstance(raw, Mapping)
        or set(raw) != _GEOMETRY_FIELDS
        or raw.get("method") != "patch_grid"
        or type(fallback_tokens) is not int
    ):
        raise ValueError("Invalid image geometry policy")
    bounds = {
        "patch_size": (1, 256),
        "spatial_merge_size": (1, 16),
        "min_tokens": (1, 1_050_000),
        "overhead_tokens": (0, 65_536),
    }
    values = {}
    for name, (low, high) in bounds.items():
        value = raw[name]
        if type(value) is not int or not low <= value <= high:
            raise ValueError("Invalid image geometry policy")
        values[name] = value
    if values["min_tokens"] + values["overhead_tokens"] > fallback_tokens:
        raise ValueError("Image geometry exceeds fallback budget")
    return ImageGeometry(**values)


def _ceil_sqrt_ratio(numerator: int, denominator: int) -> int:
    return math.isqrt((numerator - 1) // denominator) + 1


def _image_dimensions(url: str) -> tuple[int, int] | None:
    if not url.startswith("data:image/"):
        return None
    comma = url.find(",", 0, 128)
    if comma < 0 or not url[:comma].endswith(";base64"):
        return None
    # Decode a finite prefix only, even when the validated transport contains
    # megabytes. This decodes base64 headers, never compressed image pixels.
    prefix_end = comma + 1 + ((_HEADER_BYTES + 2) // 3) * 4
    try:
        header = base64.b64decode(url[comma + 1 : prefix_end], validate=True)[:_HEADER_BYTES]
    except (ValueError, binascii.Error):
        return None
    size = None
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        size = _png_dimensions(header)
    elif header.startswith(b"\xff\xd8"):
        size = _jpeg_dimensions(header)
    elif header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        size = _webp_dimensions(header)
    if size is None or not all(0 < n <= _MAX_DIMENSION for n in size):
        return None
    return size


def _png_dimensions(data: bytes) -> tuple[int, int] | None:
    if len(data) < 33 or data[8:16] != b"\0\0\0\rIHDR":
        return None
    if zlib.crc32(data[12:29]) & 0xFFFFFFFF != int.from_bytes(data[29:33], "big"):
        return None
    depths = {0: {1, 2, 4, 8, 16}, 2: {8, 16}, 3: {1, 2, 4, 8}, 4: {8, 16}, 6: {8, 16}}
    if (
        data[24] not in depths.get(data[25], set())
        or data[26:28] != b"\0\0"
        or data[28] not in (0, 1)
    ):
        return None
    width, height = struct.unpack(">II", data[16:24])
    pos = 33
    while pos + 8 <= len(data):
        length = int.from_bytes(data[pos : pos + 4], "big")
        kind = data[pos + 4 : pos + 8]
        if kind in (b"acTL", b"fcTL", b"IHDR", b"IEND"):
            return None
        if kind == b"IDAT":
            return width, height
        pos += length + 12
    return None


def _jpeg_dimensions(data: bytes) -> tuple[int, int] | None:
    pos = 2
    while pos < len(data):
        if data[pos] != 0xFF:
            return None
        while pos < len(data) and data[pos] == 0xFF:
            pos += 1
        if pos >= len(data):
            return None
        marker = data[pos]
        pos += 1
        if marker in (0xDA, 0xD9, 0):
            return None
        if marker == 1 or 0xD0 <= marker <= 0xD7:
            continue
        if pos + 2 > len(data):
            return None
        length = int.from_bytes(data[pos : pos + 2], "big")
        if length < 2 or pos + length > len(data):
            return None
        if marker in (0xC0, 0xC1, 0xC2):
            if length < 8 or data[pos + 2] != 8:
                return None
            height, width = struct.unpack(">HH", data[pos + 3 : pos + 7])
            components = data[pos + 7]
            if components not in (1, 3, 4) or length != 8 + 3 * components:
                return None
            return width, height
        pos += length
    return None


def _webp_dimensions(data: bytes) -> tuple[int, int] | None:
    if len(data) < 20:
        return None
    end = int.from_bytes(data[4:8], "little") + 8
    pos = 12
    canvas = None
    while pos + 8 <= min(len(data), end):
        kind = data[pos : pos + 4]
        length = int.from_bytes(data[pos + 4 : pos + 8], "little")
        start = pos + 8
        if start + length > end:
            return None
        if kind in (b"ANIM", b"ANMF"):
            return None
        if kind == b"VP8X":
            if length != 10 or start + 10 > len(data) or data[start] & 0x02:
                return None
            canvas = (
                int.from_bytes(data[start + 4 : start + 7], "little") + 1,
                int.from_bytes(data[start + 7 : start + 10], "little") + 1,
            )
        elif kind == b"VP8 ":
            if (
                length < 10 or start + 10 > len(data)
                or data[start] & 1 or data[start + 3 : start + 6] != b"\x9d\x01\x2a"
            ):
                return None
            width, height = struct.unpack("<HH", data[start + 6 : start + 10])
            size = width & 0x3FFF, height & 0x3FFF
            return size if canvas in (None, size) else None
        elif kind == b"VP8L":
            if length < 5 or start + 5 > len(data) or data[start] != 0x2F:
                return None
            bits = int.from_bytes(data[start + 1 : start + 5], "little")
            if bits >> 29:
                return None
            size = (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
            return size if canvas in (None, size) else None
        pos = start + length + length % 2
    return None
