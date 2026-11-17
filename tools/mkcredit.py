#!/usr/bin/env python3
"""Make the "AccuWeather" half of the Forecast Channel's in-channel credit line.

  mkcredit.py <Verdana Bold .ttf> <out dir>

TPLWeather.tpl's credit lines are 214x19 IA4 pictures of "supported by
weathernews": white letters with a dark drop shadow (images 22 and 24), and grey
letters with a black outline (23 and 25).  res.py keeps the channel's own
"supported by " (columns 0-99) and puts in columns 100-213 from

  credit.ia4          drop-shadow style
  credit_outline.ia4  outline style

each 114x19 bytes, row by row, one IA4 byte per pixel (alpha << 4 | intensity).
The word is Verdana Bold at 14.25 px, 87.5% wide, baseline at row 14, from
x = 102: the size, width and position that best match the channel's lettering of
"weathernews" (fitted against the original, pixel by pixel).  Pixels nothing is
drawn on are intensity 3, alpha 0, like the channel's.
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, X0, CUT = 214, 19, 102, 100
SIZE, SX, BASE, SS = 14.25, 0.875, 14, 8


def coverage(font, text):
    f = ImageFont.truetype(font, int(SIZE * SS))
    big = Image.new('L', (W * SS * 2, H * SS), 0)
    ImageDraw.Draw(big).text((0, BASE * SS), text, font=f, fill=255, anchor='ls')
    bb = big.getbbox()
    g = big.crop((bb[0], 0, bb[2], H * SS))
    g = g.resize((round(g.width * SX), H * SS), Image.LANCZOS)
    out = Image.new('L', (W * SS, H * SS), 0)
    out.paste(g, (X0 * SS, 0))
    return out.resize((W, H), Image.BOX)


def styles(g):
    G = [[g.getpixel((x, y)) / 255 for x in range(W)] for y in range(H)]
    outline = g.filter(ImageFilter.MaxFilter(3))
    O = [[outline.getpixel((x, y)) / 255 for x in range(W)] for y in range(H)]
    shadow, line = bytearray(), bytearray()
    for y in range(H):
        for x in range(CUT, W):
            gv = G[y][x]
            s = G[y - 1][x - 1] if x and y else 0.0
            a = max(gv, s)                          # white letter over a dark shadow, 1 px down-right
            i = (gv * 15 + (1 - gv) * s) / a if a else 3
            shadow.append(round(a * 15) << 4 | min(15, round(i)) if a else 3)
            a = max(gv, O[y][x])                    # grey letter (12) in a black outline
            i = gv * 12 / a if a else 3
            line.append(round(a * 15) << 4 | min(15, round(i)) if a else 3)
    return bytes(shadow), bytes(line)


if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    a, b = styles(coverage(sys.argv[1], 'AccuWeather'))
    open(os.path.join(sys.argv[2], 'credit.ia4'), 'wb').write(a)
    open(os.path.join(sys.argv[2], 'credit_outline.ia4'), 'wb').write(b)
