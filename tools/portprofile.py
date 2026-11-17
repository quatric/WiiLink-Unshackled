#!/usr/bin/env python3
"""Port a whole build.py CHANNELS profile to another build of the same channel
(another region or language).

  portprofile.py <key> <known main DOL> <new main DOL> [new key] [title]

Every code address in the profile (hook sites, arena, functions, patches,
debug / feature patches, keyboard and SD hooks) is found in the new DOL by
masked signature (sig.py), with a few window sizes until exactly one match;
data addresses are read back from the lis/addi pairs that build them in matched
code.  Patch words are checked against the new DOL, and branches in the new
words are pointed at the ported targets.  Prints the profile.
"""
import os
import pprint
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
from sig import Dol, find  # noqa: E402
from port import lis_pairs, s16  # noqa: E402
import build  # noqa: E402

WINDOWS = ((8, 8), (6, 6), (12, 12), (16, 16), (4, 4), (0, 16), (16, 0), (24, 24), (3, 3), (2, 2))


class Porter:
    def __init__(self, ref, new):
        self.ref, self.new = ref, new
        self.text = [(b, b + 4 * len(ws)) for b, ws in ref.text()]
        self.cache = {}
        self.done, self.later = {}, []        # data ported from lis/addi; data ported by its neighbour

    def is_code(self, a):
        return any(b <= a < e for b, e in self.text)

    def code(self, a):
        if a in self.cache:
            return self.cache[a]
        for before, after in WINDOWS:
            try:
                h = find(self.ref, self.new, a, before, after)
            except KeyError:
                continue
            if len(h) == 1:
                self.cache[a] = h[0]
                return h[0]
        # near a unique match: the same distance from it
        for d in range(4, 0x100, 4):
            for s in (-d, d):
                for before, after in ((8, 8), (12, 12)):
                    try:
                        h = find(self.ref, self.new, a + s, before, after)
                    except KeyError:
                        continue
                    if len(h) == 1:
                        self.cache[a] = h[0] - s
                        return h[0] - s
        raise SystemExit('code 0x%08X: not found' % a)

    def data(self, a):
        vals = set()
        for lis, user in lis_pairs(self.ref, a)[:12]:
            try:
                h = self.code(lis)
            except SystemExit:
                continue
            w1, w2 = self.new.w(h), self.new.w(h + user - lis)
            vals.add((((w1 & 0xFFFF) << 16) + s16(w2 & 0xFFFF)) & 0xFFFFFFFF)
        if len(vals) == 1:
            v = vals.pop()
            self.done[a] = v
            return v
        if not vals and self.done:          # nothing builds it with lis/addi: the shift of the
            near = min(self.done, key=lambda k: abs(k - a))      # nearest ported data address
            if abs(near - a) < 0x10000:
                self.later.append(a)
                return self.done[near] + a - near
        raise SystemExit('data 0x%08X: %s' % (a, [hex(v) for v in vals]))

    def addr(self, a):
        return self.code(a) if self.is_code(a) else self.data(a)

    def words(self, at_ref, at_new, ws):
        """new words at at_new: branches re-aimed at the ported targets"""
        out = []
        for i, w in enumerate(ws):
            if w >> 26 == 18 and not w & 2:                    # b / bl, relative
                off = w & 0x03FFFFFC
                if off & 0x02000000:
                    off -= 0x04000000
                tgt = self.code(at_ref + 4 * i + off)
                off = (tgt - (at_new + 4 * i)) & 0x03FFFFFC
                w = (w & 0xFC000003) | off
            elif w >> 26 == 16 and not w & 2:                  # bc, relative
                off = s16(w & 0xFFFC)
                tgt = at_ref + 4 * i + off
                if not (at_ref <= tgt < at_ref + 4 * len(ws) + 0x40):   # leaves the patch: port it
                    tgt = self.code(tgt)
                    w = (w & 0xFFFF0003) | ((tgt - (at_new + 4 * i)) & 0xFFFC)
            out.append(w)
        return out


def port_patch(P, new, p):
    a, old, neww = p[-4], p[-3], p[-2]
    na = P.addr(a)
    have = [new.w(na + 4 * i) for i in range(len(old))]
    want = P.words(a, na, old)
    if have != want:
        raise SystemExit('patch 0x%08X (%s): %s, expected %s' % (a, p[-1], [hex(w) for w in have],
                                                               [hex(w) for w in want]))
    return p[:-4] + (na, have, P.words(a, na, neww), p[-1])


