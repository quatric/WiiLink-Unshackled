# WiiLink Unshackled (Wii app)

A Homebrew Channel app that patches WiiLink's channels where they are installed, with the features you tick, and puts
the clean copy back when you ask.

## Install

1. Build it (below) or take `apps/WiiLinkUnshackled/` from a release.
2. Copy `apps/WiiLinkUnshackled/` (`boot.dol`, `meta.xml`, `icon.png`) to the SD card.
3. Start it from the **Homebrew Channel**. It needs HW_AHBPROT (`<ahb_access/>` in `meta.xml`) for the NAND and the
   console's keys.

An SD card is required: every clean copy is backed up there before anything is changed.

## Use

The app lists the channels it recognises, on the NAND and on the SD card, and whether each is **clean** (WiiLink's
build) or **patched**. Pick one, tick the features you want and choose **Patch with these**. **Restore the clean copy**
puts WiiLink's build back. Patching a patched channel starts again from the clean copy, so features can be turned off as
well as on.

| Channel | Features |
|---|---|
| Forecast Channel (USA) | Classic Controller and GameCube pads, clock on US consoles, globe tilts both ways |
| News Channel (USA) | pads, clock on US consoles |
| Everybody Votes Channel (USA) | pads, USB keyboard, no daily suggestion limit |
| Check Mii Out Channel (USA) | pads, gold pants Miis, debug menu (hold 1+2; off by default) |
| Nintendo Channel (USA) | pads |
| Photo Channel 1.1 | pads, Message Board photos from the SD card |
| Food Channel (Standard, Domino's, Just Eat) / Demae Channel | pads |
| Digicam Print / Photo Prints Channel | pads |
| Today and Tomorrow Channel (Japan, PAL) | pads |
| Wii no Ma / Wii Room | pads |

The USB keyboard, the globe tilt table and the Message Board photos live in the controller patch's hook section, so
they need it ticked. The clock patch is only offered for the US builds: the EU and Japanese ones already show the clock.
The AccuWeather banner (`build.py --accuweather`) isn't in the app yet.

### What it checks

* A channel is only patched from WiiLink's own build: content 1 must match, by SHA-1, the build `build.py export`
  recorded (unpacked as well). Anything else isn't listed, so the app never layers onto an unknown or already-modified
  channel.
* **Before the first patch** the clean content 1 and TMD (or the whole `content.bin`) are copied to
  `sd:/wiilink-unshackled/backup/<title ID>[-sd]/`, read back and compared. `applied.txt` there says which features
  are on.
* The patched DOL is packed again with the LZ type WiiLink used (LZ10 / LZ11; the packed data is unpacked and compared
  before writing), or left unpacked where WiiLink left it unpacked.
* The TMD gets content 1's new size and SHA-1 and is fakesigned, as for any homebrew channel; the System Menu launches
  fakesigned channels as they are.
* NAND files are written to `/tmp`, read back, then moved into place with the old file's owner and permissions. Only
  the channel's own content 1 and `title.tmd` are touched.

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

In Dolphin: the app lists clean WiiLink channels from the NAND. Patching Wii no Ma / Wii Room (LZ11, the largest)
backed it up, wrote exactly the DOL `build.py` makes (packed again), and the channel then booted from the NAND, with
the Classic Controller stick moving its pointer. **Restore** put WiiLink's signed TMD and content back, byte for byte.
A native build of the patcher core makes the same DOL as `build.py` for all 16 WADs below, and every feature set
checked.

## Build

```
cd wii
make            # WiiLinkUnshackled.dol
make hbc        # apps/WiiLinkUnshackled/{boot.dol,meta.xml,icon.png}
```

Needs devkitPPC and libogc (`DEVKITPRO`, `DEVKITPPC`). The patches are `data/patches.bin`, linked in with bin2o
(`patches_bin.h`). To make it again after changing the hooks or the profiles in `build.py`:

```
python3 build.py export wii/data/patches.bin "Forecast Channel (USA) (WiiLink).wad" "News Channel (USA) (WiiLink).wad" ...
```

with every WAD the app should recognise. The export used for `data/patches.bin`: Forecast, News, Everybody Votes, Check
Mii Out and Nintendo Channels (USA), Food Channel (Standard, Domino's, Just Eat), Demae Channel (Standard), Digicam
Print and Photo Prints Channels, Today and Tomorrow Channel (Japan, PAL), Wii Room and Wii no Ma (all WiiLink's), and
the Photo Channel 1.1 system WAD. Builds with the same content 1 share an entry.

## patches.bin

Big-endian. It holds the hook section and changed words only, plus hashes: nothing of the channels themselves.

| Offset | |
|---|---|
| 0x00 | `WLUP`, version 1, number of channels, offset of the channel table, offset of the pool, file size |
| table | 0x100 bytes per channel: name (48), title ID, content 1 size and SHA-1 (as in the TMD), unpacked DOL size and SHA-1, LZ type (0 / 0x10 / 0x11), new DOL header (pool offset), `at`, `cut`, hook section (pool offset, length), number of features, offset of its features, then (0xA4) flags: 1 = NAND only |
| features | 0x40 bytes each: id (12), name (40), flags (1 on by default, 2 needs the hook section, 4 is the hook section), number of words, pool offset of the words |
| pool | each feature's words as {offset in the DOL, original word, new word}, the headers and hook sections |

The patched DOL is: the features' words changed in the clean DOL, then, with the hook section, the new header +
DOL[0x100:at] + hook section + DOL[at:cut].

## Credits and licence

`source/aes.c`, `sha1.c`, `ecc233.c`, `otp.c`, the `content.bin` layout and AP signature (`sdbin.c`) and the way the
console keys are read (`keys.c`) come from [GodModeWii](https://github.com/quatric/GodModeWii), which follows
DarkMatterCore's [wad2bin](https://github.com/DarkMatterCore/wad2bin). `runtimeiospatch.c` is libruntimeiospatch
(Joseph Jordan, damysteryman, Christopher Bratusek, DarkMatterCore, megazig, FIX94), as GodModeWii carries it.
This app is under the GNU GPL version 2 (`LICENSE`), like the code it includes.
