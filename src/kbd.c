/* USB keyboard for the channel's software keyboard (Everybody Votes Channel).
 *
 * The channel's text input library (an early build of the SDK's
 * SoftwareKeyboard) has no hardware keyboard support.  Once per frame while the
 * on-screen keyboard is up, kbd_frame() (hooks.S: hook_kbd) reads IOS's USB
 * keyboard device, /dev/usb/kbd, and turns key presses into the same commands
 * the on-screen keys send to the input form:
 *
 *   letters, digits, symbols, space  -> type the character (US layout)
 *   Backspace -> delete   Left / Right -> move the cursor
 *   Enter -> OK           Esc -> Quit
 *
 * /dev/usb/kbd answers ioctl 0 with a 16-byte message once something happens:
 *   u32 type (0 attach, 1 detach, 2 event), u32 id, u8 modifiers, u8 -, u8 keys[6]
 * (HID boot-protocol usage codes).  IOS holds the request until then, so it is
 * issued async and the callback only flags completion.
 *
 * Built soft-float.  Addresses and vtable slots come in as -D macros (build.py).
 */
typedef unsigned int u32;
typedef signed int s32;
typedef unsigned short u16;
typedef unsigned char u8;

#define SENTINEL 0xFFFFFFFFu
#define TB_HZ    60750000u                  /* timebase ticks per second */

struct kst {
    s32 fd;                 /* /dev/usb/kbd handle; < 0 = not open */
    u32 open_tb;            /* last open attempt */
    u32 last_tb;            /* last kbd_frame call */
    u32 rep_tb;             /* when the held key repeats next */
    volatile u32 done;      /* ioctl completed (set by the callback) */
    u8 busy;                /* ioctl outstanding */
    u8 mods;                /* modifier byte of the last event */
    u8 caps;                /* Caps Lock on */
    u8 rep_key;             /* key being auto-repeated (0 = none) */
    u8 held[6];             /* keys down in the last event */
    u8 tries;               /* failed opens */
    u8 inited;
};
#define KS ((struct kst *)(STATE + 0x100))
#define KBUF ((volatile u32 *)(STATE + 0x140))     /* 32-byte aligned IPC buffer */
#ifdef DEBUG_FEED
#define KFEED ((volatile u32 *)(STATE + 0x160))    /* test builds: a debugger writes messages here */
#endif

typedef s32 (*ios_cb)(s32 result, void *arg);
#define IOS_Open(path, mode) ((s32 (*)(const char *, u32))FN_IOS_OPEN)(path, mode)
#define IOS_IoctlAsync(fd, cmd, in, inl, out, outl, cb, arg) \
    ((s32 (*)(s32, u32, void *, u32, void *, u32, ios_cb, void *))FN_IOS_IOCTLASYNC)(fd, cmd, in, inl, out, outl, cb, arg)

static const char kbd_path[] __attribute__((aligned(32))) = "/dev/usb/kbd";

