"""calibrate.py — Sigma fp 配方标定求解器

流程：
  1. response photos (chart photos at known axis settings) → patch values
  2. target charts (LUT-applied chart images) → patch values
  3. solve: find (base_mode, sat, con, ton, shp, eff) minimizing patch error

用法：
  python calibrate.py --demo        # 用 photo19 现有数据做演示
  python calibrate.py --responses DIR --targets DIR --out looks.cfg
"""
import argparse
import itertools
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import numpy as np
from PIL import Image

# ---------- chart patch model ----------
# 16-level gray wedge (y 280..420): x steps of (1920-40)/16
# 8 saturated colors (y 20..240)
# 6 skins (y 460..640)
# RGB gradient + lum ramp (y 460..640 right)
# We auto-locate patches by color-nearest match in the PHOTO (robust to framing).

PATCH_REFS = {
    # name: (r,g,b) reference color as painted in testchart.png
    "RED":   (230, 30, 40),
    "GREEN": (30, 200, 60),
    "BLUE":  (40, 60, 230),
    "CYAN":  (30, 200, 210),
    "MAGENTA": (220, 40, 200),
    "YELLOW": (235, 220, 40),
    "SKIN1": (235, 190, 165),
    "SKIN2": (210, 160, 130),
    "SKIN3": (170, 115, 85),
    "GRAY_BLACK": (17, 17, 17),     # step 1
    "GRAY_DARK":  (85, 85, 85),     # ~step 5
    "GRAY_MID":   (136, 136, 136),  # step 8
    "GRAY_LIGHT": (187, 187, 187),  # ~step 11
    "GRAY_WHITE": (255, 255, 255),  # step 16
    "ORANGE": (240, 130, 30),
    "TEAL":   (30, 160, 180),
}

def extract_patches(img_arr, tol=70):
    """img_arr: HxWx3 float. Returns {name: measured (r,g,b)}."""
    out = {}
    H, W = img_arr.shape[:2]
    for name, ref in PATCH_REFS.items():
        r = np.array(ref, dtype=float)
        m = np.abs(img_arr - r).sum(axis=2) < tol
        if m.sum() < 400:
            m = np.abs(img_arr - r).sum(axis=2) < 110
        if m.sum() < 100:
            out[name] = None
            continue
        ys, xs = np.where(m)
        cy, cx = np.median(ys).astype(int), np.median(xs).astype(int)
        hy, wx = int(H * 0.03), int(W * 0.03)
        sel = m[max(cy-hy,0):cy+hy, max(cx-wx,0):cx+wx]
        reg = img_arr[max(cy-hy,0):cy+hy, max(cx-wx,0):cx+wx]
        vals = reg[sel]
        # trim outliers (chart edges/reflections)
        mu = vals.mean(axis=0) if len(vals) else r; sd = vals.std(axis=0) + 1e-6 if len(vals) else np.ones(3)
        keep = (np.abs(vals - mu) / sd).max(axis=1) < 2.5
        if keep.sum() > 50:
            vals = vals[keep]
        out[name] = vals.mean(axis=0)
    return out

def load_image(path):
    return np.asarray(Image.open(path).convert('RGB'), dtype=float)

# fixed chart coordinates (from make_chart.py layout) for synth targets
def extract_patches_fixed(img_arr):
    """img_arr: 1080x1920 synthetic chart (LUT-applied target). Fixed positions."""
    W = 1920
    out = {}
    sat = [("RED",(230,30,40)),("GREEN",(30,200,60)),("BLUE",(40,60,230)),
           ("CYAN",(30,200,210)),("MAGENTA",(220,40,200)),("YELLOW",(235,220,40)),
           ("ORANGE",(240,130,30)),("TEAL",(30,160,180))]
    pw = (W-40)//8
    for i,(nm,_) in enumerate(sat):
        x = 20+i*pw+pw//2
        out[nm] = img_arr[120, x]
    skins = [("SKIN1",0),("SKIN2",1),("SKIN3",2),("SKIN4",3),("SKIN5",4),("SKIN6",5)]
    spw = 210
    for i,(nm,_) in enumerate(skins):
        x = 20+i*(spw+8)+spw//2
        out[nm] = img_arr[550, x]
    steps = 16
    sw = (W-40)/steps
    for k in range(steps):
        v = round(255*k/(steps-1))
        nm = {0:"GRAY_BLACK",68:"GRAY_DARK",136:"GRAY_MID",204:"GRAY_LIGHT",255:"GRAY_WHITE"}.get(v)
        if nm:
            out[nm] = img_arr[350, int(20+k*sw+sw/2)]
    return out

