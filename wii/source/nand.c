#include <gccore.h>
#include <malloc.h>
#include <stdio.h>
#include <string.h>

#include "nand.h"

#define CHUNK 0x20000

static bool up;
static char why[96];

const char *nand_why(void) { return why; }

#define WHY(...) snprintf(why, sizeof(why), __VA_ARGS__)

bool nand_init(void)
{
    if (!up)
        up = ISFS_Initialize() >= 0;
    return up;
}

void nand_exit(void)
{
    if (up)
        ISFS_Deinitialize();
    up = false;
}

uint8_t *nand_read(const char *path, uint32_t *n)
{
    static fstats st ATTRIBUTE_ALIGN(32);
    s32 fd = ISFS_Open(path, ISFS_OPEN_READ);
    if (fd < 0)
        return NULL;
    if (ISFS_GetFileStats(fd, &st) < 0) {
        ISFS_Close(fd);
        return NULL;
    }
    uint32_t size = st.file_length;
    uint8_t *b = memalign(32, size ? (size + 31) & ~31u : 32);
    uint32_t done = 0;
    while (b && done < size) {
        uint32_t c = size - done > CHUNK ? CHUNK : size - done;
        if (ISFS_Read(fd, b + done, c) != (s32)c) {
            free(b);
            b = NULL;
        } else {
            done += c;
        }
    }
    ISFS_Close(fd);
    if (b)
        *n = size;
    return b;
}

bool nand_exists(const char *path)
{
    s32 fd = ISFS_Open(path, ISFS_OPEN_READ);
    if (fd < 0)
        return false;
    ISFS_Close(fd);
    return true;
}

static bool write_new(const char *path, const uint8_t *data, uint32_t n, u8 attr, u8 op, u8 gp, u8 xp)
{
    ISFS_Delete(path);
    s32 r = ISFS_CreateFile(path, attr, op, gp, xp);
    if (r < 0) {
        WHY("creating %s: error %d", path, (int)r);
        return false;
    }
    s32 fd = ISFS_Open(path, ISFS_OPEN_WRITE);
    if (fd < 0) {
        WHY("opening %s: error %d", path, (int)fd);
        ISFS_Delete(path);
        return false;
    }
    uint8_t *bounce = memalign(32, CHUNK);
    bool ok = bounce != NULL;
    for (uint32_t done = 0; ok && done < n;) {
        uint32_t c = n - done > CHUNK ? CHUNK : n - done;
        memcpy(bounce, data + done, c);
        s32 w = ISFS_Write(fd, bounce, c);
        ok = w == (s32)c;
        if (!ok)
            WHY("writing %s: error %d", path, (int)w);
        done += c;
    }
    free(bounce);
    if (ok && ISFS_Close(fd) < 0) {
        WHY("closing %s", path);
        ok = false;
    } else if (!ok) {
        ISFS_Close(fd);
    }
    if (!ok)
        ISFS_Delete(path);
    return ok;
}

/* true when `path` holds exactly `data` */
static bool same_as(const char *path, const uint8_t *data, uint32_t n)
{
    uint32_t back_n = 0;
    uint8_t *back = nand_read(path, &back_n);
    bool same = back && back_n == n && !memcmp(back, data, n);
    free(back);
    return same;
}

int nand_replace(const char *path, const uint8_t *data, uint32_t n)
{
    /* NAND file names are 12 characters at most (IOS refuses longer ones; Dolphin doesn't) */
    static const char tmp[] ATTRIBUTE_ALIGN(32) = "/tmp/wlu.tmp";
    u32 owner = 0;
    u16 group = 0;
    u8 attr = 0, op = 3, gp = 3, xp = 1;
    bool exists = ISFS_GetAttr(path, &owner, &group, &attr, &op, &gp, &xp) >= 0;
    if (!exists) {                      /* a new file: the folder's owner */
        char dir[128];
        snprintf(dir, sizeof(dir), "%s", path);
        char *slash = strrchr(dir, '/');
        if (!slash)
            return NAND_UNTOUCHED;
        *slash = 0;
        if (ISFS_GetAttr(dir, &owner, &group, &attr, &op, &gp, &xp) < 0)
            return NAND_UNTOUCHED;
        attr = 0, op = 3, gp = 3, xp = 1;
    }
    why[0] = 0;
    if (!write_new(tmp, data, n, attr, op, gp, xp) || !same_as(tmp, data, n)) {
        if (!why[0])
            WHY("%s reads back wrong", tmp);
        ISFS_Delete(tmp);
        return NAND_UNTOUCHED;
    }
    s32 r;
    if (exists && (r = ISFS_Delete(path)) < 0) {
        WHY("removing %s: error %d (NAND permissions not patched?)", path, (int)r);
        ISFS_Delete(tmp);
        return NAND_UNTOUCHED;
    }
    bool ok;
    if (ISFS_Rename(tmp, path) >= 0) {
        ok = same_as(path, data, n);
        if (!ok)
            WHY("%s reads back wrong", path);
    } else {                            /* rename refused: write it in place instead */
        ok = write_new(path, data, n, attr, op, gp, xp) && same_as(path, data, n);
        if (!ok && !why[0])
            WHY("%s reads back wrong", path);
        ISFS_Delete(tmp);
    }
    if (ok)
        ISFS_SetAttr(path, owner, group, attr, op, gp, xp);
    return ok ? NAND_OK : NAND_DAMAGED;
}
