#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "patchdb.h"

#define MAX_TARGETS 64

static const uint8_t *db;
static uint32_t db_size;
static pdb_target_t targets[MAX_TARGETS];
static int ntargets;

static uint32_t rb32(const uint8_t *p) { return (uint32_t)p[0] << 24 | (uint32_t)p[1] << 16 | (uint32_t)p[2] << 8 | p[3]; }

static void str(char *dst, const uint8_t *src, int n)
{
    memcpy(dst, src, (size_t)n);
    dst[n] = 0;
}

bool pdb_init(const uint8_t *data, uint32_t size)
{
    db = data, db_size = size, ntargets = 0;
    if (size < 0x20 || memcmp(data, "WLUP", 4) || rb32(data + 4) != 1 || rb32(data + 20) != size)
        return false;
    uint32_t n = rb32(data + 8), to = rb32(data + 12), pool = rb32(data + 16);
    if (n > MAX_TARGETS || to + 0x100 * n > size || pool > size)
        return false;
    for (uint32_t i = 0; i < n; i++) {
        const uint8_t *e = data + to + 0x100 * i;
        pdb_target_t *t = &targets[i];
        memset(t, 0, sizeof(*t));
        str(t->name, e, 48);
        t->tid = (uint64_t)rb32(e + 0x30) << 32 | rb32(e + 0x34);
        t->app_size = rb32(e + 0x38);
        memcpy(t->app_sha1, e + 0x3C, 20);
        t->dol_size = rb32(e + 0x50);
        memcpy(t->dol_sha1, e + 0x54, 20);
        t->lz = (int)rb32(e + 0x68);
        t->hdr_off = rb32(e + 0x6C) + pool;
        t->at = rb32(e + 0x70);
        t->cut = rb32(e + 0x74);
        t->pay_off = rb32(e + 0x78) + pool;
        t->pay_len = rb32(e + 0x7C);
        uint32_t nf = rb32(e + 0x80), fo = rb32(e + 0x84);
        t->flags = rb32(e + 0xA4);
        if (nf > PDB_MAX_FEAT || fo + 0x40 * nf > size || t->hdr_off + 0x100 > size || t->pay_off + t->pay_len > size ||
            t->at < 0x100 || t->at > t->cut || t->cut > t->dol_size)
            return false;
        t->nfeat = (int)nf;
        for (uint32_t j = 0; j < nf; j++) {
            const uint8_t *f = data + fo + 0x40 * j;
            pdb_feat_t *ft = &t->feat[j];
            str(ft->id, f, 12);
            str(ft->name, f + 12, 40);
            ft->flags = rb32(f + 0x34);
            ft->n = rb32(f + 0x38);
            ft->off = rb32(f + 0x3C) + (rb32(f + 0x38) ? pool : 0);
            if (ft->off + 12 * ft->n > size)
                return false;
        }
    }
    ntargets = (int)n;
    return true;
}

int pdb_count(void) { return ntargets; }

const pdb_target_t *pdb_get(int i) { return i >= 0 && i < ntargets ? &targets[i] : NULL; }

const pdb_target_t *pdb_find(const uint8_t sha1[20])
{
    for (int i = 0; i < ntargets; i++)
        if (!memcmp(targets[i].app_sha1, sha1, 20))
            return &targets[i];
    return NULL;
}

static int pad_index(const pdb_target_t *t)
{
    for (int i = 0; i < t->nfeat; i++)
        if (t->feat[i].flags & FEAT_PAD)
            return i;
    return -1;
}

uint32_t pdb_effective(const pdb_target_t *t, uint32_t mask)
{
    int p = pad_index(t);
    bool pad = p >= 0 && (mask >> p & 1);
    uint32_t m = 0;
    for (int i = 0; i < t->nfeat; i++)
        if ((mask >> i & 1) && (pad || !(t->feat[i].flags & FEAT_NEEDS_PAD)))
            m |= 1u << i;
    return m;
}

uint32_t pdb_default_mask(const pdb_target_t *t)
{
    uint32_t m = 0;
    for (int i = 0; i < t->nfeat; i++)
        if (t->feat[i].flags & FEAT_DEFAULT)
            m |= 1u << i;
    return m;
}

uint8_t *pdb_apply(const pdb_target_t *t, const uint8_t *dol, uint32_t mask, uint32_t *out_n, char *err, int errsz)
{
    mask = pdb_effective(t, mask);
    int p = pad_index(t);
    bool pad = p >= 0 && (mask >> p & 1);
    uint32_t n = pad ? t->cut + t->pay_len : t->dol_size;
    uint8_t *w = malloc(t->dol_size), *out = NULL;
    if (!w) {
        snprintf(err, (size_t)errsz, "Out of memory");
        return NULL;
    }
    memcpy(w, dol, t->dol_size);
    for (int i = 0; i < t->nfeat; i++) {
        if (!(mask >> i & 1))
            continue;
        const pdb_feat_t *f = &t->feat[i];
        for (uint32_t k = 0; k < f->n; k++) {
            const uint8_t *e = db + f->off + 12 * k;
            uint32_t off = rb32(e), old = rb32(e + 4), nw = rb32(e + 8);
            if (off < 0x100 || off + 4 > t->dol_size || rb32(dol + off) != old) {
                snprintf(err, (size_t)errsz, "%s: the word at 0x%X isn't the expected one", f->name, off);
                free(w);
                return NULL;
            }
            w[off] = (uint8_t)(nw >> 24), w[off + 1] = (uint8_t)(nw >> 16), w[off + 2] = (uint8_t)(nw >> 8);
            w[off + 3] = (uint8_t)nw;
        }
    }
    if (!pad) {
        *out_n = n;
        return w;
    }
    /* the new header, the sections up to `at`, the hook section, then the rest up to `cut` */
    out = malloc(n);
    if (!out) {
        free(w);
        snprintf(err, (size_t)errsz, "Out of memory");
        return NULL;
    }
    memcpy(out, db + t->hdr_off, 0x100);
    memcpy(out + 0x100, w + 0x100, t->at - 0x100);
    memcpy(out + t->at, db + t->pay_off, t->pay_len);
    memcpy(out + t->at + t->pay_len, w + t->at, t->cut - t->at);
    free(w);
    *out_n = n;
    return out;
}
