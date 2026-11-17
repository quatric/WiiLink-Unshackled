#ifndef PATCHDB_H
#define PATCHDB_H

#include <stdbool.h>
#include <stdint.h>

/* The patches (data/patches.bin, written by `build.py export`): for each WiiLink build of a channel
 * it knows, the clean content 1 (size and SHA-1, as in the TMD) and its features. */

#define PDB_MAX_FEAT 12

enum {
    FEAT_DEFAULT = 1,                   /* on unless the user turns it off */
    FEAT_NEEDS_PAD = 2,                 /* uses the hook section (needs the 'pad' feature) */
    FEAT_PAD = 4,                       /* the controller hooks and the hook section */
};

enum { TGT_NAND_ONLY = 1 };             /* misbehaves when run from the SD card */

typedef struct {
    char id[13];
    char name[41];
    uint32_t flags, n, off;             /* n words at off: {file offset, old word, new word} */
} pdb_feat_t;

typedef struct {
    char name[49];
    uint64_t tid;                       /* of the WAD it was made from (others can carry the same content) */
    uint32_t app_size;
    uint8_t app_sha1[20];               /* content 1 as installed (packed or not) */
    uint32_t dol_size;
    uint8_t dol_sha1[20];               /* content 1 unpacked */
    int lz;                             /* 0x10 / 0x11 when WiiLink packed content 1 */
    uint32_t hdr_off, at, cut, pay_off, pay_len;
    int nfeat;
    pdb_feat_t feat[PDB_MAX_FEAT];
    uint32_t flags;
} pdb_target_t;

/* Checks and indexes the database. False when it is damaged. */
bool pdb_init(const uint8_t *data, uint32_t size);
int pdb_count(void);
const pdb_target_t *pdb_get(int i);

/* The target whose clean content 1 has this SHA-1, or NULL. */
const pdb_target_t *pdb_find(const uint8_t sha1[20]);

/* Patched DOL from the clean one (dol_size bytes, checked by the caller) with the features whose
 * bit is set in `mask` (bit i = feat[i]). New buffer, its size in *out_n; NULL with err when a
 * word isn't what the database expects or out of memory. */
uint8_t *pdb_apply(const pdb_target_t *t, const uint8_t *dol, uint32_t mask, uint32_t *out_n, char *err,
                   int errsz);

/* The features a mask really gets: those needing the hook section are dropped without it. */
uint32_t pdb_effective(const pdb_target_t *t, uint32_t mask);

/* The default mask. */
uint32_t pdb_default_mask(const pdb_target_t *t);

#endif
