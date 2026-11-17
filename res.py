#!/usr/bin/env python3
"""Edits to a channel's resources (everything but its main DOL): text in
manuals, layouts and message files, and a few pictures.

  res.py <unpacked WAD folder> <feature>...      (build.py wad calls apply())

Features:
  accuweather  Forecast Channel: "supported by weathernews" -> "supported by AccuWeather"
               in the channel (TPLWeather.tpl credit lines) and in its manual, and the
               manual's Weathernews Inc. source note -> AccuWeather.  (The Wii Menu
               banner and icon are banner.py.)
  wiilink      Every channel: "WiiConnect24" -> "WiiLink" where it names the service
               (manuals, layouts, message files, the News Channel's banner), but not
               where it names the Wii Settings option (standby connection, "WiiConnect24
               setting"), which the console still calls WiiConnect24.  "Nintendo" ->
               "WiiLink" only where Nintendo runs the service: the Forecast manual's
               "Nintendo may not be able to answer...", the Everybody Votes manual's
               "send your suggested question to Nintendo" and Check Mii Out's
               "Please Contact Nintendo".  Copyright lines and Club Nintendo stay.
  aplogo       News Channel: the manual's 2000s AP logo -> AP's current logo.

The containers are opened as needed (U8, LZ10 / LZ11 with or without the LZ77
magic, IMD5, the IMET banner) and only the ones holding a changed file are
packed again, with the same compression.
"""
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import banner  # noqa: E402  (U8, LZ10)

ASSETS = os.path.join(HERE, 'assets')

# ---- compression ----


def lz_decompress(d):
    from build import lz_decompress as f
    return f(d)


def lz11_compress(d):
    """LZ11 (type 0x11), hash chains, greedy."""
    n = len(d)
    out = bytearray(bytes([0x11]) + (n.to_bytes(3, 'little') if n < 1 << 24 else b'\0\0\0' + struct.pack('<I', n)))
    heads = {}
    i = 0
    added = 0
    while i < n:
        fp = len(out)
        out.append(0)
        flags = 0
        for bit in range(8):
            if i >= n:
                break
            while added < i:
                if added + 3 <= n:
                    heads.setdefault(d[added:added + 3], []).append(added)
                added += 1
            best, disp = 0, 0
            if i + 3 <= n:
                for j in reversed(heads.get(d[i:i + 3], [])[-256:]):
                    if i - j > 4096:
                        break
                    k = 3
                    lim = min(0x10110, n - i)
                    while k < lim and d[j + k] == d[i + k]:
                        k += 1
                    if k > best:
                        best, disp = k, i - j
                        if k == lim:
                            break
            if best >= 3:
                flags |= 0x80 >> bit
                dd = disp - 1
                if best <= 0x10:
                    out += bytes(((best - 1) << 4 | dd >> 8, dd & 0xFF))
                elif best <= 0x110:
                    v = best - 0x11
                    out += bytes((v >> 4, (v & 15) << 4 | dd >> 8, dd & 0xFF))
                else:
                    v = best - 0x111
                    out += bytes((0x10 | v >> 12, (v >> 4) & 0xFF, (v & 15) << 4 | dd >> 8, dd & 0xFF))
                i += best
            else:
                out.append(d[i])
                i += 1
        out[fp] = flags
    while len(out) % 4:
        out.append(0)
    return bytes(out)


def lz_compress(d, typ):
    if typ == 0x10:
        return banner.lz77_compress(d)[4:]        # without the 'LZ77' magic
    return lz11_compress(d)


# ---- containers ----
IMET_SIZES = {'meta/icon.bin': 0, 'meta/banner.bin': 1}


def unwrap(d, name):
    """(kind, inner) for a file that wraps another"""
    if d[:4] == b'LZ77' and d[4] in (0x10, 0x11):
        return ('LZ77', d[4]), lz_decompress(d[4:])
    if d[:4] == b'IMD5':
        inner = d[32:]
        if inner[:4] == b'LZ77':
            return ('IMD5', 'LZ77'), banner.lz77_decompress(inner)
        return ('IMD5', None), inner
    low = name.lower()
    if d[:1] in (b'\x10', b'\x11') and low.endswith(('.lz', '.lz7')):
        return ('LZ', d[0]), lz_decompress(d)
    return None, d


