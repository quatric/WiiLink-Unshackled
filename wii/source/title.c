#include <gccore.h>
#include <dirent.h>
#include <errno.h>
#include <malloc.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>

#include "lz.h"
#include "nand.h"
#include "sha1.h"
#include "title.h"
#include "tmd.h"

#define E(...) (snprintf(err, (size_t)errsz, __VA_ARGS__), false)

static void sha1_of(const void *p, uint32_t n, uint8_t out[20])
{
    sha1_t c;
    sha1_init(&c);
    sha1_update(&c, p, n);
    sha1_final(&c, out);
}

/* ---------------------------------------------------------------- SD card files */

static uint8_t *sd_read(const char *path, uint32_t *n)
{
    FILE *f = fopen(path, "rb");
    if (!f)
        return NULL;
    fseek(f, 0, SEEK_END);
    long size = ftell(f);
    fseek(f, 0, SEEK_SET);
    uint8_t *b = size >= 0 ? memalign(32, (size_t)size + 32) : NULL;
    if (b && fread(b, 1, (size_t)size, f) != (size_t)size) {
        free(b);
        b = NULL;
    }
    fclose(f);
    if (b)
        *n = (uint32_t)size;
    return b;
}

/* written whole and read back */
static bool sd_write(const char *path, const void *p, uint32_t n)
{
    FILE *f = fopen(path, "wb");
    if (!f)
        return false;
    bool ok = fwrite(p, 1, n, f) == n;
    ok = fclose(f) == 0 && ok;
    uint32_t bn = 0;
    uint8_t *back = ok ? sd_read(path, &bn) : NULL;
    ok = back && bn == n && !memcmp(back, p, n);
    free(back);
    if (!ok)
        remove(path);
    return ok;
}

static bool sd_copy(const char *from, const char *to)
{
    FILE *a = fopen(from, "rb"), *b = fopen(to, "wb");
    uint8_t *buf = malloc(0x40000);
    bool ok = a && b && buf;
    while (ok) {
        size_t r = fread(buf, 1, 0x40000, a);
        if (!r)
            break;
        ok = fwrite(buf, 1, r, b) == r;
    }
    ok = ok && !ferror(a);
    free(buf);
    if (a)
        fclose(a);
    if (b && fclose(b) != 0)
        ok = false;
    if (!ok)
        remove(to);
    return ok;
}

static bool mkdirs(const char *dir)
{
    char p[160];
    snprintf(p, sizeof(p), "%s", dir);
    for (char *s = strchr(p + 4, '/'); s; s = strchr(s + 1, '/')) {
        *s = 0;
        mkdir(p, 0777);
        *s = '/';
    }
    return mkdir(p, 0777) == 0 || errno == EEXIST;
}

/* replaces `path` by `tmp` (already written) */
static bool sd_swap(const char *tmp, const char *path)
{
    char old[200];
    snprintf(old, sizeof(old), "%s.old", path);
    remove(old);
    if (rename(path, old) != 0)
        return false;
    if (rename(tmp, path) != 0) {
        rename(old, path);
        return false;
    }
    remove(old);
    return true;
}

/* ---------------------------------------------------------------- the backup folder */

static void backup_dir(title_t *tt)
{
    snprintf(tt->backup, sizeof(tt->backup), BACKUP_ROOT "/%08X%08X%s", (unsigned)(tt->tid >> 32), (unsigned)tt->tid,
             tt->on_sd ? "-sd" : "");
}

static void bpath(const title_t *tt, const char *name, char *out, size_t n)
{
    snprintf(out, n, "%s/%s", tt->backup, name);
}

/* the target the backed-up clean TMD names, and the mask it was patched with */
static const pdb_target_t *backup_target(title_t *tt)
{
    char p[200];
    uint32_t n = 0;
    bpath(tt, "title.tmd", p, sizeof(p));
    uint8_t *tmd = sd_read(p, &n);
    tmd_rec_t r;
    const pdb_target_t *t = tmd && tmd_find(tmd, n, 1, &r) ? pdb_find(r.sha1) : NULL;
    free(tmd);
    tt->mask = t ? pdb_default_mask(t) : 0;
    bpath(tt, "applied.txt", p, sizeof(p));
    FILE *f = fopen(p, "r");
    if (f) {
        unsigned m;
        if (fscanf(f, "%x", &m) == 1)
            tt->mask = m;
        fclose(f);
    }
    return t;
}

