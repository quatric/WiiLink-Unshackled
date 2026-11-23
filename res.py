#!/usr/bin/env python3
"""Edits to a channel's resources (everything but its main DOL): text in
manuals, layouts and message files, and a few pictures.

  res.py <unpacked WAD folder> <feature>...      (build.py wad calls apply())

Features:
  accuweather  Forecast Channel: "supported by weathernews" -> "supported by WiiLink"
               in the channel (TPLWeather.tpl credit lines) and in its manual, and the
               manual's Weathernews Inc. source note -> AccuWeather.  (The Wii Menu
               banner and icon are banner.py.)
  wiilink      Every channel: "WiiConnect24" -> "WiiLink" where it names the service
               (manuals, layouts, message files, the News Channel's banner), but not
               where it names the Wii Settings option (standby connection, "WiiConnect24
               setting"), which the console still calls WiiConnect24.  "Nintendo" ->
               "WiiLink" only where Nintendo runs the service: the Forecast and News
               manuals' "Nintendo may not be able to answer..." / "cannot answer any
               inquiries" (and the Japanese 弊社), the Everybody Votes manual's
               "send your suggested question to Nintendo" and Check Mii Out's
               "Please Contact Nintendo".  Copyright lines and Club Nintendo stay.
  newslogos    News Channel: the manual's Source page shows the source WiiLink uses
               for the console's language, with its logo (assets/news, from WiiLink's
               News Channel server) and copyright line: USA AP (current logo); PAL
               English Reuters, French France 24, German tagesschau, Spanish RTVE,
               Italian ANSA, Dutch NOS; Japan Reuters.  (aplogo is the old name.)
  articlemusic News Channel: the music layer for reading the news (rev_news.brsar's
               NEW_BGM_READ, bgm_news_read_only) is heard.  The channel always plays
               it with the main music (NEW_BGM_NEWS, bgm_news_anytime) and fades it in
               on the reading screens (out on the globe), but the archive gives it
               volume 0.  Its loop
               is 78 bars and the main music's 56, so after the first pass the two
               no longer line up: every track of it now loops after 56 bars too.

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
    if not wanted(name) and not getattr(leaf, 'wants', lambda n: False)(name):
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


def u8_add(nodes, paths, rel, data):
    """add the file rel (its folder must exist) at the end of its folder"""
    folder, name = rel.rsplit('/', 1)
    p = paths.index(folder)
    if nodes[p][0] != 1:
        raise SystemExit('U8: %s is not a folder' % folder)
    k = nodes[p][3]                                 # one past the folder's last entry
    for i, n in enumerate(nodes):
        if n[0] == 1:
            if i >= k or (i <= p and (paths[i] == '' or folder == paths[i] or folder.startswith(paths[i] + '/'))):
                n[3] += 1
            if i >= k and n[2] >= k:
                n[2] += 1
    nodes.insert(k, [0, name, 0, len(data), data])
    paths.insert(k, rel)


def edit_u8(d, path, leaf, sizes):
    nodes, paths = banner.u8_read(d)
    changed = False
    for rel, data in getattr(leaf, 'add', lambda p: {})(path).items():
        if rel in paths:
            nodes[paths.index(rel)][4] = data
        else:
            u8_add(nodes, paths, rel, data)
        changed = True
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
           'Einstellung', 'impostazion', 'instelling', 'ingesteld', '設定', 'Wii Options', 'espera', 'veille',
           # the console's WiiConnect24 switched on / off, the Wii Options in other languages
           'activ', 'attiv', 'ausgeschaltet', 'uit.', 'turned off', 'enabled', 'disabled', 'Optionen', 'pzioni Wii',
           'opciones de Wii',
           # Nintendo Channel: games' "Supports WiiConnect24" feature tag
           'Supports', 'Compatible', 'Unterst\u00fctzt', 'Supporta', 'Werkt met', '\u5bfe\u5fdc')
SENTENCE = re.compile(r'[^.。!?！？]*(?:[.。!?！？]|$)', re.S)

NINTENDO = [            # (old, new): Nintendo as the service's operator
    ('Please note that Nintendo may not', 'Please note that WiiLink may not'),
    ('que Nintendo no pueda', 'que WiiLink no pueda'),
    ('que Nintendo ne sera', 'que WiiLink ne sera'),
    ('question to Nintendo.', 'question to WiiLink.'),
    ('propuesta a Nintendo.', 'propuesta a WiiLink.'),
    ('suggestion \xe0 Nintendo.', 'suggestion \xe0 WiiLink.'),
    ('suggestion &agrave; Nintendo.', 'suggestion &agrave; WiiLink.'),
    # News Channel (PAL, Japan) Source page: "Nintendo cannot answer any inquiries..."
    ('Please note that Nintendo cannot', 'Please note that WiiLink cannot'),
    ("Veuillez noter que Nintendo n'est", "Veuillez noter que WiiLink n'est"),
    ('dass Nintendo keinerlei', 'dass WiiLink keinerlei'),
    ('Recuerda que Nintendo no puede', 'Recuerda que WiiLink no puede'),
    ('Nota: Nintendo non ', 'Nota: WiiLink non '),
    ('Nintendo kan geen vragen', 'WiiLink kan geen vragen'),
    ('\u5f0a\u793e\u306f\u3001\u914d\u4fe1', 'WiiLink\u306f\u3001\u914d\u4fe1'),      # 弊社は、配信 (Japan)
]
# Check Mii Out's contest script (icon.cs) keeps its strings length-prefixed: same length
SAME_LENGTH = [
    ('Please Contact Nintendo For Further Information', 'Please Contact WiiLink For Further Information '),
]

ACCU = [
    ('supported by weathernews', 'supported by WiiLink'),
    ('apoyado por weathernews', 'apoyado por WiiLink'),
    ('soutien de weathernews', 'soutien de WiiLink'),
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
        try:
            enc, s = 'utf-8', d.decode('utf-8')     # most manuals (the Japanese ones' sentences need it)
        except UnicodeDecodeError:
            enc, s = 'latin1', d.decode('latin1')
        new = rule(s)
        return new.encode(enc) if new != s else None
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
    company's name) come from assets/credit/credit*.ia4 (tools/mkcredit.py);
    the channel's own "supported by " stays."""
    d = bytearray(d)
    n, to = struct.unpack('>II', d[4:12])
    for idx, f in ((22, 'credit.ia4'), (23, 'credit_outline.ia4'), (24, 'credit.ia4'), (25, 'credit_outline.ia4')):
        ih, _ = struct.unpack('>II', d[to + 8 * idx:to + 8 * idx + 8])
        h, w, fmt, off = struct.unpack('>HHII', d[ih:ih + 12])
        new = open(os.path.join(ASSETS, 'credit', f), 'rb').read()
        if (w, h, fmt) != (214, 19, 2) or len(new) != 114 * 19:
            raise SystemExit('TPLWeather.tpl: image %d is %dx%d format %d, not the credit line' % (idx, w, h, fmt))
        tiles_x = (w + 7) // 8
        for y in range(h):
            for x in range(100, w):                 # IA4: 8x4 tiles, a byte per pixel
                t = (y // 4) * tiles_x + x // 8
                d[off + t * 32 + (y % 4) * 8 + x % 8] = new[y * 114 + x - 100]
    return bytes(d)


# ---- News Channel article music ----
SEQ_U8 = set(range(0xB0, 0xE0))            # commands with a u8 argument
SEQ_S16 = {0xE0, 0xE1, 0xE3}


def seq_varlen(n):
    out = [n & 0x7F]
    while n > 0x7F:
        n >>= 7
        out.insert(0, 0x80 | (n & 0x7F))
    return bytes(out)


def seq_walk(d, base, at):
    """a track's commands from at to its jump: [(offset, tick before, command, tick after,
    in a subroutine)], the jump's target and the subroutines called"""
    out, t, notewait, stack, calls = [], 0, True, [], set()
    while True:
        start, c = at, d[base + at]
        at += 1

        def varlen():
            nonlocal at
            v = 0
            while True:
                b = d[base + at]
                at += 1
                v = v << 7 | b & 0x7F
                if not b & 0x80:
                    return v
        if 0xA0 <= c <= 0xA5:
            raise SystemExit('bgm_news: prefix command 0x%02X at 0x%X (not expected)' % (c, start))
        before, sub = t, bool(stack)
        if c < 0x80:                                # note: key, velocity, length
            at += 1
            n = varlen()
            t += n if notewait else 0
        elif c == 0x80:
            t += varlen()
        elif c == 0x81:
            varlen()
        elif c == 0x88:
            at += 4
        elif c == 0x89:
            if stack:
                raise SystemExit('bgm_news: a jump in a subroutine at 0x%X' % start)
            out.append((start, before, c, t, sub))
            return out, int.from_bytes(d[base + at:base + at + 3], 'big'), calls
        elif c == 0x8A:
            tgt = int.from_bytes(d[base + at:base + at + 3], 'big')
            stack.append(at + 3)
            calls.add(tgt)
            at = tgt
        elif c == 0xFD:
            at = stack.pop()
        elif c == 0xC7:
            notewait = bool(d[base + at])
            at += 1
        elif c in SEQ_U8:
            at += 1
        elif c in SEQ_S16:
            at += 2
        elif c == 0xF0:
            at += 3 if d[base + at] != 0xE0 else 2
            at += 1
        elif c == 0xFE:
            at += 2
        elif c != 0xFC:
            raise SystemExit('bgm_news: command 0x%02X at 0x%X' % (c, start))
        out.append((start, before, c, t, sub))


def rseq_tracks(d, o):
    """the RSEQ at o: (data base, name, {track: (start, loop start)})"""
    be = lambda a: struct.unpack('>I', d[a:a + 4])[0]
    db = o + be(o + 0x10)
    base = db + be(db + 8)
    lbl = o + be(o + 0x18)
    labels = {}
    for k in range(be(lbl + 8)):
        lo = lbl + 8 + be(lbl + 12 + 4 * k)
        labels[d[lo + 8:lo + 8 + be(lo + 4)].decode()] = be(lo)
    begin = [k for k in labels if k.endswith('_Begin')]
    if not begin:                                   # sound effects: no SMF tracks
        return base, None, {}
    name = begin[0][:-6]
    tracks = {}
    for k, v in labels.items():
        m = re.fullmatch(re.escape(name) + r'_Track_(\d+)', k)
        if m:
            tracks[int(m.group(1))] = (v, labels.get(k + '_LoopStart'))
    return base, name, tracks


def seq_loop(d, base, start, loop):
    """(tick at the loop start, loop length, walk)"""
    w, tgt, calls = seq_walk(d, base, start)
    if tgt != loop:
        raise SystemExit('bgm_news: a track jumps to 0x%X, not its loop start 0x%X' % (tgt, loop))
    at = {off: before for off, before, _, _, sub in w if not sub}
    return at[loop], w[-1][3] - at[loop], w, calls


def news_read_bgm(d):
    """rev_news.brsar: NEW_BGM_READ at NEW_BGM_NEWS's volume, its loop as long as the main music's"""
    d = bytearray(d)
    be = lambda a: struct.unpack('>I', d[a:a + 4])[0]
    if d[:4] != b'RSAR':
        return None
    symb, info = be(0x10), be(0x18)
    names = symb + 8 + be(symb + 8)
    string = lambda i: d[symb + 8 + be(names + 4 + 4 * i):].split(b'\0', 1)[0].decode()
    ib = info + 8
    st = ib + be(ib + 4)                                         # the sound table
    sounds = [ib + be(st + 4 + 8 * k + 4) for k in range(be(st))]
    by = {string(be(e)): e for e in sounds}
    news, read = by.get('NEW_BGM_NEWS'), by.get('NEW_BGM_READ')
    if news is None or read is None:
        raise SystemExit('rev_news.brsar: no NEW_BGM_NEWS / NEW_BGM_READ')
    d[read + 20] = d[news + 20]                                  # volume
    seqs = {}
    for m in re.finditer(b'RSEQ\xfe\xff', d):
        base, name, tracks = rseq_tracks(d, m.start())
        seqs[name] = (base, tracks)
    base, tracks = seqs['SMF_bgm_news_anytime']
    loops = {seq_loop(d, base, s, l)[:2] for s, l in tracks.values()}
    if len(loops) != 1:
        raise SystemExit('bgm_news_anytime: tracks loop differently: %s' % loops)
    first, length = loops.pop()
    base, tracks = seqs['SMF_bgm_news_read_only']
    for n, (s, l) in sorted(tracks.items()):
        lstart, llen, w, calls = seq_loop(d, base, s, l)
        if lstart != first or llen < length:
            raise SystemExit('bgm_news_read_only track %d: loop at %d, %d long' % (n, lstart, llen))
        if llen == length:
            continue
        end = lstart + length
        jump_end = w[-1][0] + 4
        top = [i for i, x in enumerate(w) if not x[4]]
        for k, i in enumerate(top[:-1]):
            at, before, c, after, _ = w[i]
            stop = w[top[k + 1]][1]                 # a call lasts until the command after it
            if before == end:
                cut = b''
            elif before < end < stop and c == 0x80:     # a wait across the new end: shortened
                cut = b'\x80' + seq_varlen(end - before)
            elif before < end < stop and c == 0x8A:     # a call: its commands up to the new end
                body = w[i + 1:top[k + 1]]
                if any(x[2] in (0x8A, 0xFD) for x in body[:-1]) or body[-1][2] != 0xFD:
                    raise SystemExit('bgm_news_read_only track %d: nested call at 0x%X' % (n, at))
                j = next(m for m, x in enumerate(body) if x[3] > end or x[1] == end)
                cut = bytes(d[base + body[0][0]:base + body[j][0]])
                if body[j][1] < end:
                    if body[j][2] != 0x80:
                        raise SystemExit('bgm_news_read_only track %d: command 0x%02X across the loop end'
                                         % (n, body[j][2]))
                    cut += b'\x80' + seq_varlen(end - body[j][1])
            elif before < end < stop:
                raise SystemExit('bgm_news_read_only track %d: command 0x%02X across the loop end' % (n, c))
            else:
                continue
            break
        else:
            raise SystemExit('bgm_news_read_only track %d: no command at the new loop end' % n)
        new = cut + b'\x89' + l.to_bytes(3, 'big')
        if at + len(new) > jump_end:
            raise SystemExit('bgm_news_read_only track %d: no room for the jump' % n)
        if any(at <= x < at + len(new) for t in tracks.values() for x in seq_loop(d, base, *t)[3]):
            raise SystemExit('bgm_news_read_only track %d: the jump would cover a subroutine' % n)
        d[base + at:base + at + len(new)] = new
        if seq_loop(d, base, s, l)[:2] != (first, length):
            raise SystemExit('bgm_news_read_only track %d: loop not shortened' % n)
    return bytes(d)


# ---- News Channel sources ----
NEWS_IMG = 'html/img/CHM_common_source/'
NEWS_PAL = {   # language: (logo, copyright line)
    'ukv': ('reuters', '\u00a9 Reuters. All rights reserved.'),
    'fra': ('france24', '\u00a9 Copyright France 24 - Tous droits r\u00e9serv\u00e9s.'),
    'noe': ('tagesschau', '\u00a9 ARD-aktuell / tagesschau.de'),
    'esp': ('rtve', '\u00a9 Corporaci\u00f3n de Radio y Televisi\u00f3n Espa\u00f1ola'),
    'ita': ('ansa', 'Copyright \u00a9 ANSA<br />Tutti i diritti riservati'),
    'hol': ('nos', '\u00a9 NOS'),
}
# PAL page_10: from the first source's logo to the closing note
NEWS_BLOCK = re.compile(r'<img src="\.\./\.\./img/CHM_common_source/(?:AFP|ANP|ANSA)_logo\.gif" ?/?>.*?(?=<span class="redTextTwo">)', re.S)


def news_pal_page(lang, s):
    logo, line = NEWS_PAL[lang]
    w, h = jpeg_size(asset('news', logo + '.jpg'))
    new = ('<img src="../../img/CHM_common_source/WiiLink_%s.jpg" width="%d" height="%d" /><br />\r\n'
           '              <img src="../../img/CHM_common_source/spacer.png" height="10" /><br />\r\n'
           '              %s<br />\r\n'
           '              <img src="../../img/CHM_common_source/spacer.png" width="30" height="30" /><br />\r\n'
           '              ' % (logo, w, h, line.encode('utf-8').decode('latin1')))
    out, n = NEWS_BLOCK.subn(lambda m: new, s, count=1)
    if not n:
        raise SystemExit('News manual (%s): the Source page is not the one expected' % lang)
    return out


def news_jp_page(s):
    """Japan page_09: one picture of all the sources (page9_logos.png, 530x350) ->
    Reuters' logo, and its copyright line under it"""
    w, h = jpeg_size(asset('news', 'reuters.jpg'))
    old = re.search(r'<img src="page9_logos\.png"[^>]*>', s)
    if not old:
        raise SystemExit('News manual (Japan): the Source page is not the one expected')
    return s[:old.start()] + ('<img src="WiiLink_reuters.jpg" alt="Reuters" width="%d" height="%d" /><br /><br />'
                              '\u00a9 Reuters. All rights reserved.' % (w, h)).encode('utf-8').decode('latin1') + s[old.end():]


def asset(*p):
    return open(os.path.join(ASSETS, *p), 'rb').read()


def jpeg_size(d):
    i = 2
    while i < len(d):
        m, n = d[i + 1], struct.unpack('>H', d[i + 2:i + 4])[0]
        if 0xC0 <= m <= 0xCF and m not in (0xC4, 0xC8, 0xCC):
            h, w = struct.unpack('>HH', d[i + 5:i + 9])
            return w, h
        i += 2 + n
    raise ValueError('no JPEG frame')


def news_leaf(path, d):
    low = path.lower()
    m = re.search(r'/html/(\w+)/page_10/page_10\.html$', path)
    if m and m.group(1) in NEWS_PAL and '/html-eu.arc/' in path:
        s = d.decode('latin1')
        return news_pal_page(m.group(1), s).encode('latin1')
    if '/html-jp.arc/' in path and low.endswith('/page_09/page_09.html'):
        return news_jp_page(d.decode('latin1')).encode('latin1')
    if low.endswith('/ap_logo.gif') and '/html-eu.arc/' not in path:
        return asset('news', 'ap_logo.gif')
    return None


def news_add(path):
    """files to add to the U8 archive at path: the logos"""
    if path.endswith('/html-eu.arc'):
        return {NEWS_IMG + 'WiiLink_%s.jpg' % logo: asset('news', logo + '.jpg') for logo, _ in NEWS_PAL.values()}
    if path.endswith('/html-jp.arc'):
        return {'html/page_09/WiiLink_reuters.jpg': asset('news', 'reuters.jpg')}
    return {}


def leaf_for(feats):
    rule = text_rules(feats)

    def leaf(path, d):
        low = path.lower()
        if 'accuweather' in feats and low.endswith('/tplweather.tpl.lz'):
            return accu_credit_tpl(d)
        if 'wiilink' in feats and low.endswith('news_layout.arc.lz/arc/blyt/error0.brlyt'):
            # the News Channel's "WiiConnect24 Standby Connection is turned off" screen: WiiLink too
            out = edit_brlyt(d, lambda t: WC24.sub(lambda w: ' '.join('WiiLink') if w.group(1) else 'WiiLink', t))
            if out is not None:
                return out
        if 'articlemusic' in feats and low.endswith('/rev_news.brsar'):
            return news_read_bgm(d)
        changed = news_leaf(path, d) if feats & {'newslogos', 'aplogo'} else None
        if changed is not None:
            d = changed
        if feats & {'wiilink', 'accuweather'}:
            out = edit_text(path, d, rule)
            if out is not None:
                return out
        return changed

    leaf.add = news_add if feats & {'newslogos', 'aplogo'} else (lambda p: {})
    leaf.wants = (lambda n: n.lower() == 'rev_news.brsar') if 'articlemusic' in feats else (lambda n: False)
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
