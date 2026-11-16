#!/usr/bin/env python3
"""Print a build.py CHANNELS profile for a channel built with the Forecast Channel's SDK.

  port.py <Forecast Channel 00000001.app> <new 00000001.app> [key]

Every code address is found by masked signature (sig.py); data addresses are
read back from the lis/addi pairs in the matched code.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sig import Dol, find  # noqa: E402

# Forecast Channel (HAFE) addresses: (address, words before, words after)
CODE = {
    'POLL': (0x8012BF30, 0, 10),
    'SAMPLE': (0x8012C048, 6, 6),
    'PROBE': (0x8011F388, 0, 40),
    'BUTTONS': (0x8012C4F8, 6, 6),
    'MOTION': (0x8012C62C, 8, 4),
    'FN_SIGETTYPE': (0x800F3900, 0, 12),
    'FN_OSDISABLE': (0x800EA948, 0, 6),
    'FN_OSRESTORE': (0x800EA970, 0, 8),
    'SISETXY': (0x800F33FC, 0, 16),
    'ARENA1': (0x800E4034, 4, 6),
    'ARENA2': (0x800E40DC, 4, 6),
    'ARENA3': (0x800E4084, 4, 4),
    'ARENA4': (0x800E4110, 4, 4),
}
DATA = {'SI_TYPES': 0x801C6E88, 'SI_BUSY': 0x801C6E70, 'WPAD_TBL': 0x802F1490}


def s16(v):
    return v - 0x10000 if v & 0x8000 else v


def lis_pairs(dol, target):
    """(lis address, user address) of every lis/addi-or-load pair building target."""
    out = []
    for base, ws in dol.text():
        for i, w in enumerate(ws):
            if w >> 26 != 15 or (w >> 16) & 31:
                continue
            rd, hi = (w >> 21) & 31, w & 0xFFFF
            for j in range(i + 1, min(i + 12, len(ws))):
                w2 = ws[j]
                if w2 >> 26 in (14, 32, 34, 36, 38, 40, 44) and (w2 >> 16) & 31 == rd:
                    if ((hi << 16) + s16(w2 & 0xFFFF)) & 0xFFFFFFFF == target:
                        out.append((base + 4 * i, base + 4 * j))
                    break
    return out


def one(hits, what):
    if len(hits) != 1:
        raise SystemExit('%s: %d matches %s' % (what, len(hits), [hex(h) for h in hits]))
    return hits[0]


def main():
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    ref, new = Dol(sys.argv[1]), Dol(sys.argv[2])
    key = sys.argv[3] if len(sys.argv) > 3 else 'channel'
    a = {k: one(find(ref, new, *v), k) for k, v in CODE.items()}
    d = {}
    for name, target in DATA.items():
        vals = set()
        for lis, user in lis_pairs(ref, target)[:8]:
            h = find(ref, new, lis, 6, 6)
            if len(h) == 1:
                w1, w2 = new.w(h[0]), new.w(h[0] + user - lis)
                vals.add((((w1 & 0xFFFF) << 16) + s16(w2 & 0xFFFF)) & 0xFFFFFFFF)
        d[name] = one(sorted(vals), name)
    d['SI_SHADOW'] = d['SI_BUSY'] + 4
    # SISetXY reads the shadow at SI_BUSY+4: check the new DOL does too
    assert new.w(a['SISETXY'] + 0x2C) == ref.w(0x800F33FC + 0x2C) == 0x80050004
    lis = new.w(a['ARENA1'] - 4) & 0xFFFF
    arena_lo = ((lis << 16) + s16(new.w(a['ARENA1']) & 0xFFFF)) & 0xFFFFFFFF
    stack_end = ((lis << 16) + s16(new.w(a['ARENA3']) & 0xFFFF)) & 0xFFFFFFFF
    for k in ('ARENA2', 'ARENA4'):
        assert new.w(a[k] - 4) & 0xFFFF == lis
    print("    '%s': {" % key)
    print("        'title': '',")
    print("        'dol_size': %d," % len(new.d))
    print("        'arena_lo': 0x%08X, 'stack_end': 0x%08X, 'lis': 0x%04X," % (arena_lo, stack_end, lis))
    print("        'arena': [0x%08X, 0x%08X, 0x%08X, 0x%08X]," % tuple(a['ARENA%d' % i] for i in range(1, 5)))
    print("        'defs': {")
    for k in ('SI_TYPES', 'SI_BUSY', 'SI_SHADOW'):
        print("            '%s': 0x%08X," % (k, d[k]))
    for k in ('FN_SIGETTYPE', 'FN_OSDISABLE', 'FN_OSRESTORE'):
        print("            '%s': 0x%08X," % (k, a[k]))
    print("            'WPAD_TBL': 0x%08X," % d['WPAD_TBL'])
    print("        },")
    print("        'sites': {'POLL': 0x%08X, 'SAMPLE': 0x%08X, 'PROBE': 0x%08X," % (a['POLL'], a['SAMPLE'], a['PROBE']))
    print("                  'BUTTONS': 0x%08X, 'MOTION': 0x%08X}," % (a['BUTTONS'], a['MOTION']))
    print("        'clock': None,")
    print("    },")


if __name__ == '__main__':
    main()
