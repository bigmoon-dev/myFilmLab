"""package.py — firmware.elf → 部署用 fpSup.BIN（VBIN · v4 修正版）

v3 冻结根因（2026-10-14 定位）：VBIN +0x08 entry 字段的语义是
  · entry == 0            → stage2 跳过入口调用
  · entry <  0x40000000   → **从 buffer 起点（"VBIN" 魔数处）算的偏移**，
                            stage2 执行 addlo r0, r0, r6（r6=buffer）后 blx
  · entry >= 0x40000000   → 绝对地址，stage2 直接 blx
（依据：fpSup stage2.S 入口处理段 + build_autorun.py file_off() =
 16 + 8*count + at[i]；loader.S 头注释。）
v3 的 package.py 写的是 **body 相对** 偏移（少了 16+8*count 的头部+段表），
v3 实测 entry=0x4D8、正确值应为 0x518 —— stage2 跳进了 stage2 本体 +0x498
（lh_unhook 的日志回放循环中段，r4=栈指针被当成日志游标）→ 乱写内存 → 冻结。
v1/v2 则是段0 直接放跳板（无 stage2），loader blx 跳板跳进从未摆放的洞区 →
同样冻结。两版根因同源：没走 stage2 的两段摆放 + entry 调用契约。

v4 范式（对齐仓库现行 fpSup.BIN：count=2、entry=0xC072F188 绝对地址）：
  [0] stage2 本体（dest=0，逐字节 = 原版提取的 tools/stage2.bin，不动）
  [1] .text   @ 0xC072E800（boot_entry：建监视任务后返回 —— entry 是 CALL）
  [2] .ARM.exidx / .rodata / .data（如有）
  [*] .bss 显式补零段（装载器不清零）
  entry = 0xC072E800（绝对地址；段在 pass1 已摆放+cache 已发布，官方同款模式）

段长度契约（build_autorun.py）：每段长度必须是 4 的倍数（stage2 按字拷贝，
非对齐长度会漏拷头几个字节）——打包时统一向上取整补零。
文件总长不得超过 loader MAXLEN 0xF000。无需整文件填充：
官方构建已注明 "file-length padding is obsolete"，8192B 的发布卡可正常开机。

用法：python package.py  （读 ../firmware/firmware.elf，写 ../dist/fpSup.BIN）
"""
import struct
import sys
import os

BASE = os.path.dirname(os.path.abspath(__file__))
ELF_PATH = os.path.join(BASE, '..', 'firmware', 'firmware.elf')
OUT_PATH = os.path.join(BASE, '..', 'dist', 'fpSup.BIN')

TEXT_ADDR   = 0xC072F800          # link.ld 的 .text 基址 = boot_entry（v8 起洞区高段）
MAXLEN      = 0xF000              # loader 单次 F_READ 上限
CAVE_HI     = 0xC0735000          # stage2 焓入的洞区上界

# ---- 最小 ELF32 LE 解析器 ----
def load_sections(path):
    d = open(path, 'rb').read()
    assert d[:4] == b'\x7fELF' and d[4] == 1 and d[5] == 1, "not ELF32 LE"
    e_shoff, = struct.unpack_from('<I', d, 0x20)
    e_shentsize, e_shnum, e_shstrndx = struct.unpack_from('<HHH', d, 0x2E)
    sh = []
    for i in range(e_shnum):
        off = e_shoff + i * e_shentsize
        name_off, s_type, flags, addr, offset, size = struct.unpack_from('<IIIIII', d, off)
        sh.append(dict(name_off=name_off, type=s_type, addr=addr, offset=offset, size=size))
    # 段名表
    strtab = sh[e_shstrndx]
    strdata = d[strtab['offset']:strtab['offset'] + strtab['size']]
    for s in sh:
        e = strdata.index(b'\x00', s['name_off'])
        s['name'] = strdata[s['name_off']:e].decode()
    return d, sh

def main():
    d, sh = load_sections(ELF_PATH)
    def sec(name):
        for s in sh:
            if s['name'] == name and s['size']:
                return s
        return None
    text = sec('.text')
    assert text and text['addr'] == TEXT_ADDR, f".text addr mismatch: {text and hex(text['addr'])}"

    # [0] stage2 本体（loader 交接目标——dest=0 段必须是它）
    sections = [(0, open(os.path.join(os.path.dirname(__file__), 'stage2.bin'),'rb').read())]
    sections.append((TEXT_ADDR, d[text['offset']:text['offset']+text['size']]))
    for nm in ('.ARM.exidx', '.rodata', '.data'):
        s = sec(nm)
        if s:
            sections.append((s['addr'], d[s['offset']:s['offset']+s['size']]))
            print(f'  +{nm}: {s["size"]}B @ 0x{s["addr"]:08X}')
    bss = sec('.bss')
    if bss:
        sections.append((bss['addr'], b'\x00' * bss['size']))   # 显式零段
        print(f'  +.bss (zeroed): {bss["size"]}B @ 0x{bss["addr"]:08X}')

    body = bytearray()
    table = []
    for addr, data in sections:
        while len(body) % 4:
            body += b'\x00'
        pad = -len(data) % 4
        if pad:
            data = data + b'\x00' * pad          # 段长必须 4 的倍数（字拷贝契约）
        table.append((addr, len(data)))
        body += data
    # entry = 绝对地址 TEXT_ADDR（>= 0x40000000，stage2 直接 blx，无需跳板段）
    entry = TEXT_ADDR
    vbin = struct.pack('<4sIII', b'VBIN', len(sections), entry, len(body))
    vbin += b''.join(struct.pack('<II', a, l) for a, l in table)
    vbin += bytes(body)
    assert len(vbin) <= MAXLEN, f'VBIN {len(vbin)}B 超过 loader MAXLEN {MAXLEN}'
    # 洞区避让硬断言（v8 教训：AutoRun 的 worker 状态区 0xC072F000-0xC072F040、
    # stage2 每 boot 写 LOAD_DONE_US 0xC072F6F8——镜像只能在 0xC072F800 之上）
    top = max(a + l for a, l in table if a >= 0x40000000)
    assert TEXT_ADDR >= 0xC072F800 and top <= CAVE_HI, \
        f'镜像越界: base=0x{TEXT_ADDR:08X} top=0x{top:08X} (洞区高段 0xC072F800..0x{CAVE_HI:08X})'
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    open(OUT_PATH, 'wb').write(vbin)
    print(f'\nVBIN: {len(sections)} sections, body {len(body)}B, total {len(vbin)}B, '
          f'entry=0x{entry:08X} -> {OUT_PATH}')
    print('部署：fpSup loader 卡的 \\fpSup.BIN 替换为本文件（AutoRun 不动）')

if __name__ == '__main__':
    main()
