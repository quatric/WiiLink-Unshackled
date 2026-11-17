#include <string.h>

#include "sha1.h"
#include "tmd.h"

static uint32_t rb32(const uint8_t *p) { return (uint32_t)p[0] << 24 | (uint32_t)p[1] << 16 | (uint32_t)p[2] << 8 | p[3]; }
static uint16_t rb16(const uint8_t *p) { return (uint16_t)(p[0] << 8 | p[1]); }

bool tmd_valid(const uint8_t *tmd, uint32_t n)
{
    return n >= TMD_RECS && rb32(tmd) == 0x00010001 && n >= TMD_RECS + (uint32_t)rb16(tmd + TMD_NCONT) * TMD_REC;
}

uint64_t tmd_tid(const uint8_t *tmd) { return (uint64_t)rb32(tmd + TMD_TID) << 32 | rb32(tmd + TMD_TID + 4); }

int tmd_count(const uint8_t *tmd) { return rb16(tmd + TMD_NCONT); }

bool tmd_rec(const uint8_t *tmd, int pos, tmd_rec_t *r)
{
    if (pos < 0 || pos >= tmd_count(tmd))
        return false;
    const uint8_t *p = tmd + TMD_RECS + TMD_REC * pos;
    r->cid = rb32(p);
    r->index = rb16(p + 4);
    r->type = rb16(p + 6);
    r->size = (uint64_t)rb32(p + 8) << 32 | rb32(p + 12);
    memcpy(r->sha1, p + 16, 20);
    r->pos = pos;
    return true;
}

bool tmd_find(const uint8_t *tmd, uint32_t n, uint16_t index, tmd_rec_t *r)
{
    if (!tmd_valid(tmd, n))
        return false;
    for (int i = 0; i < tmd_count(tmd); i++)
        if (tmd_rec(tmd, i, r) && r->index == index)
            return true;
    return false;
}

bool tmd_set_content(uint8_t *tmd, uint32_t n, uint16_t index, uint64_t size, const uint8_t sha1[20])
{
    tmd_rec_t r;
    if (!tmd_find(tmd, n, index, &r))
        return false;
    uint8_t *p = tmd + TMD_RECS + TMD_REC * r.pos;
    for (int i = 0; i < 8; i++)
        p[8 + i] = (uint8_t)(size >> (56 - 8 * i));
    memcpy(p + 16, sha1, 20);
    memset(tmd + 4, 0, 0x100);
    for (uint32_t v = 0; v < 0x10000; v++) {
        uint8_t h[20];
        sha1_t c;
        tmd[0x1E2] = (uint8_t)(v >> 8), tmd[0x1E3] = (uint8_t)v;
        sha1_init(&c);
        sha1_update(&c, tmd + 0x140, TMD_RECS + (uint32_t)tmd_count(tmd) * TMD_REC - 0x140);
        sha1_final(&c, h);
        if (!h[0])
            return true;
    }
    return false;
}
