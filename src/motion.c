/* Classic Controller sticks -> Wii Remote pointer and twist, for the Forecast Channel.
 *
 * Runs once per KPAD sample, right after KPADiRead copied it out to the
 * caller's buffer (k); KPAD's internal status is left alone.  The channel reads only the core Wii Remote fields:
 *   +0x20/+0x24 pos (pointer), +0x5E dpd_valid, +0x34/+0x38 horizon (twist).
 * So a Classic Controller (real, or a GameCube pad presented as one) gets:
 *   left stick  -> relative pointer (like a mouse)
 *   right stick -> twisting the Wii Remote (horizon = cos/sin of the angle)
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
    u8 stick[4];            /* 1: the sticks are in control, 0: the Wii Remote's IR */
};
#define MST ((volatile struct mst *)(STATE + 0x40))

#define K_F(k, off) (*(volatile float *)((k) + (off)))

static inline float clampf(float v, float lim)
{
    if (v > lim)
        return lim;
    if (v < -lim)
        return -lim;
    return v;
}

static inline float dead(float v, float dz)
{
    if (v > dz)
        return (v - dz) / (1.0f - dz);
    if (v < -dz)
        return (v + dz) / (1.0f - dz);
    return 0.0f;
}

/* k = this sample in the caller's KPADStatus buffer, chan = channel, first = first sample of this KPADRead */
void cc_motion(u8 *k, u32 chan, u32 first)
{
    float lx, ly, rx, t, t2, sn, cs, px, py;
    int moved;

    if (chan > 3 || k[0x5C] != 2 || (s8)k[0x5D] != 0)
        return;

    lx = dead(clampf(K_F(k, 0x6C), 1.0f), 0.15f);
    ly = dead(clampf(K_F(k, 0x70), 1.0f), 0.15f);
    rx = dead(clampf(K_F(k, 0x74), 1.0f), 0.15f);

    /* whichever moved last is in control: the sticks, or the Wii Remote's IR.
     * ix/iy anchor the IR position while the sticks move (or while IR is in
     * control); the IR takes back over once it drifts well away from there. */
    moved = lx != 0.0f || ly != 0.0f || rx != 0.0f;
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
            MST->px[chan] = clampf(K_F(k, 0x20), 1.0f);
            MST->py[chan] = clampf(K_F(k, 0x24), 1.0f);
            return;
        }
    }

    px = MST->px[chan];
    py = MST->py[chan];
    if (first) {
        /* ~1 s to cross the screen at full tilt; stick up = pointer up (pos y is down-positive) */
        px = clampf(px + lx * 0.033f, 1.0f);
        py = clampf(py - ly * 0.033f, 1.0f);
        MST->px[chan] = px;
        MST->py[chan] = py;
    }
    K_F(k, 0x20) = px;
    K_F(k, 0x24) = py;
    k[0x5E] = 2;                        /* pointer valid */
    if (K_F(k, 0x48) < 0.5f)
        K_F(k, 0x48) = 1.5f;            /* plausible pointer distance (m) */

    /* twist: up to ~60 degrees; horizon = (cos t, sin t) */
    t = rx * -1.0472f;
    t2 = t * t;
    sn = t * (1.0f - t2 * (1.0f / 6.0f - t2 * (1.0f / 120.0f)));
    cs = 1.0f - t2 * (0.5f - t2 * (1.0f / 24.0f));
    K_F(k, 0x34) = cs;
    K_F(k, 0x38) = sn;
}
