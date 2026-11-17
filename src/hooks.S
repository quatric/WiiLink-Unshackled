/* Hook entry stubs for the Forecast Channel Classic Controller / GameCube patch.
 *
 * Every hook site is replaced by `b <stub>`.  A stub saves every volatile
 * register, calls its body, restores, runs the instruction the hook replaced
 * and branches back to site+4.  RET_* symbols (site+4) come from build.py.
 */
    .set FRAME, 0xE0

    .macro SAVE
    stwu    1, -FRAME(1)
    stw     0, 0x0c(1)
    stw     3, 0x10(1)
    stw     4, 0x14(1)
    stw     5, 0x18(1)
    stw     6, 0x1c(1)
    stw     7, 0x20(1)
    stw     8, 0x24(1)
    stw     9, 0x28(1)
    stw     10, 0x2c(1)
    stw     11, 0x30(1)
    stw     12, 0x34(1)
    mflr    0
    stw     0, 0x38(1)
    mfcr    0
    stw     0, 0x3c(1)
    mfctr   0
    stw     0, 0x40(1)
    mfxer   0
    stw     0, 0x44(1)
    .endm

    .macro RESTORE_ALL          /* everything but r0 */
    lwz     0, 0x44(1)
    mtxer   0
    lwz     0, 0x40(1)
    mtctr   0
    lwz     0, 0x3c(1)
    mtcr    0
    lwz     0, 0x38(1)
    mtlr    0
    lwz     3, 0x10(1)
    lwz     4, 0x14(1)
    lwz     5, 0x18(1)
    lwz     6, 0x1c(1)
    lwz     7, 0x20(1)
    lwz     8, 0x24(1)
    lwz     9, 0x28(1)
    lwz     10, 0x2c(1)
    lwz     11, 0x30(1)
    lwz     12, 0x34(1)
    .endm

    .macro SAVE_FP
    stfd    0, 0x48(1)
    stfd    1, 0x50(1)
    stfd    2, 0x58(1)
    stfd    3, 0x60(1)
    stfd    4, 0x68(1)
    stfd    5, 0x70(1)
    stfd    6, 0x78(1)
    stfd    7, 0x80(1)
    stfd    8, 0x88(1)
    stfd    9, 0x90(1)
    stfd    10, 0x98(1)
    stfd    11, 0xa0(1)
    stfd    12, 0xa8(1)
    stfd    13, 0xb0(1)
    mffs    0
    stfd    0, 0xb8(1)
    .endm

    .macro RESTORE_FP
    lfd     0, 0xb8(1)
    mtfsf   0xff, 0
    lfd     0, 0x48(1)
    lfd     1, 0x50(1)
    lfd     2, 0x58(1)
    lfd     3, 0x60(1)
    lfd     4, 0x68(1)
    lfd     5, 0x70(1)
    lfd     6, 0x78(1)
    lfd     7, 0x80(1)
    lfd     8, 0x88(1)
    lfd     9, 0x90(1)
    lfd     10, 0x98(1)
    lfd     11, 0xa0(1)
    lfd     12, 0xa8(1)
    lfd     13, 0xb0(1)
    .endm

    .section .hooks, "ax"

/* WPADProbe(chan, &type) entry: report a Classic Controller while a GC pad is in */
    .globl hook_probe
hook_probe:
    SAVE
    bl      gc_probe
    stw     3, 0x08(1)
    RESTORE_ALL
    lwz     0, 0x08(1)
    addi    1, 1, FRAME
    cmpwi   0, 0
    beq     1f
    li      3, 0                    /* WPAD_ERR_NONE */
    blr
1:  stwu    1, -16(1)               /* replaced instruction */
    b       RET_PROBE

#ifdef SDK2009

/* ---- 2009 SDK (KPAD/WPAD built Feb 2009) ---- */

/* Per-profile registers and offsets (build.py 'asm_defs'); the defaults are
 * the Nintendo Channel's (Feb 2009 KPAD).  Later KPADs keep the same code
 * shape but allocate registers differently:
 *   POLL_FRAME      KPADiRead's stack frame (its first instruction)
 *   K_BLK           KPAD block register (also r25 = channel at SAMPLE)
 *   K_CNT           sample count offset in the KPAD block
 *   BTN_TMP         scratch register at the button compose (the replaced
 *                   andi. writes it; the other one may be live)
 *   M_TOTAL         samples this read, at the copy-outs */
