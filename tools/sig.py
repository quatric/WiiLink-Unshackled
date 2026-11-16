#!/usr/bin/env python3
"""Find code from one DOL in another by masked byte signature.

  sig.py <known.dol> <new.dol> <addr> [before] [after]

Prints every address in new.dol whose instructions match the words around
addr in known.dol (before/after words, default 8/8).  Relative branch targets,
r2/r13-relative offsets and immediates are masked, so the same SDK function
built into another program still matches.
"""
import struct
import sys


class Dol:
    def __init__(self, path):
        self.d = open(path, 'rb').read()
        f = lambda t, i: struct.unpack('>I', self.d[t + 4 * i:t + 4 * i + 4])[0]
        self.secs = [(i, f(0, i), f(0x48, i), f(0x90, i)) for i in range(18) if f(0x90, i)]
        self._masked = None

    def w(self, addr):
        for _, o, b, n in self.secs:
            if b <= addr < b + n:
                return struct.unpack('>I', self.d[o + addr - b:o + addr - b + 4])[0]
        raise KeyError(hex(addr))

    def text(self):
        """(base, words) of every text section (slots 0-6)."""
        for i, o, b, n in self.secs:
            if i < 7:
                yield b, struct.unpack('>%dI' % (n // 4), self.d[o:o + n - n % 4])

    def masked(self):
        if self._masked is None:
            self._masked = [(b, struct.pack('>%dI' % len(ws), *map(mask, ws))) for b, ws in self.text()]
        return self._masked


def mask(w):
    op = w >> 26
    if op == 18:                                    # b/bl: target
        return w & 0xFC000003
    if op == 16:                                    # bc: target
        return w & 0xFFFF0003
    if op in (7, 8, 10, 11, 12, 13, 14, 15, 24, 25, 28, 29):   # immediates
        return w & 0xFFFF0000
    if 32 <= op <= 55 and ((w >> 16) & 31) in (2, 13):         # small-data loads/stores
        return w & 0xFFFF0000
    return w


def find(ref, new, addr, before=8, after=8):
    pat = struct.pack('>%dI' % (before + after + 1),
                      *[mask(ref.w(addr + 4 * k)) for k in range(-before, after + 1)])
    hits = []
    for base, blob in new.masked():
        i = blob.find(pat)
        while i >= 0:
            if i % 4 == 0:
                hits.append(base + i + 4 * before)
            i = blob.find(pat, i + 1)
    return hits


if __name__ == '__main__':
    if len(sys.argv) < 4:
        raise SystemExit(__doc__)
    a = [int(x, 0) for x in sys.argv[3:]]
    for h in find(Dol(sys.argv[1]), Dol(sys.argv[2]), *a):
        print('0x%08X' % h)
