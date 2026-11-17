# WiiLink-Unshackled

Adds Classic Controller and GameCube controller support to WiiLink's channels, the Internet Channel and the Photo Channel:

| Channel | Title | Main DOL (content 1) |
|---|---|---|
| Forecast Channel (USA, PAL, Japan: one DOL) | HAFE / HAFP / HAFJ | 1,926,048 bytes |
| News Channel (USA, PAL, Japan: one DOL) | HAGE / HAGP / HAGJ | 2,019,232 bytes |
| Everybody Votes Channel (USA) | HAJE | 2,653,152 bytes |
| Everybody Votes Channel (PAL) | HAJP | 2,653,376 bytes |
| Everybody Votes Channel (Japan) | HAJJ | 2,882,016 bytes |
| Check Mii Out Channel (USA) | HAPE | 3,410,240 bytes |
| Mii Contest Channel (PAL) | HAPP | 3,410,240 bytes (another build: told apart by its code) |
| Check Mii Out Channel (Japan) | HAPJ | 3,410,304 bytes |
| Nintendo Channel (USA) | HATE | 3,988,896 bytes |
| Nintendo Channel (PAL) | HATP | 3,992,768 bytes |
| Nintendo Channel (Japan) | HATJ | 4,195,200 bytes |
| Photo Channel 1.1 | HAYA | 2,300,448 bytes |
| Food Channel (Standard, Domino's, Just Eat) / Demae Channel | HCHJ | 3,709,084 or 3,722,036 bytes |
| Digicam Print Channel / Photo Prints Channel | HCDJ | 3,303,168 bytes |
| Today and Tomorrow Channel (Japan) | HAVJ | 4,247,616 bytes |
| Today and Tomorrow Channel (PAL) | HAVP | 3,384,512 bytes |
| Wii no Ma / Wii Room (every language) | HCIJ | 8,929,568 bytes (Portuguese 8,929,328, Russian 8,929,324) |
| Kirby TV Channel | HCMP | 4,825,024 bytes |
| Wii Speak Channel (USA, PAL; Wiimmfi) | HCFE / HCFP | 4,369,376 bytes |
| Wii Speak Channel (Japan, Wiimmfi) | HCFJ | 4,372,384 bytes |
| Internet Channel (USA, PAL, Japan: one DOL) | HADE / HADP / HADJ | 9,180,992 bytes |

Sizes are for the uncompressed DOL. Most of these WADs store content 1 LZ-compressed; `build.py` unpacks it and writes the patched DOL back uncompressed (the boot program loads either).

```
python3 build.py wad "<channel> (WiiLink).wad" out.wad [--clock] [--calm] [--wiilink] [--accuweather] [--newslogos] [--articlemusic]
python3 build.py dol 00000001.app out.app [--clock] [--calm] [--wiilink]
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

* **Hold to repeat:** holding +, −, Up or Down repeats it after 0.4 s, then every 0.15 s. That zooms or tilts the globe step after step, or flips through the forecast pages, like holding them in the News Channel. The Forecast Channel finds presses itself, from the moment a button goes down, so each repeat lets go of the button for one read and presses it again.
* **Globe tilt both ways:** Up/Down (and the curved-arrow buttons) tilt the globe. They now use the News Channel's 11 angles (−80° to 80°, level in the middle) instead of 0° to 80°. The globe can tilt over to its far side, upside down. It opens level, and Restore goes back to level.
* **Tilt sounds:** each angle plays the News Channel's sound for it, rising toward level and falling again past it (sounds 17…12…17), instead of the Forecast Channel's six rising ones, which ran past the end of their table on the new angles.
* **Upside down, not mirrored:** the Forecast Channel's camera keeps its "up" pointing to the top of the globe, so tilted past level the view flipped round and the globe came out mirrored left to right. A hook on the camera's posture call (`globe_posture`, `call_hooks` in `build.py`) turns "up" over when the tilt is below level, as the News Channel does.

The tilt code is the same in both channels, apart from the angle table and its bounds. The new angle and sound tables live in the hook section, and `build.py` points the channel's table loads at them (`sympatches`).

## Forecast Channel: calm wind (`--calm`)

The forecast data gives each wind a direction code, and code 0 means no wind. The channel prints that as a word ("Calm", "Windstill", "Pas de vent", "Viento en calma", "Assenza di vento", "Windstil", in the system language) only when the console's area is not a "USA" one. `SCGetProductArea` sorts the areas: USA, Brazil, Korea, Taiwan-ROC and Asia count as USA; Japan, Europe, Australia and Latin America don't. On a US console the line shows just the speed ("3 mph"), and the city labels on the globe say "None".

So "Calm" needs two things: WiiLink's data sending direction 0 for the city, and a console outside the USA area. `--calm` drops the second: direction 0 then reads "Calm" on US consoles as well, on the forecast screens and on the globe. It changes two words: the wind line's branch for direction 0 (0x8001F148) and the US table's English entry ("None" becomes "Calm").

Tested in Dolphin with a test build that forced direction 0 for the current weather: an unpatched US console showed "3 mph", with `--calm` it showed "Calm".

## Forecast Channel: AccuWeather (`--accuweather`)

`--accuweather` (Forecast Channel, `wad` mode) replaces WeatherNews with AccuWeather in three places:

* **The Wii Menu banner and icon:** the logo (below). `banner.py` does the work on content 0 (`opening.bnr`), and can also be run on its own: `python3 banner.py 00000000.app out.app`.
* **In the channel:** the "supported by weathernews" credit line under the forecast (`TPLWeather.tpl`, images 22 to 25: plain and outlined, and the Japanese "ウェザーニュース" versions) reads "supported by AccuWeather". The channel's own "supported by " is kept; the new name is drawn to match its lettering (`tools/mkcredit.py`, Verdana Bold fitted to the original pixel by pixel, in `assets/accuweather/credit*.ia4`).
* **The banner** (Wii Menu) of the Japanese build says "supported by ウェザーニュース": it becomes "supported by AccuWeather" too (the text pane grows to fit).
* **The manual:** the "supported by weathernews" captions (English, French, Spanish) and the Source page: "provided by AccuWeather, Inc." and https://www.accuweather.com. The screenshots in the manual still show the old credit; it is too small to read in them.

`res.py` makes the channel and manual changes. There is no "weathernews" in the channel's `banner.rso` (checked as stored, LZ-unpacked and as UTF-16), and `TPLCommon.tpl` has only NASA's image credits.

### The logo

* The logo has its real colours: a Hero Orange (#F05514) sun and a black wordmark, per [AccuWeather's brand guidelines](https://developer.accuweather.com/documentation/brand-guidelines).
* It is resized to the logo's 7:1 proportions and has half a sun height of clear space on the white plate.
* The banner's "supported by weathernews" line becomes "supported by AccuWeather".

The textures in `assets/accuweather/` are AccuWeather's official horizontal logo (`AW_RGB_R.svg`), rendered with `resvg -w 140 -h 20` (banner) and `-w 112 -h 16` (icon), then converted with `tools/mktpl.py`. Like the WeatherNews logo they replace, they are IA4 textures tinted by their material. The material maps intensity 0 to black and intensity 1 to Hero Orange, so a single small texture carries both colours. AccuWeather's logo and name are AccuWeather's trademarks.

## WiiLink for WiiConnect24 (`--wiilink`)

`--wiilink` (every channel) says "WiiLink" where the channels say "WiiConnect24" for the service that brings their data: in the manuals, the layouts' text (error messages and the like), the message files (the Nintendo Channel's) and the News Channel's Wii Menu banner, whose letter-spaced "W i i C o n n e c t 2 4" becomes "W i i L i n k". In `dol` mode (and in the Wii app) only the messages inside the main DOL change; in `wad` mode `res.py` does the rest.

* Sentences about the Wii Settings option keep "WiiConnect24", because the console still calls it that: "WiiConnect24 Standby Connection is currently turned off", "turn your WiiConnect24 setting on in the Wii Settings", "WiiConnect24 n'est pas activé", "WiiConnect24 ist zurzeit ausgeschaltet". So do the Nintendo Channel's game tags ("Supports WiiConnect24", "WiiConnect24対応"). This is done sentence by sentence, in all seven languages, in every region's build.
* "Nintendo" changes only where Nintendo stood for the service's operator: the Forecast manual's "Nintendo may not be able to answer every question" (three languages), the News manual's "Nintendo cannot answer any inquiries" (PAL, six languages; the Japanese manuals' 弊社), the Everybody Votes manual's "send your suggested question to Nintendo" (three languages) and Check Mii Out's contest text "Please Contact Nintendo For Further Information". Copyright notices, "Club Nintendo" and "created by Nintendo" stay.
* Text only ever gets shorter, so every string stays in its own space. Check Mii Out's contest script counts its strings' lengths, so there the line keeps its length (with a trailing space).

Main DOLs with WiiConnect24 messages: the Food and Demae Channels (their error messages). The other channels keep theirs in layouts or manuals.

## News Channel: article music (`--articlemusic`)

The News Channel's music is made of layers that start together and fade in and out with the screen: `bgm_news_anytime` (NEW_BGM_NEWS) always, `bgm_news_cikyu_only` (the globe) on the globe, and `bgm_news_read_only` (NEW_BGM_READ) on the reading screens (sections, headlines, articles). The channel starts and fades the reading layer, but its sound archive (`rev_news.brsar`, content 9) gives it volume 0, so it is never heard. It may have been muted because it drifts: it loops every 78 bars and the main layer every 56 (same tempo), so after the first 1 min 47 s the two no longer line up.

`--articlemusic` (News Channel, `wad` mode; `res.py`) gives NEW_BGM_READ the main layer's volume (50) and shortens each of its 16 tracks to loop after 56 bars, back to the same loop start. A jump is written where the main layer loops (a wait across that point is shortened, and a subroutine call across it is copied up to it); every note before it is left as it is. The archive is the same in all three regions. The Wii app doesn't change resources yet, so this is a `build.py` option only.

## News Channel: sources (`--newslogos`)

`--newslogos` (News Channel, `wad` mode; `--aplogo` is its old name) makes the manual's Source page show the source WiiLink's News Channel server uses for the console's language, with that source's logo (`assets/news/`, the logos WiiLink's server sends to the channel) and copyright line:

| Manual | Source |
|---|---|
| USA | The Associated Press: the old "AP Associated Press" logo becomes AP's current one |
| PAL English | Reuters |
| PAL French | France 24 |
| PAL German | tagesschau (ARD-aktuell) |
| PAL Spanish | RTVE |
| PAL Italian | ANSA |
| PAL Dutch | NOS |
| Japan | Reuters (in place of the picture of Mainichi, NNN, goo and NTT Communications' logos) |

The PAL pages lose their AFP / ANP / ANSA and AP blocks for the one source; the new logos are added to the manual's archive (`res.py` can add files to a U8 archive). With `--wiilink` too, the page's closing "Nintendo cannot answer any inquiries..." says WiiLink (every PAL language, and the Japanese 弊社 "we").

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
* **Debug Save Data Access**, **Debug Menu** and **Rare Message Check** switch to developer scenes that freeze a retail console, so the patch makes those three entries do nothing. Checked in Dolphin: selecting each of them with A leaves the channel running and the overlay working.
* Entries include Console, Debug Save Data Access, Rare Message Check, Safety Frame, Save Data Clear, All Your Base, Debug Print, Debug See Result, Debug Contest Off Limit, the Settings/Startup/Request/Response/Cache Dumps, Cache Clear, No Cache, NWC24 Tmp Error Occur and Disp Mii Info.
* **All Your Base** makes the channel treat every Mii as if it had been made on this Wii. It overrides the channel's check of a Mii's creator ID, so the Mii doesn't have to come from this console.

```bash
python3 build.py wad "Check Mii Out Channel (USA) (WiiLink).wad" "Check Mii Out Channel (USA) (WiiLink) [CC & GC + gold pants + debug menu].wad" --debug-menu
```

## Debug modes in the other channels

Found while looking, not patches (yet):

* **Digicam Print / Photo Prints Channel:** the developers' scene graph is still in the DOL, with a `DBG_SceneLayout` scene and developer exits ("to the Print Channel", "to the keyboard test", "to the network test", "to the minigame" `H_Edit_Game`, a scene of its own). There is also an offline test mode: when a byte of the account data the channel keeps is 6, every server request answers "Debug No Network Mode" and the screens fill with "test( debug mode )" data. Starting the channel in `Z_1xxx` or `DBG_SceneLayout` instead of `A_Boot` only leads to the normal title screen, so the menu behind those exits hasn't been reached yet.
* **Everybody Votes Channel:** a `DebugLayout` class.
* **Nintendo Channel:** EGG's debug root (`EGGRootDebug`, `dsDebug_c`).
* **Wii Room / Wii no Ma:** a debug server switch ("use server = DEBUG") and `Sky_Weather_Debug` layouts.

## Photo Channel: Message Board photos on the SD card

When the Wii Message Board fills up, the Wii Menu moves older posts to the SD card, under `SD:/private/wii/title/HAEA/`. The Photo Channel's "View Wii Message Board photos" only showed the photos still on NAND. It now also shows the ones on the SD card.

The channel reads the Message Board through Nintendo's CDB library, the same one the Wii Menu uses. CDB can read posts on SD, including checking their signature and decrypting them, but the Photo Channel never mounted the card for it and its scan asked for NAND posts only. `src/cdbsd.c` runs before each scan (`hook_cdbsd`):

* It mounts the SD card as the read-only drive "SD" of CDB's file library (VF). Sectors are read with the SD card driver of the channel's own SD library, the one behind "Digital Camera/Cell Phone".
* It sets CDB's "SD mounted" flag, and the scan asks for NAND and SD posts.
* The drive is mounted afresh for every scan, so a swapped card is read from scratch. With no card in, the scan is NAND-only as before.

### Posts from any console

CDB only reads posts made for this console. It looks under `HAEA/<this console's Wii ID>/` only, and it drops a post if the HMAC (keyed with this console's ID) or the console ID in the post's header doesn't match. The Wii Menu does the same, which is why posts copied from another console, or made by a tool with the wrong key, were found by neither. The patch:

