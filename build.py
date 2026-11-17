#!/usr/bin/env python3
"""Classic Controller + GameCube controller patch for WiiLink's USA channels
(Everybody Votes Channel: also USB keyboard and no daily suggestion limit).

  build.py dol <00000001.app in> <00000001.app out> [--clock] [--debug-feed]
  build.py wad <channel .wad> <out.wad> [--clock] [--accuweather] [--debug-feed]

The channel is recognised from its main DOL.  Builds the hooks in src/ with
devkitPPC, links them at the start of the OS arena (right above the main
stack), moves the arena start up past them, adds them to the main DOL as a new
section (last slot) and plants a branch at each hook site.  --clock (Forecast
Channel only) also applies forecast_us_clock_patch.py.  --accuweather
(Forecast Channel, wad mode) swaps the WeatherNews logo on the channel's banner
and Wii Menu icon for AccuWeather's (banner.py).
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

# Per-channel addresses.  Channels on the same SDK build (June 2007 unless 'sdk' says 2009) share every hook
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
    'evc': {
        'title': 'Everybody Votes Channel (USA, HAJE)',
        'dol_size': 2653152,
        'arena_lo': 0x80406FC0, 'stack_end': 0x80404FC0, 'lis': 0x8040,
        'arena': [0x800FE9D0, 0x800FEA78, 0x800FEA20, 0x800FEAAC],
        'defs': {
            'SI_TYPES': 0x80283148,
            'SI_BUSY': 0x80283130,
            'SI_SHADOW': 0x80283134,
            'FN_SIGETTYPE': 0x80155EDC,
            'FN_OSDISABLE': 0x80105530,
            'FN_OSRESTORE': 0x80105558,
            'WPAD_TBL': 0x802AFA30,
        },
        'sites': {'POLL': 0x80158E50, 'SAMPLE': 0x80158F68, 'PROBE': 0x800DD068,
                  'BUTTONS': 0x80159418, 'MOTION': 0x8015954C},
        'clock': None,
        'hook_size': 0x2000,
        # USB keyboard for the software keyboard (src/kbd.c)
        'kbd': {
            'site': 0x80085860,         # keyboard state calc: lwz r12,0(r3) before inputForm->calc()
            'defs': {
                'FN_IOS_OPEN': 0x800F53F0,
                'FN_IOS_IOCTLASYNC': 0x800F5C50,
                'SLOT_ONCOMMAND': 5,    # input form: onCommand(cmd, data)
                'SLOT_GETTOOLBAR': 16,  # keyboard state: toolbar
                'SLOT_OK': 35,          # toolbar: OK pressed
                'SLOT_CANCEL': 36,      # toolbar: Quit pressed
                'CMD_CHAR': 0, 'CMD_DELETE': 1, 'CMD_LEFT': 7, 'CMD_RIGHT': 8,
            },
        },
        # (address, original words, new words, what)
        'patches': [
            (0x80062788, [0x9421FFC0, 0x7C0802A6], [0x38600001, 0x4E800020],
             'suggestion limit: "suggested today?" check always says no'),
        ],
    },
    'cmoc': {
        'title': 'Check Mii Out Channel (USA, HAPE)',
        'dol_size': 3410240,
        'arena_lo': 0x80442740, 'stack_end': 0x80440728, 'lis': 0x8044,
        'arena': [0x8011A148, 0x8011A1F0, 0x8011A198, 0x8011A224],
        'defs': {
            'SI_TYPES': 0x80324E40,
            'SI_BUSY': 0x80324E28,
            'SI_SHADOW': 0x80324E2C,
            'FN_SIGETTYPE': 0x80174988,
            'FN_OSDISABLE': 0x8012121C,
            'FN_OSRESTORE': 0x80121244,
            'WPAD_TBL': 0x80345490,
        },
        'sites': {'POLL': 0x800F112C, 'SAMPLE': 0x800F1244, 'PROBE': 0x800F66E8,
                  'BUTTONS': 0x800F16F4, 'MOTION': 0x800F1828},
        'clock': None,
    },
    # 2009 SDK: KPAD was rewritten (see src/hooks.S); WPAD/SI/OS are the same code
    'nintendo': {
        'title': 'Nintendo Channel (USA, HATE)',
        'dol_size': 3988896,
        'sdk': 2009,
        'hook_size': 0x2000,
        'arena_lo': 0x807D30E0, 'stack_end': 0x807D10D8, 'lis': 0x807D,
        'arena': [0x801EFF9C, 0x801F0044, 0x801EFFEC, 0x801F0078],
        'defs': {
            'SI_TYPES': 0x803BB508,
            'SI_BUSY': 0x803BB4F0,
            'SI_SHADOW': 0x803BB4F4,
            'FN_SIGETTYPE': 0x80201C10,
            'FN_OSDISABLE': 0x801F6430,
            'FN_OSRESTORE': 0x801F6470,
            'WPAD_TBL': 0x806C0710,
            'KPAD_BASE': 0x806C3EA8,    # per-channel KPAD blocks...
            'KPAD_STRIDE': 0x570,       # ...this far apart
        },
        'sites': {'POLL': 0x802314D0, 'SAMPLE': 0x8023164C, 'PROBE': 0x80225060,
                  'BUTTONS': 0x8022EE54, 'MOTION': 0x80231B2C, 'MOTION2': 0x80231C9C},
        'clock': None,
    },
}
HOOK_SIZE = 0x1000              # default: code + 0x100 bytes of state, carved from the arena start

# per SDK, name: (original word, stub symbol) -- the same instruction in every channel
SITES = {
    2007: {
        'POLL':    (0x9421FF40, 'hook_poll'),     # KPADiRead: stwu r1,-192(r1)
        'SAMPLE':  (0x881F010F, 'hook_sample'),   # KPADiRead: lbz r0,0x10F(r31)
        'PROBE':   (0x9421FFF0, 'hook_probe'),    # WPADProbe: stwu r1,-16(r1)
        'BUTTONS': (0x70E09FFF, 'hook_buttons'),  # KPADiRead: andi. r0,r7,0x9FFF
        'MOTION':  (0x35EFFFFF, 'hook_motion'),   # KPADiRead: addic. r15,r15,-1 (after the copy-out)
    },
    2009: {
        'POLL':    (0x9421FEF0, 'hook_poll'),     # KPADiRead: stwu r1,-272(r1)
        'SAMPLE':  (0x881A013B, 'hook_sample'),   # KPADiRead: lbz r0,0x13B(r26)
        'PROBE':   (0x9421FFF0, 'hook_probe'),    # WPADProbe: stwu r1,-16(r1)
        'BUTTONS': (0x70C99FFF, 'hook_buttons'),  # button compose: andi. r9,r6,0x9FFF
        'MOTION':  (0x3739FFFF, 'hook_motion'),   # KPADiRead: addic. r25,r25,-1 (per-sample copy-out)
        'MOTION2': (0x3694FFFF, 'hook_motion2'),  # KPADiRead: addic. r20,r20,-1 (compose-once copy-out)
    },
}


def sites(ch):
    s = dict(SITES[ch.get('sdk', 2007)])
    if 'kbd' in ch:
        s['KBD'] = (0x81830000, 'hook_kbd')       # lwz r12,0(r3)
    return s


def site_addr(ch, name):
    return ch['kbd']['site'] if name == 'KBD' else ch['sites'][name]


def layout(ch):
    """BASE/END/STATE and the four arena patches (addi address, old lo, new hi, new lo).
    Each addi is preceded by the lis it pairs with; that lis moves too if END
    needs a different high half."""
    base = ch['arena_lo']
    end = base + ch.get('hook_size', HOOK_SIZE)
    assert end % 32 == 0
    def lo(v):
        d = v - (ch['lis'] << 16)
        assert -0x8000 <= d < 0x8000, hex(v)
        return d & 0xFFFF
    hi = ((end + 0x8000) >> 16) & 0xFFFF
    arena = []
    for i, a in enumerate(ch['arena']):
        old_lo = lo(base) if i < 2 else lo(ch['stack_end'])
        arena.append((a, old_lo, hi, end & 0xFFFF))
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
    defs = dict(ch['defs'], STATE=state)
    if 'kbd' in ch:
        defs.update(ch['kbd']['defs'])
    D = ['-D%s=0x%08Xu' % kv for kv in defs.items()]
    if ch.get('sdk', 2007) == 2009:
        D.append('-DSDK2009')
    if 'kbd' in ch:
        D.append('-DKBD')
    if debug_feed:
        D.append('-DDEBUG_FEED')
    objs = [tmp + '/hooks.o', tmp + '/gc.o', tmp + '/motion.o']
    run([CC + 'gcc'] + CFLAGS + ['-msoft-float'] + D + ['-c', src + '/gc.c', '-o', tmp + '/gc.o'])
    run([CC + 'gcc'] + CFLAGS + ['-mhard-float'] + D + ['-c', src + '/motion.c', '-o', tmp + '/motion.o'])
    if 'kbd' in ch:
        run([CC + 'gcc'] + CFLAGS + ['-msoft-float'] + D + ['-c', src + '/kbd.c', '-o', tmp + '/kbd.o'])
        objs.append(tmp + '/kbd.o')
    run([CC + 'gcc', '-mbig-endian', '-c', '-x', 'assembler-with-cpp'] + D + [src + '/hooks.S', '-o', tmp + '/hooks.o'])
    ld = open(tmp + '/link.ld', 'w')
    ld.write('SECTIONS {\n  . = 0x%08X;\n  .text : { *(.hooks) *(.text .text.*) *(.rodata .rodata.*) }\n'
             '  /DISCARD/ : { *(.comment) *(.eh_frame) *(.note*) *(.gnu.attributes) }\n}\n' % base)
    ld.close()
    syms = ['--defsym=RET_%s=0x%08X' % (n, site_addr(ch, n) + 4) for n in sites(ch)]
    run([CC + 'ld', '-T', tmp + '/link.ld', '--no-undefined', '-o', tmp + '/b.elf'] + syms + objs)
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
    for name, (orig, stub) in sites(ch).items():
        cur = dol.word(site_addr(ch, name))
        if cur != orig:
            raise SystemExit('%s site 0x%08X: found 0x%08X, want 0x%08X (already patched?)' % (
                name, site_addr(ch, name), cur, orig))
    for addr, old_lo, new_hi, new_lo in arena:
        cur = dol.word(addr)
        if cur & 0xFFFF != old_lo or cur >> 26 != 14:
            raise SystemExit('arena site 0x%08X: found 0x%08X' % (addr, cur))
        lis = dol.word(addr - 4)            # lis rA,hi right before addi rD,rA,lo
        if lis >> 26 != 15 or (lis >> 16) & 31 or (lis >> 21) & 31 != (cur >> 16) & 31 or lis & 0xFFFF != ch['lis']:
            raise SystemExit('arena site 0x%08X: no matching lis before it (0x%08X)' % (addr, lis))
        dol.put(addr - 4, (lis & 0xFFFF0000) | new_hi)
        dol.put(addr, (cur & 0xFFFF0000) | new_lo)
    for addr, old, new, what in ch.get('patches', []):
        for j, (o, n) in enumerate(zip(old, new)):
            cur = dol.word(addr + 4 * j)
            if cur != o:
                raise SystemExit('patch 0x%08X: found 0x%08X, want 0x%08X' % (addr + 4 * j, cur, o))
            dol.put(addr + 4 * j, n)
        print('  patched 0x%08X: %s' % (addr, what))
    payload = blob + b'\0' * (end - base - len(blob))           # code, then zeroed state up to END
    slot = dol.add_text(base, payload)
    only = os.environ.get('HOOKS')            # debugging: HOOKS=POLL,SAMPLE plants only those
    for name, (orig, stub) in sites(ch).items():
        if only is not None and name not in only.split(','):
            continue
        site = site_addr(ch, name)
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
    accu = '--accuweather' in sys.argv
    if len(a) != 3 or a[0] not in ('dol', 'wad'):
        raise SystemExit(__doc__)
    mode, src, dst = a
    if mode == 'dol':
        if accu:
            raise SystemExit('--accuweather needs wad mode (the banner is content 0)')
        patched = patch_dol(open(src, 'rb').read(), clock, feed)
        open(dst, 'wb').write(patched)
        return
    tmp = tempfile.mkdtemp(prefix='fcwad')
    run([SHARPII, 'WAD', '-u', src, tmp + '/u'])
    app = tmp + '/u/00000001.app'
    if accu and detect(open(app, 'rb').read())[0] != 'forecast':
        raise SystemExit('--accuweather is only for the Forecast Channel')
    patched = patch_dol(open(app, 'rb').read(), clock, feed)
    open(app, 'wb').write(patched)
    if accu:
        sys.path.insert(0, HERE)
        import banner
        bnr = tmp + '/u/00000000.app'
        new = banner.patch_opening(open(bnr, 'rb').read())
        open(bnr, 'wb').write(new)
        print('banner: WeatherNews logo -> AccuWeather')
    if os.path.exists(dst):
        os.remove(dst)
    run([SHARPII, 'WAD', '-p', tmp + '/u', dst, '-f'])
    fakesign(dst)
    shutil.rmtree(tmp)
    print('wrote', dst)


if __name__ == '__main__':
    main()
