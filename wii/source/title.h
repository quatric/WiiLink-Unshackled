#ifndef TITLE_H
#define TITLE_H

#include <stdbool.h>
#include <stdint.h>

#include "patchdb.h"
#include "sdbin.h"

#define BACKUP_ROOT "sd:/wiilink-unshackled/backup"

enum { ST_CLEAN, ST_PATCHED };

typedef struct {
    uint64_t tid;
    bool on_sd;                         /* a content.bin on the SD card, not the NAND */
    char sdpath[128];
    const pdb_target_t *t;
    int state;                          /* ST_CLEAN: WiiLink's content 1 is installed */
    uint32_t mask;                      /* ST_PATCHED: the features it was patched with (from the backup) */
    char backup[128];                   /* its backup folder */
} title_t;

/* Progress and messages while working. */
typedef void (*say_fn)(const char *fmt, ...);
typedef void (*pct_fn)(void *ctx, uint32_t done, uint32_t total);

/* The channels the database knows, on the NAND and (if keys) on the SD card. Returns how many. */
int titles_scan(title_t *out, int max, const sd_keys_t *keys);

/* Patches with `mask` (from the clean copy: the installed one, or the backup once patched).
 * A clean install is backed up first. */
bool title_patch(title_t *tt, uint32_t mask, const sd_keys_t *keys, say_fn say, pct_fn pct, char *err, int errsz);

/* Puts the backed-up clean copy back. */
bool title_restore(title_t *tt, const sd_keys_t *keys, say_fn say, char *err, int errsz);

#endif
