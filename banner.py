#!/usr/bin/env python3
"""Forecast Channel banner/icon: WeatherNews logo -> AccuWeather logo.

  banner.py <00000000.app in> <00000000.app out>

Content 0 is the channel's opening.bnr: an IMET header, then a U8 archive with
meta/banner.bin and meta/icon.bin (each IMD5 header + LZ77 + U8 archive).  The
logo is a picture pane on a white plate:

  banner: wn_logo  (89x34, IA4 texture tinted WeatherNews blue 84,82,172)
  icon:   logo_wn  (111x37, same)

Both become AccuWeather's horizontal logo in its real colours (Hero Orange
#F05514 sun, black wordmark): still a small IA4 texture, whose intensity picks
orange or black through the material's colours (tools/mktpl.py), resized to
the logo's 7:1 proportions with half a sun height of clear space on the plate.
The textures are 1:1 with their panes, like the originals, so icon.bin and
banner.bin stay about as small as WiiLink's.  The banner's
"supported by weathernews" line becomes "supported by AccuWeather" (same
length).  Textures: assets/accuweather/ (see tools/mktpl.py).
"""
import hashlib
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, 'assets', 'accuweather')
HERO_ORANGE = (0xF0, 0x55, 0x14)            # AccuWeather brand guidelines

# archive: [(tpl name, asset), (pane, new size, new x or None), material]
EDITS = {
    'meta/banner.bin': {
        'tpl': ('arc/timg/logo_weathernews.tpl', 'banner_logo.tpl'),
        'layout': 'arc/blyt/banner.brlyt',
        'pane': ('wn_logo', 140.0, 20.0, 80.0),     # centre origin, on the 0-160 white plate
        'mat': 'wn_logo',
        'text': ('supported by weathernews', 'supported by AccuWeather'),
    },
    'meta/icon.bin': {
        'tpl': ('arc/timg/icon_logo_wn.tpl', 'icon_logo.tpl'),
        'layout': 'arc/blyt/icon.brlyt',
        'pane': ('logo_wn', 112.0, 16.0, None),
        'mat': 'logo_wn',
        'text': None,
    },
}


# ---- LZ77 (type 0x10) ----
def lz77_decompress(d):
    if d[:4] != b'LZ77' or d[4] != 0x10:
        raise SystemExit('not LZ77 type 0x10')
    size = int.from_bytes(d[5:8], 'little')
    out = bytearray()
    i = 8
    while len(out) < size:
        flags = d[i]
        i += 1
        for bit in range(8):
            if len(out) >= size:
                break
            if flags & (0x80 >> bit):
                n = (d[i] >> 4) + 3
                disp = ((d[i] & 15) << 8 | d[i + 1]) + 1
                i += 2
                for _ in range(n):
                    out.append(out[-disp])
            else:
                out.append(d[i])
                i += 1
    return bytes(out)


def lz77_compress(d):
    """Hash chains plus one step of lazy matching (a bit tighter than the
    channel's own files)."""
    out = bytearray(b'LZ77' + bytes([0x10]) + len(d).to_bytes(3, 'little'))
    heads = {}
    n = len(d)
    added = 0                           # positions < added are in the chains

    def add_upto(e):
        nonlocal added
        while added < e:
            if added + 3 <= n:
                heads.setdefault(d[added:added + 3], []).append(added)
            added += 1

    def match(i):
        add_upto(i)
        best_len, best_disp = 0, 0
        if i + 3 <= n:
            for j in reversed(heads.get(d[i:i + 3], [])[-512:]):
                if i - j > 4096:
                    break
                k = 3
                while k < 18 and i + k < n and d[j + k] == d[i + k]:
                    k += 1
                if k > best_len:
                    best_len, best_disp = k, i - j
                    if k == 18:
                        break
        return best_len, best_disp

    i = 0
    while i < n:
        flag_pos = len(out)
        out.append(0)
        flags = 0
        for bit in range(8):
            if i >= n:
                break
            ln, disp = match(i)
            if 3 <= ln < 18 and match(i + 1)[0] > ln:
                ln = 0                  # a literal now buys a longer match next
            if ln >= 3:
                flags |= 0x80 >> bit
                v = (ln - 3) << 12 | (disp - 1)
                out += bytes((v >> 8, v & 0xFF))
                i += ln
            else:
                out.append(d[i])
                i += 1
        out[flag_pos] = flags
    while len(out) % 4:
        out.append(0)
    return bytes(out)


# ---- U8 ----
def u8_read(d):
    """[(path, is_dir, data)] in node order, plus the raw node/string info to rebuild."""
    if d[:4] != b'\x55\xAA\x38\x2D':
        raise SystemExit('not a U8 archive')
    root, = struct.unpack('>I', d[4:8])
    n, = struct.unpack('>I', d[root + 8:root + 12])
    st = root + 12 * n
    nodes = []
    for i in range(n):
        e = d[root + 12 * i:root + 12 * i + 12]
        typ = e[0]
        name_off = int.from_bytes(e[1:4], 'big')
        a, b = struct.unpack('>II', e[4:12])
        name = d[st + name_off:d.index(b'\0', st + name_off)].decode()
        nodes.append([typ, name, a, b, d[a:a + b] if typ == 0 else None])
    # full paths
    paths = [''] * n
    stack = [(0, n)]                    # (dir index, end)
    for i in range(1, n):
        while stack and i >= stack[-1][1]:
            stack.pop()
        parent = paths[stack[-1][0]] if stack else ''
        paths[i] = (parent + '/' if parent else '') + nodes[i][1]
        if nodes[i][0] == 1:
            stack.append((i, nodes[i][3]))
    return nodes, paths


