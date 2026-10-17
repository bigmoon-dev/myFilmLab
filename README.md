# FILMLAB — Sigma fp 胶片模拟包

Sigma fp 固件级胶片模拟：10 卷经典胶片色彩，通过 SD 卡装载，
RAM-only（拔电池=完全原厂），照片+EXIF 同步。

## 原理

利用 fpSup VBIN 装载机制在相机 RAM 中驻留一个监视任务：
- 监视 Color 模式状态变量，用户选择 DUO 变体时自动应用配方
- 配方 = 底座色彩模式 + 五轴微调（对比度/饱和度/色调/锐度/效果）
- 经固件官方 setter 链同步到 取景+捕获+EXIF 三层
- 选片后顶部 OSD 闪显胶片全名 2 秒

## 当前胶片阵容

| # | DUO 变体 | 胶片 | 底座 | EXIF 名 |
|---|---|---|---|---|
| 1 | R1 | Leica M Color | NTR | LEICA |
| 2 | OR1 | Portra 160 | NTR | PRT160 |
| 3 | YE1 | Kodak 5207 | STD | 5207 |
| 4 | YG1 | Ektar 100 | STD | EKTAR |
| 5 | G1 | Gold 200 | STD | GLD200 |
| 6 | G2 | Fuji 400H | NTR | FUJI4H |
| 7 | B1 | Kodak 5209 | STD | 5209 |
| 8 | B2 | Ricoh Positive | STD | RPOS |
| 9 | P1 | Ricoh Negative | NTR | RNEG |
| 10 | M1 | Velvia 50 | STD | VLV50 |

## 部署

1. SD 卡根目录放 `\fpSup.BIN`（dist/ 产物）和 `\FILMLAB\` 素材文件夹
2. `AutoRun.txt` 保持原版不动
3. 拔电池冷启动
4. Color 键 → DUO → 拨轮选变体 → 停留 3 秒 → 配方+名条自动出现

## 安全

- **零 flash 写**：全程 RAM-only，拔电池+拔卡 = 完全原厂
- 离线模拟门：unicorn 全路装载链+运行期验证，含实物负控五件套

## 项目结构

```
firmware/          boot.S + monitor.c + link.ld + Makefile
tools/             package.py(打包) gen_looks.py(配方表) simulate_load.py(模拟门)
                   make_panel.py(OSD素材) calibrate.py(标定求解)
autorun/           各阶段简报与设计文档
luts/              GlassMeter 胶片模拟 LUT (CC BY 4.0)
dist/              构建产物 + FILMLAB OSD 素材
reference/         fpSup 源码留档 + 历史版本负控 BIN
REPORT_MILESTONE.md  全程里程碑
```

## 逆向工程方法论

- 实机 dump → Ghidra headless 反编译 → ABI 提取 → 实现 → 模拟门 → 唯一次烧录
- 所有写入地址必须有"已知基址 dump 的逐字节实证"
- 模拟门与被测产物零共享假设（白名单硬编自独立证据）

## 致谢

- [fpSup](https://www.elcacharrista.com/) — VBIN 装载器架构与 USB shell
- [GlassMeter](https://glass.works) — 胶片模拟 LUT (CC BY 4.0)

## 许可

本项目代码仅供学习和个人使用。
Sigma fp 固件版权归 Sigma Corporation 所有。