# ---------- response model ----------
class ResponseModel:
    """axis response: base patch vector + per-axis additive deltas (linear, first-order)."""
    def __init__(self, base_patches):
        self.base = base_patches              # {name: rgb} at all-zero axes
        self.deltas = {}                       # {axis: {name: rgb_delta_per_unit}}

    def add_axis(self, axis, value, patches):
        d = {}
        for k in self.base:
            if self.base[k] is not None and patches.get(k) is not None:
                d[k] = (patches[k] - self.base[k]) / value
        self.deltas[axis] = d

    def predict(self, axes):
        out = {}
        for k, b in self.base.items():
            if b is None: continue
            v = np.array(b, dtype=float)
            for axis, val in axes.items():
                if axis in self.deltas and k in self.deltas[axis] and val != 0:
                    v = v + self.deltas[axis][k] * val
            out[k] = v
        return out

def patch_error(pred, target, weights=None):
    keys = [k for k in target if target[k] is not None and k in pred and pred[k] is not None]
    if not keys: return 1e9
    w = weights or {k: 1.0 for k in keys}
    # emphasize skins + grays (what humans notice)
    for k in keys:
        if k.startswith('SKIN') or k.startswith('GRAY'):
            w[k] = w.get(k, 1.0) * 2.0
    err = sum(w[k] * np.sum((pred[k] - target[k])**2) for k in keys) / sum(w[k] for k in keys)
    return float(np.sqrt(err))

# ---------- solver ----------
AXIS_RANGES = {"saturation": [-1, 4], "contrast": [-1, 4], "toning": [-1, 4],
               "sharpness": [0, 4], "effect": [0, 4]}

def solve(model, target, base_modes=None):
    """greedy coordinate descent over axis values; base modes handled by caller."""
    best = (1e18, {})
    axes = {a: 0 for a in AXIS_RANGES}
    # init
    cur = patch_error(model.predict(axes), target)
    improved = True
    it = 0
    while improved and it < 10:
        improved = False
        it += 1
        for a in AXIS_RANGES:
            lo, hi = AXIS_RANGES[a]
            for v in range(lo, hi + 1):
                if v == axes[a]: continue
                trial = dict(axes); trial[a] = v
                e = patch_error(model.predict(trial), target)
                if e < cur - 1e-6:
                    cur, axes = e, trial
                    improved = True
    return cur, axes

# ---------- demo with photo19 ----------
PHOTO19 = {  # tag -> (filename, axis, value)
    'base':  ('SDIM0574', None, 0),
    'sat+4': ('SDIM0575', 'saturation', 4),
    'sat-1': ('SDIM0576', 'saturation', -1),
    'con+4': ('SDIM0577', 'contrast', 4),
    'con-1': ('SDIM0578', 'contrast', -1),
    'ton+4': ('SDIM0579', 'toning', 4),
    'shp+4': ('SDIM0580', 'sharpness', 4),
    'eff+2': ('SDIM0581', 'effect', 2),
}

