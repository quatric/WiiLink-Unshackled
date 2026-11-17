#ifndef NAND_H
#define NAND_H

#include <stdbool.h>
#include <stdint.h>

/* Whole-file NAND access through ISFS (needs the ISFS permission patch to write titles' files). */

bool nand_init(void);
void nand_exit(void);

/* The file in a new buffer (32-byte aligned; free() it), its size in *n. NULL when missing. */
uint8_t *nand_read(const char *path, uint32_t *n);
bool nand_exists(const char *path);

/* Replaces `path` with `data`: written to /tmp and read back first, then put in place with the old
 * file's owner and permissions (a new file gets the folder's) and read back again. The old file is
 * only removed once the new one is complete in /tmp. */
enum {
    NAND_OK = 0,
    NAND_UNTOUCHED = -1,                /* failed; `path` is as it was */
    NAND_DAMAGED = -2,                  /* failed after the old file was removed */
};
int nand_replace(const char *path, const uint8_t *data, uint32_t n);
/* What the last failed nand_replace ran into. */
const char *nand_why(void);

#endif