def u8_write(nodes):
    names = bytearray()
    name_offs = []
    for typ, name, a, b, data in nodes:
        name_offs.append(len(names))
        names += name.encode() + b'\0'
    hdr_size = 12 * len(nodes) + len(names)
    data_off = (0x20 + hdr_size + 31) & ~31
    blob = bytearray()
    table = bytearray()
    for (typ, name, a, b, data), no in zip(nodes, name_offs):
        if typ == 0:
            off = data_off + len(blob)
            blob += data
            while len(blob) % 32:
                blob.append(0)
            a, b = off, len(data)
        table += bytes([typ]) + no.to_bytes(3, 'big') + struct.pack('>II', a, b)
    out = struct.pack('>IIII', 0x55AA382D, 0x20, hdr_size, data_off) + b'\0' * 16
    out += table + names
    out += b'\0' * (data_off - len(out))
    return bytes(out + blob)


# ---- layout edits ----
def edit_layout(d, pane, mat, text):
    d = bytearray(d)
    n, = struct.unpack('>H', d[0xE:0x10])
    off, = struct.unpack('>H', d[0xC:0xE])
    done = set()
    for _ in range(n):
        mg = bytes(d[off:off + 4])
        sz, = struct.unpack('>I', d[off + 4:off + 8])
        if mg == b'mat1':
            cnt, = struct.unpack('>H', d[off + 8:off + 10])
            for i in range(cnt):
                o = off + struct.unpack('>I', d[off + 12 + 4 * i:off + 16 + 4 * i])[0]
                if d[o:o + 20].split(b'\0')[0].decode() == mat:
                    d[o + 28:o + 36] = struct.pack('>4h', *HERO_ORANGE, 255)   # texture intensity 1 -> orange
                    done.add('mat')
        elif mg == b'pic1' and d[off + 0xC:off + 0x1C].split(b'\0')[0].decode() == pane[0]:
            d[off + 0x44:off + 0x4C] = struct.pack('>2f', pane[1], pane[2])
            if pane[3] is not None:
                d[off + 0x24:off + 0x28] = struct.pack('>f', pane[3])
            done.add('pane')
        elif mg == b'txt1' and text:
            sl, = struct.unpack('>H', d[off + 0x4E:off + 0x50])
            so, = struct.unpack('>I', d[off + 0x58:off + 0x5C])
            old, new = (t.encode('utf-16-be') for t in text)
            if bytes(d[off + so:off + so + len(old)]) == old:
                assert len(new) == len(old)
                d[off + so:off + so + len(new)] = new
                done.add('text')
        off += sz
    want = {'mat', 'pane'} | ({'text'} if text else set())
    if done != want:
        raise SystemExit('layout: missing %s' % sorted(want - done))
    return bytes(d)


def patch_bin(data, e):
    if data[:4] != b'IMD5':
        raise SystemExit('expected IMD5 header')
    arc = lz77_decompress(data[32:])
    nodes, paths = u8_read(arc)
    by_path = dict(zip(paths, nodes))
    tpl = open(os.path.join(ASSETS, e['tpl'][1]), 'rb').read()
    by_path[e['tpl'][0]][4] = tpl
    lyt = by_path[e['layout']]
    lyt[4] = edit_layout(lyt[4], e['pane'], e['mat'], e['text'])
    raw = u8_write(nodes)
    comp = lz77_compress(raw)
    return b'IMD5' + struct.pack('>I', len(comp)) + b'\0' * 8 + hashlib.md5(comp).digest() + comp, len(raw)


def patch_opening(d):
    imet = d.find(b'IMET')
    if imet < 0 or d[imet + 4:imet + 8] != b'\0\0\x06\0':
        raise SystemExit('no IMET header')
    start = imet - 0x40
    u8 = start + 0x600
    nodes, paths = u8_read(d[u8:])
    sizes = {}
    for path, node in zip(paths, nodes):
        if path in EDITS:
            node[4], sizes[path] = patch_bin(node[4], EDITS[path])
    if set(sizes) != set(EDITS):
        raise SystemExit('banner: missing %s' % sorted(set(EDITS) - set(sizes)))
    hdr = bytearray(d[:u8])
    # IMET sizes are the uncompressed archive sizes: icon, banner, sound
    struct.pack_into('>II', hdr, imet + 0xC, sizes['meta/icon.bin'], sizes['meta/banner.bin'])
    return bytes(hdr) + u8_write(nodes)


if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    out = patch_opening(open(sys.argv[1], 'rb').read())
    open(sys.argv[2], 'wb').write(out)