def run_demo(targets_dir):
    d = r'D:\work\fp\dump\photo19'
    print('[1] extracting response patches from photo19...')
    patches = {}
    for tag, (fn, axis, val) in PHOTO19.items():
        p = extract_patches(load_image(os.path.join(d, fn + '.JPG')))
        patches[tag] = p
        ok = sum(1 for v in p.values() if v is not None)
        print(f'    {tag}: {ok}/{len(PATCH_REFS)} patches')
    model = ResponseModel(patches['base'])
    for tag, (fn, axis, val) in PHOTO19.items():
        if axis and val != 0:
            model.add_axis(axis, val, patches[tag])
    print('[2] solving recipes against LUT targets...')
    results = []
    for f in sorted(os.listdir(targets_dir)):
        if not f.startswith('tgt_'): continue
        img = load_image(os.path.join(targets_dir, f))
        if img.shape[0] == 1080 and img.shape[1] == 1920:
            tgt = extract_patches_fixed(img)
        else:
            tgt = extract_patches(img, tol=95)
        err, axes = solve(model, tgt)
        results.append((err, f[4:-4], axes))
        print(f'    {f[4:-4]:22s} err={err:6.2f}  recipe={axes}')
    results.sort()
    print('\n[3] best-match ranking (低 err = 更接近该胶片):')
    for err, name, axes in results:
        print(f'  {err:6.2f}  {name}')
    return model, results

# ---------- matrix mode (Part B 标定矩阵) ----------
# 目标文件名 → 配方名/host 变体（沿用 looks.cfg 现行映射;SEPIA/MONO+ 为创意配方不在内）
TARGET_MAP = {   # tgt_ 文件基名: (配方名, host)
    'kodak-portra-400':   ('PRT400', 'DUO_R1'),
    'kodak-portra-160':   ('PRT160', 'DUO_OR1'),
    'cinestill-400d':     ('CS400D', 'DUO_YE1'),
    'kodak-ektar-100':    ('EKTAR',  'DUO_YG1'),
    'kodak-gold-200':     ('GLD200', 'DUO_G1'),
    'fuji-pro-400h':      ('FUJI4H', 'DUO_G2'),
    'cinestill-800t':     ('CS800T', 'DUO_B1'),
}
MENU2BASE = {0: 'STD', 1: 'VIV', 2: 'NTR', 5: 'CINE', 11: 'MONO'}  # R_FileSelect 全排列
AX2KEY = {'Effect': 'effect', 'Contrast': 'contrast', 'Sharpness': 'sharpness',
          'Saturation': 'saturation', 'Toning': 'toning'}   # 与 AXIS_RANGES 同域
NAME_WIN = {'STD': 8, 'VIV': 5, 'NTR': 7, 'CINE': 9, 'MONO': 10}  # 名长上限(池紧缩窗)