* takes out CDB's two comparisons. The post is still decrypted with the key and IV it carries, as mailboxbomb's format describes, so the photo (the post's JPEG attachment) reads the same;
* chooses which console folder CDB reads before each scan. It uses this console's `HAEA/<id>/<id>` folder if the card has one, and otherwise the first console folder on the card. CDB's two folder-ID getters are used only to build SD paths, and they now read the chosen ID (`cdbsd.c`, `SCAN_ID`).

One console folder is read per scan, so with posts from several consoles on one card, only this console's (or the first) folder is shown.

Tested in Dolphin:

* A photo post that exists only on the SD card was found and its thumbnail was shown, also when the view was opened again.
* The same post moved to another console's folder, with that console's ID in its header and an HMAC made with another key, was dropped before this change. It is shown now: "Found 2 photos" (one NAND post, one SD post), with both thumbnails.
* Without a card, NAND photos showed as before. The "Digital Camera/Cell Phone" SD view works as in the original channel.

The SD posts were made by a script in the format CDB reads, not by the Wii Menu itself.

## Wii Speak Channel: Message Board photos on the SD card

The Wii Speak Channel (USA) reads Message Board photos through the same CDB scan as the Photo Channel. It looks for NAND posts only (`li r10,1` at `0x800340B4`). The same `cdbsd` hook makes it look on the SD card as well. Wii Speak has the same VF library and SD card driver, but nothing in the channel ever starts that driver. With `FA_SD_INIT` in its profile, `cdbsd.c` starts the driver for the first SD drive it attaches. It then points the driver at each new drive, so the driver's card insert/eject callbacks report to a live drive, or to none.

Posts from any console work the same way here (same CDB code, ported addresses for the USA/PAL and Japanese builds). Not tested in a running channel: the scan only runs when the photo viewer (`photoAppre`) asks for it, which is in an online chat room. The addresses were found by signature from the Photo Channel's, `build.py` builds and checks every original word, and the channel boots with the patch in Dolphin, with emulated Wii Speak and an SD card.

## Wii app

`wii/` is a Homebrew Channel app that does the same on the console: it finds WiiLink's channels on the NAND (and on the SD card as `content.bin`, except the Forecast, News and Photo Channels), lets you tick the features you want, backs up the unpatched copy to the SD card, patches content 1 and packs it again with WiiLink's LZ type. It can put the unpatched copy back. It only patches WiiLink's own builds, recognised by their SHA-1. See [wii/README.md](wii/README.md).

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

The code and 0x200 bytes of state take the first 0x1800 bytes of the OS arena (0x2000 in the Nintendo, Everybody Votes, Photo and Wii Speak Channels; 0x1818 in Kirby TV, whose `__ArenaLo` is only 8-byte aligned). The state is split into 0x00 for gc.c, 0x40 for motion.c and 0x100 for kbd.c. That's `__ArenaLo`, right above the debugger stack. OSInit's arena constants (each a `lis`/`addi` pair) move up past it, so the game never allocates over it.

Wii no Ma / Wii Room (and Kirby TV, the same OS) needs two exceptions:

* **Text slot:** code in a data section doesn't run under its boot program, so the hook section goes in the first free text slot (slot 2, `text_slot`). Its bytes are inserted into the stream between text slot 1 and data slot 7.
* **Arena guard:** its OS writes the 0x800 bytes just below `__ArenaLo`, which the original layout leaves unused. The arena therefore starts 0x2000 past the hooks (`arena_guard`).

### The boot loader packs sections

WiiLink's NAND boot program (content `0xb`) ignores DOL file offsets. It streams sections back to back from file offset `0x100`, text slots 0–6 then data slots 7–17.

The hook section therefore takes the last slot (data 17), and its bytes start exactly where the previous section ends (Wii no Ma: text slot 2, see above). If a section is aligned or out of order, it loads another section's bytes, and OSInit crashes.

### Two SDK versions

Forecast, News, Everybody Votes, Check Mii Out and Today and Tomorrow (Japan) have the 2007 KPAD. The Internet Channel's November 2006 KPAD is the same code with the channel in r28 rather than r27 (`K_CHAN`), and its WPAD keeps the device type and status at 2049/2044 (`WPAD_TYPE`/`WPAD_STATUS`). The Nintendo Channel uses a 2009 KPAD, built with `-DSDK2009`:

* **Sample ring:** 16 inline slots at `k+0x13C` plus an optional external buffer (`k+0x4BC`/`k+0x4C0`), instead of 16 slots at `k+0x110`.
* **Sample count:** keeps one already-read sample, so "nothing new" is a count of 1, not 0.
* **Copy-out:** two sites (MOTION and MOTION2), and the output `KPADStatus` is 0xB0 bytes. The field offsets the hooks use are unchanged.

Later KPADs keep the 2009 code's shape, so they build with `-DSDK2009` too. Each profile passes its differences to `hooks.S` and `gc.c` through `asm_defs`.

* **September 2008** (Photo, Food/Demae, Digicam/Photo Prints, Wii Speak): see below.
* **June 2009** (Today and Tomorrow, PAL): an 8-byte bigger KPAD block (0x578) and a 240-byte KPADiRead frame (`POLL_FRAME`).
* **August 2010** (Wii no Ma / Wii Room; Kirby TV's December 2009 KPAD is the same code): WPAD samples grow to 0x42 bytes for MotionPlus. The ring moves to `k+0x180` (index/count `k+0x17A`/`k+0x17B`, external buffer `k+0x5A0`/`k+0x5A4`), the format byte moves from `+0x36` to `+0x40`, and the count is used up completely (no kept sample). The output `KPADStatus` is 0xF0 bytes, the block is 0x688 bytes, and WPAD's device type/status move to 2309/2304. Every hook site uses different registers, and OSInit splits the arena start's `lis`/`addi`, so that arena entry is a `(lis, addi)` pair.

The Photo Channel's September 2008 KPAD is the same code with two differences. The per-channel KPAD block is 0x5C0 bytes instead of 0x570, and the copy-out loops use different registers. The profile passes those registers to `hooks.S` through `asm_defs` (`M1_DEST`/`M1_LEFT`, `M2_DEST`/`M2_LEFT`), and the replaced loop words through `site_words`.

### Porting to another channel

The 2007-SDK channels share one SDK build, so each address is the same code in a new place. `tools/sig.py` finds an address from a known DOL in a new DOL by masked byte signature. It masks relative branches, r2/r13 offsets and immediates.

* **Data addresses** (SI tables, WPAD table, arena constants) are read from the matched lis/addi pairs.
* **New profile:** `tools/port.py <Forecast 00000001.app> <new 00000001.app> <key>` prints a `CHANNELS` entry for a 2007-SDK channel. Paste it into `build.py` and fill in the title.
* **Another region of a supported channel:** `tools/portprofile.py <key> <known main DOL> <new main DOL> <new key> <title>` ports the whole profile: hook sites, arena, functions, data, the channel's patches (checked against the new DOL, with their branches re-aimed), the keyboard and SD hooks. Data that no lis/addi pair builds is moved by its nearest ported neighbour's shift (it says which). The PAL and Japanese profiles in `build.py` were made this way. Two builds of the same size (Check Mii Out USA, Mii Contest PAL) are told apart by the words at their hook sites and patches.

## Debugging

Set `HOOKS=POLL,SAMPLE,...` in the environment to plant only the listed hooks.
