#!/usr/bin/env python3
"""Classic Controller + GameCube controller patch for the WiiLink Forecast and News Channels (USA).

  build.py dol <00000001.app in> <00000001.app out> [--clock] [--debug-feed]
  build.py wad <channel .wad> <out.wad> [--clock] [--debug-feed]

The channel is recognised from its main DOL.  Builds the hooks in src/ with
devkitPPC, links them at the start of the OS arena (right above the main
stack), moves the arena start up past them, adds them to the main DOL as a new
section (last slot) and plants a branch at each hook site.  --clock (Forecast
Channel only) also applies forecast_us_clock_patch.py.
`wad` unpacks with Sharpii, patches content 1, repacks and fakesigns.

Mapping (Wii Remote <- Classic Controller / GameCube):
  A <- A / A       B <- B / B       1 <- X / X       2 <- Y / Y
  - <- Minus / L   + <- Plus / R    HOME <- HOME / Start
  D-pad <- D-pad / D-pad
  pointer <- left stick / control stick      twist <- right stick / C-stick
"""
import hashlib, os, shutil, struct, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
DEVKIT = os.environ.get('DEVKITPPC', '/opt/devkitpro/devkitPPC')
CC = DEVKIT + '/bin/powerpc-eabi-'
SHARPII = os.environ.get('SHARPII', 'sharpii')

# Per-channel addresses.  Both channels use the same SDK build, so every hook
# site is the same code at a different address (tools/sig.py finds them).
#   arena:   OSInit's four "addi rX,rX,lo" that build the arena start; lis is
#            the high half they pair with.  __ArenaLo is where the hooks go.
CHANNELS = {
    'forecast': {
        'title': 'Forecast Channel (USA, HAFE)',
        'dol_size': 1926048,
        'arena_lo': 0x803457C0, 'stack_end': 0x803437A8, 'lis': 0x8034,
        'arena': [0x800E4034, 0x800E40DC, 0x800E4084, 0x800E4110],
        'defs': {
            'SI_TYPES': 0x801C6E88,     # si:: per-channel device type cache
            'SI_BUSY': 0x801C6E70,      # si:: channel being transferred (-1 = idle)
            'SI_SHADOW': 0x801C6E74,    # si:: shadow of SIPOLL (SISetXY rewrites SIPOLL from it)
            'FN_SIGETTYPE': 0x800F3900,
            'FN_OSDISABLE': 0x800EA948, # OSDisableInterrupts
            'FN_OSRESTORE': 0x800EA970, # OSRestoreInterrupts
            'WPAD_TBL': 0x802F1490,     # WPAD control block pointers
        },
        'sites': {'POLL': 0x8012BF30, 'SAMPLE': 0x8012C048, 'PROBE': 0x8011F388,
                  'BUTTONS': 0x8012C4F8, 'MOTION': 0x8012C62C},
        'clock': 'forecast_us_clock_patch',
    },
    'news': {
        'title': 'News Channel (USA, HAGE)',
        'dol_size': 2019232,
        'arena_lo': 0x8036C6E0, 'stack_end': 0x8036A6D0, 'lis': 0x8037,
        'arena': [0x800FC710, 0x800FC7B8, 0x800FC760, 0x800FC7EC],
        'defs': {
            'SI_TYPES': 0x801DDDC8,
            'SI_BUSY': 0x801DDDB0,
            'SI_SHADOW': 0x801DDDB4,
            'FN_SIGETTYPE': 0x8010BFDC,
            'FN_OSDISABLE': 0x80103024,
            'FN_OSRESTORE': 0x8010304C,
            'WPAD_TBL': 0x80318690,
        },
        'sites': {'POLL': 0x80144B70, 'SAMPLE': 0x80144C88, 'PROBE': 0x80137FC8,
                  'BUTTONS': 0x80145138, 'MOTION': 0x8014526C},
        'clock': None,
    },
}
HOOK_SIZE = 0x1000              # code + 0x100 bytes of state, carved from the arena start

# name: (original word, stub symbol) -- the same instruction in every channel
SITES = {
    'POLL':    (0x9421FF40, 'hook_poll'),     # KPADiRead: stwu r1,-192(r1)
    'SAMPLE':  (0x881F010F, 'hook_sample'),   # KPADiRead: lbz r0,0x10F(r31)
    'PROBE':   (0x9421FFF0, 'hook_probe'),    # WPADProbe: stwu r1,-16(r1)
    'BUTTONS': (0x70E09FFF, 'hook_buttons'),  # KPADiRead: andi. r0,r7,0x9FFF
    'MOTION':  (0x35EFFFFF, 'hook_motion'),   # KPADiRead: addic. r15,r15,-1 (after the copy-out)
}


def layout(ch):
    """BASE/END/STATE and the four arena patches (address, old word, new word)."""
    base = ch['arena_lo']
    end = base + HOOK_SIZE
    assert end % 32 == 0
    def lo(v):
        d = v - (ch['lis'] << 16)
        assert -0x8000 <= d < 0x8000, hex(v)
        return d & 0xFFFF
    arena = []
    for i, a in enumerate(ch['arena']):
        old_lo = lo(base) if i < 2 else lo(ch['stack_end'])
        arena.append((a, old_lo, lo(end)))
    return base, end, end - 0x100, arena


