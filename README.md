# WiiLink-Unshackled

Adds Classic Controller and GameCube controller support to WiiLink's channels and to the Photo Channel:

| Channel | Title | Main DOL (content 1) |
|---|---|---|
| Forecast Channel | HAFE | 1,926,048 bytes |
| News Channel | HAGE | 2,019,232 bytes |
| Everybody Votes Channel | HAJE | 2,653,152 bytes |
| Check Mii Out Channel | HAPE | 3,410,240 bytes |
| Nintendo Channel | HATE | 3,988,896 bytes |
| Photo Channel 1.1 | HAYA | 2,300,448 bytes |
| Food Channel (Standard, Domino's, Just Eat) / Demae Channel | HCHJ | 3,709,084 or 3,722,036 bytes |
| Digicam Print Channel / Photo Prints Channel | HCDJ | 3,303,168 bytes |
| Today and Tomorrow Channel (Japan) | HAVJ | 4,247,616 bytes |
| Today and Tomorrow Channel (PAL) | HAVP | 3,384,512 bytes |
| Wii no Ma / Wii Room (every language) | HCIJ | 8,929,568 bytes |

Sizes are for the uncompressed DOL. Most of these WADs store content 1 LZ-compressed; `build.py` unpacks it and writes the patched DOL back uncompressed (the boot program loads either).

```
python3 build.py wad "<channel> (USA) (WiiLink).wad" out.wad [--clock] [--accuweather]
python3 build.py dol 00000001.app out.app [--clock]
```

The Photo Channel isn't a WiiLink channel: use the Photo Channel 1.1 system title WAD (`Photo Channel v1.1 (World) (v3) (Channel).wad`). The channel is recognised from its main DOL. `--clock` (Forecast and News Channels) also applies `forecast_us_clock_patch.py` or `news_us_clock_patch.py`. Those enable the clock on US consoles with a 12-hour a.m./p.m. display.

You need devkitPPC (set `DEVKITPPC`; default `/opt/devkitpro/devkitPPC`). The `wad` mode also needs Sharpii (set `SHARPII`). The output WAD is fakesigned.

## Clock on US consoles (`--clock`)

Both channels have a clock in the top-left corner, but Nintendo hid it on US-region consoles. JPN and EUR consoles show it. The two channels share the clock code.

* **Forecast Channel:** `forecast_us_clock_patch.py`.
* **News Channel:** `news_us_clock_patch.py`. Every screen used to set the clock's hide flag to "region is USA" (17 places); they now set it the way they do on EUR/JPN consoles.
* **Both:** the clock uses the channel's own 12-hour "h:mm a.m./p.m." formatter on US consoles, whatever the system language.

As on EUR/JPN consoles, the clock fades out while the pointer is over the button under it (the News Channel's "Text Zoom" button, for example).

## Forecast Channel extras

The Forecast Channel build also gets:

* **Hold to repeat:** holding +, −, Up or Down repeats it after 0.4 s, then every 0.15 s. That zooms or tilts the globe step after step, or flips through the forecast pages, like holding them in the News Channel.
* **Globe tilt both ways:** Up/Down (and the curved-arrow buttons) tilt the globe. They now use the News Channel's 11 angles (−80° to 80°, level in the middle) instead of 0° to 80°. The globe can tilt over to its far side, upside down. It opens level, and Restore goes back to level.

The tilt code is the same in both channels, apart from the angle table and its bounds. The new table lives in the hook section, and `build.py` points the channel's four table loads at it (`sympatches`).

## Forecast Channel: AccuWeather logo

`--accuweather` (Forecast Channel, `wad` mode) replaces the WeatherNews logo on the channel's Wii Menu banner and icon with AccuWeather's. `banner.py` does the work on content 0 (`opening.bnr`), and can also be run on its own: `python3 banner.py 00000000.app out.app`.

* The logo has its real colours: a Hero Orange (#F05514) sun and a black wordmark, per [AccuWeather's brand guidelines](https://developer.accuweather.com/documentation/brand-guidelines).
* It is resized to the logo's 7:1 proportions and has half a sun height of clear space on the white plate.
* The banner's "supported by weathernews" line becomes "supported by AccuWeather".

The textures in `assets/accuweather/` are AccuWeather's official horizontal logo (`AW_RGB_R.svg`), rendered with `resvg -w 140 -h 20` (banner) and `-w 112 -h 16` (icon), then converted with `tools/mktpl.py`. Like the WeatherNews logo they replace, they are IA4 textures tinted by their material. The material maps intensity 0 to black and intensity 1 to Hero Orange, so a single small texture carries both colours. AccuWeather's logo and name are AccuWeather's trademarks.

## Everybody Votes Channel extras

The Everybody Votes Channel build also gets two more patches:

* **USB keyboard:** type into the on-screen keyboard from a USB keyboard (US layout). Letters, digits, symbols and Space type; Backspace deletes; Left/Right move the cursor; Enter is OK; Esc is Quit. Keys auto-repeat when held. The on-screen keyboard keeps working as before.
* **No daily suggestion limit:** "Suggest a Question" no longer stops at "You can suggest only one poll per day." Any limit WiiLink's server applies is unaffected.

The channel's text-input library is an early build of the SDK's SoftwareKeyboard, from before it supported hardware keyboards. `src/kbd.c` reads IOS's `/dev/usb/kbd` itself, once per frame while the on-screen keyboard is up. It sends key presses to the input form as the same commands the on-screen keys send. The device needs an IOS that has the USB keyboard module; if `/dev/usb/kbd` can't be opened, the patch does nothing.

## Check Mii Out Channel: gold pants Miis

The Check Mii Out Channel build lets special Miis, the ones with gold pants, be used. The channel sorts each Mii as made on this Wii, made on another Wii, or special, and only Miis made on this Wii can be your Mii Artisan or be posted. The patch counts special Miis as made on this Wii, wherever they came from.

In Dolphin, a gold pants Mii could be chosen as the Mii Artisan; the unpatched channel says there are no Miis on the Wii. Posting wasn't tried, and WiiLink's server may still refuse special Miis.

## Check Mii Out Channel: debug menu (`--debug-menu`)

The Check Mii Out Channel still contains its developers' debug overlay. The overlay is built and updated every frame, but the test that decides whether to open it was stubbed to always say no. `--debug-menu` replaces that test: hold **1 and 2** together (X and Y on a Classic Controller or GameCube controller) and the overlay appears over the left side of the screen.

* **Up/Down** moves the `>` cursor, **A** turns the selected entry on or off (`+` marks entries that are on), and **B** closes the overlay.
* The channel still sees these button presses too, so close the overlay before using the channel normally.
* Entries include Console, Debug Save Data Access, Rare Message Check, Safety Frame, Save Data Clear, All Your Base, Debug Print, Debug See Result, Debug Contest Off Limit, the Settings/Startup/Request/Response/Cache Dumps, Cache Clear, No Cache, NWC24 Tmp Error Occur and Disp Mii Info.
* **All Your Base** makes the channel treat every Mii as if it had been made on this Wii. It overrides the channel's check of a Mii's creator ID, so the Mii doesn't have to come from this console.

```bash
python3 build.py wad "Check Mii Out Channel (USA) (WiiLink).wad" "Check Mii Out Channel (USA) (WiiLink) [CC & GC + gold pants + debug menu].wad" --debug-menu
```

## Photo Channel: Message Board photos on the SD card

When the Wii Message Board fills up, the Wii Menu moves older posts to the SD card, under `SD:/private/wii/title/HAEA/`. The Photo Channel's "View Wii Message Board photos" only showed the photos still on NAND. It now also shows the ones on the SD card.

The channel reads the Message Board through Nintendo's CDB library, the same one the Wii Menu uses. CDB can read posts on SD, including checking their signature and decrypting them, but the Photo Channel never mounted the card for it and its scan asked for NAND posts only. `src/cdbsd.c` runs before each scan (`hook_cdbsd`):

* It mounts the SD card as the read-only drive "SD" of CDB's file library (VF). Sectors are read with the SD card driver of the channel's own SD library, the one behind "Digital Camera/Cell Phone".
* It sets CDB's "SD mounted" flag, and the scan asks for NAND and SD posts.
* The drive is mounted afresh for every scan, so a swapped card is read from scratch. With no card in, the scan is NAND-only as before.

Tested in Dolphin with a photo post that exists only on the SD card: it was found and its thumbnail was shown, also when the view was opened again. Without a card, NAND photos showed as before. The SD post was made by a script in the format CDB reads, not by the Wii Menu itself.

## Wii app

`wii/` is a Homebrew Channel app that does the same on the console: it finds WiiLink's channels on the NAND (and on the SD card as `content.bin`, except the Forecast, News and Photo Channels), lets you tick the features you want, backs up the clean copy to the SD card, patches content 1 and packs it again with WiiLink's LZ type. It can put the clean copy back. It only patches WiiLink's own builds, recognised by their SHA-1. See [wii/README.md](wii/README.md).

`python3 build.py export wii/data/patches.bin <WADs...>` writes the patch list it carries.

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

* **Pointer:** the sticks move it like a mouse, out to every edge of the screen, on 16:9 and 4:3 TVs alike. The channels map the Wii Remote's pos ±1 to only part of the screen, so the stick's range comes from the console's aspect ratio setting (SYSCONF `IPL.AR`). Light pushes aim finely. Held at full tilt, the pointer speeds up to four times faster over about 2/3 s, for fast flings, such as spinning the Forecast Channel's globe.
* **Twist:** the right stick or C-stick's direction is the twist angle. Up is level, right is 90° clockwise, down is upside down, so circling the stick turns the Wii Remote all the way round. Letting go levels it again. In the Forecast Channel, hold A to grab the globe and circle the stick to rotate it.
* **GameCube pad alone:** works with no Wii Remote connected. KPAD sees it as a Classic Controller on channel 0.
* **GameCube pad with a Wii Remote:** the pad acts as the remote's extension. A real Nunchuk or Classic Controller takes priority.
* **The remote's own pointer:** IR pointing and twist still work. Whichever input moved last is in control.
* **Per-channel pointer range:** Food/Demae and Wii no Ma / Wii Room put the screen edge at pos x = ±1 on any TV, so their stick range is ±1 there (profile `pointer`).
* **Pointers that must keep moving:** Today and Tomorrow hides a pointer whose position stops changing (a real one never stops dead), and Wii Room's buttons react to movement. For those channels (`pointer_vec`), the stick pointer also reports its velocity, and while it's still it wobbles by an invisible 0.0005.

## How it works

Five hooks branch out of KPAD/WPAD:

| Hook | Site | What it does |
|---|---|---|
| POLL | `KPADiRead` entry | Keeps SI port 1 auto-polled. The channels link SI but not PAD. |
| SAMPLE | `KPADiRead` sample-count check | Writes the pad into Classic Controller samples. |
| PROBE | `WPADProbe` | Reports a Classic Controller while a pad answers. |
| BUTTONS | KPAD button compose | ORs Classic Controller buttons into the Wii Remote buttons. |
| MOTION | After each sample is copied out | Writes the stick pointer and twist into the caller's copy only, so KPAD's IR tracking state is never touched. |

The code and 0x200 bytes of state take the first 0x1800 bytes of the OS arena (0x2000 in the Nintendo, Everybody Votes and Photo Channels). The state is split into 0x00 for gc.c, 0x40 for motion.c and 0x100 for kbd.c. That's `__ArenaLo`, right above the debugger stack. OSInit's arena constants (each a `lis`/`addi` pair) move up past it, so the game never allocates over it.

Wii no Ma / Wii Room needs two exceptions:

* **Text slot:** code in a data section doesn't run under its boot program, so the hook section goes in the first free text slot (slot 2, `text_slot`). Its bytes are inserted into the stream between text slot 1 and data slot 7.
* **Arena guard:** its OS writes the 0x800 bytes just below `__ArenaLo`, which the original layout leaves unused. The arena therefore starts 0x2000 past the hooks (`arena_guard`).

### The boot loader packs sections

WiiLink's NAND boot program (content `0xb`) ignores DOL file offsets. It streams sections back to back from file offset `0x100`, text slots 0–6 then data slots 7–17.

The hook section therefore takes the last slot (data 17), and its bytes start exactly where the previous section ends (Wii no Ma: text slot 2, see above). If a section is aligned or out of order, it loads another section's bytes, and OSInit crashes.

### Two SDK versions

Forecast, News, Everybody Votes, Check Mii Out and Today and Tomorrow (Japan) have the 2007 KPAD. The Nintendo Channel uses a 2009 KPAD, built with `-DSDK2009`:

* **Sample ring:** 16 inline slots at `k+0x13C` plus an optional external buffer (`k+0x4BC`/`k+0x4C0`), instead of 16 slots at `k+0x110`.
* **Sample count:** keeps one already-read sample, so "nothing new" is a count of 1, not 0.
* **Copy-out:** two sites (MOTION and MOTION2), and the output `KPADStatus` is 0xB0 bytes. The field offsets the hooks use are unchanged.

Later KPADs keep the 2009 code's shape, so they build with `-DSDK2009` too. Each profile passes its differences to `hooks.S` and `gc.c` through `asm_defs`.

* **September 2008** (Photo, Food/Demae, Digicam/Photo Prints): see below.
* **June 2009** (Today and Tomorrow, PAL): an 8-byte bigger KPAD block (0x578) and a 240-byte KPADiRead frame (`POLL_FRAME`).
* **August 2010** (Wii no Ma / Wii Room): WPAD samples grow to 0x42 bytes for MotionPlus. The ring moves to `k+0x180` (index/count `k+0x17A`/`k+0x17B`, external buffer `k+0x5A0`/`k+0x5A4`), the format byte moves from `+0x36` to `+0x40`, and the count is used up completely (no kept sample). The output `KPADStatus` is 0xF0 bytes, the block is 0x688 bytes, and WPAD's device type/status move to 2309/2304. Every hook site uses different registers, and OSInit splits the arena start's `lis`/`addi`, so that arena entry is a `(lis, addi)` pair.

The Photo Channel's September 2008 KPAD is the same code with two differences. The per-channel KPAD block is 0x5C0 bytes instead of 0x570, and the copy-out loops use different registers. The profile passes those registers to `hooks.S` through `asm_defs` (`M1_DEST`/`M1_LEFT`, `M2_DEST`/`M2_LEFT`), and the replaced loop words through `site_words`.

### Porting to another channel

The 2007-SDK channels share one SDK build, so each address is the same code in a new place. `tools/sig.py` finds an address from a known DOL in a new DOL by masked byte signature. It masks relative branches, r2/r13 offsets and immediates.

* **Data addresses** (SI tables, WPAD table, arena constants) are read from the matched lis/addi pairs.
* **New profile:** `tools/port.py <Forecast 00000001.app> <new 00000001.app> <key>` prints a `CHANNELS` entry for a 2007-SDK channel. Paste it into `build.py` and fill in the title.

## Debugging

Set `HOOKS=POLL,SAMPLE,...` in the environment to plant only the listed hooks.
