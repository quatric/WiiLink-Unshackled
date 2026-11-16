#!/usr/bin/env python3
"""
Forecast Channel (USA, HAFE, WiiLink build) - enable the belt clock on US-region Wiis
in 12-hour format.

Target: main DOL = content index 1 (00000001.app, 1,926,048 bytes) as unpacked by Sharpii.

Background (from Ghidra decompilation of the DOL):
  * r13 = 0x80337540, r2 = 0x80339900
  * region  = word @ r13-0x6A04  (0 = JPN, 1 = USA, 2 = EUR; from SC product area)
  * lang    = byte @ r13-0x6A0A  (0 JP, 1 EN, 2 DE, 3 FR, 4 ES, 5 IT, 6 NL; clamped to <= 6)
  * hide    = byte @ r13-0x7378  (clock fade-out flag, default 1; read by the fader @ 0x8003D020)
  * The belt clock (layout base_belt.brlyt: belt_time / belt_timeB<LANG> / bnd timeWW) is
    drawn every frame by a pointer-to-member at scene+0x64, chosen in the scene ctor from
    the table @ 0x8019C310. Entry 1 (0x8003C784) is the 12-hour formatter: "h:mm" followed
    by "a.m." / "p.m." using font_weather_timeWW.brfnt (which contains a, m, p, '.').

Nintendo gated the clock off for region == USA in three places:
  0x8000D6EC  init:          if (region == US) hide = 1;
  0x8000EFA0  screen state:  if (region != US) hide = 0;
  0x8000F6DC  screen state:  if (region != US) hide = 0;
and only selected the 12-hour formatter for US + English.

Patches:
  1. 0x8000D6F0  bne +8   -> b +8     never force-hide on US
  2. 0x8000EFA4  beq ...  -> nop      clear hide on US like EUR/JPN
  3. 0x8000F6E0  beq +0xC -> nop      clear hide on US like EUR/JPN
  4. 0x8003B9D8  formatter select: if region == US use entry 1 (12-hour a.m./p.m.)
                 for every system language; otherwise fall through to the original
                 language switch (bounds check dropped: language is already clamped to <= 6).

JPN/EUR behaviour is unchanged.
"""
import hashlib
import struct
import sys

TEXT1_FILE_OFF = 0x25E0
TEXT1_ADDR = 0x80006FC0

PATCHES = [
    # (address, original words, new words, description)
    (0x8000D6F0, [0x40820008], [0x48000008], "init: don't hide clock on US"),
    (0x8000EFA4, [0x418204F8], [0x60000000], "state A: show clock on US"),
    (0x8000F6E0, [0x4182000C], [0x60000000], "state B: show clock on US"),
    (0x8003B9D8,
     [0x880D95F6, 0x28000006, 0x41810124, 0x3C60801A, 0x5400103A,
      0x3863C490, 0x7C63002E, 0x7C6903A6, 0x4E800420],
     [0x800D95FC,  # lwz   r0,-0x6A04(r13)   region
      0x2C000001,  # cmpwi r0,1               USA?
      0x41820048,  # beq   0x8003BA28         -> 12-hour a.m./p.m. formatter
      0x880D95F6,  # lbz   r0,-0x6A0A(r13)   language
      0x5400103A,  # slwi  r0,r0,2
      0x387E02C0,  # addi  r3,r30,0x2C0      jump table 0x8019C490 (r30 = 0x8019C1D0)
      0x7C63002E,  # lwzx  r3,r3,r0
      0x7C6903A6,  # mtctr r3
      0x4E800420], # bctr
     "US: always use 12-hour formatter"),
]


def addr_to_off(addr):
    return TEXT1_FILE_OFF + (addr - TEXT1_ADDR)


def main():
    if len(sys.argv) != 3:
        sys.exit(f"usage: {sys.argv[0]} <00000001.app in> <00000001.app out>")
    data = bytearray(open(sys.argv[1], "rb").read())
    if len(data) != 1926048:
        sys.exit(f"unexpected DOL size {len(data)}; this patch targets the 1,926,048-byte HAFE DOL")
    for addr, old, new, desc in PATCHES:
        off = addr_to_off(addr)
        cur = list(struct.unpack(f">{len(old)}I", data[off:off + 4 * len(old)]))
        if cur == new:
            print(f"  {addr:08X} already patched  ({desc})")
            continue
        if cur != old:
            sys.exit(f"  {addr:08X} original bytes mismatch: {[hex(w) for w in cur]}")
        data[off:off + 4 * len(new)] = struct.pack(f">{len(new)}I", *new)
        print(f"  {addr:08X} patched          ({desc})")
    open(sys.argv[2], "wb").write(data)
    print("sha1", hashlib.sha1(data).hexdigest())


if __name__ == "__main__":
    main()