def detect(data):
    for key, ch in CHANNELS.items():
        if len(data) == ch['dol_size']:
            return key, ch
    raise SystemExit('unknown main DOL (%d bytes); supported: %s' % (
        len(data), ', '.join('%s (%d)' % (c['title'], c['dol_size']) for c in CHANNELS.values())))


CFLAGS = ['-O2', '-mcpu=750', '-mbig-endian', '-msdata=none', '-ffreestanding', '-fno-pic', '-fno-builtin',
          '-fno-tree-loop-distribute-patterns', '-fno-unroll-loops', '-fno-asynchronous-unwind-tables',
          '-fno-stack-protector', '-nostdlib', '-Wall', '-Werror']


def run(cmd):
    subprocess.check_call(cmd)


def build_blob(ch, base, state, debug_feed=False):
    tmp = tempfile.mkdtemp(prefix='fcpad')
    src = os.path.join(HERE, 'src')
    D = ['-D%s=0x%08Xu' % kv for kv in dict(ch['defs'], STATE=state).items()]
    if debug_feed:
        D.append('-DDEBUG_FEED')
    run([CC + 'gcc'] + CFLAGS + ['-msoft-float'] + D + ['-c', src + '/gc.c', '-o', tmp + '/gc.o'])
    run([CC + 'gcc'] + CFLAGS + ['-mhard-float'] + D + ['-c', src + '/motion.c', '-o', tmp + '/motion.o'])
    run([CC + 'gcc', '-mbig-endian', '-c', '-x', 'assembler-with-cpp', src + '/hooks.S', '-o', tmp + '/hooks.o'])
    ld = open(tmp + '/link.ld', 'w')
    ld.write('SECTIONS {\n  . = 0x%08X;\n  .text : { *(.hooks) *(.text .text.*) *(.rodata .rodata.*) }\n'
             '  /DISCARD/ : { *(.comment) *(.eh_frame) *(.note*) *(.gnu.attributes) }\n}\n' % base)
    ld.close()
    syms = ['--defsym=RET_%s=0x%08X' % (n, ch['sites'][n] + 4) for n in SITES]
    run([CC + 'ld', '-T', tmp + '/link.ld', '--no-undefined', '-o', tmp + '/b.elf'] + syms +
        [tmp + '/hooks.o', tmp + '/gc.o', tmp + '/motion.o'])
    # no data/bss outside .text allowed: everything must live in the one section
    hdr = subprocess.check_output([CC + 'objdump', '-h', tmp + '/b.elf']).decode()
    for line in hdr.splitlines():
        f = line.split()
        if len(f) > 6 and f[0].isdigit() and f[1] != '.text' and int(f[2], 16):
            raise SystemExit('unexpected section %s in hook image' % f[1])
    run([CC + 'objcopy', '-O', 'binary', '-j', '.text', tmp + '/b.elf', tmp + '/b.bin'])
    blob = open(tmp + '/b.bin', 'rb').read()
    nm = subprocess.check_output([CC + 'nm', tmp + '/b.elf']).decode()
    syms = {l.split()[2]: int(l.split()[0], 16) for l in nm.splitlines() if len(l.split()) == 3}
    if base + len(blob) > state:
        raise SystemExit('hook image too big: ends at 0x%08X, state starts 0x%08X' % (base + len(blob), state))
    shutil.rmtree(tmp)
    return blob, syms


def b_to(src, dst):
    off = dst - src
    assert -0x2000000 <= off < 0x2000000 and off % 4 == 0
    return 0x48000000 | (off & 0x03FFFFFC)


class Dol:
    def __init__(self, data):
        self.d = bytearray(data)

    def field(self, table, i):
        return struct.unpack('>I', self.d[table + 4 * i:table + 4 * i + 4])[0]

    def set(self, table, i, v):
        self.d[table + 4 * i:table + 4 * i + 4] = struct.pack('>I', v)

    def sections(self):
        return [(i, self.field(0, i), self.field(0x48, i), self.field(0x90, i)) for i in range(18)]

    def off(self, addr):
        for i, o, a, s in self.sections():
            if s and a <= addr < a + s:
                return o + addr - a
        raise KeyError(hex(addr))

    def word(self, addr):
        o = self.off(addr)
        return struct.unpack('>I', self.d[o:o + 4])[0]

    def put(self, addr, w):
        o = self.off(addr)
        self.d[o:o + 4] = struct.pack('>I', w)

    def add_text(self, addr, payload):
        for i, o, a, s in self.sections():
            if s and a < addr + len(payload) and addr < a + s:
                raise SystemExit('section %d (0x%08X-0x%08X) overlaps the hook section' % (i, a, a + s))
        # The NAND boot program ignores the file offsets: it streams the sections
        # back to back from 0x100, text slots 0-6 then data slots 7-17.  So the
        # new section takes the last slot (shifting used data slots down by one
        # if 17 is taken) and its bytes go right after the last section's end.
        if not self.field(0x90, 17):
            slot = 17
        else:
            free = [i for i in range(7, 17) if not self.field(0x90, i)]
            if not free:
                raise SystemExit('no free data section slot')
            f = free[-1]
            for i in range(f, 17):          # slide slots f+1..17 down to f..16
                for t in (0, 0x48, 0x90):
                    self.set(t, i, self.field(t, i + 1))
            for t in (0, 0x48, 0x90):
                self.set(t, 17, 0)
            slot = 17
        if any(self.field(0, i) > len(self.d) for i in range(18)):
            raise SystemExit('bad DOL section offsets')
        live = [(self.field(0, i), self.field(0x90, i)) for i in range(18) if self.field(0x90, i)]
        off = 0x100
        for o, sz in live:
            if o != off:
                raise SystemExit('DOL sections are not packed back to back (0x%X != 0x%X)' % (o, off))
            off += sz
        self.d = self.d[:off] + payload
        self.set(0, slot, off)
        self.set(0x48, slot, addr)
        self.set(0x90, slot, len(payload))
        return slot


