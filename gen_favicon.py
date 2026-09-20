#!/usr/bin/env python3
"""Build favicon.ico (32x32, 32bpp BGRA, uncompressed BMP-in-ICO) with the
isometric cube mark used by the page. No third-party libraries.

Run: python3 gen_favicon.py
"""
from __future__ import annotations

import pathlib
import struct

W = H = 32
BG = (0x0F, 0x0D, 0x0D, 0xFF)      # #0d0d0f
TOP = (0x28, 0x42, 0x5C, 0xFF)     # #5c4228
SIDE = (0x1A, 0x2B, 0x3D, 0xFF)    # #3d2b1a
FRONT = (0x2E, 0x5C, 0x1A, 0xFF)   # #1a5c2e


def in_tri(p, a, b, c) -> bool:
    (px, py), (ax, ay), (bx, by), (cx, cy) = p, a, b, c
    d1 = (px - bx) * (ay - by) - (ax - bx) * (py - by)
    d2 = (px - cx) * (by - cy) - (bx - cx) * (py - cy)
    d3 = (px - ax) * (cy - ay) - (cx - ax) * (py - ay)
    neg = d1 < 0 or d2 < 0 or d3 < 0
    pos = d1 > 0 or d2 > 0 or d3 > 0
    return not (neg and pos)


def rounded_bg(x: int, y: int, r: int = 7) -> bool:
    """True when the pixel is inside the rounded square."""
    cx = min(max(x, r), W - 1 - r)
    cy = min(max(y, r), H - 1 - r)
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def build_pixels() -> list[tuple[int, int, int, int]]:
    # cube vertices
    top_apex = (16, 4)
    top_left = (5, 10)
    top_right = (27, 10)
    mid = (16, 16)
    bot_left = (5, 22)
    bot_right = (27, 22)
    bot_apex = (16, 28)

    px = []
    for y in range(H):
        for x in range(W):
            c = BG if rounded_bg(x, y) else (0, 0, 0, 0)
            if in_tri((x + 0.5, y + 0.5), top_apex, top_right, mid) or in_tri(
                (x + 0.5, y + 0.5), top_apex, mid, top_left
            ):
                c = TOP
            elif in_tri((x + 0.5, y + 0.5), top_left, mid, bot_left) or in_tri(
                (x + 0.5, y + 0.5), top_left, bot_left, bot_apex
            ):
                c = SIDE
            elif in_tri((x + 0.5, y + 0.5), top_right, mid, bot_right) or in_tri(
                (x + 0.5, y + 0.5), top_right, bot_right, bot_apex
            ):
                c = FRONT
            px.append(c)
    return px


def main() -> None:
    pixels = build_pixels()

    # BMP rows are bottom-up; ICO stores BGRA in a bottom-up DIB.
    xor_rows = []
    for y in range(H - 1, -1, -1):
        row = bytearray()
        for x in range(W):
            r, g, b, a = pixels[y * W + x]
            row += bytes((b, g, r, a))
        xor_rows.append(bytes(row))
    xor_bitmap = b"".join(xor_rows)

    # AND mask: 1bpp, rows padded to 4 bytes. 0 = opaque (alpha channel wins).
    mask_row_bytes = ((W + 31) // 32) * 4
    and_mask = b"\x00" * (mask_row_bytes * H)

    dib = struct.pack(
        "<IiiHHIIiiII",
        40,            # header size
        W, H * 2,      # width, height (XOR + AND)
        1,             # planes
        32,            # bits per pixel
        0,             # BI_RGB
        len(xor_bitmap) + len(and_mask),
        0, 0, 0, 0,
    )
    image = dib + xor_bitmap + and_mask

    header = struct.pack("<HHH", 0, 1, 1) + struct.pack(
        "<BBBBHHII", W % 256, H % 256, 0, 0, 1, 32, len(image), 22
    )
    out = pathlib.Path(__file__).resolve().parent / "favicon.ico"
    out.write_bytes(header + image)
    print(f"wrote {out} ({out.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
