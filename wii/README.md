# WiiLink Unshackled (Wii app)

A Homebrew Channel app that patches WiiLink's channels where they are installed, with the features you tick, and puts
the unpatched copy back when you ask.

## Install

1. Build it (below) or take `apps/WiiLinkUnshackled/` from a release.
2. Copy `apps/WiiLinkUnshackled/` (`boot.dol`, `meta.xml`, `icon.png`) to the SD card.
3. Start it from the **Homebrew Channel**. It needs HW_AHBPROT (`<ahb_access/>` in `meta.xml`) for the NAND and the
   console's keys.

An SD card is required: every unpatched copy is backed up there before anything is changed.

At start the app checks GitHub for a newer release (libwiiupdate). B skips the check; when there is one, A installs it
over the app's folder.

## Use

The app lists the channels it recognises, on the NAND and on the SD card, and whether each is **unpatched** (WiiLink's
build) or **patched**. Pick one, tick the features you want and choose **Patch with these**. **Restore the unpatched
copy** puts WiiLink's build back. Patching a patched channel starts again from the unpatched copy, so features can be
turned off as well as on.

Up/Down move one row, Left/Right jump a page (stopping at the first and last rows), and a held D-pad repeats, as in
GodModeWii. Every controller libwiiinput reads works: Wii Remote, Classic Controller, GameCube pad, USB keyboard.

