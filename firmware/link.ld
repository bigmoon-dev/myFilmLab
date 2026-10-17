/* link.ld — FILMLAB firmware 链接脚本
 * 代码安放地址 = fpSup 洞区高段（VBIN 摆放时按此地址链接）
 * v8 起上移到 0xC072F800：避开 shell 卡 AutoRun 的 worker 状态区
 * （0xC072F000-0xC072F040）与 stage2 每 boot 写的 LOAD_DONE_US（0xC072F6F8）。
 * 上界 CAVE_HI=0xC0735000（stage2 焓入常量），可用 ~14KB。
 */
ENTRY(boot_entry)
SECTIONS
{
    . = 0xC072F800;
    .text : { *(.text*) }
    .rodata : { *(.rodata*) }
    .data : { *(.data*) }
    .bss : { *(.bss*) *(COMMON) }
}