def port(key, ref_path, new_path):
    ch = build.CHANNELS[key]
    ref, new = Dol(ref_path), Dol(new_path)
    P = Porter(ref, new)
    out = dict(ch)
    out['dol_size'] = len(new.d)
    arena = []
    for a in ch['arena']:
        arena.append(tuple(P.code(x) for x in a) if isinstance(a, tuple) else P.code(a))
    out['arena'] = arena
    first = arena[0]
    lis_a, addi_a = first if isinstance(first, tuple) else (first - 4, first)
    lis = new.w(lis_a) & 0xFFFF
    out['lis'] = lis
    out['arena_lo'] = ((lis << 16) + s16(new.w(addi_a) & 0xFFFF)) & 0xFFFFFFFF
    stack = [a for a in arena[1:] if not isinstance(a, tuple)]
    sl = sorted({((lis << 16) + s16(new.w(a) & 0xFFFF)) & 0xFFFFFFFF for a in stack} - {out['arena_lo']})
    out['stack_end'] = sl[0] if sl else ch['stack_end'] - ch['arena_lo'] + out['arena_lo']
    defs = {}
    for k, v in ch['defs'].items():
        if k in ('KPAD_STRIDE',):
            defs[k] = v
        elif k == 'SI_SHADOW':
            continue
        else:
            defs[k] = P.addr(v)
    if 'SI_SHADOW' in ch['defs']:
        defs['SI_SHADOW'] = defs['SI_BUSY'] + 4
    out['defs'] = {k: defs[k] for k in ch['defs']}
    out['sites'] = {k: P.code(v) for k, v in ch['sites'].items()}
    for k in ('patches', 'feature_patches', 'debug_patches'):
        if k in ch:
            out[k] = [port_patch(P, new, p) for p in ch[k]]
    if 'sympatches' in ch:
        out['sympatches'] = [(P.code(a), P.code(b), s) for a, b, s in ch['sympatches']]
    for k in ('kbd', 'cdbsd'):
        if k in ch:
            sub = dict(ch[k])
            sub['site'] = P.code(ch[k]['site'])
            sub['defs'], retry = {}, []
            for n, v in ch[k]['defs'].items():
                try:
                    sub['defs'][n] = P.addr(v) if v > 0x80000000 else v
                except SystemExit:
                    retry.append(n)
            for n in retry:                 # after the neighbours are ported
                sub['defs'][n] = P.addr(ch[k]['defs'][n])
            sub['defs'] = {n: sub['defs'][n] for n in ch[k]['defs']}
            out[k] = sub
    if P.later:
        print('# from the nearest ported data address: %s' % ', '.join('0x%08X' % a for a in P.later), file=sys.stderr)
    # every hook site still holds the instruction the stub replaces
    for name, (word, _) in build.sites(out).items():
        w = new.w(build.site_addr(out, name))
        if w != word:
            raise SystemExit('site %s at 0x%08X: 0x%08X, expected 0x%08X' % (name, build.site_addr(out, name), w, word))
    return out


def fmt(v):
    return pprint.pformat(v, width=110, sort_dicts=False)


def hexify(o):
    if isinstance(o, bool) or not isinstance(o, int):
        if isinstance(o, dict):
            return '{' + ', '.join('%r: %s' % (k, hexify(v)) for k, v in o.items()) + '}'
        if isinstance(o, (list, tuple)):
            s = ', '.join(hexify(v) for v in o)
            return ('(%s,)' % s if len(o) == 1 else '(%s)' % s) if isinstance(o, tuple) else '[%s]' % s
        return repr(o)
    return '0x%08X' % o if o >= 0x80000000 else '0x%X' % o if o >= 0x100 else repr(o)


if __name__ == '__main__':
    if len(sys.argv) < 4:
        raise SystemExit(__doc__)
    p = port(sys.argv[1], sys.argv[2], sys.argv[3])
    if len(sys.argv) > 5:
        p['title'] = sys.argv[5]
    print('    %r: {' % (sys.argv[4] if len(sys.argv) > 4 else sys.argv[1] + '_new'))
    for k, v in p.items():
        print('        %r: %s,' % (k, hexify(v)))
    print('    },')
