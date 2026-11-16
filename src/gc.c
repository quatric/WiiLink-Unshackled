/* GameCube controller (port 1) -> Classic Controller bridge for the Forecast Channel.
 *
 * The channel links the SI library but not PAD, so nothing polls the pads.
 * gc_poll() drives the Serial Interface's own auto-polling (the approach from
 * Barrel Blast Patch / ACCF-Patch gcpad), gc_sample() turns the pad's state into
 * Classic Controller samples in KPAD's ring, and gc_probe() makes WPADProbe
 * report a Classic Controller on channel 0 while a pad is plugged in.  From
 * there, the Classic Controller hooks (hooks.S, motion.c) map everything onto
 * the Wii Remote.
 *
 * Built soft-float: these hooks never touch FPRs.
 * Addresses come in as -D macros (see build.py).
 */
typedef unsigned int u32;
typedef signed int s32;
typedef unsigned short u16;
typedef signed short s16;
typedef unsigned char u8;

#define R32(a) (*(volatile u32 *)(a))
#define SI_OUT0   (0xCD006400u)
#define SI_IN0H   (0xCD006404u)
#define SI_IN0L   (0xCD006408u)
#define SI_POLL   (0xCD006430u)
#define SI_COMCSR (0xCD006434u)
#define SI_SR     (0xCD006438u)

struct st {
    u32 probe_tb;   /* last SIGetType */
    u32 busy_tb;    /* when si:: was first seen busy (0 = idle) */
    u8 norep;       /* consecutive frames with NOREP on port 1 */
    u8 ours;        /* the last KPAD sample on channel 0 was ours */
    u8 pad[2];
    u32 prev_btn;   /* Classic Controller buttons of the previous frame's sample */
};
#define ST ((volatile struct st *)STATE)

static inline u32 tb(void)
{
    u32 t;
    __asm__ volatile("mftb %0" : "=r"(t));
    return t;
}

/* a valid, error-free pad response on port 1 */
static inline int gc_in(u32 *h, u32 *l)
{
#ifdef DEBUG_FEED
    /* test builds: a debugger writes the pad response to STATE+0x20/0x24 */
    if (R32(STATE + 0x20)) {
        *h = R32(STATE + 0x20);
        *l = R32(STATE + 0x24);
        return 1;
    }
#endif
    u32 v = R32(SI_IN0H);
    if ((v & 0x80000000u) || !(v & 0x00800000u))
        return 0;
    *h = v;
    *l = R32(SI_IN0L);
    return 1;
}

/* ---- KPADiRead entry: keep port 1 polled ---- */
void gc_poll(u32 chan)
{
    volatile u32 *types = (volatile u32 *)SI_TYPES;
    u32 type, sisr, mask, poll;
    int confirmed;
    s32 busy;

    if (chan)
        return;

    /* probe until a standard pad answers, at most every 0.25 s
     * (probing every frame collides with polling on hardware) */
    type = types[0];
    confirmed = !(type & 0x80) && (type & 0x18000000u) == 0x08000000u;
    if (!confirmed) {
        u32 now = tb();
        if (now - ST->probe_tb >= 15187500u) {
            ST->probe_tb = now;
            ((u32 (*)(u32))FN_SIGETTYPE)(0);
        }
    }

    /* an unplugged pad latches NOREP; with no PAD library nothing reads it,
     * so copy a persistent one into si::'s type cache so it re-probes */
    sisr = R32(SI_SR);
    if (sisr & 0x08000000u) {
        if (ST->norep < 10)
            ST->norep++;
        else
            types[0] = 8;
    } else {
        ST->norep = 0;
    }

    R32(SI_OUT0) = 0x00400300u;                      /* poll command */
    R32(SI_SR) = (sisr & 0x0F0F0F0Fu) | 0x80000000u; /* ack errors, latch OUT */

    type = types[0];
    confirmed = !(type & 0x80) && (type & 0x18000000u) == 0x08000000u;
    mask = confirmed ? 0x88u : 0;                    /* EN0 + VBCPY0 */
    poll = R32(SI_POLL) & ~0xFFu;
    if (!(poll & 0xFF00u))
        poll |= 0x0100u;
    R32(SI_POLL) = poll | mask;
    /* si:: rewrites SIPOLL from its shadow on every retrace */
    R32(SI_SHADOW) = (R32(SI_SHADOW) & ~0xFFu) | mask;

    /* a pad unplugged mid-transfer can wedge si::'s busy flag; clear it after ~1 s */
    busy = (s32)R32(SI_BUSY);
    if (busy == -1) {
        ST->busy_tb = 0;
    } else {
        u32 now = tb();
        if (ST->busy_tb == 0) {
            ST->busy_tb = now | 1;
        } else if (now - ST->busy_tb >= 60750000u) {
            u32 lvl = ((u32 (*)(void))FN_OSDISABLE)();
            R32(SI_BUSY) = (u32)-1;
            R32(SI_COMCSR) = 0x80000000u;
            ((void (*)(u32))FN_OSRESTORE)(lvl);
            ST->busy_tb = 0;
        }
    }
}

