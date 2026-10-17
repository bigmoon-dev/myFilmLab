/* boot.S — FILMLAB 常驻引导（loader 范式 v2）
 * 模式：fpSup loader BIN 的 entry（stage2 在任务上下文 branch 过来）。
 * 职责只剩两件事：创建监视任务，然后长眠。
 * （v1 的陀螺钩子代理已删除——pass-1 竞态窗口类别整个消失；
 *   任务上下文创建也终于符合 taskcreate.S 的要求）
 */
    .syntax unified
    .arm

    .equ TK_CRE_TSK,  0xC0016A58
    .equ TK_STA_TSK,  0xC0016BC0
    .equ DLY_TSK,     0xC03705D8
    .equ TASK_PRI,    28
    .equ TASK_STKSZ,  0x2000

    .global boot_entry
    .extern monitor_main

boot_entry:
    push    {r4, r5, r6, lr}    @ 偶数寄存器数：AAPCS 要求调用边界 sp 8 字节对齐

    /* T_CTSK on stack (48B):
       +0 exinf=0  +4 tskatr=0x41  +8 entry  +12 pri  +16 stksz  +20 dsname[12] */
    sub     sp, sp, #48
    mov     r0, #0
    str     r0, [sp]
    mov     r0, #0x41
    str     r0, [sp, #4]
    movw    r0, #:lower16:monitor_main
    movt    r0, #:upper16:monitor_main
    str     r0, [sp, #8]
    mov     r0, #TASK_PRI
    str     r0, [sp, #12]
    movw    r0, #:lower16:TASK_STKSZ
    movt    r0, #0
    str     r0, [sp, #16]
    ldr     r0, =0x00424D4B              @ dsname "KMB\0"
    str     r0, [sp, #20]
    mov     r0, #0
    str     r0, [sp, #24]
    str     r0, [sp, #28]

    mov     r0, sp
    movw    r12, #:lower16:TK_CRE_TSK
    movt    r12, #:upper16:TK_CRE_TSK
    blx     r12                          @ r0 = task id (or negative)
    cmp     r0, #0
    ble     .created
    mov     r1, #0                       @ stacd = 0
    movw    r12, #:lower16:TK_STA_TSK    @ tk_sta_tsk(r0=id, r1=0)
    movt    r12, #:upper16:TK_STA_TSK
    blx     r12
.created:
    add     sp, sp, #48

    /* stage2 是 CALL（blx）过来的，entry 必须返回（SUP_BUILD_RULES 第2条）：
       任务已创建常驻，这里返回后 stage2 继续 pass2/flash 写 */
    pop     {r4, r5, r6, pc}
    .ltorg