def rewrap(kind, inner):
    if kind is None:
        return inner
    if kind[0] == 'LZ77':
        return b'LZ77' + lz_compress(inner, kind[1])
    if kind[0] == 'LZ':
        return lz_compress(inner, kind[1])
    if kind[0] == 'IMD5':
        import hashlib
        body = banner.lz77_compress(inner) if kind[1] == 'LZ77' else inner
        return b'IMD5' + struct.pack('>I', len(body)) + b'\0' * 8 + hashlib.md5(body).digest() + body


def wanted(name):
    """only open the files that can hold something we edit (the big fonts, models
    and the browser library would be slow to unpack for nothing)"""
    low = name.lower()
    return not any(s in low for s in ('wwwlib', 'earth', 'font', '.brfn', '.brres', '.brsar', 'homebutton',
                                      '.ttc', '.ttf', '.atd', 'cursor'))


def edit_tree(d, path, leaf):
    """leaf(path, data) -> new data or None.  Returns the new data, or None."""
    name = path.rsplit('/', 1)[-1]
    if not wanted(name):
        return None
    if path.count('/') == 0:                       # a content: maybe the IMET banner
        i = d.find(b'IMET', 0, 0x100)
        if i >= 0 and d[i + 4:i + 8] == b'\0\0\x06\0':
            u8 = i - 0x40 + 0x600
            hdr = bytearray(d[:u8])
            new = edit_u8(d[u8:], path, leaf, sizes := {})
            if new is None:
                return None
            for p, k in IMET_SIZES.items():
                if p in sizes:
                    struct.pack_into('>I', hdr, i + 0xC + 4 * k, sizes[p])
            return bytes(hdr) + new
    try:
        kind, inner = unwrap(d, name)
    except Exception:
        return None
    if inner[:4] == b'U\xaa8-':
        new = edit_u8(inner, path, leaf, {})
    else:
        new = leaf(path, inner)
    if new is None:
        return None
    return rewrap(kind, new)


def edit_u8(d, path, leaf, sizes):
    nodes, paths = banner.u8_read(d)
    changed = False
    for node, p in zip(nodes, paths):
        if node[0] != 0:
            continue
        new = edit_tree(node[4], path + '/' + p, leaf)
        if new is not None:
            if p in IMET_SIZES:
                sizes[p] = len(unwrap(new, p)[1])
            node[4] = new
            changed = True
    return banner.u8_write(nodes) if changed else None


# ---- text ----
WC24 = re.compile(r'W( ?)i\1i\1C\1o\1n\1n\1e\1c\1t\1(?:2\1)?4')
# a sentence naming the Wii Settings option keeps "WiiConnect24"
SETTING = ('Standby', 'standby', 'スタンバイ', 'setting', 'Setting', 'param', 'configuraci', 'configurad',
           'Einstellung', 'impostazion', 'instelling', 'ingesteld', '設定', 'Wii Options', 'espera', 'veille')
SENTENCE = re.compile(r'[^.。!?！？]*(?:[.。!?！？]|$)', re.S)

NINTENDO = [            # (old, new): Nintendo as the service's operator
    ('Please note that Nintendo may not', 'Please note that WiiLink may not'),
    ('que Nintendo no pueda', 'que WiiLink no pueda'),
    ('que Nintendo ne sera', 'que WiiLink ne sera'),
    ('question to Nintendo.', 'question to WiiLink.'),
    ('propuesta a Nintendo.', 'propuesta a WiiLink.'),
    ('suggestion \xe0 Nintendo.', 'suggestion \xe0 WiiLink.'),
    ('suggestion &agrave; Nintendo.', 'suggestion &agrave; WiiLink.'),
    ('suggestion \xc3\xa0 Nintendo.', 'suggestion \xc3\xa0 WiiLink.'),     # UTF-8 read as Latin-1
]
# Check Mii Out's contest script (icon.cs) keeps its strings length-prefixed: same length
SAME_LENGTH = [
    ('Please Contact Nintendo For Further Information', 'Please Contact WiiLink For Further Information '),
]

