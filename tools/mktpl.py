#!/usr/bin/env python3
"""Encode a two-colour logo PNG as a single-image IA4 TPL (GX format 2).

  mktpl.py in.png out.tpl

The banner's logo material draws a texture as lerp(black, white, texture):
with black = (0,0,0) and white = Hero Orange #F05514, intensity 1 gives the
orange sun and intensity 0 the black wordmark, and alpha carries the shape.
So each pixel stores I = 15 where the logo is orange (red > 127), 0 where it is
black, and its alpha in 4 bits, the same format as the WeatherNews logo it
replaces.

Any size (the last tiles are padded with transparent texels).  Used to make
assets/accuweather/*.tpl from AccuWeather's official logo (AW_RGB_R.svg from
developer.accuweather.com's brand guidelines), rendered with
`resvg -w W -h H AW_RGB_R.svg out.png`.
"""
import struct
import sys

from PIL import Image


def encode(im):
    im = im.convert('RGBA')
    w, h = im.size
    px = im.load()
    out = bytearray()
    for ty in range(0, h, 4):
        for tx in range(0, w, 8):
            for y in range(ty, ty + 4):
                for x in range(tx, tx + 8):
                    r, g, b, a = px[x, y] if x < w and y < h else (0, 0, 0, 0)
                    i = 15 if r > 127 else 0
                    out.append((a * 15 + 127) // 255 << 4 | i)
    hdr = struct.pack('>III', 0x0020AF30, 1, 0x0C)
    hdr += struct.pack('>II', 0x14, 0)                    # image header, no palette
    hdr += struct.pack('>HHII', h, w, 2, 0x40)            # IA4, data at 0x40
    hdr += struct.pack('>IIIIfBBBB', 0, 0, 1, 1, 0.0, 0, 0, 0, 0)   # clamp, linear
    hdr += b'\0' * (0x40 - len(hdr))
    return bytes(hdr + out)


if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    open(sys.argv[2], 'wb').write(encode(Image.open(sys.argv[1])))
