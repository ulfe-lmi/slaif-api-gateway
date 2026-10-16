"""Bounded noninterlaced eight-bit RGB/RGBA PNG validation, no dependency.

Adapted from the SLAIF Asset Reservation branding reference (revision
dad6e29d4f8e4fd941843b230474d35dafb69d1a, Apache License 2.0).

Check the complete chunk framing/CRCs and bounded zlib scanlines, rather than
claiming decoder validity from a signature. Ancillary chunks and other PNG
modes are deliberately unsupported; operators can export RGB/RGBA PNG or SVG.
"""

from __future__ import annotations

import struct
import zlib

MAX_DIMENSION = 4096
MAX_PIXELS = 1024 * 1024


def png_is_valid(data: bytes) -> bool:
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return False
    offset = 8
    header = None
    compressed = bytearray()
    seen_end = False
    try:
        while offset + 12 <= len(data):
            length = struct.unpack_from(">I", data, offset)[0]
            tag = data[offset + 4 : offset + 8]
            end = offset + 12 + length
            if end > len(data):
                return False
            payload = data[offset + 8 : end - 4]
            crc = struct.unpack_from(">I", data, end - 4)[0]
            if zlib.crc32(tag + payload) & 0xFFFFFFFF != crc:
                return False
            if tag == b"IHDR":
                if header is not None or offset != 8 or length != 13:
                    return False
                width, height, depth, color, compression, filtering, interlace = struct.unpack(
                    ">IIBBBBB", payload
                )
                if not (0 < width <= MAX_DIMENSION and 0 < height <= MAX_DIMENSION):
                    return False
                if width * height > MAX_PIXELS:
                    return False
                if (
                    depth != 8
                    or color not in (2, 6)
                    or (compression, filtering, interlace) != (0, 0, 0)
                ):
                    return False
                header = (width, height, 3 if color == 2 else 4)
            elif tag == b"IDAT":
                if header is None or seen_end:
                    return False
                compressed.extend(payload)
            elif tag == b"IEND":
                if header is None or length != 0 or not compressed or end != len(data):
                    return False
                seen_end = True
            else:
                return False
            offset = end
        if offset != len(data) or not seen_end or header is None:
            return False
        width, height, channels = header
        stride = width * channels + 1
        expected = stride * height
        decoder = zlib.decompressobj()
        raw = decoder.decompress(bytes(compressed), expected + 1)
        if (
            len(raw) != expected
            or not decoder.eof
            or decoder.unused_data
            or decoder.unconsumed_tail
        ):
            return False
        return all(raw[row * stride] <= 4 for row in range(height))
    except (struct.error, zlib.error, ValueError, OverflowError):
        return False