ACCU = [
    ('supported by weathernews', 'supported by AccuWeather'),
    ('apoyado por weathernews', 'apoyado por AccuWeather'),
    ('soutien de weathernews', 'soutien de AccuWeather'),
    ('provided by Weathernews Inc.', 'provided by AccuWeather, Inc.'),
    ('Weathernews Inc. facilita', 'AccuWeather, Inc. facilita'),
    ('fournies par Weathernews Inc.', 'fournies par AccuWeather, Inc.'),
    ('http://weathernews.com', 'https://www.accuweather.com'),
]


def wiilink_text(s):
    """WiiConnect24 -> WiiLink in s, sentence by sentence"""
    def sent(m):
        t = m.group(0)
        if not WC24.search(t) or any(k in t for k in SETTING):
            return t
        return WC24.sub(lambda w: ' '.join('WiiLink') if w.group(1) else 'WiiLink', t)
    return SENTENCE.sub(sent, s)


def text_rules(feats):
    """str -> str for the enabled features"""
    def f(s):
        if 'wiilink' in feats:
            s = wiilink_text(s)
            for a, b in NINTENDO:
                s = s.replace(a, b)
        if 'accuweather' in feats:
            for a, b in ACCU:
                s = s.replace(a, b)
        return s
    return f


def utf16_strings(d, start=0, end=None, escapes=False):
    """(offset, text) of each NUL-terminated UTF-16BE run of printable text"""
    end = len(d) if end is None else min(end, len(d))
    i = start
    while i + 1 < end:
        o = i
        chars = []
        while i + 1 < end:
            c = d[i] << 8 | d[i + 1]
            if c == 0:
                break
            if escapes and c == 0x1A:
                if i + 2 >= end or d[i + 2] < 4:
                    break
                chars.append(d[i:i + d[i + 2]].decode('latin1'))      # kept as is
                i += d[i + 2]
                continue
            if c < 0x20 and c not in (10, 13, 9) or 0xD800 <= c < 0xE000 or c == 0xFFFF:
                break
            chars.append(chr(c))
            i += 2
        if len(chars) >= 4 and i + 1 < end and d[i] == 0 and d[i + 1] == 0:
            yield o, i + 2, chars
            i += 2
        else:
            i = o + 2


def encode16(chars):
    out = bytearray()
    for c in chars:
        out += c.encode('latin1') if len(c) > 1 else c.encode('utf-16-be')
    return bytes(out)


def edit_utf16(d, rule, start=0, end=None, escapes=False, must=None):
    """apply rule to each UTF-16 string that holds a keyword, in place: a shorter
    text is followed by NULs up to the old terminator, a longer one is refused"""
    d = bytearray(d)
    changed = False
    for o, e, chars in list(utf16_strings(d, start, end, escapes)):
        text = ''.join(c if len(c) == 1 else '\x1a' for c in chars)
        if must and not any(k in text for k in must):
            continue
        new = rule(text)
        if new == text:
            continue
        esc = iter(c for c in chars if len(c) > 1)
        nb = encode16([next(esc) if c == '\x1a' else c for c in new])
        if len(nb) + 2 > e - o:
            raise SystemExit('text grew: %r' % new)
        d[o:e] = nb + b'\0' * (e - o - len(nb))
        changed = True
    return bytes(d) if changed else None


def edit_brlyt(d, rule):
    d = bytearray(d)
    n, = struct.unpack('>H', d[0xE:0x10])
    off, = struct.unpack('>H', d[0xC:0xE])
    changed = False
    for _ in range(n):
        mg = bytes(d[off:off + 4])
        sz, = struct.unpack('>I', d[off + 4:off + 8])
        if mg == b'txt1':
            bl, sl = struct.unpack('>HH', d[off + 0x4C:off + 0x50])
            so, = struct.unpack('>I', d[off + 0x58:off + 0x5C])
            try:
                t = d[off + so:off + so + sl - 2].decode('utf-16-be') if sl >= 2 and sl % 2 == 0 else None
            except UnicodeDecodeError:
                t = None                            # not plain text (or not where the header says)
            if t is not None:
                new = rule(t)
                if new != t:
                    nb = new.encode('utf-16-be') + b'\0\0'
                    if len(nb) > bl:
                        raise SystemExit('layout text grew past its buffer: %r' % new)
                    d[off + so:off + so + max(sl, len(nb))] = nb + b'\0' * (max(sl, len(nb)) - len(nb))
                    struct.pack_into('>H', d, off + 0x4E, len(nb))
                    changed = True
        off += sz
    return bytes(d) if changed else None


