/* WiiLink Unshackled: patches WiiLink's channels where they are installed (the NAND, or the SD card
 * as content.bin), with the features the user picks, and puts the clean copy back on request.
 * Every patch is made from WiiLink's own build of the channel, checked by its SHA-1, and that clean
 * copy is backed up to the SD card first. */
#include <fat.h>
#include <gccore.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wiiuse/wpad.h>

#include "nand.h"
#include "patchdb.h"
#include "patches_bin.h"
#include "runtimeiospatch.h"
#include "sdbin.h"
#include "title.h"

#define VERSION "1.0"
#define MAX_TITLES 48

static void *xfb;
static GXRModeObj *rmode;
static volatile bool quit_now, power_off;

enum { K_UP = 1, K_DOWN = 2, K_A = 4, K_B = 8, K_HOME = 16, K_LEFT = 32, K_RIGHT = 64 };

static void power_cb(void) { quit_now = power_off = true; }
static void reset_cb(u32 irq, void *ctx) { (void)irq, (void)ctx, quit_now = true; }

static void video_init(void)
{
    VIDEO_Init();
    rmode = VIDEO_GetPreferredMode(NULL);
    xfb = MEM_K0_TO_K1(SYS_AllocateFramebuffer(rmode));
    console_init(xfb, 20, 20, rmode->fbWidth, rmode->xfbHeight, rmode->fbWidth * VI_DISPLAY_PIX_SZ);
    VIDEO_Configure(rmode);
    VIDEO_SetNextFramebuffer(xfb);
    VIDEO_SetBlack(false);
    VIDEO_Flush();
    VIDEO_WaitVSync();
    if (rmode->viTVMode & VI_NON_INTERLACE)
        VIDEO_WaitVSync();
}

static int read_keys(void)
{
    WPAD_ScanPads();
    PAD_ScanPads();
    u32 w = 0;
    for (int i = 0; i < 4; i++)
        w |= WPAD_ButtonsDown(i);
    u16 g = PAD_ButtonsDown(0);
    int k = 0;
    if (w & (WPAD_BUTTON_UP | WPAD_CLASSIC_BUTTON_UP) || g & PAD_BUTTON_UP)
        k |= K_UP;
    if (w & (WPAD_BUTTON_DOWN | WPAD_CLASSIC_BUTTON_DOWN) || g & PAD_BUTTON_DOWN)
        k |= K_DOWN;
    if (w & (WPAD_BUTTON_LEFT | WPAD_CLASSIC_BUTTON_LEFT) || g & PAD_BUTTON_LEFT)
        k |= K_LEFT;
    if (w & (WPAD_BUTTON_RIGHT | WPAD_CLASSIC_BUTTON_RIGHT) || g & PAD_BUTTON_RIGHT)
        k |= K_RIGHT;
    if (w & (WPAD_BUTTON_A | WPAD_CLASSIC_BUTTON_A) || g & PAD_BUTTON_A)
        k |= K_A;
    if (w & (WPAD_BUTTON_B | WPAD_CLASSIC_BUTTON_B) || g & PAD_BUTTON_B)
        k |= K_B;
    if (w & (WPAD_BUTTON_HOME | WPAD_CLASSIC_BUTTON_HOME) || g & PAD_BUTTON_START)
        k |= K_HOME;
    return k;
}

static int wait_key(void)
{
    for (;;) {
        VIDEO_WaitVSync();
        if (quit_now)
            return K_HOME;
        int k = read_keys();
        if (k)
            return k;
    }
}

static void cls(void) { printf("\x1b[2J\x1b[1;0H"); }

static void header(void)
{
    cls();
    printf("\x1b[36mWiiLink Unshackled " VERSION "\x1b[37m - controller support and more for WiiLink's channels\n");
    printf("--------------------------------------------------------------------------\n");
}

static void say(const char *fmt, ...)
{
    va_list ap;
    va_start(ap, fmt);
    vprintf(fmt, ap);
    va_end(ap);
    printf("\n");
    VIDEO_WaitVSync();
}

static void pct(void *ctx, uint32_t done, uint32_t total)
{
    (void)ctx;
    printf("\r  %3u%%", total ? (unsigned)((uint64_t)done * 100 / total) : 100);
    if (done >= total)
        printf("\n");
}

static bool confirm(const char *q)
{
    printf("\n%s\n\x1b[33mA: yes   B: no\x1b[37m\n", q);
    for (;;) {
        int k = wait_key();
        if (k & K_A)
            return true;
        if (k & (K_B | K_HOME))
            return false;
    }
}

static void pause_msg(void)
{
    printf("\nPress A to go on.\n");
    while (!(wait_key() & (K_A | K_B | K_HOME)))
        ;
}

static void fail_exit(const char *msg)
{
    printf("\n\x1b[31m%s\x1b[37m\n\nPress any button to go back.\n", msg);
    wait_key();
    exit(0);
}

static const char *where(const title_t *t) { return t->on_sd ? "SD  " : "NAND"; }

/* ---------------------------------------------------------------- one channel */

