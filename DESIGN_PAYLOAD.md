# 配方装载器（Recipe Loader）设计 — A1/A2 交付 【架构定稿 v2】

> MVP：SD 卡开机自动生效的胶片模拟包。
> **定稿架构（用户拍板 2026-10-13）：DUO 借壳**——DUO 家族（用户从不使用）改名+换芯，
> 原生上下键变体导航 = 我们的风格选择器；隐藏槽 0x02/0x04/0x10 作配方底色原料。

## 0. 定稿架构（v2，替代 §6 旧方案）

```
Color 栏：..., POW B, W.GLD, FILMLAB(原 DUO)   ← 入口改名
选 FILMLAB → 上下键切变体（原生 DUO 导航，零钩子）
  变体 R1  = "PRT"  (底色 0x02 隐藏棕调 + sat3/con2/ton3)   ← Portra 风
  变体 OR1 = "KDK"  (底色 0x05 NTR + ...)
  变体 YE1 = "CCH"  (底色 0x00 STD + sat-1/con1 ...)         ← ClassicChrome 风
  ... 最多 10 条（每变体一条配方）
常驻任务：监测 0xC31F8914 ∈ {0x18..0x21} → 查表 → 切底色模式 + 应用 5 轴微调
牺牲面：仅 DUO 双色调（10 变体）；其余 15 模式 + 3 隐藏底色全保留
```

## 0.1 改名靶点清单（P1 实验对象）

| 目标 | 已知位置 | 形态 |
|---|---|---|
| Color 栏 DUO 缩写 | 语言资源库（活动语言 DB 内，待上机定位） | "DUO.R1" 为组合显示（前缀+变体码拼接） |
| 变体码 R1/OR1/... | N3 资源记录区 0xC0D0FB6F/0xC0D48593/0xC0D4927F/0xC0D4ADC0/0xC0D4CCDC 多份 + 各语言 DB | 待实读记录格式 |
| 内部符号表（勿动） | 0xC18D0100/0xC18DBD60 | 调试符号，非 UI 串 |
| 全名 DuoTone | 0xC097090C 等（名字表） | 菜单全名用 |

> MVP：SD 卡开机自动生效的胶片模拟包。用户在 Color 栏选冷门模式 = 选中我们的风格。

## 1. 产品架构

```
SD 卡（三件套）
├── AutoRun.txt      开机脚本：mem set 写引导补丁（照 fpSup 模式）
├── LOOKS.BIN        VBIN 容器：stage2 + 监视任务 + 配方数据 + 钩子
└── (可选) looks.cfg 用户可编辑的配方清单（构建时装进 BIN）

开机 → AutoRun 引导 → LOOKS.BIN 装载 → 陀螺钩子武装（50-90Hz）
     → 监视任务轮询 0xC31F8914（模式主拷贝）
     → 用户切到宿主模式（如 FOV B）→ 任务检测到 → 应用配方（5 轴微调）
     → 取景/成片/EXIF = 原生体验（EXIF 记 FOV B，P1 后可改显自定义名）
拔卡重启 = 完全还原
```

## 2. 关键地址表（全部已验证或来自 fpSup 源码）

| 用途 | 地址 | 来源 |
|---|---|---|
| 模式主拷贝（轮询目标） | 0xC31F8914 | 简报 8 写入验证 |
| 陀螺回调钩子位 | 0xC00D0794 | fpSup（50-90Hz 周期执行权） |
| 引导器洞区 | 0xC072DE64（≤0x200） | fpSup cave |
| 工作器安放 | 0xC072E800 | fpSup WORKER_AT |
| echo 命令劫持槽 | 0xC0BAC2F8（原 0xC03D99A0） | fpSup 执行权借道 |
| 内存池描述符 | 0xC072F6D8 | fpSup POOL_DESC |
| D-cache 清理 / I-cache 失效 | 0xC000E91C / 0xC000EABC | fpSup（必须，否则 CPU 跑旧缓存指令） |
| shell 读延迟 NOP | 0xC04215F4（原 0xEB00005D） | fpSup（AutoRun 解析 11.5s→3s） |
| 菜单 setter 名/描述/处理函数表 | 0xC0BBB5E8 起 | fpSup MENU_MODIFICATION |
| 模式镜像字节（不可写，只读） | 0xC31B32BC+0x12C | 简报 18/19 |

