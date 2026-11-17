# WiiLink-Unshackled

Adds Classic Controller and GameCube controller support to WiiLink's USA channels:

| Channel | Title | Main DOL (content 1) |
|---|---|---|
| Forecast Channel | HAFE | 1,926,048 bytes |
| News Channel | HAGE | 2,019,232 bytes |
| Everybody Votes Channel | HAJE | 2,653,152 bytes |
| Check Mii Out Channel | HAPE | 3,410,240 bytes |
| Nintendo Channel | HATE | 3,988,896 bytes |

```
python3 build.py wad "<channel> (USA) (WiiLink).wad" out.wad [--clock]
python3 build.py dol 00000001.app out.app [--clock]
```

The channel is recognised from its main DOL. `--clock` (Forecast Channel only) also applies `forecast_us_clock_patch.py`, which enables the clock on US consoles with a 12-hour a.m./p.m. display.

You need devkitPPC (set `DEVKITPPC`; default `/opt/devkitpro/devkitPPC`). The `wad` mode also needs Sharpii (set `SHARPII`). The output WAD is fakesigned.

## Everybody Votes Channel extras

The Everybody Votes Channel build also gets two more patches:

* **USB keyboard:** type into the on-screen keyboard from a USB keyboard (US layout). Letters, digits, symbols and Space type; Backspace deletes; Left/Right move the cursor; Enter is OK; Esc is Quit. Keys auto-repeat when held. The on-screen keyboard keeps working as before.
* **No daily suggestion limit:** "Suggest a Question" no longer stops at "You can suggest only one poll per day." Any limit WiiLink's server applies is unaffected.

The channel's text-input library is an early build of the SDK's SoftwareKeyboard, from before it supported hardware keyboards. `src/kbd.c` reads IOS's `/dev/usb/kbd` itself, once per frame while the on-screen keyboard is up. It sends key presses to the input form as the same commands the on-screen keys send. The device needs an IOS that has the USB keyboard module; if `/dev/usb/kbd` can't be opened, the patch does nothing.

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

The code (and 0x100 bytes of state) takes the first 0x1000 bytes of the OS arena (0x2000 in the Nintendo and Everybody Votes Channels). That's `__ArenaLo`, right above the debugger stack. OSInit's arena constants (each a `lis`/`addi` pair) move up past it, so the game never allocates over it.

### The boot loader packs sections

WiiLink's NAND boot program (content `0xb`) ignores DOL file offsets. It streams sections back to back from file offset `0x100`, text slots 0–6 then data slots 7–17.

The hook section therefore takes the last slot (data 17), and its bytes start exactly where the previous section ends. If a section is aligned or out of order, it loads another section's bytes, and OSInit crashes.

### Two SDK versions

Forecast, News, Everybody Votes and Check Mii Out share the June 2007 SDK. The Nintendo Channel uses a 2009 KPAD, built with `-DSDK2009`:

* **Sample ring:** 16 inline slots at `k+0x13C` plus an optional external buffer (`k+0x4BC`/`k+0x4C0`), instead of 16 slots at `k+0x110`.
* **Sample count:** keeps one already-read sample, so "nothing new" is a count of 1, not 0.
* **Copy-out:** two sites (MOTION and MOTION2), and the output `KPADStatus` is 0xB0 bytes. The field offsets the hooks use are unchanged.

### Porting to another channel

The 2007-SDK channels share one SDK build, so each address is the same code in a new place. `tools/sig.py` finds an address from a known DOL in a new DOL by masked byte signature. It masks relative branches, r2/r13 offsets and immediates.

* **Data addresses** (SI tables, WPAD table, arena constants) are read from the matched lis/addi pairs.
* **New profile:** `tools/port.py <Forecast 00000001.app> <new 00000001.app> <key>` prints a `CHANNELS` entry for a 2007-SDK channel. Paste it into `build.py` and fill in the title.

## Debugging

Set `HOOKS=POLL,SAMPLE,...` in the environment to plant only the listed hooks.
