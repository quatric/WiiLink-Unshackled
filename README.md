# WiiLink-Unshackled

Adds Classic Controller and GameCube controller support to WiiLink's USA channels:

| Channel | Title | Main DOL (content 1) |
|---|---|---|
| Forecast Channel | HAFE | 1,926,048 bytes |
| News Channel | HAGE | 2,019,232 bytes |

```
python3 build.py wad "<channel> (USA) (WiiLink).wad" out.wad [--clock]
python3 build.py dol 00000001.app out.app [--clock]
```

The channel is recognised from its main DOL. `--clock` (Forecast Channel only) also applies `forecast_us_clock_patch.py`, which enables the clock on US consoles with a 12-hour a.m./p.m. display.

You need devkitPPC (set `DEVKITPPC`; default `/opt/devkitpro/devkitPPC`). The `wad` mode also needs Sharpii (set `SHARPII`). The output WAD is fakesigned.

## Controls

| Wii Remote | Classic Controller | GameCube (port 1) |
|---|---|---|
| A | A | A |
| B | B | B |
| 1 | X | X |
| 2 | Y | Y |
| Pointer | Left Stick | Control Stick |
| Twist | Right Stick | C-Stick |
| − | Minus | L |
| + | Plus | R |
| HOME | HOME | START |
| D-pad | D-pad | D-pad |

* **Pointer:** the sticks move it like a mouse. About 1 s crosses the screen at full tilt.
* **Twist:** goes up to about ±60°. In the Forecast Channel, hold A to grab the globe and push the right stick or C-stick to rotate it.
* **GameCube pad alone:** works with no Wii Remote connected. KPAD sees it as a Classic Controller on channel 0.
* **GameCube pad with a Wii Remote:** the pad acts as the remote's extension. A real Nunchuk or Classic Controller takes priority.
* **The remote's own pointer:** IR pointing and twist still work. Whichever input moved last is in control.

## How it works

Five hooks branch out of KPAD/WPAD:

| Hook | Site | What it does |
|---|---|---|
| POLL | `KPADiRead` entry | Keeps SI port 1 auto-polled. The channels link SI but not PAD. |
| SAMPLE | `KPADiRead` sample-count check | Writes the pad into Classic Controller samples. |
| PROBE | `WPADProbe` | Reports a Classic Controller while a pad answers. |
| BUTTONS | KPAD button compose | ORs Classic Controller buttons into the Wii Remote buttons. |
| MOTION | After each sample is copied out | Writes the stick pointer and twist into the caller's copy only, so KPAD's IR tracking state is never touched. |

The code (and 0x100 bytes of state) takes the first 0x1000 bytes of the OS arena. That's `__ArenaLo`, right above the debugger stack. OSInit's two arena constants move up past it, so the game never allocates over it.

### The boot loader packs sections

WiiLink's NAND boot program (content `0xb`) ignores DOL file offsets. It streams sections back to back from file offset `0x100`, text slots 0–6 then data slots 7–17.

The hook section therefore takes the last slot (data 17), and its bytes start exactly where the previous section ends. If a section is aligned or out of order, it loads another section's bytes, and OSInit crashes.

### Porting to another channel

Both channels share one SDK build, so each address is the same code in a new place. `tools/sig.py` finds an address from a known DOL in a new DOL by masked byte signature. It masks relative branches, r2/r13 offsets and immediates.

* **Data addresses** (SI tables, WPAD table, arena constants) are read from the matched lis/addi pairs.
* **New profile:** add an entry to `CHANNELS` in `build.py`.

## Debugging

Set `HOOKS=POLL,SAMPLE,...` in the environment to plant only the listed hooks.
