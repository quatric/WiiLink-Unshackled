#include <stdlib.h>
#include <string.h>

#include "lz.h"

int lz_type(const uint8_t *d, size_t n)
{
    if (n < 8 || (d[0] != 0x10 && d[0] != 0x11))
        return 0;
    if (d[0] == 0 && d[1] == 0 && d[2] == 1 && d[3] == 0)
        return 0;
    return d[0];
}

uint32_t lz_size(const uint8_t *d, size_t n)
{
    if (!lz_type(d, n))
        return 0;
    uint32_t s = d[1] | d[2] << 8 | (uint32_t)d[3] << 16;
    if (s == 0)
        s = d[4] | d[5] << 8 | (uint32_t)d[6] << 16 | (uint32_t)d[7] << 24;
    return s;
}

int lz_decompress(const uint8_t *d, size_t n, uint8_t *out, uint32_t out_n)
{
    int t = lz_type(d, n);
    size_t p = 4;
    if (!t)
        return 0;
    if (!(d[1] | d[2] | d[3]))
        p = 8;
    uint32_t o = 0;
    while (o < out_n) {
        if (p >= n)
            return 0;
        uint8_t f = d[p++];
        for (int b = 0; b < 8 && o < out_n; b++, f <<= 1) {
            if (!(f & 0x80)) {
                if (p >= n)
                    return 0;
                out[o++] = d[p++];
                continue;
            }
            if (p + 1 >= n)
                return 0;
            uint32_t a = d[p], len, disp;
            if (t == 0x10) {
                len = (a >> 4) + 3;
                disp = ((a & 15) << 8 | d[p + 1]) + 1;
                p += 2;
            } else if (a >> 4 == 0) {
                if (p + 2 >= n)
                    return 0;
                len = ((a & 15) << 4 | d[p + 1] >> 4) + 0x11;
                disp = ((d[p + 1] & 15) << 8 | d[p + 2]) + 1;
                p += 3;
            } else if (a >> 4 == 1) {
                if (p + 3 >= n)
                    return 0;
                len = ((a & 15) << 12 | d[p + 1] << 4 | d[p + 2] >> 4) + 0x111;
                disp = ((d[p + 2] & 15) << 8 | d[p + 3]) + 1;
                p += 4;
            } else {
                len = (a >> 4) + 1;
                disp = ((a & 15) << 8 | d[p + 1]) + 1;
                p += 2;
            }
            if (disp > o || len > out_n - o)
                return 0;
            for (; len; len--, o++)
                out[o] = out[o - disp];
        }
    }
    return 1;
}

/* ---------------------------------------------------------------- packing */

#define WIN 4096
#define HBITS 15
#define CHAIN 96                        /* candidates tried per position: speed vs size */

static uint32_t hash3(const uint8_t *p) { return ((p[0] << 16 | p[1] << 8 | p[2]) * 2654435761u) >> (32 - HBITS); }

uint8_t *lz_compress(int type, const uint8_t *in, uint32_t n, uint32_t *out_n,
                     void (*progress)(void *ctx, uint32_t done, uint32_t total), void *ctx)
{
    uint32_t maxlen = type == 0x10 ? 18 : 0x10110;
    /* worst case: every byte a literal, a flag byte per 8, a header */
    size_t cap = (size_t)n + n / 8 + 16;
    uint8_t *out = malloc(cap);
    int32_t *head = malloc(sizeof(int32_t) << HBITS);
    int32_t *prev = malloc(sizeof(int32_t) * WIN);
    if (!out || !head || !prev) {
        free(out), free(head), free(prev);
        return NULL;
    }
    memset(head, 0xFF, sizeof(int32_t) << HBITS);
    size_t o = 0;
    out[o++] = (uint8_t)type;
    if (n <= 0xFFFFFF) {
        out[o++] = (uint8_t)n, out[o++] = (uint8_t)(n >> 8), out[o++] = (uint8_t)(n >> 16);
    } else {
        out[o++] = 0, out[o++] = 0, out[o++] = 0;
        out[o++] = (uint8_t)n, out[o++] = (uint8_t)(n >> 8), out[o++] = (uint8_t)(n >> 16), out[o++] = (uint8_t)(n >> 24);
    }
    uint32_t i = 0, next_report = 0;
    size_t flag_at = 0;
    int bit = 8;
    while (i < n) {
        if (bit == 8) {
            flag_at = o;
            out[o++] = 0;
            bit = 0;
        }
        if (progress && i >= next_report) {
            progress(ctx, i, n);
            next_report = i + 0x40000;
        }
        uint32_t best = 0, best_d = 0;
        if (i + 3 <= n) {
            uint32_t lim = n - i < maxlen ? n - i : maxlen;
            int32_t c = head[hash3(in + i)];
            for (int k = 0; k < CHAIN && c >= 0 && i - (uint32_t)c <= WIN; k++) {
                const uint8_t *a = in + c, *b = in + i;
                if (a[best] == b[best]) {
                    uint32_t l = 0;
                    while (l < lim && a[l] == b[l])
                        l++;
                    if (l > best) {
                        best = l, best_d = i - (uint32_t)c;
                        if (l == lim)
                            break;
                    }
                }
                int32_t pc = prev[c % WIN];
                if (pc >= c)
                    break;
                c = pc;
            }
        }
        uint32_t step;
        if (best >= 3) {
            uint32_t d = best_d - 1;
            out[flag_at] |= (uint8_t)(0x80 >> bit);
            if (type == 0x10) {
                out[o++] = (uint8_t)((best - 3) << 4 | d >> 8);
                out[o++] = (uint8_t)d;
            } else if (best <= 16) {
                out[o++] = (uint8_t)((best - 1) << 4 | d >> 8);
                out[o++] = (uint8_t)d;
            } else if (best <= 0x110) {
                uint32_t l = best - 0x11;
                out[o++] = (uint8_t)(l >> 4);
                out[o++] = (uint8_t)((l & 15) << 4 | d >> 8);
                out[o++] = (uint8_t)d;
            } else {
                uint32_t l = best - 0x111;
                out[o++] = (uint8_t)(0x10 | l >> 12);
                out[o++] = (uint8_t)(l >> 4);
                out[o++] = (uint8_t)((l & 15) << 4 | d >> 8);
                out[o++] = (uint8_t)d;
            }
            step = best;
        } else {
            out[o++] = in[i];
            step = 1;
        }
        bit++;
        for (; step; step--, i++) {
            if (i + 3 <= n) {
                uint32_t h = hash3(in + i);
                prev[i % WIN] = head[h];
                head[h] = (int32_t)i;
            }
        }
    }
    while (o % 4)
        out[o++] = 0;
    free(head), free(prev);
    if (progress)
        progress(ctx, n, n);
    *out_n = (uint32_t)o;
    return out;
}
