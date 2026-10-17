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

## 色彩配方标定方法

配方不是手调的——用**数据驱动**的标定管线求解：

### 1. 地面真值（Ground Truth）

30 个 [GlassMeter](https://glass.works) 胶片模拟 LUT（CC BY 4.0）——
社区用**真实胶片扫描**标定的 3D LUT，覆盖 Kodak Portra/Ektar/Gold、
CineStill、Fuji 400H/Velvia、Ilford、Kodak B&W 等。

### 2. 相机响应矩阵（Part B，33 张）

用固件官方 setter 链对测试图（`tools/testchart.png`）拍照：
- 5 个底座（STD/VIV/NTR/CINE/MONO）的基线
- STD 底座的五轴单变量增量（对比度/饱和度/色调/锐度各档）
- 负档线性度验证

每张照片提取 16 个色块的 Lab 均值 → 建立线性响应模型。

### 3. 跨底座贪心求解

```
tools/calibrate.py --matrix --shots dump/calib --targets luts/targets
```

对每个胶片 LUT 目标：遍历所有底座 × 轴参数组合，
最小化色块误差（Lab 空间欧氏距离）→ 产出 `(底座, 五轴)` 最优解。

### 4. 已知局限

- **分辨率极限**：五轴是线性调整，同系列胶片会塌缩同解
  （如 Portra 160/400 在参数空间里不可区分——已如实披露）
- **底座覆盖**：Part B 只标定了 5 个底座，fp 共有 15 个可用
  （补拍 9 个底座的基线即可扩展）
- **误差仅排序参考**：最终配方以人眼复核为准

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

本项目采用 [GPL v3](LICENSE) 许可（因内嵌 fpSup GPL v3 组件）。

- [fpSup](https://github.com/ijigen/fpSup) — GPL v3，作者 ijigen/Bei
- [GlassMeter](https://glass.works) LUTs — CC BY 4.0
- Sigma fp 固件版权归 Sigma Corporation 所有（本项目不分发固件原像）