static void write_applied(const title_t *tt, uint32_t mask)
{
    char p[200];
    bpath(tt, "applied.txt", p, sizeof(p));
    FILE *f = fopen(p, "w");
    if (!f)
        return;
    fprintf(f, "%08X\n", (unsigned)mask);
    for (int i = 0; i < tt->t->nfeat; i++)
        if (mask >> i & 1)
            fprintf(f, "%s\n", tt->t->feat[i].id);
    fclose(f);
}

/* ---------------------------------------------------------------- finding the channels */

static int scan_nand(title_t *out, int n, int max, uint32_t hi)
{
    static char path[64] ATTRIBUTE_ALIGN(32);
    u32 num = 0;
    snprintf(path, sizeof(path), "/title/%08x", (unsigned)hi);
    if (ISFS_ReadDir(path, NULL, &num) < 0 || !num)
        return n;
    char *names = memalign(32, (num * 13 + 31) & ~31u);
    if (!names || ISFS_ReadDir(path, names, &num) < 0) {
        free(names);
        return n;
    }
    char *nm = names;
    for (u32 i = 0; i < num && n < max; i++, nm += strlen(nm) + 1) {
        title_t *tt = &out[n];
        memset(tt, 0, sizeof(*tt));
        tt->tid = (uint64_t)hi << 32 | strtoul(nm, NULL, 16);
        char p[96];
        snprintf(p, sizeof(p), "/title/%08x/%s/content/title.tmd", (unsigned)hi, nm);
        uint32_t tn = 0;
        uint8_t *tmd = nand_read(p, &tn);
        tmd_rec_t r;
        if (!tmd || !tmd_find(tmd, tn, 1, &r)) {
            free(tmd);
            continue;
        }
        free(tmd);
        snprintf(p, sizeof(p), "/title/%08x/%s/content/%08x.app", (unsigned)hi, nm, (unsigned)r.cid);
        if (!nand_exists(p))            /* contents on the SD card (or not installed) */
            continue;
        backup_dir(tt);
        if ((tt->t = pdb_find(r.sha1))) {
            tt->state = ST_CLEAN;
            tt->mask = pdb_default_mask(tt->t);
            n++;
        } else if ((tt->t = backup_target(tt))) {
            tt->state = ST_PATCHED;
            n++;
        }
    }
    free(names);
    return n;
}

static int scan_sd(title_t *out, int n, int max, const sd_keys_t *keys)
{
    DIR *d = opendir("sd:/private/wii/title");
    if (!d)
        return n;
    struct dirent *e;
    while ((e = readdir(d)) && n < max) {
        if (strlen(e->d_name) != 4)
            continue;
        title_t *tt = &out[n];
        memset(tt, 0, sizeof(*tt));
        snprintf(tt->sdpath, sizeof(tt->sdpath), "sd:/private/wii/title/%s/content.bin", e->d_name);
        sdbin_t s;
        char err[128];
        if (!sdbin_open(&s, tt->sdpath, err, sizeof(err)))
            continue;
        tmd_rec_t r;
        tt->tid = tmd_tid(s.tmd);
        tt->on_sd = true;
        backup_dir(tt);
        bool have = tmd_find(s.tmd, s.tmd_n, 1, &r) && sdbin_console(&s) == keys->console_id;
        sdbin_close(&s);
        if (!have)
            continue;
        if ((tt->t = pdb_find(r.sha1))) {
            tt->state = ST_CLEAN;
            tt->mask = pdb_default_mask(tt->t);
        } else if ((tt->t = backup_target(tt))) {
            tt->state = ST_PATCHED;
        } else {
            continue;
        }
        if (tt->t->flags & TGT_NAND_ONLY)       /* not run from the SD card */
            continue;
        n++;
    }
    closedir(d);
    return n;
}

int titles_scan(title_t *out, int max, const sd_keys_t *keys)
{
    int n = scan_nand(out, 0, max, 0x00010001);
    n = scan_nand(out, n, max, 0x00010002);
    if (keys)
        n = scan_sd(out, n, max, keys);
    return n;
}

/* ---------------------------------------------------------------- patching */

static void nand_paths(const title_t *tt, const tmd_rec_t *r, char *tmdp, char *appp)
{
    snprintf(tmdp, 96, "/title/%08x/%08x/content/title.tmd", (unsigned)(tt->tid >> 32), (unsigned)tt->tid);
    snprintf(appp, 96, "/title/%08x/%08x/content/%08x.app", (unsigned)(tt->tid >> 32), (unsigned)tt->tid,
             (unsigned)r->cid);
}

