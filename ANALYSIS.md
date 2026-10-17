# SIGMA fp 固件 (FP__V502.BIN) 逆向分析笔记

> 分析日期: 2026-10-10 · 固件版本: DVR=5.02 (内部 VER=V91, 平台代号 w71c1) · 文件大小: 25,692,160 字节

## 1. 固件容器结构

```
0x000000  tar 风格头: "LENGTH=24503296 w71c1 VER=V91 DVR=5.02 SUM=... IPL PTBL DAT1"
0x000100  @DFI 头 (版本1) + 分区表
             +0x20: 0x02EF6E00   镜像总大小/解压目标
             +0x28: 0xC0000000   加载地址 (SDRAM)
             +0x34: 0x01740E00   DAT1 偏移
             +0x38: 0x00039A00   段大小
             +0x48: 17           表项数
0x000300  LZSS 压缩流起点 (解压输出以 ARM 向量表 e59ff018 开头)
0x3F9CC7  (同一流内的重同步点, 扫描发现)
0x1740E00 DAT1: 独立 LZSS 流, 内容为大端 float 表 (增益/曝光曲线, 值域 -2.1 ~ -7.0)
0x1760000 零填充
0x1770000 硬件寄存器初始化表 (外设 0x300A8000+, 共享 RAM 0x2E000000)
0x1780000 DCT/无损JPEG 编解码器自检数据块 (512点14bit余弦表 + 1122..ff 测试阶梯, 134 块)
0x1880800 EOF
```

## 2. 压缩格式 (已破解 90%)

自定义 LZSS 变体:
- 每字节标志管 8 个项目, **LSB 优先**, **1=字面量, 0=匹配**
- 匹配 = 2 字节小端: **长度 = 高4位 + 3** (3..18) ✅ 已用已知明文证实
- 偏移 = 低 12 位, 语义未完全解决: 匹配引用一个 4096 字节**预初始化字典**
  (内容既不是流前原始字节、也不是空格/零 → 疑为上一级引导程序构建的表)
- 结论: **字面量区 100% 正确** (所有字符串/表格), 匹配复制区有噪声
- 主流从 0x300 解压后约 61.6MB, 加载到 0xC0000000

## 3. 相机工作原理 (从字符串/结构推断)

### 启动流程
Flash → IPL → 解压主镜像到 0xC0000000 → 自研 RTOS (无 Linux/u-boot 痕迹;
有线程序、邮箱、XC_Queue/XC_Observer 模式) → shell (读 SD 卡 AutoRun.txt 脚本)

### 软件模块树 (源码路径透出)
```
src/hal/ImageSensor/        传感器驱动 (config/IMX410, config/IMX455)
src/hal/Lens/               镜头 HAL
src/hal/SdkSigproConv       Sigma 处理转换 (DSP 管线驱动)
src/driver/AF               自动对焦驱动 (PDAF + 反差)
src/library/CameraController/  相机控制 (AfMgr/, PictureQuality/, Simulator/)
src/library/SigProcess/     图像处理
src/library/DetectionMgr/   检测管理 (人脸/眼部?)
src/library/LiveViewState/  取景状态
src/library/UserS...        用户设置
src/library/Fwup/           固件升级
src/library/TempAdcConversion  温度 ADC (过热保护)
src/library/DeviceOperation 设备操作
src/apl/ui/, src/apl/gui/   UI/GUI (多语言: 丹麦语/韩语/日语资源都在)
src/apl/oem/ui/             OEM 定制 UI
src/shell/src/cmd/          Shell 命令 (AutoRun.txt)
src/Utils/xclib/            XC 基础库 (Observer, Queue, OpNew)
src/Movie/                  视频录制
ext_SdkDrv/src/Movie/       外部 SDK (SoC 厂商, "XC_" 前缀)
```

