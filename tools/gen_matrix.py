"""gen_matrix.py — Part B 标定拍摄矩阵生成器

产出两件：
  1. 控制台打印逐张命令清单（贴进简报/执行）
  2. dump/calib/manifest.json：拍摄序号 → {base_menu, axis, value}
     （calibrate.py --matrix 按此把 SDIM 序列映射回实验条件）

矩阵设计（线性可加响应模型：基线 + 每轴单位增量）：
  5 底座 ×(基线1 + 5轴×1档) = 30 张；STD 加 3 张线性度抽查(-1档) = 33 张。
  轴档位：sat/con/ton +4，shp +4，eff +2（与 photo19 demo 同标；
  负档抽查 -1）。menu 序号：K3 实测映射。
"""
import json, os, sys

BASES = [  # (menu_idx, 名, 枚举)——menu 序号= R_FileSelect 全排列实测定案
    (0, 'STD', 0x00), (1, 'VIV', 0x03), (2, 'NTR', 0x05), (5, 'CINE', 0x08), (11, 'MONO', 0x01),
]
AXES = [   # (setter 后缀, 档位)——eff 轴实测档位偏低,用 +2
    ('Effect', 2), ('Contrast', 4), ('Sharpness', 4), ('Saturation', 4), ('Toning', 4),
]
LINEARITY = [  # STD 上的负档抽查
    ('Saturation', -1), ('Contrast', -1), ('Toning', -1),
]

def shots():
    seq = []
    for mi, bn, _ in BASES:
        seq.append(dict(base_menu=mi, base=bn, axis=None, value=0))          # 基线
        for ax, v in AXES:
            seq.append(dict(base_menu=mi, base=bn, axis=ax, value=v))
    for ax, v in LINEARITY:
        seq.append(dict(base_menu=0, base='STD', axis=ax, value=v))          # 线性度
    return seq

def main():
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'dump', 'calib')
    os.makedirs(out_dir, exist_ok=True)
    seq = shots()
    with open(os.path.join(out_dir, 'manifest.json'), 'w') as f:
        json.dump(seq, f, indent=1)
    print(f'manifest → {out_dir}/manifest.json  （{len(seq)} 张）\n')
    n = 0
    cur_base = None
    print('=== 逐张命令清单（menu setter 路径；setter 应答应为 OK）===')
    for i, s in enumerate(seq):
        if s['base_menu'] != cur_base:
            cur_base = s['base_menu']
            print(f'\n# —— 底座 {s["base"]} (menu {cur_base}) ——')
            print(f'menu SetColorMode {cur_base}')
            print(f'# 五轴归零确认: menu SetColorModeEffect/Contrast/Sharpness/Saturation/Toning 各读一次应为 0')
        n += 1
        if s['axis'] is None:
            print(f'#[{n:02d}] 基线 {s["base"]}  → 拍摄')
        else:
            print(f'menu SetColorMode{s["axis"]} {s["value"]}')
            print(f'#[{n:02d}] {s["base"]} {s["axis"]}={s["value"]:+d}  → 拍摄')
            print(f'menu SetColorMode{s["axis"]} 0')
    print('\n# 收尾：五轴确认归零；卡取回 dump/calib/')

if __name__ == '__main__':
    main()
