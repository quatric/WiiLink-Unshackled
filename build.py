#!/usr/bin/env python3
"""Classic Controller + GameCube controller patch for WiiLink's channels and the Photo Channel
(Everybody Votes Channel: also USB keyboard and no daily suggestion limit).

  build.py dol <00000001.app in> <00000001.app out> [--clock] [--debug-feed] [--debug-menu]
  build.py wad <channel .wad> <out.wad> [--clock] [--accuweather] [--debug-feed] [--debug-menu]

The channel is recognised from its main DOL.  Builds the hooks in src/ with
devkitPPC, links them at the start of the OS arena (right above the main
stack), moves the arena start up past them, adds them to the main DOL as a new
section (last slot) and plants a branch at each hook site.  --clock (Forecast
and News Channels) also applies forecast_us_clock_patch.py / news_us_clock_patch.py.  --accuweather
(Forecast Channel, wad mode) swaps the WeatherNews logo on the channel's banner
and Wii Menu icon for AccuWeather's (banner.py).  --debug-menu (Check Mii Out
Channel) lets 1+2 open the developers' debug overlay.
`wad` unpacks with Sharpii, patches content 1 (decompressing it if WiiLink LZ-packed it), repacks and fakesigns.

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
        # hold + / - / Up / Down to repeat them (src/motion.c)
        'repeat': 0x101C,
        # globe tilt (Up/Down, the curved-arrow buttons): the News Channel's
        # 11 angles, -80..80 degrees, so it can tilt over to the far side
        # (upside down) instead of stopping at 0..80
        'patches': [
            (0x80040B88, [0x2C000006], [0x2C00000B], 'globe tilt: step up to index 10 (was 5)'),
            (0x80040B94, [0x38000005], [0x3800000A], 'globe tilt: clamp at index 10 (was 5)'),
            (0x8001860C, [0x2C000005], [0x2C00000A], 'globe tilt: grey the tilt-up arrow at index 10'),
            (0x8000F334, [0x38800000], [0x38800005], 'globe tilt: open the globe level (index 5 = 0 degrees)'),
            (0x8000F344, [0x38800000], [0x38800005], 'globe tilt: open the globe level (index 5 = 0 degrees)'),
            (0x80018A0C, [0x38800000], [0x38800005], 'globe tilt: Restore goes back to level'),
        ],
        # (lis address, addi address, hook symbol): point the angle table loads at tilt_angles
        'sympatches': [(0x80040A58, 0x80040A60, 'tilt_angles'), (0x80040B08, 0x80040B10, 'tilt_angles'),
                       (0x80040BA0, 0x80040BA4, 'tilt_angles'), (0x80040C04, 0x80040C08, 'tilt_angles')],
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
        'clock': 'news_us_clock_patch',
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
        # The channel sorts each Mii into 0/1 (made on this Wii), 2 (made on another Wii)
        # or 3 (special, "gold pants").  Only 0/1 can be the Mii Artisan or be posted.
        # Send special Miis on to the 0/1 test instead of returning 3.
        'patches': [
            (0x80273450, [0x38600003], [0x48000020],
             'gold pants Miis: special Miis count as made on this Wii'),
        ],
        # --debug-menu: the developers' debug overlay is still built and updated every
        # frame, but its "open?" test (0x80287750) was stubbed to return 0.  Replace the
        # call to it with: open the overlay when 1 and 2 are both held and one of them
        # was just pressed.
        'debug_patches': [
            (0x80287794,
             [0x7F83E378, 0x4BFFFFB9, 0x2C030000, 0x41820028, 0x38000000, 0x901C2394, 0x387C2398,
              0x38800001, 0x48000651, 0x387C23AC, 0x38800000, 0x48000615, 0x480001E4],
             [0x4BD85A7D,   # bl   0x8000D210        pad manager
              0x38800000,   # li   r4,0
              0x4BFDE131,   # bl   0x802658CC        Wii Remote 1's buttons
              0x80030014,   # lwz  r0,20(r3)         held
              0x80830018,   # lwz  r4,24(r3)         just pressed
              0x70840300,   # andi. r4,r4,1|2
              0x4182001C,   # beq  0x802877C8
              0x70000300,   # andi. r0,r0,1|2
              0x2C000300,   # cmpwi r0,1|2
              0x40820010,   # bne  0x802877C8
              0x387C2398,   # addi r3,r28,9112       the overlay's "open" flag
              0x38800001,   # li   r4,1
              0x48000641],  # bl   0x80287E04        set it
             'debug menu: 1+2 opens the debug overlay'),
        ],
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
    # Photo Channel 1.1 (system title, not WiiLink): a Sept 2008 KPAD, the 2009
    # code with the copy-out loops' registers allocated differently
    'photo': {
        'title': 'Photo Channel 1.1 (HAYA)',
        'hook_size': 0x2000,
        'dol_size': 2300448,
        'sdk': 2009,
        'arena_lo': 0x80397680, 'stack_end': 0x80395668, 'lis': 0x8039,
        'arena': [0x80149090, 0x80149138, 0x801490E0, 0x8014916C],
        'defs': {
            'SI_TYPES': 0x802231B8,
            'SI_BUSY': 0x802231A0,
            'SI_SHADOW': 0x802231A4,
            'FN_SIGETTYPE': 0x80157D50,
            'FN_OSDISABLE': 0x8014D864,
            'FN_OSRESTORE': 0x8014D88C,
            'WPAD_TBL': 0x803446B0,
            'KPAD_BASE': 0x80347E48,
            'KPAD_STRIDE': 0x5C0,
        },
        'sites': {'POLL': 0x8018B6D0, 'SAMPLE': 0x8018B848, 'PROBE': 0x8017F5A0,
                  'BUTTONS': 0x801891D4, 'MOTION': 0x8018BDB8, 'MOTION2': 0x8018BF34},
        # copy-out loops: per-sample entry r25 / left r24, compose-once entry r27 / left r25
        'site_words': {'MOTION': 0x3718FFFF, 'MOTION2': 0x3739FFFF},
        'asm_defs': {'M1_DEST': 25, 'M1_LEFT': 24, 'M2_DEST': 27, 'M2_LEFT': 25},
        'clock': None,
        # Wii Message Board photos from the SD card too (src/cdbsd.c)
        'cdbsd': {
            'site': 0x8000E6FC,                 # li r10,1: CDBDatabaseSearch(..., NAND only)
            'defs': {
                'VF_LOOKUP': 0x8007348C,        # drive name -> index
                'VF_ATTACH': 0x800716A0,        # new drive from the disk table template
                'VF_SETNAME': 0x800734EC,
                'VF_VOLUME': 0x800719E4,        # drive index -> volume
                'VF_DRV_PRESENT': 0x800741C8,   # (disk, 1): medium present
                'VF_NOTIFY_INSERT': 0x80058A48, # disk manager: medium inserted
                'VF_UNMOUNT': 0x8006FA1C,       # VFUnmountDrive(name): unmount and detach
                'VF_MOUNT': 0x8006F79C,         # open the partition, mount
                'VF_DISK_TMPL': 0x80382FD8,     # {NAND file driver init, 0}
                'VF_LOCK_ON': 0x8038395C,
                'VF_MUTEX': 0x8025FB20,
                'FN_OSLOCKMUTEX': 0x8014EA04,
                'FN_OSUNLOCKMUTEX': 0x8014EAE0,
                'FA_SD_STATE': 0x802FFF20,      # SD card driver: bit 0 = initialised, +16 card in
                'FA_SD_MOUNT': 0x8009D5D0,      # card init (once; later calls return 0)
                'FA_SD_READ': 0x8009D870,
                'FA_SD_BUSY': 0x80383984,       # SDIO request in flight
                'FA_SD_INFO': 0x8009DA20,
                'CDB_SD': 0x802370A8,           # CDB SD paths / flags (+4: SD mounted)
            },
        },
    },
    # The WiiLink WADs below store content 1 LZ-compressed (main_dol() unpacks it).
    # Food Channel (Standard, Domino's, Just Eat) and Demae Channel: the Photo
    # Channel's Sept 2008 KPAD, and all three DOLs have the same addresses
    'food': {
        'title': "Food / Demae Channel (HCHJ: Standard, Domino's, Just Eat)",
        'dol_size': [3709084, 3722036],
        'sdk': 2009,
        'arena_lo': 0x804865C0, 'stack_end': 0x804845B8, 'lis': 0x8048,
        'arena': [0x8019A054, 0x8019A0FC, 0x8019A0A4, 0x8019A130],
        'defs': {
            'SI_TYPES': 0x803782C8,
            'SI_BUSY': 0x803782B0,
            'SI_SHADOW': 0x803782B4,
            'FN_SIGETTYPE': 0x80238FAC,
            'FN_OSDISABLE': 0x8019FDB0,
            'FN_OSRESTORE': 0x8019FDD8,
            'WPAD_TBL': 0x803C5FD0,
            'KPAD_BASE': 0x80407080,
            'KPAD_STRIDE': 0x5C0,
        },
        'sites': {'POLL': 0x8022DCC4, 'SAMPLE': 0x8022DE3C, 'PROBE': 0x801AAD64,
                  'BUTTONS': 0x8022B7C8, 'MOTION': 0x8022E3AC, 'MOTION2': 0x8022E528},
        'site_words': {'MOTION': 0x3718FFFF, 'MOTION2': 0x3739FFFF},
        'asm_defs': {'M1_DEST': 25, 'M1_LEFT': 24, 'M2_DEST': 27, 'M2_LEFT': 25},
        # pos x +-1 is the screen edge here (no 16:9 widening); y clamps at ~0.75 as usual
        'pointer': {'LIM_X_WIDE': 1.0, 'LIM_X_43': 1.0},
        'clock': None,
    },
    # Digicam Print Channel / Photo Prints Channel: Sept 2008 KPAD
    'digicam': {
        'title': 'Digicam Print / Photo Prints Channel (HCDJ)',
        'dol_size': 3303168,
        'sdk': 2009,
        'arena_lo': 0x804B7920, 'stack_end': 0x804B5908, 'lis': 0x804B,
        'arena': [0x80087A3C, 0x80087AE4, 0x80087A8C, 0x80087B18],
        'defs': {
            'SI_TYPES': 0x80303658,
            'SI_BUSY': 0x80303640,
            'SI_SHADOW': 0x80303644,
            'FN_SIGETTYPE': 0x800C000C,
            'FN_OSDISABLE': 0x8008C1E0,
            'FN_OSRESTORE': 0x8008C208,
            'WPAD_TBL': 0x80363910,
            'KPAD_BASE': 0x8039DE18,
            'KPAD_STRIDE': 0x5C0,
        },
        'sites': {'POLL': 0x80117708, 'SAMPLE': 0x80117880, 'PROBE': 0x800D62DC,
                  'BUTTONS': 0x8011520C, 'MOTION': 0x80117DF0, 'MOTION2': 0x80117F6C},
        'site_words': {'MOTION': 0x3718FFFF, 'MOTION2': 0x3739FFFF},
        'asm_defs': {'M1_DEST': 25, 'M1_LEFT': 24, 'M2_DEST': 27, 'M2_LEFT': 25},
        'clock': None,
    },
    # Today and Tomorrow Channel (Japan): an Aug 2007 KPAD, the same code as June 2007
    'tt_jp': {
        'title': 'Today and Tomorrow Channel (Japan, HAVJ)',
        'dol_size': 4247616,
        'arena_lo': 0x8056D6E0, 'stack_end': 0x8056B6C8, 'lis': 0x8057,
        'arena': [0x800E8848, 0x800E88F0, 0x800E8898, 0x800E8924],
        'defs': {
            'SI_TYPES': 0x803F9AF0,
            'SI_BUSY': 0x803F9AD8,
            'SI_SHADOW': 0x803F9ADC,
            'FN_SIGETTYPE': 0x8012ADDC,
            'FN_OSDISABLE': 0x800EECEC,
            'FN_OSRESTORE': 0x800EED14,
            'WPAD_TBL': 0x8043F650,
        },
        'sites': {'POLL': 0x80182228, 'SAMPLE': 0x80182340, 'PROBE': 0x80141E98,
                  'BUTTONS': 0x801827F0, 'MOTION': 0x80182924},
        # shows the pointer only while it moves: give the stick pointer a vec/speed
        'pointer_vec': True,
        'clock': None,
    },
    # Today and Tomorrow Channel (PAL): a June 2009 KPAD, the Nintendo Channel's
    # with an 8-byte bigger block and a smaller KPADiRead frame
    'tt_pal': {
        'title': 'Today and Tomorrow Channel (PAL, HAVP)',
        'dol_size': 3384512,
        'sdk': 2009,
        'arena_lo': 0x8057A4E0, 'stack_end': 0x805784C8, 'lis': 0x8058,
        'arena': [0x800EDCBC, 0x800EDD64, 0x800EDD0C, 0x800EDD98],
        'defs': {
            'SI_TYPES': 0x80326CB8,
            'SI_BUSY': 0x80326CA0,
            'SI_SHADOW': 0x80326CA4,
            'FN_SIGETTYPE': 0x80130990,
            'FN_OSDISABLE': 0x800F4470,
            'FN_OSRESTORE': 0x800F44B0,
            'WPAD_TBL': 0x8044CC30,
            'KPAD_BASE': 0x80487138,
            'KPAD_STRIDE': 0x578,
        },
        'sites': {'POLL': 0x80189AD0, 'SAMPLE': 0x80189C3C, 'PROBE': 0x80147E70,
                  'BUTTONS': 0x80187454, 'MOTION': 0x80189FE4, 'MOTION2': 0x8018A154},
        'site_words': {'POLL': 0x9421FF10},
        'asm_defs': {'POLL_FRAME': 240},
        'pointer_vec': True,
        'clock': None,
    },
    # Wii no Ma / Wii Room (all languages): an Aug 2010 KPAD.  Same flow as 2009,
    # but MotionPlus-sized samples (0x42 bytes) move the ring, the KPADStatus
    # output is 0xF0 bytes, and the registers are all different.
    'wiinoma': {
        'title': 'Wii no Ma / Wii Room (HCIJ)',
        'dol_size': 8929568,
        'sdk': 2009,
        'arena_lo': 0x809A2C20, 'stack_end': 0x809A0C20, 'lis': 0x809A,
        # the OS writes the 0x800 bytes below __ArenaLo: keep the original gap free
        'arena_guard': 0x2000,
        'text_slot': True,
        # OSInit keeps the arena start in r29 (lis/addi split by other code),
        # and builds the debugger stack end twice
        'arena': [(0x802D0538, 0x802D0540), 0x802D06A4, 0x802D072C],
        'defs': {
            'SI_TYPES': 0x80832238,
            'SI_BUSY': 0x80832220,
            'SI_SHADOW': 0x80832224,
            'FN_SIGETTYPE': 0x802E22B0,
            'FN_OSDISABLE': 0x802D6E10,
            'FN_OSRESTORE': 0x802D6E50,
            'WPAD_TBL': 0x808B88B0,
            'KPAD_BASE': 0x808BEA68,
            'KPAD_STRIDE': 0x688,
        },
        'sites': {'POLL': 0x803303E0, 'SAMPLE': 0x80330584, 'PROBE': 0x80319900,
                  'BUTTONS': 0x8032D3B4, 'MOTION': 0x803308CC, 'MOTION2': 0x80330A8C},
        'site_words': {'POLL': 0x9421FDC0,        # stwu r1,-576(r1)
                       'SAMPLE': 0x8815017B,      # lbz r0,0x17B(r21)
                       'BUTTONS': 0x70C09FFF,     # andi. r0,r6,0x9FFF (r9 is live)
                       'MOTION': 0x3673FFFF,      # addic. r19,r19,-1
                       'MOTION2': 0x36D6FFFF},    # addic. r22,r22,-1
        'asm_defs': {'POLL_FRAME': 576, 'K_BLK': 21, 'BTN_TMP': 0, 'M_TOTAL': 29,
                     'M1_DEST': 18, 'M1_LEFT': 19, 'M2_DEST': 19, 'M2_LEFT': 22,
                     'K_IDX': 0x17A, 'K_CNT': 0x17B, 'K_FRESH': 0, 'K_RING': 0x180,
                     'K_EXTP': 0x5A0, 'K_EXTN': 0x5A4, 'K_SLOT': 0x42, 'S_FMT': 0x40,
                     'WPAD_TYPE': 2309, 'WPAD_STATUS': 2304},
        'pointer': {'LIM_X_WIDE': 1.0, 'LIM_X_43': 1.0},
        'pointer_vec': True,
        'clock': None,
    },
}
HOOK_SIZE = 0x1800              # default: code + state, carved from the arena start
STATE_SIZE = 0x200             # gc.c 0x00-0x40, motion.c 0x40-0x100, kbd.c 0x100-0x200

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
    for name, word in ch.get('site_words', {}).items():
        s[name] = (word, s[name][1])
    if 'kbd' in ch:
        s['KBD'] = (0x81830000, 'hook_kbd')       # lwz r12,0(r3)
    if 'cdbsd' in ch:
        s['CDBSD'] = (0x39400001, 'hook_cdbsd')   # li r10,1
    return s


def site_addr(ch, name):
    if name == 'KBD':
        return ch['kbd']['site']
    if name == 'CDBSD':
        return ch['cdbsd']['site']
    return ch['sites'][name]


def layout(ch):
    """BASE/END/STATE and the arena patches (lis address, addi address, old los, new hi, new lo).
    Each arena entry is an addi address (its lis right before it) or a (lis, addi)
    pair; the addi builds either __ArenaLo or the debugger stack end, and both
    move up to END (the lis too if END needs a different high half).
    'arena_guard' leaves that many bytes free between the hooks and END: the
    2010 OS uses the space right below __ArenaLo as scratch (the original
    layout has an unused gap there)."""
    base = ch['arena_lo']
    top = base + ch.get('hook_size', HOOK_SIZE)        # code + state end here
    end = top + ch.get('arena_guard', 0)
    assert end % 32 == 0
    def lo(v):
        d = v - (ch['lis'] << 16)
        assert -0x8000 <= d < 0x8000, hex(v)
        return d & 0xFFFF
    hi = ((end + 0x8000) >> 16) & 0xFFFF
    arena = []
    for a in ch['arena']:
        lis_a, addi_a = a if isinstance(a, tuple) else (a - 4, a)
        arena.append((lis_a, addi_a, (lo(base), lo(ch['stack_end'])), hi, end & 0xFFFF))
    return base, end, top - STATE_SIZE, arena


def dol_sizes(ch):
    return ch['dol_size'] if isinstance(ch['dol_size'], list) else [ch['dol_size']]


def detect(data):
    for key, ch in CHANNELS.items():
        if len(data) in dol_sizes(ch):
            return key, ch
    raise SystemExit('unknown main DOL (%d bytes); supported: %s' % (
        len(data), ', '.join('%s (%s)' % (c['title'], '/'.join(map(str, dol_sizes(c)))) for c in CHANNELS.values())))


def lz_decompress(d):
    """Nintendo LZ77 (type 0x10 / 0x11), as WiiLink stores most main DOLs."""
    t, n, p = d[0], d[1] | d[2] << 8 | d[3] << 16, 4
    if n == 0:
        n, p = struct.unpack('<I', d[4:8])[0], 8
    o = bytearray()
    while len(o) < n:
        f = d[p]
        p += 1
        for b in range(8):
            if len(o) >= n:
                break
            if not f & (0x80 >> b):
                o.append(d[p])
                p += 1
                continue
            a = d[p]
            if t == 0x10:
                ln, disp, p = (a >> 4) + 3, ((a & 15) << 8 | d[p + 1]) + 1, p + 2
            elif a >> 4 == 0:
                ln, disp, p = ((a & 15) << 4 | d[p + 1] >> 4) + 0x11, ((d[p + 1] & 15) << 8 | d[p + 2]) + 1, p + 3
            elif a >> 4 == 1:
                ln = ((a & 15) << 12 | d[p + 1] << 4 | d[p + 2] >> 4) + 0x111
                disp, p = ((d[p + 2] & 15) << 8 | d[p + 3]) + 1, p + 4
            else:
                ln, disp, p = (a >> 4) + 1, ((a & 15) << 8 | d[p + 1]) + 1, p + 2
            for _ in range(ln):
                o.append(o[-disp])
    return bytes(o)


def main_dol(data):
    """content 1 as a DOL: WiiLink LZ-compresses most (the NAND boot program
    takes either), so unpack those"""
    if data[0] in (0x10, 0x11) and data[:4] != b'\0\0\1\0':
        return lz_decompress(data)
    return data


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
    if 'cdbsd' in ch:
        defs.update(ch['cdbsd']['defs'])
    D = ['-D%s=0x%08Xu' % kv for kv in defs.items()]
    if ch.get('sdk', 2007) == 2009:
        D.append('-DSDK2009')
    D += ['-D%s=%d' % kv for kv in ch.get('asm_defs', {}).items()]
    # pointer range (KPAD pos at the screen edges), where it isn't the Forecast Channel's
    D += ['-D%s=%.4ff' % kv for kv in ch.get('pointer', {}).items()]
    if 'kbd' in ch:
        D.append('-DKBD')
    if 'cdbsd' in ch:
        D.append('-DCDBSD')
    if debug_feed:
        D.append('-DDEBUG_FEED')
    if 'repeat' in ch:
        D.append('-DREPEAT_MASK=0x%04Xu' % ch['repeat'])
    if 'sympatches' in ch:
        D.append('-DTILT')
    if ch.get('pointer_vec'):
        D.append('-DPOINTER_VEC')
    D += os.environ.get('HOOK_CFLAGS', '').split()     # test builds
    objs = [tmp + '/hooks.o', tmp + '/gc.o', tmp + '/motion.o']
    run([CC + 'gcc'] + CFLAGS + ['-msoft-float'] + D + ['-c', src + '/gc.c', '-o', tmp + '/gc.o'])
    run([CC + 'gcc'] + CFLAGS + ['-mhard-float'] + D + ['-c', src + '/motion.c', '-o', tmp + '/motion.o'])
    if 'kbd' in ch:
        run([CC + 'gcc'] + CFLAGS + ['-msoft-float'] + D + ['-c', src + '/kbd.c', '-o', tmp + '/kbd.o'])
        objs.append(tmp + '/kbd.o')
    if 'cdbsd' in ch:
        run([CC + 'gcc'] + CFLAGS + ['-msoft-float'] + D + ['-c', src + '/cdbsd.c', '-o', tmp + '/cdbsd.o'])
        objs.append(tmp + '/cdbsd.o')
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

    def add_text(self, addr, payload, text_slot=False):
        for i, o, a, s in self.sections():
            if s and a < addr + len(payload) and addr < a + s:
                raise SystemExit('section %d (0x%08X-0x%08X) overlaps the hook section' % (i, a, a + s))
        if text_slot:
            return self.insert_text(addr, payload)
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

    def insert_text(self, addr, payload):
        """Put the section in the first free text slot after the used ones.  The
        boot program loads text sections as code (data sections are only
        copied), so this is for channels where code in a data section doesn't
        run.  The bytes go in the stream between that slot's neighbours."""
        used = [i for i in range(7) if self.field(0x90, i)]
        slot = max(used) + 1
        if slot > 6:
            raise SystemExit('no free text section slot')
        live = sorted((self.field(0, i), self.field(0x90, i), i) for i in range(18) if self.field(0x90, i))
        off = 0x100
        for o, sz, i in live:
            if o != off:
                raise SystemExit('DOL sections are not packed back to back (0x%X != 0x%X)' % (o, off))
            off += sz
        if [i for _, _, i in live] != sorted(i for _, _, i in live):
            raise SystemExit('DOL sections are not in slot order')
        at = 0x100 + sum(sz for _, sz, i in live if i < slot)
        for _, _, i in live:
            if i > slot:
                self.set(0, i, self.field(0, i) + len(payload))
        self.d = self.d[:at] + payload + self.d[at:]
        self.set(0, slot, at)
        self.set(0x48, slot, addr)
        self.set(0x90, slot, len(payload))
        return slot


