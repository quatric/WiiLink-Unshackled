/* Wii Message Board photos from the SD card (Photo Channel 1.1).
 *
 * The Photo Channel's "View Wii Message Board photos" reads the Message Board
 * database through the CDB library.  CDB keeps records in the VFF file on NAND
 * (drive "CDB") and, when the card is mounted, in SD:/private/wii/title/HAEA/
 * (where the Wii Menu moves them), but the Photo Channel only ever mounts the
 * NAND drive: CDBMountSD() and the VF library's SD mount were left out of this
 * build, and the scan asks for NAND records only.  CDB's SD record reader
 * (signature check, decryption) is all still there.
 *
 * cdbsd_mount() runs before every scan (hooks.S: hook_cdbsd, which also makes
 * the scan ask for SD records).  It mounts the SD card as VF drive "SD" afresh
 * each time, so a card swapped since the last scan is read from scratch, and
 * drops the drive when there is no card:
 *
 *  - The VF library attaches a drive with a disk driver table ({init function,
 *    argument}, copied from a template).  The template is pointed at
 *    drv_tbl_init for the one attach, so the new drive uses sd_ops.
 *  - sd_ops reads sectors with the SD card driver of the Photo Channel's own
 *    SD file library (FA).  That driver keeps its state in globals, so its
 *    mount (card init, done once), read and disk-info functions work for any
 *    disk.  Writes and formats are refused, and unmount leaves the card to FA:
 *    the drive is read-only.  The driver turns a call away while one of FA's
 *    own is in flight; those calls are retried.
 *  - The init function does what the VF NAND driver's does: mark the medium
 *    present and tell the disk manager it is inserted.
 *  - CDB's "SD mounted" flag is set, which lets it open records on SD.
 *
 * The Wii Speak Channel (USA) has the same Message Board scan, VF library and
 * SD card driver, but never starts the driver (FA_SD_INIT is defined for it).
 * There drv_init starts it for the new drive the first time, and points it at
 * each new drive after that: the driver's card insert / eject callbacks
 * report to that drive, and are kept off (0) while there is none.
 *
 * Built soft-float.  Addresses come in as -D macros (build.py 'cdbsd').
 */
typedef unsigned int u32;
typedef signed int s32;

typedef s32 (*fn_t)(void);
typedef s32 (*fn1_t)(u32);
typedef s32 (*fn2_t)(u32, u32);
typedef s32 (*fn3_t)(u32, u32, u32);
typedef s32 (*fn5_t)(u32, u32, u32, u32, u32);
#define CALL1(a, x) (((fn1_t)(a))((u32)(x)))
#define CALL2(a, x, y) (((fn2_t)(a))((u32)(x), (u32)(y)))
#define CALL3(a, x, y, z) (((fn3_t)(a))((u32)(x), (u32)(y), (u32)(z)))

#define W(a) (*(volatile u32 *)(a))
#define TB_HZ 60750000u                     /* timebase ticks per second */
#define SD_BUSY_READ -37                    /* FA SD driver: another request in flight */
#define SD_BUSY_INFO -39

static u32 tb(void)
{
    u32 t;
    __asm__ volatile ("mftb %0" : "=r"(t));
    return t;
}

/* Wait for the request in flight to finish, for up to 2 s from t0 in all. */
static int sd_retry(u32 t0)
{
    u32 t = tb();
    if (t - t0 > 2 * TB_HZ)
        return 0;
    while (W(FA_SD_BUSY) && tb() - t < TB_HZ / 10)
        ;
    while (tb() - t < TB_HZ / 500)
        ;
    return 1;
}

static s32 sd_read(u32 disk, u32 buf, u32 block, u32 n, u32 done)
{
    u32 t0 = tb();
    s32 r;
    do
        r = ((fn5_t)FA_SD_READ)(disk, buf, block, n, done);
    while (r == SD_BUSY_READ && sd_retry(t0));
    return r;
}

static s32 sd_info(u32 disk, u32 info)
{
    u32 t0 = tb();
    s32 r;
    do
        r = CALL2(FA_SD_INFO, disk, info);
    while (r == SD_BUSY_INFO && sd_retry(t0));
    return r;
}

static s32 drv_init(u32 disk)
{
    if (!disk)
        return -20;
#ifdef FA_SD_INIT
    if (W(FA_SD_STATE) & 1)
        W(FA_SD_STATE + 12) = disk;             /* the drive the driver reports to */
    else if (CALL1(FA_SD_INIT, disk))
        return -20;
#endif
    CALL2(VF_DRV_PRESENT, disk, 1);
    CALL1(VF_NOTIFY_INSERT, disk);
    return 0;
}

static s32 drv_ok(u32 disk) { return 0; }

static s32 drv_format(u32 disk, u32 param) { return -20; }

static s32 drv_write(u32 disk, u32 buf, u32 block, u32 n, u32 *done)
{
    if (done)
        *done = 0;
    return -20;
}

/* PDM driver: init, finalize, mount, unmount, format, read, write, disk info */
static const fn_t sd_ops[8] = {
    (fn_t)drv_init, (fn_t)drv_ok, (fn_t)FA_SD_MOUNT, (fn_t)drv_ok,
    (fn_t)drv_format, (fn_t)sd_read, (fn_t)drv_write, (fn_t)sd_info,
};

static s32 drv_tbl_init(u32 *drv, u32 arg)
{
    drv[0] = (u32)sd_ops;
    drv[1] = arg;
    return 0;
}

void cdbsd_mount(void)
{
    static const char name[] = "SD";
    u32 lock, t0, t1, vol;
    s32 idx = -1;

    W(CDB_SD + 4) = 0;                              /* "SD is mounted to CDB" */
#ifdef FA_SD_INIT
    W(FA_SD_STATE + 12) = 0;                        /* the old drive goes */
#endif
    if (CALL1(VF_LOOKUP, name) != -1)
        CALL1(VF_UNMOUNT, name);                    /* unmount and detach */
#ifdef FA_SD_INIT
    if ((W(FA_SD_STATE) & 1) && W(FA_SD_STATE + 16) == 0)
        return;                                     /* driver up, no card */
#else
    if ((W(FA_SD_STATE) & 1) == 0 || W(FA_SD_STATE + 16) == 0)
        return;                                     /* driver not up / no card */
#endif

    lock = W(VF_LOCK_ON);
    if (lock)
        CALL1(FN_OSLOCKMUTEX, VF_MUTEX);
    t0 = W(VF_DISK_TMPL);
    t1 = W(VF_DISK_TMPL + 4);
    W(VF_DISK_TMPL) = (u32)drv_tbl_init;
    W(VF_DISK_TMPL + 4) = 0;
    if (CALL3(VF_ATTACH, &idx, 0, 0))
        idx = -1;
    W(VF_DISK_TMPL) = t0;
    W(VF_DISK_TMPL + 4) = t1;
    if (idx != -1) {
        CALL2(VF_SETNAME, name, idx & 0xFF);
        vol = CALL1(VF_VOLUME, idx);                /* drive + 4; the device is at drive + 0 */
        if (vol) {
            W(W(vol - 4) + 8) = 3;                  /* device type: SD (no backing file) */
            if (CALL3(VF_MOUNT, idx, "", 0) == 0)
                W(CDB_SD + 4) = 1;
        }
    }
    if (lock)
        CALL1(FN_OSUNLOCKMUTEX, VF_MUTEX);
    if (idx != -1 && !W(CDB_SD + 4)) {
#ifdef FA_SD_INIT
        W(FA_SD_STATE + 12) = 0;
#endif
        CALL1(VF_UNMOUNT, name);
    }
}
