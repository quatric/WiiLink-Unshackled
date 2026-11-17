/* Classic Controller sticks -> Wii Remote pointer and twist.
 *
 * Runs once per KPAD sample, right after KPADiRead copied it out to the
 * caller's buffer (k); KPAD's internal status is left alone.  The channels read
 * only the core Wii Remote fields:
 *   +0x20/+0x24 pos (pointer), +0x5E dpd_valid, +0x34/+0x38 horizon (twist).
 * So a Classic Controller (real, or a GameCube pad presented as one) gets:
 *   left stick  -> relative pointer (like a mouse), with acceleration
 *   right stick -> twisting the Wii Remote: the stick's direction is the
 *                  angle (up = level, right = 90 degrees clockwise, down = upside
 *                  down), so circling the stick turns it all the way round
 * The Wii Remote's own IR pointer and twist still work: whichever moved last
 * is in control (a Wii Remote lying still in view of the sensor bar doesn't
 * pin the pointer, and picking it up and pointing takes over again).
 *
 * Built hard-float; the entry stub saves f0-f13.
 */
typedef unsigned int u32;
typedef signed char s8;
typedef unsigned char u8;

struct mst {
    float px[4], py[4];     /* stick pointer position per channel */
    float ix[4], iy[4];     /* last real IR position per channel */
    float accel[4];         /* pointer speed multiplier, grows while the stick is held at full tilt */
    float lim_x, lim_y;     /* pointer range (KPAD pos units) that reaches the screen edges */
    u32 rep_tb[4];          /* when the held buttons repeat next */
    u8 stick[4];            /* 1: the sticks are in control, 0: the Wii Remote's IR */
    u8 inited;
    float vx[4], vy[4];     /* stick pointer movement this read (POINTER_VEC) */
    u8 tick[4];             /* idle wobble phase (POINTER_VEC) */
    u8 rep_act[4];          /* this read: 0 nothing, 1 let go, 2 press again (REPEAT_MASK) */
};
#define MST ((volatile struct mst *)(STATE + 0x40))         /* 0x40-0x100 */

#define K_F(k, off) (*(volatile float *)((k) + (off)))

/* How far the stick pointer may go: the pos where the cursor reaches the
 * screen edges (measured on the Forecast Channel).  The channels don't map
 * pos +-1 to the screen edges: x = +-1 is only two thirds of the way out on a
 * 16:9 TV and four fifths on a 4:3 one (a real Wii Remote's pos runs past 1
 * to get the rest), while y = +-0.75 is already the top/bottom.  Which pair
 * applies comes from the console's aspect ratio setting. */
#ifndef LIM_X_WIDE
#define LIM_X_WIDE 1.5f
#endif
#ifndef LIM_Y_WIDE
#define LIM_Y_WIDE 0.72f
#endif
#ifndef LIM_X_43
#define LIM_X_43 1.25f
#endif
#ifndef LIM_Y_43
#define LIM_Y_43 0.75f
#endif

#define SPEED     0.033f    /* pos units per frame at full tilt, before acceleration */
#define ACCEL_MAX 4.0f      /* after ~2/3 s at full tilt the pointer moves this much faster */
#define ACCEL_UP  0.075f    /* per frame */

static inline float clampf(float v, float lim)
{
    if (v > lim)
        return lim;
    if (v < -lim)
        return -lim;
    return v;
}

static inline float absf(float v)
{
    return v < 0.0f ? -v : v;
}

static inline float dead(float v, float dz)
{
    if (v > dz)
        return (v - dz) / (1.0f - dz);
    if (v < -dz)
        return (v + dz) / (1.0f - dz);
    return 0.0f;
}

/* 1/sqrt(x) for x > 0: frsqrte + two Newton steps */
static inline float rsqrt(float x)
{
    float y;
    __asm__("frsqrte %0,%1" : "=f"(y) : "f"(x));
    y = y * (1.5f - 0.5f * x * y * y);
    y = y * (1.5f - 0.5f * x * y * y);
    return y;
}