def patch_dol(data, clock=False, debug_feed=False, debug_menu=False):
    key, ch = detect(data)
    if debug_menu and not ch.get('debug_patches'):
        raise SystemExit('--debug-menu is only for the Check Mii Out Channel')
    print('main DOL:', ch['title'])
    base, end, state, arena = layout(ch)
    dol = Dol(data)
    if clock:
        if not ch['clock']:
            raise SystemExit('--clock is only for the Forecast and News Channels')
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
    for lis_a, addr, old_los, new_hi, new_lo in arena:
        cur = dol.word(addr)
        if cur & 0xFFFF not in old_los or cur >> 26 != 14:
            raise SystemExit('arena site 0x%08X: found 0x%08X' % (addr, cur))
        lis = dol.word(lis_a)               # lis rA,hi that addi rD,rA,lo pairs with
        if lis >> 26 != 15 or (lis >> 16) & 31 or (lis >> 21) & 31 != (cur >> 16) & 31 or lis & 0xFFFF != ch['lis']:
            raise SystemExit('arena site 0x%08X: no matching lis at 0x%08X (0x%08X)' % (addr, lis_a, lis))
        dol.put(lis_a, (lis & 0xFFFF0000) | new_hi)
        dol.put(addr, (cur & 0xFFFF0000) | new_lo)
    for addr, old, new, what in ch.get('patches', []) + (ch['debug_patches'] if debug_menu else []):
        for j, (o, n) in enumerate(zip(old, new)):
            cur = dol.word(addr + 4 * j)
            if cur != o:
                raise SystemExit('patch 0x%08X: found 0x%08X, want 0x%08X' % (addr + 4 * j, cur, o))
            dol.put(addr + 4 * j, n)
        print('  patched 0x%08X: %s' % (addr, what))
    for lis_a, addi_a, sym in ch.get('sympatches', []):
        lis, addi, v = dol.word(lis_a), dol.word(addi_a), syms[sym]
        if lis >> 26 != 15 or addi >> 26 != 14 or (addi >> 16) & 31 != (lis >> 21) & 31:
            raise SystemExit('sympatch 0x%08X/0x%08X: not a lis/addi pair' % (lis_a, addi_a))
        dol.put(lis_a, (lis & 0xFFFF0000) | ((v + 0x8000) >> 16 & 0xFFFF))
        dol.put(addi_a, (addi & 0xFFFF0000) | (v & 0xFFFF))
        print('  patched 0x%08X/0x%08X: -> %s 0x%08X' % (lis_a, addi_a, sym, v))
    payload = blob + b'\0' * (state + STATE_SIZE - base - len(blob))   # code, then zeroed state
    slot = dol.add_text(base, payload, ch.get('text_slot', False))
    only = os.environ.get('HOOKS')            # debugging: HOOKS=POLL,SAMPLE plants only those
    for name, (orig, stub) in sites(ch).items():
        if only is not None and name not in only.split(','):
            continue
        site = site_addr(ch, name)
        dol.put(site, b_to(site, syms[stub]))
        print('  %-8s 0x%08X -> %-13s 0x%08X' % (name, site, stub, syms[stub]))
    print('hook section: DOL slot %d, 0x%08X-0x%08X (%d bytes code, state at 0x%08X); arena now starts at 0x%08X' % (
        slot, base, base + len(payload), len(blob), state, end))
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
    dbg = '--debug-menu' in sys.argv
    if len(a) != 3 or a[0] not in ('dol', 'wad'):
        raise SystemExit(__doc__)
    mode, src, dst = a
    if mode == 'dol':
        if accu:
            raise SystemExit('--accuweather needs wad mode (the banner is content 0)')
        patched = patch_dol(main_dol(open(src, 'rb').read()), clock, feed, dbg)
        open(dst, 'wb').write(patched)
        return
    tmp = tempfile.mkdtemp(prefix='fcwad')
    run([SHARPII, 'WAD', '-u', src, tmp + '/u'])
    app = tmp + '/u/00000001.app'
    main = main_dol(open(app, 'rb').read())
    if accu and detect(main)[0] != 'forecast':
        raise SystemExit('--accuweather is only for the Forecast Channel')
    patched = patch_dol(main, clock, feed, dbg)
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