static void channel_menu(title_t *tt, const sd_keys_t *keys)
{
    const pdb_target_t *t = tt->t;
    uint32_t mask = tt->mask;
    int sel = 0;
    for (;;) {
        uint32_t eff = pdb_effective(t, mask);
        int nrows = t->nfeat + 3;
        header();
        printf("%s\n", t->name);
        printf("Title %08X-%08X on the %s, %s\n\n", (unsigned)(tt->tid >> 32), (unsigned)tt->tid,
               tt->on_sd ? "SD card" : "NAND",
               tt->state == ST_CLEAN ? "\x1b[32mclean (as WiiLink made it)\x1b[37m" : "\x1b[33mpatched\x1b[37m");
        for (int i = 0; i < t->nfeat; i++) {
            const pdb_feat_t *f = &t->feat[i];
            bool on = mask >> i & 1, live = eff >> i & 1;
            printf("%s [%c] %s%s%s\x1b[37m\n", sel == i ? "\x1b[33m>" : " ", on ? 'x' : ' ',
                   on && !live ? "\x1b[35m" : "", f->name, on && !live ? " (needs the controller patch)" : "");
        }
        printf("\n%s Patch with these\n", sel == t->nfeat ? "\x1b[33m>" : " ");
        printf("\x1b[37m%s %s\n", sel == t->nfeat + 1 ? "\x1b[33m>" : " ",
               tt->state == ST_PATCHED ? "Restore the clean copy" : "(Restore the clean copy: it is clean)");
        printf("\x1b[37m%s Back\x1b[37m\n", sel == t->nfeat + 2 ? "\x1b[33m>" : " ");
        printf("\n\x1b[36mUp/Down: choose  A: tick / do it  B: back\x1b[37m\n");
        int k = wait_key();
        if (k & K_HOME || k & K_B)
            return;
        if (k & K_UP)
            sel = (sel + nrows - 1) % nrows;
        if (k & K_DOWN)
            sel = (sel + 1) % nrows;
        if (!(k & K_A))
            continue;
        if (sel < t->nfeat) {
            mask ^= 1u << sel;
            continue;
        }
        if (sel == t->nfeat + 2)
            return;
        char err[160];
        bool ok;
        if (sel == t->nfeat) {
            char q[300];
            snprintf(q, sizeof(q), "Patch %s with the ticked features?%s", t->name,
                     tt->state == ST_CLEAN ? "\nThe clean copy is backed up to " BACKUP_ROOT " first." :
                                             "\nIt is patched again from the backed-up clean copy.");
            if (!confirm(q))
                continue;
            printf("\n");
            ok = title_patch(tt, eff, keys, say, pct, err, sizeof(err));
        } else {
            if (tt->state != ST_PATCHED || !confirm("Put the clean copy back?"))
                continue;
            printf("\n");
            ok = title_restore(tt, keys, say, err, sizeof(err));
            mask = tt->mask;
        }
        if (ok)
            printf("\x1b[32mDone.\x1b[37m\n");
        else
            printf("\x1b[31m%s\x1b[37m\n", err);
        pause_msg();
    }
}

/* ---------------------------------------------------------------- start */

int main(void)
{
    video_init();
    WPAD_Init();
    PAD_Init();
    SYS_SetPowerCallback(power_cb);
    SYS_SetResetCallback(reset_cb);
    header();

    if (!pdb_init(patches_bin, patches_bin_size))
        fail_exit("The built-in patch list is damaged.");
    if (!AHBPROT_DISABLED)
        fail_exit("Start WiiLink Unshackled from the Homebrew Channel:\nit needs full access to the NAND (HW_AHBPROT).");
    if (IosPatch_ISFS(false) <= 0)
        say("\x1b[33mNote: couldn't patch NAND permissions; writing may fail.\x1b[37m");
    if (!nand_init())
        fail_exit("Can't open the NAND.");
    if (!fatInitDefault())
        fail_exit("No SD card: it is needed for the backups.");

    sd_keys_t keys;
    char why[160];
    bool have_keys = sd_keys_get(&keys, why, sizeof(why));

    static title_t titles[MAX_TITLES];
    say("Looking for WiiLink's channels...");
    int n = titles_scan(titles, MAX_TITLES, have_keys ? &keys : NULL);
    int sel = 0;
    while (!quit_now) {
        header();
        if (!n) {
            printf("None of the channels this version knows were found.\n\n"
                   "It patches WiiLink's builds of: Forecast, News, Everybody Votes, Check Mii Out,\n"
                   "Nintendo, Food / Demae, Digicam Print / Photo Prints, Today and Tomorrow,\n"
                   "Wii no Ma / Wii Room, and the Photo Channel 1.1. Install them from WiiLink's\n"
                   "WADs first.\n\nPress HOME / START to exit.\n");
            if (wait_key() & K_HOME)
                break;
            continue;
        }
        printf("Channels found (%d). Pick one:\n\n", n);
        for (int i = 0; i < n; i++)
            printf("%s %-46.46s %s  %s\x1b[37m\n", i == sel ? "\x1b[33m>" : " ", titles[i].t->name, where(&titles[i]),
                   titles[i].state == ST_CLEAN ? "clean" : "patched");
        printf("\nBackups: " BACKUP_ROOT "\n");
        if (!have_keys)
            printf("\x1b[33mChannels on the SD card aren't listed: %s\x1b[37m\n", why);
        printf("\n\x1b[36mUp/Down: choose  A: open  HOME / START: exit\x1b[37m\n");
        int k = wait_key();
        if (k & K_HOME)
            break;
        if (k & K_UP)
            sel = (sel + n - 1) % n;
        if (k & K_DOWN)
            sel = (sel + 1) % n;
        if (k & K_A)
            channel_menu(&titles[sel], have_keys ? &keys : NULL);
    }
    memset(&keys, 0, sizeof(keys));
    header();
    printf("Exiting...\n");
    nand_exit();
    fatUnmount("sd:/");
    WPAD_Shutdown();
    if (power_off)
        SYS_ResetSystem(SYS_POWEROFF, 0, 0);
    return 0;
}
