#ifndef LZ_H
#define LZ_H

#include <stdint.h>
#include <stddef.h>

/* Nintendo LZ77, type 0x10 (LZ10) and 0x11 (LZ11), as WiiLink stores most channels' main DOL.
 * The channels' NAND boot program loads a DOL either packed or not. */

/* 0x10 / 0x11 when `d` looks LZ-packed (and isn't a DOL), else 0. */
int lz_type(const uint8_t *d, size_t n);

/* Unpacked size from the header, 0 when it isn't one. */
uint32_t lz_size(const uint8_t *d, size_t n);

/* Unpacks into out (lz_size bytes). False when the data runs out or is damaged. */
int lz_decompress(const uint8_t *d, size_t n, uint8_t *out, uint32_t out_n);

/* Packs `in` with the given type into a new buffer (its length, padded to 4 bytes, in *out_n).
 * NULL when out of memory. progress (may be NULL) is called now and then with bytes done. */
uint8_t *lz_compress(int type, const uint8_t *in, uint32_t n, uint32_t *out_n,
                     void (*progress)(void *ctx, uint32_t done, uint32_t total), void *ctx);

#endif