def edit_bmg(d, rule):
    if d[:8] != b'MESGbmg1':
        return None
    off = 0x20
    dat = None
    while off < len(d):
        mg = d[off:off + 4]
        sz, = struct.unpack('>I', d[off + 4:off + 8])
        if mg == b'DAT1':
            dat = (off + 8, off + sz)
        if sz == 0:
            break
        off += sz
    if not dat or d[0x10] != 2:                     # UTF-16 only
        return None
    return edit_utf16(d, rule, dat[0], dat[1], escapes=True)


KEYWORDS = ('WiiConnect', 'W i i C o n n e c t', 'Nintendo', 'weathernews', 'Weathernews')


def edit_text(path, d, rule):
    low = path.lower()
    if low.endswith(('.html', '.htm')):
        s = d.decode('latin1')
        new = rule(s)
        return new.encode('latin1') if new != s else None
    if low.endswith('.brlyt'):
        return edit_brlyt(d, rule)
    if low.endswith('.bmg'):
        return edit_bmg(d, rule)
    if low.endswith('.cs.lz7') or low.endswith('.cs'):
        new = d
        if rule('WiiConnect24') != 'WiiConnect24':            # wiilink on
            for a, b in SAME_LENGTH:
                new = new.replace(a.encode('utf-16-be'), b.encode('utf-16-be'))
        return new if new != d else None
    return None                 # other formats may count their strings' lengths: left alone


# ---- pictures ----
def accu_credit_tpl(d):
    """TPLWeather.tpl: images 22-25 are the 'supported by' lines (ウェザーニュース and
    weathernews, each plain and outlined), IA4 214x19.  Columns 100-213 (the
    company's name) come from assets/accuweather/credit*.ia4 (tools/mkcredit.py);
    the channel's own "supported by " stays."""
    d = bytearray(d)
    n, to = struct.unpack('>II', d[4:12])
    for idx, f in ((22, 'credit.ia4'), (23, 'credit_outline.ia4'), (24, 'credit.ia4'), (25, 'credit_outline.ia4')):
        ih, _ = struct.unpack('>II', d[to + 8 * idx:to + 8 * idx + 8])
        h, w, fmt, off = struct.unpack('>HHII', d[ih:ih + 12])
        new = open(os.path.join(ASSETS, 'accuweather', f), 'rb').read()
        if (w, h, fmt) != (214, 19, 2) or len(new) != 114 * 19:
            raise SystemExit('TPLWeather.tpl: image %d is %dx%d format %d, not the credit line' % (idx, w, h, fmt))
        tiles_x = (w + 7) // 8
        for y in range(h):
            for x in range(100, w):                 # IA4: 8x4 tiles, a byte per pixel
                t = (y // 4) * tiles_x + x // 8
                d[off + t * 32 + (y % 4) * 8 + x % 8] = new[y * 114 + x - 100]
    return bytes(d)


def leaf_for(feats):
    rule = text_rules(feats)

    def leaf(path, d):
        low = path.lower()
        if 'accuweather' in feats and low.endswith('/tplweather.tpl.lz'):
            return accu_credit_tpl(d)
        if 'aplogo' in feats and low.endswith('/ap_logo.gif'):
            return open(os.path.join(ASSETS, 'news', 'ap_logo.gif'), 'rb').read()
        if feats & {'wiilink', 'accuweather'}:
            return edit_text(path, d, rule)
        return None
    return leaf


def apply(folder, feats, skip=()):
    """edit the contents (.app files) of an unpacked WAD in place; skip: file names
    to leave alone (the main DOL).  Returns the changed contents."""
    feats = set(feats)
    leaf = leaf_for(feats)
    done = []
    for f in sorted(os.listdir(folder)):
        if not f.endswith('.app') or f in skip:
            continue
        p = os.path.join(folder, f)
        d = open(p, 'rb').read()
        if d[:4] == b'\0\0\1\0' or (d[:1] in (b'\x10', b'\x11') and f in skip):
            continue
        new = edit_tree(d, f, leaf)
        if new is not None and new != d:
            open(p, 'wb').write(new)
            done.append(f)
    return done


if __name__ == '__main__':
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    print(apply(sys.argv[1], sys.argv[2:]))
