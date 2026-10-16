"""PNG override validation contract (187-a): complete framing, CRCs and
bounded scanlines; no decoder is claimed from a signature.

Adapted from the SLAIF Asset Reservation branding reference (Apache-2.0).
"""

from __future__ import annotations

import struct
import zlib

from slaif_gateway.web.branding_png import MAX_DIMENSION, png_is_valid


def _chunk(tag: bytes, payload: bytes, crc_delta: int = 0) -> bytes:
    body = tag + payload
    return struct.pack(">I", len(payload)) + body + struct.pack(">I", (zlib.crc32(body) + crc_delta) & 0xFFFFFFFF)


def _png(width: int, height: int, rgba: tuple[int, ...]) -> bytes:
    color = 6 if len(rgba) == 4 else 2
    raw = bytearray()
    for _ in range(height):
        raw.append(0)
        for _ in range(width):
            raw += bytes(rgba)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, color, 0, 0, 0)
    data = b"\x89PNG\r\n\x1a\n"
    data += _chunk(b"IHDR", ihdr)
    data += _chunk(b"IDAT", zlib.compress(bytes(raw)))
    data += _chunk(b"IEND", b"")
    return data


def _chunk_spans(data: bytes) -> list[tuple[int, int, bytes]]:
    """Chunk (start, end, tag) spans of a well-framed PNG body."""
    spans = []
    offset = 8
    while offset + 12 <= len(data):
        length = struct.unpack_from(">I", data, offset)[0]
        end = offset + 12 + length
        spans.append((offset, end, data[offset + 4 : offset + 8]))
        offset = end
    return spans


def test_valid_rgb_and_rgba_accepted() -> None:
    assert png_is_valid(_png(4, 2, (1, 2, 3)))
    assert png_is_valid(_png(4, 2, (1, 2, 3, 255)))
    assert png_is_valid(_png(1, 1, (0, 0, 0)))


def test_boundary_dimensions_and_pixels_accepted() -> None:
    assert png_is_valid(_png(1, MAX_DIMENSION, (0, 0, 0)))
    assert png_is_valid(_png(MAX_DIMENSION, 1, (0, 0, 0)))
    # 1024x1024 == MAX_PIXELS exactly.
    assert png_is_valid(_png(1024, 1024, (0, 0, 0)))


def test_oversized_dimensions_or_pixels_refused() -> None:
    assert not png_is_valid(_png(MAX_DIMENSION + 1, 1, (0, 0, 0)))
    assert not png_is_valid(_png(1, MAX_DIMENSION + 1, (0, 0, 0)))
    assert not png_is_valid(_png(1449, 1449, (0, 0, 0)))


def test_unsupported_modes_refused() -> None:
    def recolor(color: int) -> bytes:
        channels = 3 if color in (0, 2, 3) else 4
        raw = b"".join(bytes([0] + [0] * (4 * 4 * channels)) for _ in range(4))
        ihdr = struct.pack(">IIBBBBB", 4, 4, 8, color, 0, 0, 0)
        return (
            b"\x89PNG\r\n\x1a\n"
            + _chunk(b"IHDR", ihdr)
            + _chunk(b"IDAT", zlib.compress(raw))
            + _chunk(b"IEND", b"")
        )

    for color in (0, 3, 4, 5):  # grayscale, palette, gray+alpha, palette+alpha
        assert not png_is_valid(recolor(color))


def test_interlaced_refused() -> None:
    ihdr = struct.pack(">IIBBBBB", 4, 4, 8, 2, 0, 0, 1)
    raw = bytearray()
    for _ in range(4):
        raw.append(0)
        raw += b"\x00\x00\x00" * 4
    data = (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", zlib.compress(bytes(raw)))
        + _chunk(b"IEND", b"")
    )
    assert not png_is_valid(data)


def test_sixteen_bit_refused() -> None:
    ihdr = struct.pack(">IIBBBBB", 2, 1, 16, 2, 0, 0, 0)
    raw = b"\x00" + b"\x00\x00\x00\x00\x00\x00"
    data = (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", zlib.compress(raw))
        + _chunk(b"IEND", b"")
    )
    assert not png_is_valid(data)


def test_bad_signature_or_truncation_refused() -> None:
    good = _png(2, 2, (0, 0, 0))
    assert png_is_valid(good)
    assert not png_is_valid(good[1:])
    assert not png_is_valid(b"\x89PNG\r\n\x1a\n")
    assert not png_is_valid(good[:-1])
    assert not png_is_valid(b"")
    assert not png_is_valid(b"\x89PNG\r\n\x1a\n" + good[9:])


