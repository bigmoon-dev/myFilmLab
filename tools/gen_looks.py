"""gen_looks.py — looks.cfg → firmware/gen_looks.c（v11：v9 语义 + 面板）

名槽 = 按底色的五表族（v8 实证矩阵，v9 实机验证）。
EXIF 在捕获窗读底座串 → 配方名写底座槽（v9 机制原样）。
面板全名（title 字段）不进固件——由 make_panel.py 渲染成卡上 OSD 素材。
"""
import configparser, sys, os
BASE = os.path.dirname(os.path.abspath(__file__))

#        底座:    (menu序号, 枚举, 原串, [池A, 池B, RFS, 远A, 远B] —— 0=该表无副本)
BASES = {
 'STD':  ( 0, 0x00, 'Standard',    [0xC09709B0, 0xC0970A98, 0xC0CC2FDC, 0xC2DFD180, 0]),
 'VIV':  ( 1, 0x03, 'Vivid',       [0xC0970918, 0xC0970A00, 0xC0CC2FE8, 0xC2DFD0C8, 0]),
 'NTR':  ( 2, 0x05, 'Neutral',     [0xC0970904, 0xC09709EC, 0xC0CC2FF0, 0xC2DFD08C, 0xC2E44ABC]),
 'PORT': ( 3, 0x06, 'Portrait',    [0xC09709BC, 0xC0970AA4, 0xC0CC2FF8, 0xC2DFD18C, 0xC2E44AC4]),
 'LAND': ( 4, 0x07, 'Landscape',   [0xC0970970, 0xC0970A58, 0xC0CC3004, 0xC2DFD124, 0xC2E44AD0]),
 'CINE': ( 5, 0x08, 'Cinematic',   [0xC097097C, 0xC0970A64, 0xC0CC3010, 0xC2DFD130, 0xC2E44ADC]),
 'TO':   ( 6, 0x0A, 'TealAndOrange',[0xC0970994, 0xC0970A7C, 0xC0CC3028, 0xC2DFD13C, 0xC2E44AF4]),
 'SUNR': ( 7, 0x0B, 'SunsetRed',   [0xC0970988, 0xC0970A70, 0xC0CC3038, 0xC2DFD14C, 0xC2E44B04]),
 'FORG': ( 8, 0x0C, 'ForestGreen', [0xC0970928, 0xC0970A10, 0xC0CC3044, 0xC2DFD0FC, 0xC2E44B10]),
 'POWB': (13, 0x0D, 'PowderBlue',  [0xC09709D4, 0xC0970ABC, 0xC0CC3050, 0xC2DFD198, 0xC2E44B1C]),
 'WGLD': (15, 0x09, 'WarmGold',    [0xC09709E0, 0xC0970AC8, 0xC0CC301C, 0,          0xC2E44AE8]),
 'FOVB': ( 9, 0x0E, 'FCBlue',      [0xC0970920, 0xC0970A08, 0xC0CC305C, 0xC2DFD0D8, 0xC2E44B28]),
 'FOVY': (10, 0x0F, 'FCYellow',    [0xC09709C8, 0xC0970AB0, 0xC0CC3064, 0xC2DFD1A4, 0xC2E44B30]),
 'MONO': (11, 0x01, 'Monochrome',  [0xC09709A4, 0xC0970A8C, 0xC0CC3078, 0,          0xC2E44B44]),
}
VARIANT_ENUMS = {  # host 变体（用户入口）→ 枚举 0x18..0x21
 'DUO_R1':0x18,'DUO_OR1':0x19,'DUO_YE1':0x1A,'DUO_YG1':0x1B,'DUO_G1':0x1C,
 'DUO_G2':0x1D,'DUO_B1':0x1E,'DUO_B2':0x1F,'DUO_P1':0x20,'DUO_M1':0x21,
}

def main(out_path):
    cfg = configparser.ConfigParser()
    cfg.read(os.path.join(BASE, 'looks.cfg'), encoding='utf-8')
    by_variant = [None]*10
    for sec in cfg.sections():
        g = cfg[sec]
        host = VARIANT_ENUMS[g.get('host').strip().upper()]
        idx = host - 0x18
        bn = g.get('mode','STD').strip().upper()
        assert bn in BASES, f'{sec}: 底座 {bn} 不在已实证表内'
        menu_idx, enum, stock, slots = BASES[bn]
        bwin = len(stock) + 1                    # 底座紧缩池窗口 = 原串长+1
        name = g.get('name', sec)
        assert len(name) <= bwin - 1, f'{sec}: 名字 {name!r} 超 {bn} 底座窗口 {bwin-1} 字符'
        by_variant[idx] = dict(
            name=name, base=enum, menu=menu_idx, bwin=bwin,
            eff=int(g.get('eff',0)), con=int(g.get('con',0)), shp=int(g.get('shp',0)),
            sat=int(g.get('sat',0)), ton=int(g.get('ton',0)),
            addrs=[a for a in slots if a])
    duo = ''
    lines = ['#include <stdint.h>', '',
             'typedef unsigned char u8; typedef signed char i8; typedef unsigned int u32;',
             'typedef struct { u32 n_addr; u32 addrs[5]; } slot_list_t;',
             'typedef struct { u8 valid; u8 base; u8 menu_idx; u8 name_win;',
             '  i8 eff,con,shp,sat,ton; u8 name[12]; u8 _p[3]; slot_list_t slots; } look_t;',
             '',
             'const look_t g_looks[10] = {']
    for lk in by_variant:
        if lk is None:
            lines.append('  {0},')
            continue
        nm = lk['name'].encode('ascii','replace')
        nmbytes = ','.join(f"0x{b:02X}" for b in nm) + ',' + ','.join('0'*(12-len(nm)))
        ad = ','.join(f'0x{a:08X}u' for a in lk['addrs'])
        pad = ','.join(['0u']*(5-len(lk['addrs'])))
        lines.append(
            f"  {{1,0x{lk['base']:02X},{lk['menu']},{lk['bwin']},"
            f"{lk['eff']},{lk['con']},{lk['shp']},{lk['sat']},{lk['ton']},"
            f"{{{nmbytes}}},{{0,0,0}},"
            f"{{{len(lk['addrs'])},{{{ad}{',' if pad else ''}{pad}}}}}}},"
            f"  /* {lk['name']} */")
    lines += ['};', '']
    open(out_path, 'w', encoding='utf-8').write('\n'.join(lines))
    print(f'wrote {out_path} ({sum(1 for x in by_variant if x)} looks)')

if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'gen_looks.c')