| Channel | Features |
|---|---|
| Forecast Channel (USA, PAL, Japan) | Classic Controller and GameCube pads, clock on US consoles, globe tilts both ways, Japanese version on any console (off by default) |
| News Channel (USA, PAL, Japan) | pads, clock on US consoles |
| Everybody Votes Channel (USA, PAL, Japan) | pads, USB keyboard, no daily suggestion limit |
| Check Mii Out Channel (USA, Japan) / Mii Contest Channel (PAL) | pads, gold pants Miis, debug menu (hold 1+2; off by default; the three entries that freeze a console do nothing) |
| Nintendo Channel (USA, PAL, Japan) | pads |
| Photo Channel 1.1 | pads, Message Board photos from the SD card |
| Food Channel (Standard, Domino's, Just Eat) / Demae Channel | pads |
| Digicam Print / Photo Prints Channel | pads |
| Today and Tomorrow Channel (Japan, PAL) | pads |
| Wii no Ma / Wii Room (every language) | pads |
| Kirby TV Channel | pads |
| Wii Speak Channel (USA, PAL, Japan) | pads, Message Board photos from the SD card |
| Internet Channel (USA, PAL, Japan) | pads |

The USB keyboard, the globe tilt table and the Message Board photos live in the controller patch's hook section, so
they need it ticked. The clock patch only changes what a US console shows (EU and Japanese consoles already show the clock); the Forecast and News Channels' PAL and Japanese builds have the same main DOL as the USA ones, so they get the same choices.
The app only changes content 1 (the main DOL), so the options that change the other contents are `build.py`-only for now: `--accuweather`, `--newslogos`, and `--wiilink` (whose DOL part alone would leave the manuals and layouts unchanged, so the app doesn't offer it either).

### What it checks

* A channel is only patched from WiiLink's own build: content 1 must match, by SHA-1, the build `build.py export`
  recorded (unpacked as well). Anything else isn't listed, so the app never layers onto an unknown or already-modified
  channel.
* **Before the first patch** the unpatched content 1 and TMD (or the whole `content.bin`) are copied to
  `sd:/wiilink-unshackled/backup/<title ID>[-sd]/`, read back and compared. `applied.txt` there says which features
  are on.
* The patched DOL is packed again with the LZ type WiiLink used (LZ10 / LZ11; the packed data is unpacked and compared
  before writing), or left unpacked where WiiLink left it unpacked.
* The TMD gets content 1's new size and SHA-1 and is fakesigned, as for any homebrew channel; the System Menu launches
  fakesigned channels as they are.
* NAND files are written to `/tmp/wlu.tmp` (IOS takes file names of 12 characters at most), read back, then moved
  into place with the old file's owner and permissions, and read back again. Only the channel's own content 1 and
  `title.tmd` are touched. If writing fails half way, WiiLink's unpatched copy is put back, and the message says which
  of the two happened (and the NAND error).

### Channels on the SD card

A channel moved to the SD card (or installed there with wad2bin) is `private/wii/title/<ID>/content.bin`, encrypted and
signed with the console's keys. The app decrypts content 1 with the console's PRNG key, patches it, writes Parts C to F
again (the TMD, content 1 and the AP signature; the other contents and Parts A and B are copied as they are), and
updates the title's TMD on the NAND. The whole `content.bin` is backed up first.

* The Forecast, News and Photo Channels misbehave when run from the SD card, so the app doesn't look for them there.
* A channel on the SD card with a changed (fakesigned) TMD may need a System Menu IOS with the signing bug to load
  (GodModeWii notes the same for wad2bin with non-console tickets). This hasn't been tried on a console yet.
* Dolphin can't read a console's keys, so the SD card path was tested on a computer: a `content.bin` made in wad2bin's
  layout with test keys was read, rewritten, read back and its signatures verified.

## Tested

In Dolphin: the app lists unpatched WiiLink channels from the NAND. Patching Wii no Ma / Wii Room (LZ11, the largest)
backed it up, wrote exactly the DOL `build.py` makes (packed again), and the channel then booted from the NAND, with
the Classic Controller stick moving its pointer. **Restore** put WiiLink's signed TMD and content back, byte for byte.
A native build of the patcher core makes the same DOL as `build.py` for all 19 WADs below, and every feature set
checked. Kirby TV, Wii Speak and the Internet Channel, patched, moved their pointer with the Classic Controller stick in
Dolphin (and the Internet Channel with a GameCube pad); the app's list paging was checked there too.

## Build

```
git submodule update --init      # wii/libwiiinput, wii/libwiiupdate
cd wii
make            # WiiLinkUnshackled.dol (builds the two libraries first)
make hbc        # apps/WiiLinkUnshackled/{boot.dol,meta.xml,icon.png}
```

Needs devkitPPC, libogc2 and libwiikeyboard (`DEVKITPRO`, `DEVKITPPC`). libwiiinput and libwiiupdate are git
submodules, pinned to the commits GodModeWii uses. The patches are `data/patches.bin`, linked in with bin2o
(`patches_bin.h`). To make it again after changing the hooks or the profiles in `build.py`:

```
python3 build.py export wii/data/patches.bin "Forecast Channel (USA) (WiiLink).wad" "News Channel (USA) (WiiLink).wad" ...
```

with every WAD the app should recognise. The export used for `data/patches.bin`: every channel WAD in WiiLink's WAD set (USA, PAL and Japan, every Wii Room language; not Region Select or the Address Settings), USA first, and the Photo Channel 1.1 system WAD. Builds with the same content 1 share an entry.

## patches.bin

Big-endian. It holds the hook section and changed words only, plus hashes: nothing of the channels themselves.

| Offset | |
|---|---|
| 0x00 | `WLUP`, version 1, number of channels, offset of the channel table, offset of the pool, file size |
| table | 0x100 bytes per channel: name (48), title ID, content 1 size and SHA-1 (as in the TMD), unpacked DOL size and SHA-1, LZ type (0 / 0x10 / 0x11), new DOL header (pool offset), `at`, `cut`, hook section (pool offset, length), number of features, offset of its features, then (0xA4) flags: 1 = NAND only |
| features | 0x40 bytes each: id (12), name (40), flags (1 on by default, 2 needs the hook section, 4 is the hook section), number of words, pool offset of the words |
| pool | each feature's words as {offset in the DOL, original word, new word}, the headers and hook sections |

The patched DOL is: the features' words changed in the unpatched DOL, then, with the hook section, the new header +
DOL[0x100:at] + hook section + DOL[at:cut].

## Credits and licence

[libwiiinput](https://github.com/quatric/libwiiinput) reads the controllers and
[libwiiupdate](https://github.com/quatric/libwiiupdate) checks for updates. `source/aes.c`, `sha1.c`, `ecc233.c`, `otp.c`, the `content.bin` layout and AP signature (`sdbin.c`) and the way the
console keys are read (`keys.c`) come from [GodModeWii](https://github.com/quatric/GodModeWii), which follows
DarkMatterCore's [wad2bin](https://github.com/DarkMatterCore/wad2bin). `runtimeiospatch.c` is libruntimeiospatch
(Joseph Jordan, damysteryman, Christopher Bratusek, DarkMatterCore, megazig, FIX94), as GodModeWii carries it.
This app is under the GNU GPL version 2 (`LICENSE`), like the code it includes.