def run_matrix(shots_dir, manifest_path, targets_dir, out_path):
    man = json.load(open(manifest_path))
    jpgs = sorted(f for f in os.listdir(shots_dir) if f.upper().endswith('.JPG'))
    assert len(jpgs) >= len(man), f'照片数 {len(jpgs)} < 矩阵 {len(man)}（manifest 与目录不符）'
    jpgs = jpgs[:len(man)]
    print(f'[1] {len(man)} 张矩阵照片 ↔ manifest 按序绑定（首张 {jpgs[0]}）')
    # [2] 逐底座建响应模型
    by_base = {}
    for entry, fn in zip(man, jpgs):
        by_base.setdefault(entry['base'], []).append((entry, fn))
    models = {}
    for bn, rows in by_base.items():
        base_row = next((e, f) for e, f in rows if e['axis'] is None)
        base_patches = extract_patches(load_image(os.path.join(shots_dir, base_row[1])))
        ok = sum(1 for v in base_patches.values() if v is not None)
        print(f'    底座 {bn}: 基线 {ok}/{len(PATCH_REFS)} patch')
        m = ResponseModel(base_patches)
        for e, f in rows:
            if e['axis'] is None: continue
            p = extract_patches(load_image(os.path.join(shots_dir, f)))
            key = AX2KEY[e['axis']]
            # 同轴多档: 每档单独记(线性度抽查档不进模型,只做验证报告)
            m.deltas.setdefault(key, {})
            d = {}
            for k in m.base:
                if m.base[k] is not None and p.get(k) is not None:
                    d[k] = (p[k] - m.base[k]) / e['value']
            if abs(e['value']) >= 2:        # 主档(+4/+2)进模型
                m.deltas[key] = d
            else:                            # 抽查档(-1): 只报线性度
                pred = {k: m.base[k] + m.deltas.get(key, {}).get(k, np.zeros(3)) * e['value']
                        for k in m.base if m.base[k] is not None}
                lin = patch_error(pred, p)
                print(f'    线性度 {bn}.{key}@{e["value"]}: err={lin:.2f} (越接近0越线性)')
        models[bn] = m
    # [3] 逐目标跨底座求解
    print('[2] 跨底座求解:')
    solved = {}
    for f in sorted(os.listdir(targets_dir)):
        if not f.startswith('tgt_'): continue
        key = f[4:-4]
        if key not in TARGET_MAP: continue
        img = load_image(os.path.join(targets_dir, f))
        tgt = extract_patches_fixed(img) if img.shape[:2] == (1080, 1920) else extract_patches(img, tol=95)
        best = (1e18, None, None)
        for bn, m in models.items():
            err, axes = solve(m, tgt)
            if err < best[0]: best = (err, bn, axes)
        err, bn, axes = best
        name, host = TARGET_MAP[key]
        warn = ''
        if len(name) > NAME_WIN.get(bn, 99):
            warn = f'  ⚠ 名超 {bn} 窗口({NAME_WIN[bn]}字符)'
        print(f'    {name:8s} → {bn:4s} err={err:6.2f} axes={axes}{warn}')
        solved[key] = (name, host, bn, axes)
    # [4] 写 looks.cfg 草案(创意三条从现行 looks.cfg 透传)
    import configparser
    cur = configparser.ConfigParser(); cur.read(os.path.join(os.path.dirname(__file__), 'looks.cfg'), encoding='utf-8')
    out = ['# looks_solved.cfg — Part B 矩阵求解草案（核对人眼后再替换 looks.cfg）']
    for key, (name, host, bn, axes) in solved.items():
        out.append(f'[{name}]')
        out.append(f'host   = {host}')
        out.append(f'mode   = {bn}')
        for short, lng in (('eff','effect'), ('con','contrast'), ('shp','sharpness'),
                           ('sat','saturation'), ('ton','toning')):
            out.append(f'{short:4s} = {axes.get(lng, 0)}')
        out.append(f'name   = {name}\n')
    for sec in cur.sections():
        if cur[sec].get('host', '').strip().upper() not in [h for _, h, _, _ in solved.values()]:
            out.append(f'[{sec}]  # 创意配方(未参与求解,原样保留)')
            for k, v in cur[sec].items(): out.append(f'{k} = {v}')
            out.append('')
    open(out_path, 'w', encoding='utf-8').write('\n'.join(out))
    print(f'[3] 草案 → {out_path}')
    print('    注: 求解轴域 sat/con/ton∈[-1,4] shp/eff∈[0,4](AXIS_RANGES);'
          ' err 仅排序参考,最终凭人眼复核')

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--demo', action='store_true')
    ap.add_argument('--matrix', action='store_true')
    ap.add_argument('--shots', default=r'D:\work\fp\dump\calib')
    ap.add_argument('--manifest', default=r'D:\work\fp\dump\calib\manifest.json')
    ap.add_argument('--targets', default=r'D:\work\fp\luts\targets')
    ap.add_argument('--out', default=r'D:\work\fp\tools\looks_solved.cfg')
    args = ap.parse_args()
    if args.demo:
        run_demo(args.targets)
    elif args.matrix:
        run_matrix(args.shots, args.manifest, args.targets, args.out)
    else:
        print('用法: --demo (photo19 演示) 或 --matrix (Part B 正式求解)')

if __name__ == '__main__':
    main()