def patch_dol(data, clock=False, debug_feed=False):
    key, ch = detect(data)
    print('main DOL:', ch['title'])
    base, end, state, arena = layout(ch)
    dol = Dol(data)
    if clock:
        if not ch['clock']:
            raise SystemExit('--clock is only for the Forecast Channel')
        sys.path.insert(0, HERE)
        clk = __import__(ch['clock'])
        for addr, old, new, desc in clk.PATCHES:
            for j, (o, n) in enumerate(zip(old, new)):
                cur = dol.word(addr + 4 * j)
                if cur not in (o, n):
                    raise SystemExit('clock site 0x%08X: unexpected word 0x%08X' % (addr + 4 * j, cur))
                dol.put(addr + 4 * j, n)
        print('clock patch applied')
    blob, syms = build_blob(ch, base, state, debug_feed)
    for name, (orig, stub) in SITES.items():
        cur = dol.word(ch['sites'][name])
        if cur != orig:
            raise SystemExit('%s site 0x%08X: found 0x%08X, want 0x%08X (already patched?)' % (
                name, ch['sites'][name], cur, orig))
    for addr, old_lo, new_lo in arena:
        cur = dol.word(addr)
        if cur & 0xFFFF != old_lo or cur >> 26 != 14:
            raise SystemExit('arena site 0x%08X: found 0x%08X' % (addr, cur))
        dol.put(addr, (cur & 0xFFFF0000) | new_lo)
    payload = blob + b'\0' * (end - base - len(blob))           # code, then zeroed state up to END
    slot = dol.add_text(base, payload)
    only = os.environ.get('HOOKS')            # debugging: HOOKS=POLL,SAMPLE plants only those
    for name, (orig, stub) in SITES.items():
        if only is not None and name not in only.split(','):
            continue
        site = ch['sites'][name]
        dol.put(site, b_to(site, syms[stub]))
        print('  %-8s 0x%08X -> %-13s 0x%08X' % (name, site, stub, syms[stub]))
    print('hook section: DOL slot %d, 0x%08X-0x%08X (%d bytes code, state at 0x%08X); arena now starts at 0x%08X' % (
        slot, base, end, len(blob), state, end))
    return bytes(dol.d)


def fakesign(path):
    al = lambda x: (x + 63) & ~63
    d = bytearray(open(path, 'rb').read())
    hs, typ, ver, cs, _, ts, tms, ds, fs = struct.unpack('>IHHIIIIII', d[:0x20])
    tik = al(hs) + al(cs)
    tmd = tik + al(ts)
    for o, size, brute, name in ((tmd, tms, 0x1E2, 'tmd'), (tik, ts, 0x262, 'ticket')):
        d[o + 4:o + 4 + 256] = b'\0' * 256
        for v in range(65536):
            d[o + brute:o + brute + 2] = struct.pack('>H', v)
            if hashlib.sha1(d[o + 0x140:o + size]).digest()[0] == 0:
                break
        else:
            raise SystemExit('fakesign failed for ' + name)
    open(path, 'wb').write(d)


def main():
    a = [x for x in sys.argv[1:] if not x.startswith('--')]
    clock = '--clock' in sys.argv
    feed = '--debug-feed' in sys.argv
    if len(a) != 3 or a[0] not in ('dol', 'wad'):
        raise SystemExit(__doc__)
    mode, src, dst = a
    if mode == 'dol':
        patched = patch_dol(open(src, 'rb').read(), clock, feed)
        open(dst, 'wb').write(patched)
        return
    tmp = tempfile.mkdtemp(prefix='fcwad')
    run([SHARPII, 'WAD', '-u', src, tmp + '/u'])
    app = tmp + '/u/00000001.app'
    patched = patch_dol(open(app, 'rb').read(), clock, feed)
    open(app, 'wb').write(patched)
    if os.path.exists(dst):
        os.remove(dst)
    run([SHARPII, 'WAD', '-p', tmp + '/u', dst, '-f'])
    fakesign(dst)
    shutil.rmtree(tmp)
    print('wrote', dst)


if __name__ == '__main__':
    main()