def test_second_or_misplaced_ihdr_refused() -> None:
    good = _png(2, 2, (0, 0, 0))
    assert png_is_valid(good)
    spans = _chunk_spans(good)
    ihdr_start, ihdr_end, _ = spans[0]
    ihdr_payload = good[ihdr_start + 8 : ihdr_end - 4]
    iend_start, _, _ = spans[-1]
    # A second IHDR inside the image data is refused.
    assert not png_is_valid(good[:iend_start] + _chunk(b"IHDR", ihdr_payload) + good[iend_start:])
    # IHDR out of its first-chunk position (IDAT first) is refused.
    idat_start, idat_end, _ = spans[1]
    swapped = good[:8] + good[idat_start:idat_end] + good[8:ihdr_end] + good[idat_end:]
    assert not png_is_valid(swapped)


def test_bad_crc_refused() -> None:
    good = _png(2, 2, (0, 0, 0))
    assert png_is_valid(good)
    bad = good[:-4] + struct.pack(">I", struct.unpack(">I", good[-4:])[0] + 1)
    assert not png_is_valid(bad)


def test_unknown_ancillary_chunks_refused() -> None:
    good = _png(2, 2, (0, 0, 0))
    assert png_is_valid(good)
    spans = _chunk_spans(good)
    ihdr_start, ihdr_end, _ = spans[0]
    # A CRC-valid ancillary chunk after the valid IHDR is itself refused.
    text = good[:ihdr_end] + _chunk(b"tEXt", b"k\x00v") + good[ihdr_end:]
    assert not png_is_valid(text)


def test_idat_before_ihdr_and_after_iend_refused() -> None:
    good = _png(2, 2, (0, 0, 0))
    assert png_is_valid(good)
    spans = _chunk_spans(good)
    idat_start, idat_end, _ = spans[1]
    idat = good[idat_start:idat_end]
    # IDAT before IHDR (first chunk is not IHDR) is refused.
    moved = good[:8] + idat + good[8:idat_start] + good[idat_end:]
    assert not png_is_valid(moved)
    # IDAT after the final IEND is refused.
    assert not png_is_valid(good + idat)


def test_iend_with_payload_or_trailing_bytes_refused() -> None:
    good = _png(2, 2, (0, 0, 0))
    assert png_is_valid(good)
    assert not png_is_valid(good + b"trail")
    iend = good.rindex(b"IEND") - 4
    assert not png_is_valid(good[:iend] + _chunk(b"IEND", b"x") + good[iend + 12:])


def test_scanline_filter_and_length_mismatches_refused() -> None:
    ihdr = struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0)
    header = b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr)
    end = _chunk(b"IEND", b"")
    good_raw = b"".join(bytes([0]) + b"\x01\x02\x03" * 2 for _ in range(2))
    assert png_is_valid(header + _chunk(b"IDAT", zlib.compress(good_raw)) + end)
    bad_filter = bytearray(good_raw)
    bad_filter[0] = 5
    assert not png_is_valid(header + _chunk(b"IDAT", zlib.compress(bytes(bad_filter))) + end)
    assert not png_is_valid(header + _chunk(b"IDAT", zlib.compress(good_raw[:-1])) + end)
    assert not png_is_valid(header + _chunk(b"IDAT", zlib.compress(good_raw + b"\x00")) + end)


def test_zlib_trailing_compressed_bytes_refused() -> None:
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    header = b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr)
    end = _chunk(b"IEND", b"")
    good_raw = b"\x00" + b"\x00\x00\x00"
    compressed = zlib.compress(good_raw) + zlib.compress(b"extra")
    assert not png_is_valid(header + _chunk(b"IDAT", compressed) + end)


def test_multi_idat_concatenation_accepted() -> None:
    good = _png(3, 3, (9, 8, 7))
    assert png_is_valid(good)
    spans = _chunk_spans(good)
    idat_start, idat_end, _ = spans[1]
    payload = good[idat_start + 8 : idat_end - 4]
    half = len(payload) // 2
    data = (
        b"\x89PNG\r\n\x1a\n"
        + good[8:idat_start]
        + _chunk(b"IDAT", payload[:half])
        + _chunk(b"IDAT", payload[half:])
        + good[idat_end:]
    )
    assert png_is_valid(data)
