#!/usr/bin/env python3
"""
News Channel (USA, HAGE, WiiLink build) - show the clock on US-region Wiis, in
12-hour format, like forecast_us_clock_patch.py does for the Forecast Channel.

Target: main DOL = content index 1 (00000001.app, 2,019,232 bytes) as unpacked by Sharpii.

The News Channel shares the Forecast Channel's clock code (the clock in the
top-left corner of the menus):
  * region  = word @ r13-0x7094  (0 = JPN, 1 = USA, 2 = EUR)
  * lang    = byte @ r13-0x709A  (clamped to <= 6)
  * hide    = byte @ r13-0x7AA0  (clock fade-out flag, read by the fader @ 0x8004B2A0)
  * the formatter is picked in the clock's ctor from the table @ 0x801B31A0;
    entry 1 (0x8004AA04) is the 12-hour "h:mm a.m./p.m." one, used only for
    US English.

Nintendo set hide = (region == USA) every time a screen opens: 13 places as
    hide = (region == 1)          lwz rX,region; addi r0,rX,-1; cntlzw; srwi; stb
and 4 more as
    hide = region == 1 ? 1 : saved_value
Each of those is patched to the EUR/JPN result (hide = 0 / the saved value).
The forced hides that don't depend on the region (slide show etc.) stay.

The formatter select gets the same change as on the Forecast Channel: US
uses the 12-hour formatter for every system language.
JPN/EUR behaviour is unchanged.
"""
import hashlib
import struct
import sys

LI_R0_1 = 0x38000001        # replaces addi r0,rX,-1: (region == 1) becomes 0
NOP = 0x60000000

PATCHES = [
    # (address, original words, new words, description)
    *[(a, [0x3803FFFF], [LI_R0_1], "screen init: don't hide clock on US")
      for a in (0x80016A90, 0x80017800, 0x80017FD0, 0x800188BC, 0x800197EC, 0x8001A874,
                0x8001AD7C, 0x8001B34C, 0x8001B8E8, 0x8001BFB8, 0x8001EE50)],
    (0x8002FC98, [0x3804FFFF], [LI_R0_1], "screen init: don't hide clock on US"),
    (0x80023DF4, [0x3805FFFF], [LI_R0_1], "screen init: don't hide clock on US"),
    *[(a, [0x41820008], [NOP], "screen state: restore clock on US like EUR/JPN")
      for a in (0x8001C740, 0x8001EC00, 0x800254BC, 0x800271D0)],
    (0x80049B40,
     [0x880D8F66, 0x28000006, 0x41810124, 0x3C60801B, 0x5400103A,
      0x38633320, 0x7C63002E, 0x7C6903A6, 0x4E800420],
     [0x800D8F6C,  # lwz   r0,-0x7094(r13)   region
      0x2C000001,  # cmpwi r0,1               USA?
      0x41820048,  # beq   0x80049B90         -> 12-hour a.m./p.m. formatter
      0x880D8F66,  # lbz   r0,-0x709A(r13)   language
      0x5400103A,  # slwi  r0,r0,2
      0x387E02C0,  # addi  r3,r30,0x2C0      jump table 0x801B3320 (r30 = 0x801B3060)
      0x7C63002E,  # lwzx  r3,r3,r0
      0x7C6903A6,  # mtctr r3
      0x4E800420], # bctr
     "US: always use 12-hour formatter"),
]


def main():
    if len(sys.argv) != 3:
        sys.exit(f"usage: {sys.argv[0]} <00000001.app in> <00000001.app out>")
    data = bytearray(open(sys.argv[1], "rb").read())
    if len(data) != 2019232:
        sys.exit(f"unexpected DOL size {len(data)}; this patch targets the 2,019,232-byte HAGE DOL")
    f = lambda t, i: struct.unpack_from(">I", data, t + 4 * i)[0]

    def addr_to_off(addr):
        for i in range(18):
            o, b, s = f(0, i), f(0x48, i), f(0x90, i)
            if s and b <= addr < b + s:
                return o + addr - b
        sys.exit(f"{addr:08X} is not in the DOL")

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