/* ---- KPADiRead sample-count check: pad -> Classic Controller samples ---- */
#define CL_UP    0x0001
#define CL_LEFT  0x0002
#define CL_X     0x0008
#define CL_A     0x0010
#define CL_Y     0x0020
#define CL_B     0x0040
#define CL_PLUS  0x0400
#define CL_HOME  0x0800
#define CL_MINUS 0x1000
#define CL_DOWN  0x4000
#define CL_RIGHT 0x8000

static inline s16 stick(u32 raw)
{
    s32 v = ((s32)(raw & 0xFF) - 128) * 3;       /* pad ~+-100 -> ~+-300 */
    if (v > 308)
        v = 308;
    if (v < -308)
        v = -308;
    return (s16)v;
}

/* GC -> Classic Controller, so the Classic Controller hooks give:
 *   A->A  B->B  X->1  Y->2  L->Minus  R->Plus  Start->HOME  D-pad->D-pad
 *   control stick -> pointer, C-stick -> twist */
static __attribute__((noinline)) u32 cc_buttons(u32 h, u32 l)
{
    u32 b = 0;

    if (h & 0x01000000u) b |= CL_A;
    if (h & 0x02000000u) b |= CL_B;
    if (h & 0x04000000u) b |= CL_X;
    if (h & 0x08000000u) b |= CL_Y;
    if (h & 0x10000000u) b |= CL_HOME;
    if ((h & 0x00400000u) || ((l >> 8) & 0xFF) >= 0xA0) b |= CL_MINUS;  /* L (click or deep press) */
    if ((h & 0x00200000u) || (l & 0xFF) >= 0xA0)        b |= CL_PLUS;   /* R */
    if (h & 0x00080000u) b |= CL_UP;
    if (h & 0x00040000u) b |= CL_DOWN;
    if (h & 0x00020000u) b |= CL_RIGHT;
    if (h & 0x00010000u) b |= CL_LEFT;
    return b;
}

static __attribute__((noinline)) void fill_cc(u8 *s, u32 h, u32 l, u32 b)
{
    *(u16 *)(s + 0x2A) = (u16)b;
    *(s16 *)(s + 0x2C) = stick(h >> 8);      /* control stick x */
    *(s16 *)(s + 0x2E) = stick(h);           /* control stick y */
    *(s16 *)(s + 0x30) = stick(l >> 24);     /* C-stick x */
    *(s16 *)(s + 0x32) = stick(l >> 16);     /* C-stick y */
    s[0x34] = 0;                             /* analog L / R: unused */
    s[0x35] = 0;
    s[0x28] = 2;                             /* extension: Classic Controller */
    s[0x29] = 0;                             /* no error */
    s[0x36] = 8;                             /* format: classic + accel + pointer */
}

static __attribute__((noinline)) void put_sample(u8 *k, u32 idx, u32 h, u32 l, u32 b)
{
    volatile u32 *p = (volatile u32 *)(k + 0x110 + (idx & 0xF) * 0x38);
    u32 i;

    for (i = 0; i < 0x38 / 4; i++)
        p[i] = 0;
    fill_cc((u8 *)p, h, l, b);
}

void gc_sample(u8 *k, u32 chan)
{
    u32 h, l, b, i, idx, cnt;

    if (chan || !gc_in(&h, &l))
        return;

    b = cc_buttons(h, l);
    idx = k[0x10E] & 0xF;
    cnt = k[0x10F];
    if (cnt == 0) {
        /* nothing queued: no Wii Remote (0xFD), a bare one with nothing yet, or ours */
        u8 dev = k[0x5C];
        if (!(dev == 0 || dev == 0xFD || ST->ours))
            return;
        /* two samples: older with last frame's buttons, newer with this frame's */
        put_sample(k, idx, h, l, ST->prev_btn);
        put_sample(k, idx + 1, h, l, b);
        k[0x10E] = (idx + 2) & 0xF;
        k[0x10F] = 2;
        ST->prev_btn = b;
        ST->ours = 1;
        return;
    }

    /* real samples queued: a bare Wii Remote gets the pad as its extension;
     * a real Nunchuk or Classic Controller is left alone */
    ST->ours = 0;
    ST->prev_btn = b;
    if (cnt > 0x10)
        cnt = 0x10;
    for (i = 0; i < cnt; i++) {
        u8 *s = k + 0x110 + ((idx - cnt + i) & 0xF) * 0x38;
        if (s[0x28] == 0 || s[0x28] == 0xFD)
            fill_cc(s, h, l, b);
    }
}

/* ---- WPADProbe(chan, &type): a Classic Controller on channel 0 while a pad is in ---- */
u32 gc_probe(u32 chan, u32 *type)
{
    u32 h, l;
    u8 *blk;
    u32 t;
    s32 status;

    if (chan || !gc_in(&h, &l))
        return 0;
    blk = *(u8 **)(WPAD_TBL + chan * 4);
    t = blk[2241];
    status = *(s32 *)(blk + 2236);
    if (status != -1 && (t == 1 || t == 2))
        return 0;                       /* a real Nunchuk / Classic Controller wins */
    if (type)
        *type = 2;
    return 1;
}
