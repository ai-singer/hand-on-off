"""Minimal dependency-free PNG codec (Phase M3).

Phase M3 validates a **real** observation chain, which means the observer must
consume actual image bytes. That requires reading and writing an image format,
and the project has a hard constraint of zero third-party dependencies
(`pyproject.toml` declares `dependencies = []`).

PNG is the right choice: it is lossless, and a useful subset of it can be
implemented on ``zlib`` and ``struct`` alone, both of which are stdlib. This
module implements that subset:

* 8-bit RGB and RGBA, non-interlaced
* filter types 0–4 (None, Sub, Up, Average, Paeth) on read; adaptive filter
  selection on write
* ``zlib``/``deflate`` compression

Deliberately unsupported: palettes, 16-bit depth, interlacing, ancillary chunks.
Write-then-read round-trips are tested, and any unsupported input raises rather
than silently mis-decoding.

This codec is a *means*, not the point. Its only job is to let the observer read
real pixels without importing a computer-vision library.
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class PngCodecError(Exception):
    """Raised when an image cannot be encoded or decoded."""


@dataclass(frozen=True, slots=True)
class RgbImage:
    """A decoded RGB raster.

    Channels are stored as a flat ``bytes`` buffer of length ``width*height*3``
    in row-major order, which keeps slicing and statistics cheap and makes the
    memory layout explicit for the pixel backends.
    """

    width: int
    height: int
    channels: int
    pixels: bytes

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise PngCodecError("image dimensions must be positive")
        if self.channels not in (3, 4):
            raise PngCodecError("only 3- and 4-channel images are supported")
        expected = self.width * self.height * self.channels
        if len(self.pixels) != expected:
            raise PngCodecError(
                f"pixel buffer is {len(self.pixels)} bytes, expected {expected}"
            )

    def pixel(self, x: int, y: int) -> tuple[int, int, int]:
        """Return the RGB triple at ``(x, y)``, ignoring any alpha channel."""

        if not (0 <= x < self.width and 0 <= y < self.height):
            raise PngCodecError(f"pixel ({x}, {y}) is outside the image")
        offset = (y * self.width + x) * self.channels
        return (
            self.pixels[offset],
            self.pixels[offset + 1],
            self.pixels[offset + 2],
        )

    def downscale(self, factor: int) -> "RgbImage":
        """Box-filter downscale by an integer factor.

        Used to reduce a full-resolution raster to a working grid before
        connected-component analysis. Averaging rather than point-sampling keeps
        thin text rows visible in the reduced grid, which matters because text
        detection depends on them.
        """

        if factor < 1:
            raise PngCodecError("downscale factor must be at least 1")
        if factor == 1:
            return self
        out_w = max(1, self.width // factor)
        out_h = max(1, self.height // factor)
        buffer = bytearray(out_w * out_h * 3)
        for oy in range(out_h):
            for ox in range(out_w):
                totals = [0, 0, 0]
                count = 0
                for dy in range(factor):
                    sy = oy * factor + dy
                    if sy >= self.height:
                        break
                    for dx in range(factor):
                        sx = ox * factor + dx
                        if sx >= self.width:
                            break
                        offset = (sy * self.width + sx) * self.channels
                        totals[0] += self.pixels[offset]
                        totals[1] += self.pixels[offset + 1]
                        totals[2] += self.pixels[offset + 2]
                        count += 1
                target = (oy * out_w + ox) * 3
                if count:
                    buffer[target] = totals[0] // count
                    buffer[target + 1] = totals[1] // count
                    buffer[target + 2] = totals[2] // count
        return RgbImage(out_w, out_h, 3, bytes(buffer))


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa = abs(p - a)
    pb = abs(p - b)
    pc = abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def _unfilter(
    raw: bytes, width: int, height: int, channels: int
) -> bytearray:
    """Reverse PNG scanline filtering into a contiguous pixel buffer."""

    stride = width * channels
    out = bytearray(stride * height)
    previous = bytearray(stride)
    position = 0

    for row in range(height):
        if position >= len(raw):
            raise PngCodecError(f"truncated image data at row {row}")
        filter_type = raw[position]
        position += 1
        line = bytearray(raw[position : position + stride])
        if len(line) != stride:
            raise PngCodecError(f"truncated scanline {row}")
        position += stride

        if filter_type == 0:
            pass
        elif filter_type == 1:
            for index in range(channels, stride):
                line[index] = (line[index] + line[index - channels]) & 0xFF
        elif filter_type == 2:
            for index in range(stride):
                line[index] = (line[index] + previous[index]) & 0xFF
        elif filter_type == 3:
            for index in range(stride):
                left = line[index - channels] if index >= channels else 0
                line[index] = (line[index] + ((left + previous[index]) >> 1)) & 0xFF
        elif filter_type == 4:
            for index in range(stride):
                left = line[index - channels] if index >= channels else 0
                up_left = previous[index - channels] if index >= channels else 0
                line[index] = (
                    line[index] + _paeth(left, previous[index], up_left)
                ) & 0xFF
        else:
            raise PngCodecError(f"unsupported PNG filter type {filter_type}")

        out[row * stride : (row + 1) * stride] = line
        previous = line

    return out


def decode_png(data: bytes) -> RgbImage:
    """Decode an 8-bit non-interlaced RGB/RGBA PNG."""

    if not data.startswith(_PNG_SIGNATURE):
        raise PngCodecError("not a PNG file (bad signature)")

    position = len(_PNG_SIGNATURE)
    header: tuple[int, int, int, int] | None = None
    compressed = bytearray()

    while position + 8 <= len(data):
        (length,) = struct.unpack(">I", data[position : position + 4])
        chunk_type = data[position + 4 : position + 8]
        body_start = position + 8
        body_end = body_start + length
        if body_end + 4 > len(data):
            raise PngCodecError(f"truncated chunk {chunk_type!r}")
        body = data[body_start:body_end]
        position = body_end + 4  # skip CRC

        if chunk_type == b"IHDR":
            (
                width,
                height,
                bit_depth,
                color_type,
                compression,
                filter_method,
                interlace,
            ) = struct.unpack(">IIBBBBB", body)
            if bit_depth != 8:
                raise PngCodecError(f"only 8-bit depth is supported, got {bit_depth}")
            if color_type not in (2, 6):
                raise PngCodecError(
                    f"only truecolour (2) and truecolour+alpha (6) are supported, "
                    f"got colour type {color_type}"
                )
            if interlace != 0:
                raise PngCodecError("interlaced PNGs are not supported")
            if compression != 0 or filter_method != 0:
                raise PngCodecError("unsupported PNG compression or filter method")
            header = (width, height, color_type, bit_depth)
        elif chunk_type == b"IDAT":
            compressed.extend(body)
        elif chunk_type == b"IEND":
            break

    if header is None:
        raise PngCodecError("PNG is missing an IHDR chunk")
    if not compressed:
        raise PngCodecError("PNG contains no image data")

    width, height, color_type, _ = header
    channels = 3 if color_type == 2 else 4

    try:
        raw = zlib.decompress(bytes(compressed))
    except zlib.error as exc:
        raise PngCodecError(f"cannot inflate image data: {exc}") from exc

    pixels = _unfilter(raw, width, height, channels)
    if channels == 4:
        # Normalise to RGB so downstream analysis has one memory layout.
        rgb = bytearray(width * height * 3)
        for index in range(width * height):
            rgb[index * 3 : index * 3 + 3] = pixels[index * 4 : index * 4 + 3]
        return RgbImage(width, height, 3, bytes(rgb))
    return RgbImage(width, height, 3, bytes(pixels))


def _chunk(chunk_type: bytes, body: bytes) -> bytes:
    return (
        struct.pack(">I", len(body))
        + chunk_type
        + body
        + struct.pack(">I", zlib.crc32(chunk_type + body) & 0xFFFFFFFF)
    )


def encode_png(image: RgbImage) -> bytes:
    """Encode an :class:`RgbImage` as an 8-bit RGB PNG.

    Uses adaptive per-scanline filtering: for each row the encoder picks the
    filter with the smallest sum of absolute differences, which is the standard
    heuristic and keeps synthetic flat-colour images small.
    """

    if image.channels not in (3, 4):
        raise PngCodecError("only 3- and 4-channel images can be encoded")

    stride = image.width * image.channels
    raw = bytearray()

    for row in range(image.height):
        start = row * stride
        line = image.pixels[start : start + stride]
        previous = (
            image.pixels[start - stride : start] if row > 0 else bytes(stride)
        )

        candidates: list[tuple[int, bytes]] = []
        candidates.append((0, bytes(line)))
        candidates.append((1, _filter_sub(line, image.channels)))
        candidates.append((2, _filter_up(line, previous)))
        candidates.append((3, _filter_average(line, previous, image.channels)))
        candidates.append((4, _filter_paeth(line, previous, image.channels)))

        def score(entry: tuple[int, bytes]) -> int:
            return sum(b if b < 128 else 256 - b for b in entry[1])

        best_type, best_body = min(candidates, key=score)
        raw.append(best_type)
        raw.extend(best_body)

    header = struct.pack(">IIBBBBB", image.width, image.height, 8, 2, 0, 0, 0)
    return (
        _PNG_SIGNATURE
        + _chunk(b"IHDR", header)
        + _chunk(b"IDAT", zlib.compress(bytes(raw), 6))
        + _chunk(b"IEND", b"")
    )


def _filter_sub(line: bytes, bpp: int) -> bytes:
    out = bytearray(len(line))
    for index, value in enumerate(line):
        left = line[index - bpp] if index >= bpp else 0
        out[index] = (value - left) & 0xFF
    return bytes(out)


def _filter_up(line: bytes, previous: bytes) -> bytes:
    return bytes((value - previous[index]) & 0xFF for index, value in enumerate(line))


def _filter_average(line: bytes, previous: bytes, bpp: int) -> bytes:
    out = bytearray(len(line))
    for index, value in enumerate(line):
        left = line[index - bpp] if index >= bpp else 0
        out[index] = (value - ((left + previous[index]) >> 1)) & 0xFF
    return bytes(out)


def _filter_paeth(line: bytes, previous: bytes, bpp: int) -> bytes:
    out = bytearray(len(line))
    for index, value in enumerate(line):
        left = line[index - bpp] if index >= bpp else 0
        up_left = previous[index - bpp] if index >= bpp else 0
        out[index] = (value - _paeth(left, previous[index], up_left)) & 0xFF
    return bytes(out)


def write_png(path, image: RgbImage) -> None:
    """Encode and write an image to disk."""

    from pathlib import Path

    Path(path).write_bytes(encode_png(image))


def read_png(path) -> RgbImage:
    """Read and decode an image from disk."""

    from pathlib import Path

    return decode_png(Path(path).read_bytes())


__all__ = [
    "PngCodecError",
    "RgbImage",
    "decode_png",
    "encode_png",
    "read_png",
    "write_png",
]
