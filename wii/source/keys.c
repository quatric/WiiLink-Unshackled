/* This console's keys for content.bin, as GodModeWii's wad_console_keys reads them. */
#include <gccore.h>
#include <malloc.h>
#include <stdio.h>
#include <string.h>

#include "otp.h"
#include "runtimeiospatch.h"
#include "sdbin.h"

static uint32_t be32(const u8 *p) { return (uint32_t)p[0] << 24 | (uint32_t)p[1] << 16 | (uint32_t)p[2] << 8 | p[3]; }

bool sd_keys_get(sd_keys_t *k, char *why, int wn)
{
    memset(k, 0, sizeof(*k));
    u8 otp[OTP_SIZE] ATTRIBUTE_ALIGN(32);
    if (!AHBPROT_DISABLED || !otp_read_all(otp)) {
        snprintf(why, (size_t)wn, "Can't read this console's keys (start from the Homebrew Channel)");
        return false;
    }
    const otp_t *o = (const otp_t *)otp;
    k->console_id = be32(o->ng_id);
    memcpy(k->ng_priv, o->ng_priv, sizeof(k->ng_priv));
    memcpy(k->prng_key, o->rng_key, sizeof(k->prng_key));
    memset(otp, 0, sizeof(otp));
    u8 *cert = memalign(32, 0x200);
    bool ok = cert && ES_GetDeviceCert(cert) >= 0;
    if (ok)
        memcpy(k->device_cert, cert, sizeof(k->device_cert));
    free(cert);
    if (!ok) {
        memset(k, 0, sizeof(*k));
        snprintf(why, (size_t)wn, "Can't read this console's device certificate");
    }
    return ok;
}