## 3. VBIN 容器格式（照抄 fpSup，已验证可用）

```
偏移 0:  "VBIN" magic (4B)
偏移 4:  段数 u32
偏移 8:  入口偏移 u32
偏移 12: body 长度 u32
之后:    段表 (addr, len)×N  — addr<0x40000000 = DMA 池相对偏移（开机加池基址）
之后:    各段 body（4 字节对齐）
```

我们的段布局：
```
[0] stage2 (dest=0，入口)      摆放+缓存维护+跳转
[1] monitor 任务 (dest=0xC072E800)  监视+配方应用
[2] 配方数据表 (dest=池偏移)    N 条 {host_mode, sat, con, ton, shp, eff}
[3] 钩子武装段 (dest=0xC00D0794) 内容=bl monitor_entry
```

## 4. 监视任务逻辑（ARM 伪码）

```
last_applied = -1
loop (每次陀螺回调):
    mode = *(u8*)0xC31F8914
    if mode != last_seen:
        last_seen = mode
        recipe = lookup(RECIPES, mode)      // 宿主模式查表
        if recipe:
            wait_settle(50ms/若干拍)         // 等引擎应用完模式切换
            apply(recipe)                    // 5 轴写入（机制见 §5）
            last_applied = mode
```

## 5. 配方应用机制 —— 三个候选，P2 实验定夺

| 机制 | 说明 | 风险 |
|---|---|---|
| a) 直调 setter 函数 | 从 0xC0BBB5E8 表取 SetColorModeSaturation 等处理函数地址，ARM 调用约定直调 | 需逆向调用约定（argc/argv 形态），工作量大 |
| b) 写底层存储+触发事件 | 找到 5 轴在 UI 设置区的字节，直写后调 event 系统刷新 | 0x12C 教训：镜像字节不可写——但微调字节未必同构，P2 验证 |
| c) UI 设置区字节 + 模式重选触发 | 写字节后，借"任意按键 UI 重推"行为让重算读到新值 | 最 hack，依赖重推读存储的路径（fpSup 的 MovRecSize 案例正是此路！） |

**倾向 c→b→a 顺序验证**（成本递增）。fpSup MovRecSize 案例（改元数据→set→主设置变化且录影保持）证明"改源数据+触发重算"这条路在这台机器上成立。

## 6. 配方文件格式（A2，用户可见层）

文本格式（构建脚本转成 BIN 数据段）：
```ini
# looks.cfg — 每条 = 一个宿主槽的配方
[Portra400]
host   = 0x0E        ; FOV B 槽
mode   = 0x05        ; 底色模式 NTR
sat    = 3
con    = 2
ton    = 3           ; 暖调
shp    = 0
eff    = 0
name   = "Portra400" ; P1 名字表用

[ClassicChrome]
host   = 0x0F        ; FOV Y 槽
mode   = 0x00        ; STD 底
sat    = -1
con    = 1
...
```
注：`mode` 字段 = 配方先切底色模式再叠微调（监视任务检测到宿主模式 → menu 引擎切底模式 → 应用微调）。
**设计决策点**：是否允许配方改底色模式（用户选 FOV B 实际渲染 NTR 底+微调）——UI 显示与实际模式脱钩，EXIF 记 NTR。P1 名字表解决显示名后此脱钩无感。

## 7. 里程碑与验证（P1-P3 简报蓝图）

- **P1 名字表实验**（1 次相机）：改 0xC0970xxx 名字区字符串 → Color 栏/EXIF 是否显示新名
  → 里程碑：自定义名进 UI/EXIF
- **P2 微调传播实验**（1 次相机）：
  a) menu dump 逐轴 diff → 定位 5 轴存储字节
  b) 直写字节 + 按键触发 → 是否传播
  → 里程碑：配方应用机制定案（§5 三选一）
- **P3 端到端**（1 次相机）：完整三件套上卡 → 开机 → 切 FOV B = Portra400
  → 里程碑：MVP 发布

## 8. 构建工具链（我方离线部分）

- `tools/build_looks.py`：looks.cfg → LOOKS.BIN + AutoRun.txt 生成器
- 汇编：AArch32（ARM32）——用 fpSup 同款流程（clang 汇编/手工编码）
- 宿主环境：用户 WSL2（已有 clang，构建 fpSup 时装过）
