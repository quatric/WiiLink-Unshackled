/* content.bin: read a content, write it back with one content replaced.  The AP signature follows
 * GodModeWii's w2b_ap_sign (source/wad2bin.c). */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "aes.h"
#include "ecc233.h"
#include "sdbin.h"
#include "sha1.h"
#include "tmd.h"

#define CHUNK 0x40000

static const uint8_t SD_KEY[16] = { 0xAB, 0x01, 0xB9, 0xD8, 0xE1, 0x62, 0x2B, 0x08,
                                    0xAF, 0xBA, 0xD8, 0x4D, 0xBF, 0xC2, 0xA5, 0x5D };
static const uint8_t SD_IV[16] = { 0x21, 0x67, 0x12, 0xE6, 0xAA, 0x1F, 0x68, 0x9F,
                                   0x95, 0xC5, 0xA2, 0x23, 0x24, 0xDC, 0x6A, 0x98 };

static uint32_t rb32(const uint8_t *p) { return (uint32_t)p[0] << 24 | (uint32_t)p[1] << 16 | (uint32_t)p[2] << 8 | p[3]; }
static uint16_t rb16(const uint8_t *p) { return (uint16_t)(p[0] << 8 | p[1]); }
static void wb32(uint8_t *p, uint32_t v) { p[0] = (uint8_t)(v >> 24), p[1] = (uint8_t)(v >> 16), p[2] = (uint8_t)(v >> 8), p[3] = (uint8_t)v; }
static uint64_t a64(uint64_t v) { return (v + 63) & ~(uint64_t)63; }

static bool rd_at(FILE *f, uint64_t off, void *buf, uint32_t n)
{
    return fseek(f, (long)off, SEEK_SET) == 0 && fread(buf, 1, n, f) == n;
}

bool sdbin_open(sdbin_t *s, const char *path, char *err, int errsz)
{
    memset(s, 0, sizeof(*s));
    snprintf(s->path, sizeof(s->path), "%s", path);
    FILE *f = fopen(path, "rb");
    if (!f) {
        snprintf(err, (size_t)errsz, "Can't open %s", path);
        return false;
    }
    fseek(f, 0, SEEK_END);
    s->size = (uint64_t)ftell(f);
    uint8_t a[0x640];
    bool ok = rd_at(f, 0, a, sizeof(a));
    if (ok) {
        aes128_t sd;
        aes128_init_dec(&sd, SD_KEY);
        aes128_cbc_decrypt(&sd, SD_IV, a, a, sizeof(a));
        s->c_off = 0x640 + (uint32_t)a64(rb32(a + 8));
        ok = rd_at(f, s->c_off, s->bk, sizeof(s->bk)) && rb16(s->bk + 4) == 0x426B;
    }
    if (ok) {
        s->tmd_n = rb32(s->bk + 0x14);
        s->tmd = s->tmd_n < 0x10000 ? malloc(s->tmd_n) : NULL;
        ok = s->tmd && rd_at(f, s->c_off + 0x80, s->tmd, s->tmd_n) && tmd_valid(s->tmd, s->tmd_n);
        s->e_off = s->c_off + 0x80 + (uint32_t)a64(s->tmd_n);
    }
    fclose(f);
    if (!ok) {
        sdbin_close(s);
        snprintf(err, (size_t)errsz, "%s isn't a channel's content.bin", path);
    }
    return ok;
}

void sdbin_close(sdbin_t *s)
{
    free(s->tmd);
    s->tmd = NULL;
}

uint32_t sdbin_console(const sdbin_t *s) { return rb32(s->bk + 8); }

static bool present(const sdbin_t *s, int pos) { return pos < 0x200 && (s->bk[0x20 + pos / 8] >> (pos & 7) & 1); }

/* where content record `pos` is in Part E */
static uint64_t content_off(const sdbin_t *s, int pos)
{
    uint64_t off = s->e_off;
    tmd_rec_t r;
    for (int i = 0; i < pos; i++)
        if (present(s, i) && tmd_rec(s->tmd, i, &r))
            off += a64(r.size);
    return off;
}

uint8_t *sdbin_content(const sdbin_t *s, const sd_keys_t *k, uint16_t index, uint32_t *n, char *err, int errsz)
{
    tmd_rec_t r;
    if (!tmd_find(s->tmd, s->tmd_n, index, &r) || !present(s, r.pos)) {
        snprintf(err, (size_t)errsz, "content %u isn't in content.bin", index);
        return NULL;
    }
    uint32_t len = (uint32_t)a64(r.size);
    uint8_t *b = malloc(len);
    FILE *f = fopen(s->path, "rb");
    bool ok = b && f && rd_at(f, content_off(s, r.pos), b, len);
    if (f)
        fclose(f);
    if (!ok) {
        free(b);
        snprintf(err, (size_t)errsz, "Can't read content.bin");
        return NULL;
    }
    aes128_t key;
    uint8_t iv[16] = { 0 };
    iv[0] = (uint8_t)(index >> 8), iv[1] = (uint8_t)index;
    aes128_init_dec(&key, k->prng_key);
    aes128_cbc_decrypt(&key, iv, b, b, len);
    memset(&key, 0, sizeof(key));
    uint8_t h[20];
    sha1_t c;
    sha1_init(&c);
    sha1_update(&c, b, (size_t)r.size);
    sha1_final(&c, h);
    if (memcmp(h, r.sha1, 20)) {
        free(b);
        snprintf(err, (size_t)errsz, "content %u doesn't match its TMD (another console's content.bin?)", index);
        return NULL;
    }
    *n = (uint32_t)r.size;
    return b;
}