/* The console's aspect ratio (SYSCONF "IPL.AR": 0 = 4:3, 1 = 16:9), from the
 * copy of SYSCONF the SDK's SC library keeps in MEM1 (a 32-byte aligned
 * buffer starting "SCv0", u16 count, u16 offsets[], then items: a byte
 * type << 5 | (name length - 1), the name, the value).  -1 if not found. */
static int aspect_wide(void)
{
    static const char ar[] = "IPL.AR";
    u32 a;

    for (a = 0x80004000u; a < 0x81800000u; a += 32) {
        u32 n, i;
        if (*(volatile u32 *)a != 0x53437630u)          /* "SCv0" */
            continue;
        n = *(volatile unsigned short *)(a + 4);
        if (n == 0 || n > 0x400)
            continue;
        for (i = 0; i < n; i++) {
            u32 o = *(volatile unsigned short *)(a + 6 + 2 * i), j;
            volatile u8 *it = (volatile u8 *)(a + o);
            if (o < 6 || o >= 0x4000)
                break;
            if ((it[0] & 31) != 5)                      /* name length 6 */
                continue;
            for (j = 0; j < 6 && it[1 + j] == (u8)ar[j]; j++)
                ;
            if (j == 6)
                return it[7] != 0;
        }
    }
    return -1;
}

#ifdef REPEAT_MASK
/* Hold-to-repeat for the buttons in REPEAT_MASK (any controller): while one is
 * held, it is let go for one read and pressed again, 0.4 s after the press and
 * then every 0.15 s, so the channel sees repeated presses whether it reads
 * KPAD's trig bits or finds new presses in the held buttons itself (the
 * Forecast Channel does).  Decided on a read's first sample, done to all of
 * its samples.  KPADStatus: hold +0x00, trig +0x04. */
#define TB_HZ 60750000u
static void repeat(u8 *k, u32 chan, u32 first)
{
    volatile u32 *hold = (volatile u32 *)k, *trig = (volatile u32 *)(k + 4);
    u32 h = *hold & REPEAT_MASK;
    u32 now;

    if (first) {
        __asm__ volatile("mftb %0" : "=r"(now));
        if (!h)
            MST->rep_act[chan] = 0;
        else if (*trig & REPEAT_MASK) {
            MST->rep_act[chan] = 0;
            MST->rep_tb[chan] = now + TB_HZ / 5 * 2;
        } else if (MST->rep_act[chan] == 1) {
            MST->rep_act[chan] = 2;
            MST->rep_tb[chan] = now + TB_HZ / 20 * 3;
        } else if ((int)(now - MST->rep_tb[chan]) >= 0) {
            MST->rep_act[chan] = 1;
        } else {
            MST->rep_act[chan] = 0;
        }
    }
    if (MST->rep_act[chan] == 1) {
        *hold &= ~h;
        *trig &= ~h;
    } else if (MST->rep_act[chan] == 2) {
        *trig |= h;
    }
}
#endif

