#ifndef SDBIN_H
#define SDBIN_H

#include <stdbool.h>
#include <stdint.h>

/* A channel on the SD card: private/wii/title/<ABCD>/content.bin, as the System Menu (or wad2bin)
 * writes it.  The layout is GodModeWii's source/wad2bin.c's (after DarkMatterCore's wad2bin):
 *
 *   A  0x640 bytes, AES-CBC with the SD key: title ID, icon.bin size, IMET header
 *   B  icon.bin, padded to 64, AES-CBC with the SD key
 *   C  "Bk" header (0x80): console ID, TMD size, contents size, a bit per content
 *   D  the TMD, padded to 64
 *   E  every content, padded to 64, AES-CBC with this console's PRNG key, IV = its index
 *   F  ECDSA signature of SHA-1(C..E) by an AP key, the device certificate, the AP certificate
 *
 * Only C..F change when content 1 does: A and B are copied as they are. */

typedef struct {
    uint32_t console_id;
    uint8_t ng_priv[30];
    uint8_t prng_key[16];
    uint8_t device_cert[0x180];
} sd_keys_t;

typedef struct {
    char path[256];
    uint64_t size;
    uint32_t c_off;                     /* Part C */
    uint8_t bk[0x80];
    uint8_t *tmd;
    uint32_t tmd_n;
    uint32_t e_off;                     /* Part E */
} sdbin_t;

/* This console's keys (needs HW_AHBPROT off). */
bool sd_keys_get(sd_keys_t *k, char *why, int wn);

bool sdbin_open(sdbin_t *s, const char *path, char *err, int errsz);
void sdbin_close(sdbin_t *s);
uint32_t sdbin_console(const sdbin_t *s);

/* Content `index`, decrypted, in a new buffer (its TMD size in *n). */
uint8_t *sdbin_content(const sdbin_t *s, const sd_keys_t *k, uint16_t index, uint32_t *n, char *err, int errsz);

/* Writes `out` (a new file): s's content.bin with content `index` replaced by data and the TMD by
 * `tmd`, signed again with this console's keys. */
bool sdbin_rewrite(const sdbin_t *s, const char *out, const sd_keys_t *k, const uint8_t *tmd, uint32_t tmd_n,
                   uint16_t index, const uint8_t *data, uint32_t n, char *err, int errsz);

#endif
