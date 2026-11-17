#include <gccore.h>
#include <malloc.h>
#include <stdio.h>
#include <string.h>

#include "nand.h"

#define CHUNK 0x20000

static bool up;

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
    if (ISFS_CreateFile(path, attr, op, gp, xp) < 0)
        return false;
    s32 fd = ISFS_Open(path, ISFS_OPEN_WRITE);
    if (fd < 0)
        return false;
    uint8_t *bounce = memalign(32, CHUNK);
    bool ok = bounce != NULL;
    for (uint32_t done = 0; ok && done < n;) {
        uint32_t c = n - done > CHUNK ? CHUNK : n - done;
        memcpy(bounce, data + done, c);
        ok = ISFS_Write(fd, bounce, c) == (s32)c;
        done += c;
    }
    free(bounce);
    ISFS_Close(fd);
    if (!ok)
        ISFS_Delete(path);
    return ok;
}

bool nand_replace(const char *path, const uint8_t *data, uint32_t n)
{
    static char tmp[64] ATTRIBUTE_ALIGN(32);
    u32 owner = 0;
    u16 group = 0;
    u8 attr = 0, op = 3, gp = 3, xp = 1;
    char dir[128];
    snprintf(dir, sizeof(dir), "%s", path);
    char *slash = strrchr(dir, '/');
    if (!slash)
        return false;
    if (ISFS_GetAttr(path, &owner, &group, &attr, &op, &gp, &xp) < 0) {
        *slash = 0;                     /* a new file: the folder's owner */
        if (ISFS_GetAttr(dir, &owner, &group, &attr, &op, &gp, &xp) < 0)
            return false;
        attr = 0, op = 3, gp = 3, xp = 1;
    }
    snprintf(tmp, sizeof(tmp), "/tmp/wlu-%s", strrchr(path, '/') + 1);
    if (!write_new(tmp, data, n, attr, op, gp, xp))
        return false;
    /* check what was written */
    uint32_t back_n = 0;
    uint8_t *back = nand_read(tmp, &back_n);
    bool same = back && back_n == n && !memcmp(back, data, n);
    free(back);
    if (!same) {
        ISFS_Delete(tmp);
        return false;
    }
    ISFS_SetAttr(tmp, owner, group, attr, op, gp, xp);
    ISFS_Delete(path);
    if (ISFS_Rename(tmp, path) < 0) {
        /* rename refused: write it in place instead */
        bool ok = write_new(path, data, n, attr, op, gp, xp);
        ISFS_Delete(tmp);
        if (ok)
            ISFS_SetAttr(path, owner, group, attr, op, gp, xp);
        return ok;
    }
    return true;
}