static bool ap_sign(const sd_keys_t *k, const uint8_t digest[20], uint8_t r[30], uint8_t s[30], uint8_t ap[0x180])
{
    const uint8_t *dev = k->device_cert;
    uint8_t ap_priv[30], seed[20], apdig[20];
    sha1_t c;
    sha1_init(&c);                      /* an AP key of its own, made from the NG key */
    sha1_update(&c, "WiiLink Unshackled AP key", 25);
    sha1_update(&c, k->ng_priv, 30);
    sha1_final(&c, seed);
    memset(ap_priv, 0, sizeof(ap_priv));
    memcpy(ap_priv + 10, seed, 20);
    ap_priv[10] &= 0x7F;
    memset(ap, 0, 0x180);
    wb32(ap, 0x00010002);
    snprintf((char *)ap + 0x80, 0x40, "%.26s-%.10s", (const char *)dev + 0x80, (const char *)dev + 0xC4);
    wb32(ap + 0xC0, 2);
    snprintf((char *)ap + 0xC4, 0x40, "AP%08x%08x", 1u, 2u);
    ecc233_public_key(ap_priv, ap + 0x108);
    sha1_init(&c);
    sha1_update(&c, ap + 0x80, 0x100);
    sha1_final(&c, apdig);
    ecc233_sign(k->ng_priv, apdig, ap + 4, ap + 4 + 30);
    ecc233_sign(ap_priv, digest, r, s);
    memset(ap_priv, 0, sizeof(ap_priv));
    memset(seed, 0, sizeof(seed));
    return ecc233_verify(dev + 0x108, apdig, ap + 4, ap + 34) && ecc233_verify(ap + 0x108, digest, r, s);
}

bool sdbin_rewrite(const sdbin_t *s, const char *out, const sd_keys_t *k, const uint8_t *tmd, uint32_t tmd_n,
                   uint16_t index, const uint8_t *data, uint32_t n, char *err, int errsz)
{
    FILE *in = fopen(s->path, "rb"), *o = fopen(out, "wb");
    uint8_t *buf = malloc(CHUNK), *enc = NULL;
    bool ok = in && o && buf && tmd_valid(tmd, tmd_n) && tmd_count(tmd) == tmd_count(s->tmd);
    if (!ok)
        snprintf(err, (size_t)errsz, "Can't write %s", out);
    /* A and B as they are */
    for (uint32_t done = 0; ok && done < s->c_off;) {
        uint32_t c = s->c_off - done > CHUNK ? CHUNK : s->c_off - done;
        ok = rd_at(in, done, buf, c) && fwrite(buf, 1, c, o) == c;
        done += c;
    }
    sha1_t signed_area;
    sha1_init(&signed_area);
    /* C and D */
    uint64_t total = 0;
    tmd_rec_t r;
    for (int i = 0; i < tmd_count(tmd); i++)
        if (present(s, i) && tmd_rec(tmd, i, &r))
            total += a64(r.size);
    uint8_t bk[0x80];
    memcpy(bk, s->bk, sizeof(bk));
    wb32(bk + 0x14, tmd_n);
    wb32(bk + 0x18, (uint32_t)total);
    wb32(bk + 0x1C, (uint32_t)(0x80 + a64(tmd_n) + total + 0x340));
    uint32_t tpad = (uint32_t)a64(tmd_n);
    uint8_t *tp = calloc(1, tpad);
    ok = ok && tp;
    if (ok) {
        memcpy(tp, tmd, tmd_n);
        sha1_update(&signed_area, bk, sizeof(bk));
        sha1_update(&signed_area, tp, tpad);
        ok = fwrite(bk, 1, sizeof(bk), o) == sizeof(bk) && fwrite(tp, 1, tpad, o) == tpad;
    }
    free(tp);
    /* E */
    for (int i = 0; ok && i < tmd_count(tmd); i++) {
        if (!present(s, i))
            continue;
        tmd_rec_t old;
        tmd_rec(tmd, i, &r);
        tmd_rec(s->tmd, i, &old);
        if (r.index == index) {
            uint32_t len = (uint32_t)a64(n);
            enc = calloc(1, len);
            ok = enc && r.size == n;
            if (ok) {
                aes128_enc_t key;
                uint8_t iv[16] = { 0 };
                iv[0] = (uint8_t)(index >> 8), iv[1] = (uint8_t)index;
                memcpy(enc, data, n);
                aes128_init_enc(&key, k->prng_key);
                aes128_cbc_encrypt(&key, iv, enc, enc, len);
                memset(&key, 0, sizeof(key));
                sha1_update(&signed_area, enc, len);
                ok = fwrite(enc, 1, len, o) == len;
            }
            free(enc);
            enc = NULL;
        } else {
            uint64_t from = content_off(s, i), len = a64(old.size);
            ok = old.size == r.size;
            for (uint64_t done = 0; ok && done < len;) {
                uint32_t c = len - done > CHUNK ? CHUNK : (uint32_t)(len - done);
                ok = rd_at(in, from + done, buf, c) && fwrite(buf, 1, c, o) == c;
                sha1_update(&signed_area, buf, c);
                done += c;
            }
        }
        if (!ok)
            snprintf(err, (size_t)errsz, "Couldn't write content %u (is the SD card full?)", r.index);
    }
    /* F */
    if (ok) {
        uint8_t digest[20], f[0x340] = { 0 };
        sha1_final(&signed_area, digest);
        memcpy(f + 0x40, k->device_cert, 0x180);
        ok = ap_sign(k, digest, f + 2, f + 0x22, f + 0x1C0);
        if (!ok)
            snprintf(err, (size_t)errsz, "The console's key doesn't match its device certificate");
        ok = ok && fwrite(f, 1, sizeof(f), o) == sizeof(f);
    }
    free(buf);
    if (in)
        fclose(in);
    if (o && fclose(o) != 0)
        ok = false;
    if (!ok)
        remove(out);
    return ok;
}