#ifndef POLL_FRAME
#define POLL_FRAME 272
#endif
#ifndef K_BLK
#define K_BLK 26
#endif
#ifndef K_CNT
#define K_CNT 0x13B
#endif
#ifndef BTN_TMP
#define BTN_TMP 9
#endif
#ifndef M_TOTAL
#define M_TOTAL 22
#endif

/* KPADiRead entry (r3 = channel): GameCube SI poller */
    .globl hook_poll
hook_poll:
    SAVE
    bl      gc_poll
    RESTORE_ALL
    lwz     0, 0x0c(1)
    addi    1, 1, FRAME
    stwu    1, -POLL_FRAME(1)       /* replaced instruction */
    b       RET_POLL

/* KPADiRead sample-count check (K_BLK = KPAD block, r25 = channel) */
    .globl hook_sample
hook_sample:
    SAVE
    mr      3, K_BLK
    mr      4, 25
    bl      gc_sample
    RESTORE_ALL
    lwz     0, 0x0c(1)
    addi    1, 1, FRAME
    lbz     0, K_CNT(K_BLK)         /* replaced instruction */
    b       RET_SAMPLE

/* Button compose leaf (r4 = extension type, r6 = Wii Remote buttons,
 * r8 = Classic Controller buttons; BTN_TMP and cr0 are rewritten by the
 * replaced andi.). Same mapping as the 2007 stub. */
    .globl hook_buttons
hook_buttons:
    cmplwi  4, 2
    bne     9f
    andi.   BTN_TMP, 8, 0x0800      /* HOME */
    beq     1f
    ori     6, 6, 0x8000
1:  andi.   BTN_TMP, 8, 0x0001      /* Up */
    beq     1f
    ori     6, 6, 0x0008
1:  andi.   BTN_TMP, 8, 0x4000      /* Down */
    beq     1f
    ori     6, 6, 0x0004
1:  andi.   BTN_TMP, 8, 0x0002      /* Left */
    beq     1f
    ori     6, 6, 0x0001
1:  andi.   BTN_TMP, 8, 0x8000      /* Right */
    beq     1f
    ori     6, 6, 0x0002
1:  andi.   BTN_TMP, 8, 0x0010      /* A */
    beq     1f
    ori     6, 6, 0x0800
1:  andi.   BTN_TMP, 8, 0x0040      /* B */
    beq     1f
    ori     6, 6, 0x0400
1:  andi.   BTN_TMP, 8, 0x0008      /* X -> 1 */
    beq     1f
    ori     6, 6, 0x0200
1:  andi.   BTN_TMP, 8, 0x0020      /* Y -> 2 */
    beq     1f
    ori     6, 6, 0x0100
1:  andi.   BTN_TMP, 8, 0x1000      /* Minus */
    beq     1f
    ori     6, 6, 0x1000
1:  andi.   BTN_TMP, 8, 0x0400      /* Plus */
    beq     9f
    ori     6, 6, 0x0010
9:  andi.   BTN_TMP, 6, 0x9fff      /* replaced instruction */
    b       RET_BUTTONS

/* The copy-out loops' registers (Nintendo Channel defaults; the Photo
 * Channel's KPAD, built Sept 2008, allocates them differently):
 *   M1_*: per-sample mode, M2_*: compose-once mode
 *   DEST = entry just written, LEFT = samples left; K_BLK = KPAD block,
 *   M_TOTAL = samples this read in both */
#ifndef M1_DEST
#define M1_DEST 24
#define M1_LEFT 25
#define M2_DEST 27
#define M2_LEFT 20
#endif

/* KPADiRead copy-out, per-sample mode */
    .globl hook_motion
hook_motion:
    SAVE
    SAVE_FP
    mr      3, M1_DEST
    mr      4, K_BLK
    subf    5, M1_LEFT, M_TOTAL
    cntlzw  5, 5
    srwi    5, 5, 5
    bl      cc_motion_k
    RESTORE_FP
    RESTORE_ALL
    lwz     0, 0x0c(1)
    addi    1, 1, FRAME
    addic.  M1_LEFT, M1_LEFT, -1    /* replaced instruction */
    b       RET_MOTION

/* KPADiRead copy-out, compose-once mode */
    .globl hook_motion2
hook_motion2:
    SAVE
    SAVE_FP
    mr      3, M2_DEST
    mr      4, K_BLK
    subf    5, M2_LEFT, M_TOTAL
    cntlzw  5, 5
    srwi    5, 5, 5
    bl      cc_motion_k
    RESTORE_FP
    RESTORE_ALL
    lwz     0, 0x0c(1)
    addi    1, 1, FRAME
    addic.  M2_LEFT, M2_LEFT, -1    /* replaced instruction */
    b       RET_MOTION2

