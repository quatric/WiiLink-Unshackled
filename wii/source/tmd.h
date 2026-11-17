#ifndef TMD_H
#define TMD_H

#include <stdbool.h>
#include <stdint.h>

/* A TMD with an RSA-2048 signature (every channel's): its fields start at 0x140. */
#define TMD_TID 0x18C
#define TMD_NCONT 0x1DE
#define TMD_RECS 0x1E4
#define TMD_REC 0x24

typedef struct {
    uint32_t cid;
    uint16_t index, type;
    uint64_t size;
    uint8_t sha1[20];
    int pos;                            /* record number */
} tmd_rec_t;

bool tmd_valid(const uint8_t *tmd, uint32_t n);
uint64_t tmd_tid(const uint8_t *tmd);
int tmd_count(const uint8_t *tmd);
bool tmd_rec(const uint8_t *tmd, int pos, tmd_rec_t *r);
/* The record of content `index` (not its position). */
bool tmd_find(const uint8_t *tmd, uint32_t n, uint16_t index, tmd_rec_t *r);
/* Sets content `index`'s size and SHA-1, then fakesigns the TMD (signature zeroed, padding chosen so
 * the body's SHA-1 starts with 00: the signing bug). */
bool tmd_set_content(uint8_t *tmd, uint32_t n, uint16_t index, uint64_t size, const uint8_t sha1[20]);

#endif