/* the patched content 1 from the clean one */
static uint8_t *make_content(const pdb_target_t *t, const uint8_t *app, uint32_t mask, uint32_t *n, say_fn say,
                             pct_fn pct, char *err, int errsz)
{
    const uint8_t *dol = app;
    uint8_t *unpacked = NULL, h[20];
    if (t->lz) {
        unpacked = malloc(t->dol_size);
        if (!unpacked || lz_size(app, t->app_size) != t->dol_size || !lz_decompress(app, t->app_size, unpacked, t->dol_size)) {
            free(unpacked);
            snprintf(err, (size_t)errsz, "Couldn't unpack content 1");
            return NULL;
        }
        dol = unpacked;
    }
    sha1_of(dol, t->dol_size, h);
    if (memcmp(h, t->dol_sha1, 20)) {
        free(unpacked);
        snprintf(err, (size_t)errsz, "Content 1 unpacked isn't WiiLink's");
        return NULL;
    }
    uint32_t pn = 0;
    uint8_t *patched = pdb_apply(t, dol, mask, &pn, err, errsz);
    free(unpacked);
    if (!patched)
        return NULL;
    if (!t->lz) {
        *n = pn;
        return patched;
    }
    say("Packing content 1 (LZ%d)...", t->lz == 0x10 ? 10 : 11);
    uint8_t *packed = lz_compress(t->lz, patched, pn, n, pct, NULL);
    if (packed) {                       /* check it unpacks to the same */
        uint8_t *back = malloc(pn);
        bool same = back && lz_decompress(packed, *n, back, pn) && !memcmp(back, patched, pn);
        free(back);
        if (!same) {
            free(packed);
            packed = NULL;
        }
    }
    free(patched);
    if (!packed)
        snprintf(err, (size_t)errsz, "Couldn't pack content 1");
    return packed;
}

/* Writes content 1 and the TMD. If that fails half way, WiiLink's clean copy goes back in.
 * NAND_OK, or with err: NAND_UNTOUCHED (the channel is as it was), 1 (the clean copy was put
 * back) or NAND_DAMAGED (it couldn't be). */
static int write_pair(const char *appp, const uint8_t *app, uint32_t an, const char *tmdp, const uint8_t *tmd,
                      uint32_t tn, const uint8_t *clean_app, uint32_t cn, const uint8_t *clean_tmd, uint32_t ctn,
                      char *err, int errsz)
{
    int r = nand_replace(appp, app, an);
    if (r == NAND_OK) {
        r = nand_replace(tmdp, tmd, tn);
        if (r == NAND_OK)
            return NAND_OK;
    } else if (r == NAND_UNTOUCHED) {
        snprintf(err, (size_t)errsz, "Couldn't write to the NAND (%s). The channel wasn't changed.", nand_why());
        return NAND_UNTOUCHED;
    }
    char first[96];
    snprintf(first, sizeof(first), "%s", nand_why());
    bool back = nand_replace(appp, clean_app, cn) == NAND_OK && nand_replace(tmdp, clean_tmd, ctn) == NAND_OK;
    if (back) {
        snprintf(err, (size_t)errsz, "Writing to the NAND failed (%s). WiiLink's unpatched copy was put back.", first);
        return 1;
    }
    snprintf(err, (size_t)errsz, "Writing to the NAND failed (%s) and the unpatched copy couldn't be put back: "
             "choose Restore, or install the channel's WAD again.", first);
    return NAND_DAMAGED;
}