#else

/* ---- 2007 SDK (KPAD/WPAD built June 2007) ---- */

/* KPADiRead entry (r3 = channel): GameCube SI poller */
    .globl hook_poll
hook_poll:
    SAVE
    bl      gc_poll
    RESTORE_ALL
    lwz     0, 0x0c(1)
    addi    1, 1, FRAME
    stwu    1, -192(1)              /* replaced instruction */
    b       RET_POLL

/* KPADiRead sample-count check (r31 = KPAD base, r27 = channel): GC pad -> CC samples */
    .globl hook_sample
hook_sample:
    SAVE
    mr      3, 31
    mr      4, 27
    bl      gc_sample
    RESTORE_ALL
    lwz     0, 0x0c(1)
    addi    1, 1, FRAME
    lbz     0, 0x10f(31)            /* replaced instruction */
    b       RET_SAMPLE

/* KPADiRead button compose (r4 = extension type, r7 = Wii Remote buttons,
 * r9 = Classic Controller buttons): OR the Classic Controller into the Wii Remote.
 *   A->A  B->B  X->1  Y->2  Minus->Minus  Plus->Plus  HOME->HOME  D-pad->D-pad
 * r0 and cr0 are free here (the replaced andi. rewrites both). */
    .globl hook_buttons
hook_buttons:
    cmplwi  4, 2
    bne     9f
    andi.   0, 9, 0x0800            /* HOME */
    beq     1f
    ori     7, 7, 0x8000
1:  andi.   0, 9, 0x0001            /* Up */
    beq     1f
    ori     7, 7, 0x0008
1:  andi.   0, 9, 0x4000            /* Down */
    beq     1f
    ori     7, 7, 0x0004
1:  andi.   0, 9, 0x0002            /* Left */
    beq     1f
    ori     7, 7, 0x0001
1:  andi.   0, 9, 0x8000            /* Right */
    beq     1f
    ori     7, 7, 0x0002
1:  andi.   0, 9, 0x0010            /* A */
    beq     1f
    ori     7, 7, 0x0800
1:  andi.   0, 9, 0x0040            /* B */
    beq     1f
    ori     7, 7, 0x0400
1:  andi.   0, 9, 0x0008            /* X -> 1 */
    beq     1f
    ori     7, 7, 0x0200
1:  andi.   0, 9, 0x0020            /* Y -> 2 */
    beq     1f
    ori     7, 7, 0x0100
1:  andi.   0, 9, 0x1000            /* Minus */
    beq     1f
    ori     7, 7, 0x1000
1:  andi.   0, 9, 0x0400            /* Plus */
    beq     9f
    ori     7, 7, 0x0010
9:  andi.   0, 7, 0x9fff            /* replaced instruction */
    b       RET_BUTTONS

/* KPADiRead, right after a sample was copied out to the caller's buffer at
 * r14+0x84 (r27 = channel, r15 = samples left, r30 = samples this read):
 * CC sticks -> pointer and twist, in the caller's copy only, so KPAD's own
 * IR tracking state is never touched */
    .globl hook_motion
hook_motion:
    SAVE
    SAVE_FP
    addi    3, 14, 0x84
    mr      4, 27
    subf    5, 15, 30               /* first = (r15 == r30) */
    cntlzw  5, 5
    srwi    5, 5, 5
    bl      cc_motion
    RESTORE_FP
    RESTORE_ALL
    lwz     0, 0x0c(1)
    addi    1, 1, FRAME
    addic.  15, 15, -1              /* replaced instruction */
    b       RET_MOTION

#endif

#ifdef KBD
/* Software keyboard state's per-frame calc, right before inputForm->calc()
 * (r3 = input form, r31 = keyboard state): USB keyboard -> input form */
    .globl hook_kbd
hook_kbd:
    SAVE
    mr      4, 31
    bl      kbd_frame
    RESTORE_ALL
    lwz     0, 0x0c(1)
    addi    1, 1, FRAME
    lwz     12, 0(3)                /* replaced instruction */
    b       RET_KBD
#endif

#ifdef TILT
/* Forecast Channel globe tilt angles (degrees), the News Channel's table:
 * index 5 is level, 0 and 10 are tilted all the way over either way */
    .globl tilt_angles
    .balign 4
tilt_angles:
    .float -80.0, -73.0, -65.0, -55.0, -45.0, 0.0, 45.0, 55.0, 65.0, 73.0, 80.0
#endif
