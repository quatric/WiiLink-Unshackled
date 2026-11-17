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

/* Replaces `path` with `data`: written to /tmp first, then put in place with the old file's owner
 * and permissions (a new file gets the title folder's). False when anything failed; the old file is
 * only removed once the new one is complete. */
bool nand_replace(const char *path, const uint8_t *data, uint32_t n);

#endif