### 硬件
- 传感器: **Sony IMX410** (fp 24.6MP 全画幅 BSI); 固件同时含 **IMX455** (fp L 61MP) 配置
- SoC: 未识别厂商; ARM 核; 外设空间 0x300A8000; 硬件 JPEG/DCT 编解码器 (自检块)
- 陀螺仪/IMU: accel_x/accel_y/gyro/gyro_p (日志 + 元数据, 社区证实 2.5kHz, FPG2 MakerNote)
- 卡口: L-mount 协议 + **MC-21 佳能 EF 适配器**协议栈 ("MC-21 CANON EF-" 镜头库条目)
- 相机音效: 内嵌 WAV (Sound Forge Pro 12.1 制作, 音效师 sugar-keiki@infoseek.jp, 2020-02)

### 视频管线
- CinemaDNG (无损 JPEG 硬件编码, "Movie_CinemaDNG_Warn" 等字符串)
- ARRIRAW 外录支持 (ARRI/ALEXA 引用 ×130)
- ProRes 引用 (外录菜单)

## 4. 色彩管理 (重点)

### 4.1 色彩模式 = "调色板" 系统
实现类: **PaletteColor.cpp** (`src/library/.../PaletteColor` 调试路径透出)。
完整模式表 (0x363FC80 区域, 15 种):
```
Standard, Portrait, Vivid, Landscape, Cinema, Sunset, TealAndOrange,
ForestGreen, Neutral, PowderBlue, FCBlue (FOV Classic Blue), FCYellow,
WarmGold, DuoTone, Monochrome
```
- 每模式附带浮点参数 (double/float): 如 -0.8, -0.6 (色调/饱和度偏移),
  1.0417 (=25/24), 0.9167 (=11/12) (通道增益)
- DuoTone 为双色映射模式, 有独立 OFF/子选项表 ("Neutral/DuoTone/OFF/VTone..." 枚举)

### 4.2 色彩空间与白平衡
- 输出色彩空间可选 **sRGB / AdobeRGB** (菜单字符串多处)
- 白平衡: AWB 模块 + 色温结构 ("kelvin=%u" 调试格式串, ColorTemp/ColorTem 结构)
- D65/D50 白点引用

### 4.3 处理管线中的色彩数据
- `PictureQualityFuncThread` — 画质专用线程 (src/library/CameraController/PictureQuality/)
- `XC_ImageRequestOutputStyles` — 带输出风格的图像请求 (SDK 接口)
- DAT1 (0x1740E00): LZSS 压缩的**大端 float 曲线表** — 增益/曝光/色调曲线
- 解压镜像中大量 ±0.1..±0.8 浮点参数簇 = 各模式微调值
- CCM (色彩校正矩阵) 引用 ×147 (区域有匹配噪声, 结构待完美解压后确认)

### 4.4 工作模型 (综合推断)
```
传感器原始数据 (IMX410, 14bit)
  → 黑电平/OB 校正, 坏点
  → 白平衡增益 (kelvin 表 → RGB gain)
  → CCM (传感器原生 → 工作色彩空间)
  → PaletteColor: 按所选模式应用调色板变换 (矩阵+曲线+饱和度参数)
  → 输出风格分支:
      JPEG: sRGB/AdobeRGB + 色调曲线 → 硬件 JPEG 编码
      CinemaDNG: 无损 JPEG (预测器+熵编码, 硬件引擎) 
      MOV/H.264: 视频管线 (Cinema 色彩模式)
```

## 5. 色彩参数块逆向（第一步）进展

### 已确认
1. **表布局**：名字串表与参数数据是**分离的两段**（经典 `names[] + params[]` 并行数组）：
   - 名字块：`0x6C2DDE–0x6C2F10`（15 模式 + "OFF" 连续排列，顺序：
     Standard, Vivid, Neutral, Portrait, Landscape, Cinematic, WarmGold,
     TealAndOrange, Sunset, ForestGreen, PowderBlue, FCBlue, FCYellow,
     DuoTone, Monochrome — **这就是调色板索引顺序**）
   - 参数块：紧跟其后 `0x6C2F10+`，含 IEEE-754 双精度浮点
2. **参数值样例**（字面量 100% 可信）：-0.8、-0.6、-0.4、-0.2（精确值，等差序列，
   疑为色调/饱和度偏移或步长表）；0x3F 前缀 float（0.7~1.9 区间，增益类）