/* k = this sample in the caller's KPADStatus buffer, chan = channel, first = first sample of this KPADRead */
void cc_motion(u8 *k, u32 chan, u32 first)
{
    float lx, ly, rx, ry, r2, px, py, mag, step;
    int moved;

    if (chan > 3)
        return;
#ifdef REPEAT_MASK
    repeat(k, chan, first);
#endif
    if (k[0x5C] != 2 || (s8)k[0x5D] != 0)
        return;
    if (!MST->inited) {
        int wide = aspect_wide();
        MST->inited = 1;
        MST->lim_x = wide == 0 ? LIM_X_43 : LIM_X_WIDE;
        MST->lim_y = wide == 0 ? LIM_Y_43 : LIM_Y_WIDE;
    }

    lx = dead(clampf(K_F(k, 0x6C), 1.0f), 0.15f);
    ly = dead(clampf(K_F(k, 0x70), 1.0f), 0.15f);
    rx = clampf(K_F(k, 0x74), 1.0f);
    ry = clampf(K_F(k, 0x78), 1.0f);
    r2 = rx * rx + ry * ry;
    if (r2 < 0.35f * 0.35f)
        r2 = 0.0f;

    /* whichever moved last is in control: the sticks, or the Wii Remote's IR.
     * ix/iy anchor the IR position while the sticks move (or while IR is in
     * control); the IR takes back over once it drifts well away from there. */
    moved = lx != 0.0f || ly != 0.0f || r2 != 0.0f;
    if (moved)
        MST->stick[chan] = 1;
    if ((s8)k[0x5E] > 0) {
        float dx = K_F(k, 0x20) - MST->ix[chan], dy = K_F(k, 0x24) - MST->iy[chan];
        if (moved || !MST->stick[chan]) {
            MST->ix[chan] = K_F(k, 0x20);
            MST->iy[chan] = K_F(k, 0x24);
        } else if (dx * dx + dy * dy > 0.1f * 0.1f) {
            MST->stick[chan] = 0;
        }
        if (!MST->stick[chan]) {
            /* the stick pointer carries on from where the IR pointer is */
            MST->px[chan] = clampf(K_F(k, 0x20), MST->lim_x);
            MST->py[chan] = clampf(K_F(k, 0x24), MST->lim_y);
            MST->accel[chan] = 1.0f;
            return;
        }
    }

    px = MST->px[chan];
    py = MST->py[chan];
    if (first) {
        /* full tilt speeds up the longer it is held: fine aiming near the
         * middle of the stick, fast flings (globe spins) at the rim */
        mag = absf(lx) > absf(ly) ? absf(lx) : absf(ly);
        if (mag > 0.9f) {
            MST->accel[chan] += ACCEL_UP;
            if (MST->accel[chan] > ACCEL_MAX)
                MST->accel[chan] = ACCEL_MAX;
        } else {
            MST->accel[chan] = 1.0f;
        }
        step = SPEED * MST->accel[chan] * (0.4f + 0.6f * mag);
        /* stick up = pointer up (pos y is down-positive) */
        px = clampf(px + lx * step, MST->lim_x);
        py = clampf(py - ly * step, MST->lim_y);
#ifdef POINTER_VEC
        MST->vx[chan] = px - MST->px[chan];
        MST->vy[chan] = py - MST->py[chan];
#endif
        MST->px[chan] = px;
        MST->py[chan] = py;
    }
    K_F(k, 0x20) = px;
    K_F(k, 0x24) = py;
#ifdef POINTER_VEC
    /* vec / speed: KPAD works them out from the IR, so they'd say "not moving".
     * Today and Tomorrow hides a pointer that stops dead (a real one never
     * does: KPAD's smoothing keeps it creeping), so a still stick pointer
     * wobbles by an invisible 0.0005 each read. */
    {
        float vx = MST->vx[chan], vy = MST->vy[chan], v2;
        if (first && vx == 0.0f && vy == 0.0f)
            MST->tick[chan] ^= 1;
        if (vx == 0.0f && vy == 0.0f) {
            vx = MST->tick[chan] ? 0.0005f : -0.0005f;
            K_F(k, 0x20) = px + (MST->tick[chan] ? 0.0005f : 0.0f);
        }
        v2 = vx * vx + vy * vy;
        K_F(k, 0x28) = vx;
        K_F(k, 0x2C) = vy;
        K_F(k, 0x30) = v2 * rsqrt(v2);
    }
#endif
    k[0x5E] = 2;                        /* pointer valid */
    if (K_F(k, 0x48) < 0.5f)
        K_F(k, 0x48) = 1.5f;            /* plausible pointer distance (m) */

    /* twist: horizon = (cos t, sin t) with t the right stick's angle from
     * straight up, clockwise -> (ry, -rx) / |r|; centred = level */
    if (r2 != 0.0f) {
        float s = rsqrt(r2);
        K_F(k, 0x34) = ry * s;
        K_F(k, 0x38) = -rx * s;
    } else {
        K_F(k, 0x34) = 1.0f;
        K_F(k, 0x38) = 0.0f;
    }
}

#ifdef SDK2009
/* 2009 SDK: the copy-out loop has no channel register, so derive it from the
 * KPAD block pointer (KPAD_BASE + chan * KPAD_STRIDE) */
void cc_motion_k(u8 *k, u32 kblock, u32 first)
{
    cc_motion(k, (kblock - KPAD_BASE) / KPAD_STRIDE, first);
}
#endif