static bool patch_nand(title_t *tt, uint32_t mask, say_fn say, pct_fn pct, char *err, int errsz)
{
    const pdb_target_t *t = tt->t;
    char tmdp[96], appp[96], p[200];
    uint32_t tn = 0, an = 0;
    uint8_t *tmd = nand_read((snprintf(tmdp, 96, "/title/%08x/%08x/content/title.tmd", (unsigned)(tt->tid >> 32),
                                       (unsigned)tt->tid), tmdp), &tn);
    tmd_rec_t r;
    if (!tmd || !tmd_find(tmd, tn, 1, &r)) {
        free(tmd);
        return E("Can't read the title's TMD");
    }
    nand_paths(tt, &r, tmdp, appp);
    uint8_t *app = NULL, h[20];
    if (tt->state == ST_CLEAN) {
        say("Backing up the unpatched copy to %s ...", tt->backup);
        app = nand_read(appp, &an);
        if (app)
            sha1_of(app, an, h);
        if (!app || an != t->app_size || memcmp(h, t->app_sha1, 20)) {
            free(app), free(tmd);
            return E("The installed content 1 doesn't match its TMD");
        }
        bool ok = mkdirs(tt->backup);
        bpath(tt, "content1.app", p, sizeof(p));
        ok = ok && sd_write(p, app, an);
        bpath(tt, "title.tmd", p, sizeof(p));
        ok = ok && sd_write(p, tmd, tn);
        if (!ok) {
            free(app), free(tmd);
            return E("Couldn't back up to the SD card: nothing was changed");
        }
    } else {
        free(tmd);
        say("Reading the unpatched copy from the backup...");
        bpath(tt, "title.tmd", p, sizeof(p));
        tmd = sd_read(p, &tn);
        bpath(tt, "content1.app", p, sizeof(p));
        app = sd_read(p, &an);
        if (app)
            sha1_of(app, an, h);
        if (!tmd || !tmd_find(tmd, tn, 1, &r) || !app || an != t->app_size || memcmp(h, t->app_sha1, 20)) {
            free(app), free(tmd);
            return E("The backup in %s is damaged", tt->backup);
        }
    }
    say("Patching...");
    uint32_t cn = 0;
    uint8_t *content = make_content(t, app, mask, &cn, say, pct, err, errsz);
    uint8_t *clean_tmd = content ? malloc(tn) : NULL;
    if (!clean_tmd) {
        free(app), free(content), free(tmd);
        return err[0] ? false : E("Out of memory");
    }
    memcpy(clean_tmd, tmd, tn);
    sha1_of(content, cn, h);
    if (!tmd_set_content(tmd, tn, 1, cn, h)) {
        free(app), free(content), free(tmd), free(clean_tmd);
        return E("Couldn't update the TMD");
    }
    say("Writing to the NAND...");
    int w = write_pair(appp, content, cn, tmdp, tmd, tn, app, an, clean_tmd, tn, err, errsz);
    free(app), free(content), free(tmd), free(clean_tmd);
    if (w == 1) {                       /* clean again */
        tt->state = ST_CLEAN;
        tt->mask = pdb_default_mask(t);
        char p2[200];
        bpath(tt, "applied.txt", p2, sizeof(p2));
        remove(p2);
    }
    if (w != NAND_OK)
        return false;
    write_applied(tt, mask);
    tt->state = ST_PATCHED;
    tt->mask = mask;
    return true;
}

static bool patch_sd(title_t *tt, uint32_t mask, const sd_keys_t *k, say_fn say, pct_fn pct, char *err, int errsz)
{
    const pdb_target_t *t = tt->t;
    char src[200], tmp[200], nandtmd[96];
    snprintf(nandtmd, sizeof(nandtmd), "/title/%08x/%08x/content/title.tmd", (unsigned)(tt->tid >> 32), (unsigned)tt->tid);
    if (tt->state == ST_CLEAN) {
        say("Backing up content.bin to %s ...", tt->backup);
        char p[200];
        bool ok = mkdirs(tt->backup);
        bpath(tt, "content.bin", p, sizeof(p));
        ok = ok && sd_copy(tt->sdpath, p);
        uint32_t tn = 0;
        uint8_t *tmd = nand_read(nandtmd, &tn);
        if (ok && tmd) {
            bpath(tt, "nand.tmd", p, sizeof(p));
            ok = sd_write(p, tmd, tn);
        }
        free(tmd);
        sdbin_t s;
        if (ok && sdbin_open(&s, p, err, errsz)) {    /* the clean TMD, from content.bin */
            bpath(tt, "title.tmd", p, sizeof(p));
            ok = sd_write(p, s.tmd, s.tmd_n);
            sdbin_close(&s);
        }
        if (!ok)
            return E("Couldn't back up to the SD card: nothing was changed");
    }
    bpath(tt, "content.bin", src, sizeof(src));
    sdbin_t s;
    if (!sdbin_open(&s, src, err, errsz))
        return false;
    uint32_t an = 0;
    uint8_t *app = sdbin_content(&s, k, 1, &an, err, errsz), h[20];
    if (app)
        sha1_of(app, an, h);
    if (!app || an != t->app_size || memcmp(h, t->app_sha1, 20)) {
        free(app);
        sdbin_close(&s);
        return app ? E("The backed-up content.bin isn't WiiLink's") : false;
    }
    say("Patching...");
    uint32_t cn = 0;
    uint8_t *content = make_content(t, app, mask, &cn, say, pct, err, errsz);
    free(app);
    uint8_t *tmd = content ? malloc(s.tmd_n) : NULL;
    bool ok = tmd != NULL;
    if (ok) {
        memcpy(tmd, s.tmd, s.tmd_n);
        sha1_of(content, cn, h);
        ok = tmd_set_content(tmd, s.tmd_n, 1, cn, h);
    }
    snprintf(tmp, sizeof(tmp), "%s.new", tt->sdpath);
    if (ok) {
        say("Writing content.bin...");
        ok = sdbin_rewrite(&s, tmp, k, tmd, s.tmd_n, 1, content, cn, err, errsz) && sd_swap(tmp, tt->sdpath);
        if (!ok && !err[0])
            snprintf(err, (size_t)errsz, "Couldn't replace content.bin");
    }
    if (ok && nand_exists(nandtmd))
        ok = nand_replace(nandtmd, tmd, s.tmd_n) == NAND_OK ||
             E("content.bin was patched, but the TMD on the NAND couldn't be written (%s): choose Restore", nand_why());
    free(content), free(tmd);
    sdbin_close(&s);
    if (!ok)
        return false;
    write_applied(tt, mask);
    tt->state = ST_PATCHED;
    tt->mask = mask;
    return true;
}

