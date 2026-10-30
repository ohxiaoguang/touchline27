#!/usr/bin/env python3
"""Decode a DM_CTL "texraw <serial> <path>" dump into a PNG.

The dump is a text header line `w h format row_bytes` followed by h*row_bytes of texel data. Rows are padded to w*16 bytes;
texels within each row use the actual Metal format size.
This decodes by the header instead.

  texraw2png.py <dump> <out.png> [gain] [--depth]
"""
import struct, sys, zlib

# MTLPixelFormat -> (name, bytes/texel, decoder id)
FMT = {
    1: ("A8Unorm", 1, "a8"),
    20: ("R16Unorm", 2, "r16u"),
    25: ("R16Float", 2, "r16f"),
    55: ("R32Float", 4, "r32f"),
    65: ("RG16Float", 4, "rg16f"),
    70: ("RGBA8Unorm", 4, "unorm8"),
    71: ("RGBA8Unorm_sRGB", 4, "unorm8"),
    80: ("BGRA8Unorm", 4, "bgra8"),
    81: ("BGRA8Unorm_sRGB", 4, "bgra8"),
    90: ("RGB10A2Unorm", 4, "rgb10a2"),
    92: ("RG11B10Float", 4, "rg11b10f"),
    110: ("RGBA16Unorm", 8, "rgba16u"),
    115: ("RGBA16Float", 8, "rgba16f"),
    125: ("RGBA32Float", 16, "rgba32f"),
    250: ("Depth16Unorm", 2, "d16u"),
    252: ("Depth32Float", 4, "d32f"),
    253: ("Stencil8", 1, "stencil"),
    260: ("Depth32Float_Stencil8", 4, "d32f"),  # blit extracts depth only
}


def unsigned_float(bits, mantissa):
    exponent, fraction = bits >> mantissa, bits & ((1 << mantissa) - 1)
    if exponent == 31:
        return float('nan') if fraction else float('inf')
    if exponent == 0:
        return fraction * 2.0 ** (1 - 15 - mantissa)
    return (1 + fraction / (1 << mantissa)) * 2.0 ** (exponent - 15)



def decode(fmt, px, gain, depth_mode):
    kind = FMT.get(fmt, (None, None, None))[2]
    if kind == "rg11b10f":
        v = struct.unpack_from('<I', px)[0]
        r, g, b = unsigned_float(v & 2047, 6), unsigned_float((v >> 11) & 2047, 6), unsigned_float(v >> 22, 5)
    elif kind == "rgb10a2":
        v = struct.unpack_from('<I', px)[0]
        r, g, b = (v & 1023) / 1023, ((v >> 10) & 1023) / 1023, ((v >> 20) & 1023) / 1023
    elif kind == "rgba16f":
        r, g, b, a = struct.unpack_from("<4e", px, 0)
    elif kind == "bgra16f":
        b, g, r, a = struct.unpack_from("<4e", px, 0)
    elif kind == "rg16f":
        r, g = struct.unpack_from("<2e", px, 0)
        b, a = 0.0, 1.0
    elif kind == "rgba32f":
        r, g, b, a = struct.unpack_from("<4f", px, 0)
    elif kind == "d32f":
        v = struct.unpack_from("<f", px, 0)[0]
        g = 0.0 if v != v else min(max(v, 0.0), 1.0)
        return (int(g * 255),) * 3
    elif kind == "d16u":
        v = struct.unpack_from("<H", px, 0)[0] / 65535.0
        return (int(v * 255),) * 3
    elif kind == "r32f":
        v = struct.unpack_from("<f", px, 0)[0]
        v = 0.0 if v != v else min(max(v * gain, 0.0), 1.0)
        return (int(v ** (1 / 2.2) * 255),) * 3
    elif kind == "r16f":
        v = struct.unpack_from("<e", px, 0)[0]
        v = 0.0 if v != v else min(max(v * gain, 0.0), 1.0)
        return (int(v ** (1 / 2.2) * 255),) * 3
    elif kind == "bgra8":
        b, g, r, a = px[0], px[1], px[2], px[3]
        return (r, g, b)
    elif kind == "unorm8":
        return (px[0], px[1], px[2])
    elif kind == "rgba16u":
        r, g, b, a = struct.unpack_from("<4H", px, 0)
        return (r >> 8, g >> 8, b >> 8)
    elif kind == "stencil":
        v = px[0]
        return (v, v, v)
    else:                                  # unknown: treat as 4-byte float, gain on
        v = struct.unpack_from("<f", px, 0)[0]
        v = 0.0 if v != v else min(max(v * gain, 0.0), 1.0)
        return (int(v ** (1 / 2.2) * 255),) * 3
    out = []
    for v in (r, g, b):
        if v != v or v in (float("inf"), float("-inf")):
            v = 0.0
        v = min(max(v * gain, 0.0), 1.0)
        out.append(int((v if depth_mode else v ** (1 / 2.2)) * 255))
    return tuple(out)


TEXEL = {k: v[1] for k, v in FMT.items()}   # bytes per texel: the blit packs texels of the source format into each row, the row stride is padded to 16 bytes a texel


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    path, out = sys.argv[1], sys.argv[2]
    gain = float(sys.argv[3]) if len(sys.argv) > 3 and not sys.argv[3].startswith("-") else 1.0
    depth_mode = "--depth" in sys.argv
    with open(path, "rb") as f:
        head = f.readline().decode().split()
        w, h, fmt, row = int(head[0]), int(head[1]), int(head[2]), int(head[3])
        data = f.read()
    name = FMT.get(fmt, ("?", 0, "?"))[0]
    if len(data) < row * h:
        sys.exit("short dump: %d bytes, header wants %d" % (len(data), row * h))
    rows, hist, nonzero = [], {}, 0
    for y in range(h):
        line = bytearray()
        for x in range(w):
            tb = TEXEL.get(fmt, 16)
            px = data[y * row + x * tb: y * row + x * tb + 16]
            c = decode(fmt, px, gain, depth_mode)
            if max(c):
                nonzero += 1
            if y == h // 2 and x % 16 == 0:
                key = struct.unpack_from("<f", px, 0)[0] if fmt in (252, 25) else None
                if key is not None:
                    hist[round(key, 4)] = hist.get(round(key, 4), 0) + 1
            line += bytes(c)
        rows.append(bytes(line))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)

    raw = b"".join(b"\x00" + r for r in rows)
    with open(out, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))
    print("%s %dx%d fmt=%d (%s) row=%d gain=%g: %d of %d texels above zero%s"
          % (path, w, h, fmt, name, row, gain, nonzero, w * h, ("  mid-row values " + str(sorted(hist.items())[:6])) if hist else ""))


if __name__ == '__main__':
    main()