/* HID usage 0x04-0x38 -> US layout, unshifted / shifted ('\0' = not a character) */
static const char us_lo[] = "abcdefghijklmnopqrstuvwxyz1234567890\0\0\0\0 -=[]\\\0;'`,./";
static const char us_hi[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZ!@#$%^&*()\0\0\0\0 _+{}|\0:\"~<>?";
/* keypad 0x54-0x63 */
static const char kp[] = "/*-+\0" "1234567890.";

#define K_ENTER  0x28
#define K_ESC    0x29
#define K_BKSP   0x2A
#define K_CAPS   0x39
#define K_RIGHT  0x4F
#define K_LEFT   0x50
#define K_KPENT  0x58

static inline u32 tb(void)
{
    u32 t;
    __asm__ volatile("mftb %0" : "=r"(t));
    return t;
}

static s32 kbd_done(s32 result, void *arg)
{
    (void)result;
    (void)arg;
    KS->done = 1;
    return 0;
}

static inline void invalidate(volatile void *p)
{
    __asm__ volatile("dcbi 0,%0; sync" : : "r"(p) : "memory");
}

/* virtual call: obj->vtable[slot](obj, a, b) */
typedef u32 (*vfn)(void *, u32, void *);
static inline u32 vcall(void *obj, u32 slot, u32 a, void *b)
{
    vfn f = (vfn)(*(u32 **)obj)[slot];
    return f(obj, a, b);
}

static void command(void *form, u32 cmd, u32 ch)
{
    u32 data[3];                    /* INPUT_CHAR: { u16 char; u32 modifiers; ... } */
    data[0] = ch << 16;
    data[1] = 0;
    data[2] = 0;
    vcall(form, SLOT_ONCOMMAND, cmd, data);
}

static u32 to_char(u8 k, u8 mods, u8 caps)
{
    int shift = (mods & 0x22) != 0;
    char c = 0;
    if (k >= 0x04 && k <= 0x38) {
        if (k <= 0x1D && caps)          /* letters: Caps Lock flips Shift */
            shift = !shift;
        c = (shift ? us_hi : us_lo)[k - 0x04];
    } else if (k >= 0x54 && k <= 0x63) {
        c = kp[k - 0x54];
    }
    return (u8)c;
}

/* returns 1 if the key auto-repeats */
static int press(void *form, void *st, u8 k)
{
    u8 mods = KS->mods;
    u32 c;

    if (k == K_CAPS) {
        KS->caps ^= 1;
        return 0;
    }
    if (k == K_ENTER || k == K_KPENT || k == K_ESC) {
        void *bar = (void *)vcall(st, SLOT_GETTOOLBAR, 0, 0);
        if (bar)
            vcall(bar, k == K_ESC ? SLOT_CANCEL : SLOT_OK, 0, 0);
        return 0;
    }
    if (k == K_BKSP) {
        command(form, CMD_DELETE, 0);
        return 1;
    }
    if (k == K_LEFT || k == K_RIGHT) {
        command(form, k == K_LEFT ? CMD_LEFT : CMD_RIGHT, 0);
        return 1;
    }
    if (mods & 0xDD)                    /* Ctrl / Alt / GUI held: not typing */
        return 0;
    c = to_char(k, mods, KS->caps);
    if (!c)
        return 0;
    command(form, CMD_CHAR, c);
    return 1;
}

static void handle(void *form, void *st, volatile u32 *msg, u32 now)
{
    u32 type = msg[0];
    u8 keys[6];
    u32 i, j;

    if (type != 2) {                    /* attach / detach */
        for (i = 0; i < 6; i++)
            KS->held[i] = 0;
        KS->rep_key = 0;
        KS->mods = 0;
        return;
    }
    KS->mods = (u8)(msg[2] >> 24);
    for (i = 0; i < 6; i++)
        keys[i] = (u8)(msg[2 + (i + 2) / 4] >> (24 - 8 * ((i + 2) % 4)));
    for (i = 0; i < 6; i++) {
        u8 k = keys[i];
        int old = 0;
        if (k < 4)                      /* none / rollover error */
            continue;
        for (j = 0; j < 6; j++)
            if (KS->held[j] == k)
                old = 1;
        if (!old && press(form, st, k)) {
            KS->rep_key = k;
            KS->rep_tb = now + TB_HZ / 2;
        }
    }
    for (j = 0, i = 0; i < 6; i++) {
        KS->held[i] = keys[i];
        if (keys[i] == KS->rep_key)
            j = 1;
    }
    if (!j)
        KS->rep_key = 0;
}

/* once per frame while the software keyboard is up: form = input form, st = keyboard state */
void kbd_frame(void *form, void *st)
{
    u32 now = tb();

    if (!KS->inited) {
        KS->inited = 1;
        KS->fd = -1;
        KS->open_tb = now - 2 * TB_HZ;
    }
    /* keyboard reopened after a while: forget keys from back then */
    if (now - KS->last_tb > TB_HZ / 2) {
        u32 i;
        for (i = 0; i < 6; i++)
            KS->held[i] = 0;
        KS->rep_key = 0;
        if (KS->done) {
            KS->done = 0;
            KS->busy = 0;
        }
    }
    KS->last_tb = now;

#ifdef DEBUG_FEED
    if (KFEED[0] != SENTINEL && KFEED[0] != 0) {
        handle(form, st, KFEED, now);
        KFEED[0] = SENTINEL;
    }
#endif

    if (KS->fd < 0 && KS->tries < 3 && now - KS->open_tb >= 2 * TB_HZ) {
        KS->open_tb = now;
        KS->fd = IOS_Open(kbd_path, 0);
        if (KS->fd < 0)
            KS->tries++;
    }
    if (KS->fd >= 0) {
        if (KS->busy && KS->done) {
            invalidate(KBUF);
            if (KBUF[0] != SENTINEL)
                handle(form, st, KBUF, now);
            KS->busy = 0;
            KS->done = 0;
        }
        if (!KS->busy) {
            KBUF[0] = SENTINEL;
            KS->busy = 1;
            if (IOS_IoctlAsync(KS->fd, 0, 0, 0, (void *)KBUF, 16, kbd_done, 0) < 0)
                KS->busy = 0;
        }
    }

    if (KS->rep_key && (s32)(now - KS->rep_tb) >= 0) {
        KS->rep_tb = now + TB_HZ / 30;
        press(form, st, KS->rep_key);
    }
}
