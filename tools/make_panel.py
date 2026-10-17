"""make_panel.py — v11 OSD 面板素材生成器

格式（FPSUPUI 资产逆向实证）：1024×56，ARGB1555 小端（bit15=不透明，
0x0000=透明），行距=2048B 无填充。splash 的白 0xFFFF / 粉 0xFD35 同款编码。
产出 dist/FILMLAB/：
  0..9.BIN  十条胶片名条（◂ ▸ 导航提示 + 全名 + 序号）
  B.BIN     全透明空白条（关闭时覆盖 + 恢复重绘双保险）
  T.BIN     K5 显示层实测用测试图（色条 + offset 刻度）
"""
import configparser, os, struct, sys
from PIL import Image, ImageDraw, ImageFont

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, '..', 'dist', 'FILMLAB')
W, H = 1024, 56

WHITE = 0xFFFF
PINK  = 0xFD35
DARK  = 0x8210     # 深灰底 (r4,g4,b0 → 视觉近黑)
GRAY  = 0x8430

def argb1555(r, g, b):
    return 0x8000 | ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)

def render(idx, name, title, total):
    img = Image.new('RGB', (W, H), (0, 0, 0))
    dr = ImageDraw.Draw(img)
    dr.rectangle([0, 0, W - 1, H - 1], fill=(16, 16, 8))          # 不透明深底
    dr.rectangle([0, 0, 3, H - 1], fill=(255, 130, 140))           # 左缘粉条
    f_big = ImageFont.truetype('arialbd.ttf', 30)
    f_sm  = ImageFont.truetype('arial.ttf', 18)
    # ◂ ▸ 用多边形画（字体无此字形）
    dr.polygon([(28, 20), (28, 36), (16, 28)], fill=(200, 200, 200))
    dr.polygon([(64, 20), (64, 36), (76, 28)], fill=(200, 200, 200))
    dr.text((110, 8), title, font=f_big, fill=(255, 255, 255))
    dr.text((112, 40), 'FILM LAB · %s' % name, font=f_sm, fill=(255, 150, 160))
    t = '%d/%d' % (idx + 1, total)
    tw = dr.textlength(t, font=f_big)
    dr.text((W - 30 - tw, 14), t, font=f_big, fill=(255, 150, 160))
    px = img.load()
    out = bytearray()
    for y in range(H):
        for x in range(W):
            r, g, b = px[x, y]
            out += struct.pack('<H', argb1555(r, g, b))
    return bytes(out)

def blank():
    return b'\x00\x00' * (W * H)

def testpat():
    img = Image.new('RGB', (W, H), (0, 0, 0))
    dr = ImageDraw.Draw(img)
    f = ImageFont.truetype('arialbd.ttf', 22)
    cols = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0), (0, 255, 255), (255, 0, 255), (255, 255, 255)]
    for i, c in enumerate(cols):
        dr.rectangle([i * 146, 14, (i + 1) * 146 - 1, 40], fill=c)
    for x in range(0, W, 128):
        dr.line([x, 0, x, 55], fill=(90, 90, 90))
        dr.text((x + 4, 42), str(x), font=f, fill=(255, 255, 255))
    px = img.load()
    out = bytearray()
    for y in range(H):
        for x in range(W):
            r, g, b = px[x, y]
            out += struct.pack('<H', argb1555(r, g, b))
    return bytes(out)

def main():
    cfg = configparser.ConfigParser()
    cfg.read(os.path.join(BASE, 'looks.cfg'), encoding='utf-8')
    by_host = {}
    for sec in cfg.sections():
        g = cfg[sec]
        host = g.get('host').strip().upper()
        idx = int(host.split('_')[1].replace('R1', '18').replace('OR1', '19'))  if False else None
        # DUO_R1..DUO_M1 → 0x18..0x21 顺序表
        order = ['DUO_R1','DUO_OR1','DUO_YE1','DUO_YG1','DUO_G1','DUO_G2','DUO_B1','DUO_B2','DUO_P1','DUO_M1']
        idx = order.index(host)
        by_host[idx] = (g.get('name'), g.get('title', g.get('name')))
    os.makedirs(OUT, exist_ok=True)
    n = 0
    for i in range(10):
        if i in by_host:
            name, title = by_host[i]
            open(os.path.join(OUT, '%d.BIN' % i), 'wb').write(render(i, name, title, 10))
            n += 1
    open(os.path.join(OUT, 'B.BIN'), 'wb').write(blank())
    open(os.path.join(OUT, 'T.BIN'), 'wb').write(testpat())
    print('wrote %d strips + blank + test to %s (each %dB)' % (n, os.path.abspath(OUT), W * H * 2))

if __name__ == '__main__':
    main()