3. **16 字节周期记录**：参数区存在重复的 ~16 字节结构（4×float 或 1×struct），
   匹配 token 证实其周期性
4. **第二实例** `0x6E3400`：同名表 + 大端 float 表（0xC0D2–0xC0EC ≈ -6.5~-7.0，
   与 DAT1 同族）+ "ColorTem" 结构——白平衡/色温相关参数
5. **UI 字符串表** `0x35D3D00`：含 Custom1/2/3（自定义槽）、白平衡预设名
   （Daylight/Fluorescent/Incandescent）
6. 至少 5 份表副本散布镜像中（0x2A1B00 / 0x363FC80 / 0x6C2C80 / 0x6E3400 / 0x2A2275），
   均受匹配损坏影响（字面量覆盖 15-37%）
7. 内部状态名（AutoRun/shell 可操作对象）：ST_COLBKT_ColorMode、St_color、G_iso_multiShot

### 压缩解码遗留问题（已封存）
- 环形缓冲相位 s0=4078（N−F）已被样本严格证实，但全部环形变体（r0 × fill ×
  i偏置 × r推进方式 × 匹配写环与否 × source=i+ln）全局测试均失败——
  存在未知的环状态机制，错误从流头部级联传播
- 字面量数据（全部字符串+表格锚点）不受影响，100% 可信

### 结论与下一步
静态逆向已到收益递减区。**改走运行时内存 dump**（社区同款路线）：
1. 在 SD 卡放 AutoRun.txt，用 shell 命令在运行时 dump 调色板 RAM 区
   （起点：解压镜像中定位到的表地址 ± 运行时指针 0x2E00D6D0 区域）
2. 逐项切换 15 个模式 + 3 个 Custom 槽，diff dump → 直接得到每个参数的
   语义映射（比静态分析快一个量级）
3. 结合已确认的索引顺序和参数类型（double/float/16字节记录），
   即可写出"第 16 号模式"补丁验证全链路

## 7. 后续工作建议

0. **运行时 dump 路线（已就绪）**：交付物在 `autorun/` 目录：
   - `AutoRun_dump.txt` — 开机静态 dump 脚本（9 个目标区）
   - `README_workflow.md` — 三阶段工作流（静态 dump → USB 交互切模式 diff → mem set 写入验证）
   - 工厂 shell 77 条命令（fpSup 真机实测文档 SHELL_COMMANDS.md）：
     `mem save \f.bin <addr>,,size`、`mem get/set`、`setting get/set`、`pic`、
     `wb get_kelvin`、`ts ram <dst><src><size>`（证实 LZSS 由硬件解压）、`dfi load`
   - 命令表 RAM 0xC0BAC14C（77×{name[20]+handler*4}）；AutoRun 由固件
     `XC_ShellScriptAutoRun` 开机执行，无权限校验；USB Shell 走 PTP 寄生模式
   - **危险**：`prom write` 会毁校准数据，绝对禁止
1. 相机上执行 dump，验证地址模型（0xC0000000+镜像偏移）
2. 切 15 模式 + Custom 槽逐个 dump，diff 出参数语义
3. 完成参数块格式文档，写"第 16 号模式"验证补丁
4. （可选静态线）DAT1 浮点表语义、0x1770000 寄存器表逆向
5. 社区资源: fpSup (github.com/ijigen/fpSup, ijigen.github.io/fpSup),
   julienacquaviva/sigma-fp-supmod, obra/sigma-fp-automation

## 8. 提取产物 (extract/ 目录)

- `firmware_dec.bin` — 61.6MB 最佳可用解压镜像 (字面量区正确)
- `dec_strings.txt` — 全部字符串 (65.5万条)
- `strings_all.txt` — 原始文件字符串 (11.4万条, 含压缩流透出片段)
- `dat1_dec.bin` — DAT1 部分解压
- 各分析脚本 (decompress.py, decode54.py, grid.py, scan3.py ...)