bool title_patch(title_t *tt, uint32_t mask, const sd_keys_t *keys, say_fn say, pct_fn pct, char *err, int errsz)
{
    err[0] = 0;
    if (tt->on_sd && !keys)
        return E("This console's keys couldn't be read");
    return tt->on_sd ? patch_sd(tt, mask, keys, say, pct, err, errsz) : patch_nand(tt, mask, say, pct, err, errsz);
}

bool title_restore(title_t *tt, const sd_keys_t *keys, say_fn say, char *err, int errsz)
{
    char p[200];
    err[0] = 0;
    if (tt->state != ST_PATCHED)
        return E("It is already unpatched");
    if (tt->on_sd) {
        char tmp[200];
        bpath(tt, "content.bin", p, sizeof(p));
        snprintf(tmp, sizeof(tmp), "%s.new", tt->sdpath);
        say("Copying content.bin back...");
        if (!sd_copy(p, tmp) || !sd_swap(tmp, tt->sdpath))
            return E("Couldn't copy content.bin back");
        uint32_t tn = 0;
        bpath(tt, "nand.tmd", p, sizeof(p));
        uint8_t *tmd = sd_read(p, &tn);
        char nandtmd[96];
        snprintf(nandtmd, sizeof(nandtmd), "/title/%08x/%08x/content/title.tmd", (unsigned)(tt->tid >> 32),
                 (unsigned)tt->tid);
        bool ok = !tmd || nand_replace(nandtmd, tmd, tn) == NAND_OK;
        free(tmd);
        if (!ok)
            return E("content.bin is back, but the TMD on the NAND couldn't be written (%s)", nand_why());
    } else {
        uint32_t tn = 0, an = 0;
        bpath(tt, "title.tmd", p, sizeof(p));
        uint8_t *tmd = sd_read(p, &tn);
        bpath(tt, "content1.app", p, sizeof(p));
        uint8_t *app = sd_read(p, &an), h[20];
        tmd_rec_t r;
        if (app)
            sha1_of(app, an, h);
        if (!tmd || !app || !tmd_find(tmd, tn, 1, &r) || an != r.size || memcmp(h, r.sha1, 20)) {
            free(tmd), free(app);
            return E("The backup in %s is damaged", tt->backup);
        }
        char tmdp[96], appp[96];
        nand_paths(tt, &r, tmdp, appp);
        say("Writing the unpatched copy to the NAND...");
        int w = nand_replace(appp, app, an);
        if (w == NAND_OK)
            w = nand_replace(tmdp, tmd, tn);
        free(tmd), free(app);
        if (w != NAND_OK)
            return E("Writing to the NAND failed (%s)%s", nand_why(),
                     w == NAND_UNTOUCHED ? "" : ". Choose Restore again, or install the channel's WAD again.");
    }
    (void)keys;
    bpath(tt, "applied.txt", p, sizeof(p));
    remove(p);
    tt->state = ST_CLEAN;
    tt->mask = pdb_default_mask(tt->t);
    return true;
}
