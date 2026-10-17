# SIGMA fp 色彩模式逆向工程 · 里程碑报告（2026-10-11）

> 实验闭环达成：内存差分 → 候选地址 → 写入验证 → 主拷贝锁定，全链路打通。

## 一、核心成果：模式变量拓扑（简报 8 写入实验）

以 MONO 态（变量=01）为基线，写入 03（Vivid）逐处试探：

| 地址 | 写入后行为 |
|---|---|
| 0xC2F19D44 | 命令成功但 ~1 秒被改回 01（从拷贝，自愈） |
| 0xC3074E60 | 值存得住、画面无反应（被动缓存） |
| **0xC31F8914** | **取景器实时由黑白变 Vivid 彩色 ← 主拷贝（管线活源）** |
| 0xC3413B7C | 被改回 01（从拷贝） |

配套发现：
- UI（Color 快捷栏）与管线主拷贝互相独立——写主拷贝后 UI 仍显示 MONO；
  按 Color 键打开选择器，UI 会把真模式重推回主拷贝（自愈，无需手工还原）
- pic_color_mode setting 与菜单 Color Mode 双向解耦（两轮独立验证）
- 已验证模式编码：STD=0，MONO=1，Vivid=3，TealAndOrange=10
- ddr 硬件写日志器对 CPU 发起的写物理盲区（"XZ01 can not log the CPU"）

## 二、内存地图（实测边界）

| 区域 | 结论 |
|---|---|
| 0xC0000000 主镜像 + 远区（C11/C14D/C283 等） | 可读 |
| DSP 0x2E000000–0x2E028000 | 安全区（精确止于 0x2E028000） |
| 0x2E028000–0x2E030000+ | 不可读间隙（读取致 worker 挂死） |
| 0xC2EF6E00 之后 | 堆区（运行时状态所在，模式变量于 0xC2F1xxxx–0xC34xxxx） |

## 三、通往"第 16 号模式"的剩余路线

1. **补全 15 模式索引映射**：逐模式切换 + `mem get 0xC31F8914`，填全 0-14 ↔ 模式名对照表
2. **越界索引实验**：主拷贝写 15（出界值）——引擎按索引查参数表的行为 = 注入入口
3. **参数侧定位**：用"直写索引"（绕开 UI，SNR 更干净）重做差分；
   重点候选：0xC3406BF4 的 15 字节模式相关参数结构（四态四值：
   TO=`02|1001×5`、STD=`03|0a01c800×3`、VIV=全零、MON=`02|4d01fa00×2`）
4. 参数表到手 → 自定义参数包 → loader（fpSup VBIN 格式）→ 发布

## 四、数据资产

D:\work\fp\dump\ 共 33 文件（MD5 校验）：LOC/CMDS、M/N 系列、G/G2/R、F 系列、
C_STD2/V_VIV/V_MON —— 覆盖五态 × 多窗口。

## 五、基建与运维经验（复用）

- 环境：WSL2 + usbipd + fpSup v3 loader（Makefile 三处本机适配：-lrt / python3.9 / --loader）
- 零残留：全程 RAM-only；退场 = 恢复默认设置 → 删卡上三件套 → 重启
- usbipd 路径通道特性：bulk 应答随机丢 + 数秒死窗 → putfile.sh 重试；
  大文件 mem save 重试风暴淹死 worker → retries=0 + 10-15s 超时单发；
  worker 挂死恢复 = usbipd detach/attach 软复位；电池耗尽伪装死机——先排除电压

---

# 里程碑追加：VBIN 开机冻结根因破解（2026-10-14）

> v1-v3 三版自制 fpSup.BIN 开机冻结的根因已定位并修复，v4 通过 unicorn 全路
> 离线模拟（正测 20/20 PASS + v3 实物复刻负控 FAIL），待上机终验。

## 一、根因：entry 字段语义写错（不是文件物理形态）

fpSup `stage2.S` 对 VBIN 头 +0x08 entry 的真实语义（源码+官方打包器双重印证）：

| entry 值 | 语义 |
|---|---|
| 0 | 不调用入口 |
| < 0x40000000 | **从 buffer 起点（"VBIN" 魔数）算的偏移**，`addlo r0, r0, r6` 后 blx |
| ≥ 0x40000000 | 绝对地址，直接 blx |

依据：`stage2.S` 入口处理段；`build_autorun.py:1074` `file_off(i) = 16 + 8*count + at[i]`
（官方打包器明确把头部16B+段表8N 计入偏移）；loader.S 头注释只说了后半段语义。

**v3 的 package.py 写的是 body 相对偏移**（少了 16+8×count=0x40）：entry=0x4D8 而非
0x518 → stage2 跳进 stage2 本体 +0x498 = `lh_unhook` 日志回放循环中段，r4=栈指针
被当成日志游标 → 乱写 + sp 被换成 buffer → pop pc 进 VBIN 头数据区 → 冻结。
v1/v2 更基础：段0 放的是 12B 跳板而非 stage2，loader blx 跳板直接跳进从未摆放的
洞区（没有 stage2 就没有两段摆放）→ 同源冻结。三版同一冻结点因此成立。

**嫌疑①（文件形态 3114B vs 32768B）正式排除**：`build_autorun.py:1104` 注释
"file-length padding is obsolete"；8192B 的 gyro 发布卡正常开机；loader 的
F_READ 按设计就是"请求量大于文件上限"（MAXLEN=0xF000 > 任何 BIN）。

## 二、stage2.bin（原版 1240B）反编译审计结论

- 编译配置 = LH_RESTORE + SPLASH_FINISH；**无 STORE_PROVISION（无 flash 写，
  RAM-only 红线成立）**、无 ARM_ABORT、无 LOADER_HOOK（不武装 0xC03DA420）
- lh_setup 用固件分配器建日志块并注册关机回调×2（普通+强制）；我们的段全在
  洞区（0xC072E800..0xC072EF08 < CAVE_HI），lh_want 判定洞区段不入日志 →
  关机恢复为零操作；冷启动（拔电池）= 完全原厂
- 常量印证：CAVE 凹凸指针 0xC072E060/64、FRAMEBUF 0xC3757A7C、
  LOAD_DONE_US=0xC072F6F8、splash 屏 0xC0528700 等全部对上号
- 另发现段长度契约：每段必须 4 的倍数（stage2 按字拷贝，v3 的 .bss 26B 违规
  会漏拷头 2 字节——v4 已修）

## 三、v4 修复内容（tools/package.py）

- entry = 0xC072E800 绝对地址（= boot_entry，pass1 摆放+cache 发布后被 blx 调用）
  ——与仓库现行 fpSup.BIN（entry=0xC072F188 绝对地址）同款模式；删除跳板段
- 段长统一向上取整到 4 的倍数；总长断言 ≤ 0xF000（loader MAXLEN）
- 产物：`dist/fpSup.BIN` 3096B，5 段（stage2 1240B 逐字节原版 + .text/.exidx/
  .rodata/.bss），AutoRun 不动

## 四、离线验证（tools/simulate_load.py，unicorn 2.1.4）

用官方 AutoRun mem set 抠出的真实 loader 字节（316B @0xC072DE64）+ 原版 stage2 +
v4 BIN，固件函数按 ABI 打桩，写白名单审计，逐指令跑完装载全链：

- 正测 20/20 PASS：F_OPEN("\\fpSup.BIN")→F_READ(0xF000)→魔数→段0→日志块+关机
  回调→四段逐字摆放→entry 恰好调用 1 次→tk_cre_tsk(monitor_main=0xC072E880,
  pri28, stk 0x2000)+tk_sta_tsk→返回→LOAD_DONE_US→splash(osdfile×3+sleep 2000)
  →归还池→loader 返回 1；零非法访存/越界写
- 负控（v3 实物复刻）：审计精确捕获 lh_unhook 的野写（pc=buffer+0x4E4=
  stage2+0x4AC 的 `str r3,[r0],#4`，与实机冻结推导逐字节吻合）→ FAIL
- 暖重启无需防重入守卫：loader hook 未武装时每次开机 AutoRun 恰好调用 entry 一次；
  T-Kernel 暖启动重建任务表（fpSup 全架构依赖此事实），worker.S 的 'VSHL' 守卫是
  防同代多入口点重复 spawn，不适用我们的单调用点

## 五、上机终验协议

1. 卡上 `\fpSup.BIN` 换为 dist/fpSup.BIN（3096B），AutoRun.txt 保持原版不动
2. 拔电池冷启动 → 预期进度条走完显示 `fpSup!`，相机正常
3. Color 键选 DUO → 上下键切 10 变体，取景器应实时换底色+五轴，EXIF 记自定义名
4. 异常兜底：拔电池+拔卡即完全还原（v4 无任何 flash 写，已逐字节审计）
5. 若仍冻结（不应发生）：唯一未排除变量是用户卡的 AutoRun 变体差异——
   用 USB shell `mem get 0xC072F6F8,,4` 读 LOAD_DONE_US 判断装载走到哪一步

---

# 里程碑追加：P3 MVP 跑通 + EXIF 空名根因修复（2026-10-14 晚）

> v4 上机一次通过：开机/进度条/fpSup!/取景/配方应用/自愈/重启存活全 ✓。
> 唯一缺陷：DUO.R1 张 EXIF 色彩名为空（非 PRT400）。已定位修复 → v5。

## 一、空名根因（实机照片 + dump 双重取证）

1. **v4 把运行时名字池当成了"16B 定长槽表"**。0xC0970904 实际是**紧缩字符串池
   +指针表**：`"Neutral\0"`(0904) 紧挨 `"DuoTone\0"`(090C) 紧挨 `"OFF\0"`(0914)…
   v4 往 NTR 槽写 16B（"PRT400\0"+9 个零）→ **把邻接的 DuoTone 串清零**。
2. **序列化器按"选定模式"取名**（DUO 家族），不看我们改的 MODE_MASTER 底色：
   DUO 张的名字源 = "DuoTone" 串 → 被我们清零 → EXIF 名=空。
   （反证：若按底色取名，v4 写入的 "PRT400" 本会出现在 NTR 槽 → 不是空。）
3. exif_slots.json 是差分指纹（地址+当时值）混合体，不是槽位起始表——弃用。
4. R1 张参数区的 NaN/±Inf 是**原厂 DUO 张固有**（0585 原厂张同图案），非我方 bug。

名字串全部已验证位置（dump 逐字节确认，均恰好容纳 8B 写）：
| 地址 | 位置 |
|---|---|
| 0xC097090C / 0xC09709F4 | 运行时池 copy A/B（M_1/SW_* 实测） |
| 0xC05CD094 / 0xC0614B3C | 镜像模板表两份（C_STD2；前者后跟 32B 零，后者 8B 恰好邻接 Monochrome） |

## 二、v5 修复（monitor.c + gen_looks.py）

- 写目标从"底色模式槽"改为 **DUO 家族名字串的 4 个副本**，定长 **8B**（≤7 字符+NUL），
  不再碰任何邻接字节；写镜像模板表还有红利：固件重建池时也带上我们的名字
- 备份/恢复简化为一次性备份 "DuoTone\0"、退出还原（名槽与底色解耦，
  变体间切换直接覆写）
- gen_looks.py 弃用 exif_slots.json，硬编 4 个验证地址 + 名字 ≤7 字符断言
- 产物：`dist/fpSup.BIN` v5 = 2772B（sha1 0717e413cdb1447e），unicorn 全路
  20/20 PASS（段摆放逐字一致、entry 一次、建任务参数正确、零越界写）

## 三、上机验收点（v5）

1. DUO.R1 拍照 → EXIF 名应为 **PRT400**；其余变体各拍一张核名
2. 切回 STD → 拍照应为 Standard（名槽还原）
3. 分流判断：若显示 "DuoTone"（非空非 PRT400）= 序列化器读了远端未覆盖副本
   → 需补 dump 0xC0CC2FE8/0xC2DFD08C/0xC2E44ABC 区（DUO 态）再扩展槽单；
   若仍为空 = 回报照片文件，重新取证（v5 已无 16B 越界写，空名不应再现）
4. 副产品观察：Color 菜单的 DUO 标签在配方激活期可能显示 PRT400（设计内）

## 四、待办更新

- Part B 标定矩阵（20 张量化）仍需换回原版 BIN 恢复 USB shell
- 配方区分度调优（OR1/YE1/YG1）
- 相机语言非英语时池内容未验证（模式名通常不本地化——残留风险，写入
  全程等长 8B，最坏结果 = EXIF 名不变，无损坏路径）

---

# 里程碑追加：D_*_heap 基址锚定 + 捕获链候选变量（2026-10-15 路线裁决取证）

> v7 实机全通（预览层），残留唯一架构问题：快门重推是同步链，
> 轮询重应用只能赢取景、赢不了捕获 → 照片内容=原厂。裁决前取证如下。

## 一、D_*_heap / C_STD2 基址锚定 = 0xC2830000（三个独立证据互证）

三态 diff（D_std/D_viv/D_duo，同基址 13MB）筛"std=00/viv=03/duo=18"字节，
6 处强候选中的 3 处把基址钉死：

| 文件偏移 | 绝对地址 | 身份 |
|---|---|---|
| +0x9C8914 | **0xC31F8914** | MODE_MASTER 主拷贝（里程碑已载） |
| +0x6E9D44 | **0xC2F19D44** | 从拷贝（里程碑已载，自愈） |
| +0xBE3B7C | **0xC3413B7C** | 从拷贝（里程碑已载，自愈） |

⇒ C_STD2 当年的"名字串"实为 0xC2DFD094 / 0xC2E44B3C（远区运行时表），
v5 的错不在"串找错"而在"基址假设错"。**dump 基址锚定方法入库**：
找三态强候选 ↔ 已知地址对照，或已知基址 dump 的内容指纹互锚。

## 二、远区 EXIF 名串副本（DUO 态逐字节实证）

- 0xC2DFD094："DuoTone\0"+长零（≥16B 窗口）；所在表还含 Shade/Flash/Auto 等
- 0xC2E44B3C："DuoTone\0"，8B 后邻接 "Monochrome"（恰好 8B 窗口）
- 序列化器源仍是池（0xC09709xx，v4 空名排除法成立）；远区两份是否被读未证——
  若 UI 标签不显示配方名，扩槽单时先加这两份（8B 写，安全窗已验）

## 三、捕获链"当前模式"候选变量（三态全跟模式）

| 地址 | STD/VIV/DUO | 备注 |
|---|---|---|
| 0xC31F8914 | 00/03/18 | 主拷贝（我们写它，取景听它） |
| 0xC2F19D44 | 00/03/18 | 从拷贝（自愈） |
| 0xC3413B7C | 00/03/18 | 从拷贝（自愈） |
| 0xC3413F90 | 00/03/18 | 独立字 |
| 0xC3414D08/0xC3414D0C | 00/**01** 对 | {flag, mode} 记录 1：flag 仅 DUO=1 |
| 0xC3414D10/0xC3414D14 | 00/**01** 对 | {flag, mode} 记录 2（双管线？） |

快门重推的源 = 其中之一（或 UI 侧另一变量）。离线不可终定，需一次探针会话。

---

# 里程碑追加：K3 探针 + v8 官方链架构（2026-10-16）

> K1✓（五轴进捕获）K2✗（RAM 变量全不读）K3✓✓（menu 层 SetColorMode 三层同步）。
> v8 = apply 直调 menu 官方 setter，快门同步链自此推我们的值。

## 一、K3 探针定论（实机）

- `menu SetColorMode <n>` 存在且走官方"当前模式管理器"（0xC31AC51C 区）：
  取景+照片+EXIF+选择器高亮四层同步；快门后主拷贝保持设定值（接管实锤）
- menu 域 = 紧凑菜单序号（**v8 初版误判、实拍修正**：正确映射以 R_FileSelect
  表第二列全排列为准，dump 离线可查）：0=STD 1=VIV 2=NTR 3=PORT 4=LAND 5=CINE
  6=TO 7=SUNR 8=FORG 9=FOVB 10=FOVY 11=MONO 12=OFF 13=POWB 14=DUO(含变体归位)
  15=WGLD；16+ 越界钳 STD；**隐藏槽 0x02/0x10 经 menu 层不可达**
- 子命令处理器（签名 ctx/argc/argv，[ctx]=printf；M_1 dump 反编译实证）：
  SetColorMode 0xC03FE100 / Effect 0xC03FE170 / Contrast 0xC03FE1F0 /
  Sharpness 0xC03FE270 / Saturation 0xC03FE2F0 / Toning 0xC03FE370

## 二、v8 架构变更（dist/fpSup.BIN 3992B，sha1 36276fa243b9…）

- apply_look = SetColorMode(底座 menu 序号) + 五轴 setter；退出 =
  名槽还原 + 归零往返（切回底座清零五轴再切回用户模式，轴随模式记忆不串味）
- EXIF 名槽改按**底色**写（序列化器跟官方模式走）：五表族实证矩阵
  （池A/池B/R_FileSelect/远A/远B，全部已知基址 dump 逐字节实证）；
  紧缩池窗口约束 → 名长上限按底座（NTR≤7/STD≤8/VIV≤5/MONO≤10）
- 配方变更：EKT100→**EKTAR**（VIV 窗 6B）；SEPIA/SEPIA2 底座 HID02/HID10
  →**MONO**（menu 层不可达隐藏槽；MONO+toning 反而更贴 sepia 语义）
- **洞区避让**：镜像上移 0xC072F800（shell 卡 AutoRun 的 worker 状态区
  0xC072F000-0xC072F040 与 stage2 的 LOAD_DONE_US 0xC072F6F8 是硬占用；
  v8 初版镜像顶 0xC072F288 差点压上去）。package.py 加洞顶硬断言
- v7 的 last_variant=0 自愈保留（轮询/防抖/重推语义不变）

## 三、模拟门 v4（simulate_load.py）

setter 桩模拟官方链（SetColorMode→主拷贝、五轴→ADJ），实证矩阵硬编白名单。
v8：装载链 20 + 运行期 18 全 PASS（apply 序列/主拷贝归位/名槽四副本/
重推重应用/退出还原+归零往返）。负控灵敏度保持：v6 实物 FAIL（ADJ 直写出界
+无 setter）、v5 实物 FAIL（野地址）、v3 形态 FAIL（entry）。

## 四、上机验收点（v8）

1. **照片内容**（核心）：DUO.R1 → 拍照 → 照片呈 NTR+配方轴效果（非原厂 R1）；
   EXIF=PRT400；回放=照片一致
2. 快门重推/连拍：照片持续配方味（同步链已接管，不再有 300ms 窗口）
3. 退出 STD：拍照=Standard+原厂参数；再进 DUO.OR1 → PRT160 生效
4. 观察退出瞬间有无模式跳变闪烁（归零往返的副作用，预期 ~百毫秒级）
5. 选择器高亮显示底色为预期行为；模式名标签若显示 PRT400 即名槽直通 UI
6. 注意：menu setter 的模式/轴变更与手动菜单操作同级，会随相机设置持久化
   ——关机时若配方仍激活，下次无卡开机会保留该底色+轴（与手动设置等价，
   非残留 hook；退场流程照旧"恢复默认设置"即净）

---

# 终局：v8 实机双验收通过（2026-10-16，MVP 闭环达成）

> SDIM0605（DUO.R1 配方态）：照片内容=配方 ✓，EXIF="PRT400" ✓
> SDIM0606（STD 退出态）：EXIF="Standard" ✓（名槽还原零残留）

**版本演进史**：v1-v3 洞窟冻结（entry 坐标系错）→ v4 能开机（EXIF 空名：
16B 越界写踩烂紧缩池）→ v5 冻结（dump 基址不明，写进活代码）→ v6 EXIF 通
（快门同值重推缺口）→ v7 预览自愈（照片原厂——轮询赢不了同步链）→
K1/K2/K3 探针（五轴进捕获 ✓ / RAM 变量源全排除 / menu 官方链锁定）→
**v8 照片内容+EXIF 双闭环**。

**方法论遗产**（比代码值钱）：
1. 每个写入地址必须有"已知基址 dump 的逐字节实证"（v5 之鉴）；
   dump 基址锚定法 = 三态 diff 强候选 ↔ 里程碑已载地址互锚
2. 模拟门与被测产物零共享假设（白名单硬编自独立证据）；
   每次实机踩出的新路径都补成断言（v3/v5/v6 三版实物负控常驻）
3. 内存变量撞不动的同步链，走固件官方通路接管（menu setter > mem set）

**剩余打磨项**（不阻塞）：配方区分度调优（待 Part B 标定矩阵——需换回
原版 BIN 恢复 USB shell）、UI 栏显底色名的产品化（可选 OSD 叠加方案已测绘）、
非英语语言包下名串池的实测复核。

---

# 阶段启动：Part B 标定矩阵（2026-10-16）

> 目标：用 K3 实证的 menu 官方 setter 链做逐轴定量测绘，求解每条配方的
> (底座, 五轴) 最优组合——解决 OR1/YE1/YG1 区分度弱的问题。

## 交付物

- `tools/gen_matrix.py` —— 拍摄矩阵生成器：5 底座(STD/VIV/NTR/CINE/MONO)
  ×(基线+5轴) + STD 负档线性度抽查 = **33 张**；同时写
  `dump/calib/manifest.json`（序号↔实验条件绑定，拍摄按序不删片）
- `tools/calibrate.py --matrix` —— manifest 驱动：逐底座建线性响应模型
  （基线+单位增量）、负档做线性度验证报告、逐目标跨底座贪心求解、
  产 `looks_solved.cfg` 草案（创意三条 SEPIA/SEPIA2/MONO+ 原样透传；
  名长窗口约束带入校验）;`--demo` 回归无损
- `autorun/briefing_PartB_calib.txt` —— 拍摄协议：原版 BIN（监视任务绝不可
  在）、禁 DUO、M 档/定 WB/定光、testchart.png 全屏 1:1、轴随模式记忆的
  逐底座归零核验、`still` 命令可用性测试（若可拍则下轮全自动）

## 求解纪律

err 只用于排序参考；最终配方以人眼复核为准。若某底座求解质量系统性偏差
（非线性失真），下轮把该底座轴档加密到 ±2 三档重建非线性模型。

## Part B 收官（同日）：33 张矩阵 + 求解 + v9

- 数据质检：33/33 照片 EXIF 名=所属底座（官方链写名顺带做了 QC 通道）；
  MONO 底座无 Effect 轴（setter OK 但 getter 回 0——黑白管线无色彩效果轴，
  我们三条 MONO 底座配方 eff 本就为 0）；still 命令不可用（下轮自动化走
  key 注入按键）
- 求解产出（looks.cfg 已收编，手调版留档 looks_v8_handtuned.cfg.bak）：

| 变体 | 配方 | 底座 | eff/con/shp/sat/ton | 备注 |
|---|---|---|---|---|
| R1 | PRT400 | NTR | 0/-1/0/+1/-1 | |
| OR1 | PRT160 | NTR | 同上 | **与 R1 塌缩同解**（模型分辨率极限，如实披露） |
| YE1 | CS400D | STD | 0/+3/0/+4/0 | |
| YG1 | EKTAR | **STD** | 0/+4/0/+4/+1 | 底座从 VIV 改 STD |
| G1 | GLD200 | STD | 0/+4/0/+4/0 | 与 EKTAR 仅差 ton+1（如实披露） |
| G2 | FUJI4H | NTR | 0/-1/0/0/0 | |
| B1 | CS800T | STD | 0/+2/+2/0/+4 | |
| B2/P1/M1 | SEPIA/SEPIA2/MONO+ | MONO | 未参与求解，原样保留 | |

- 求解器一处 bug 修复记录：matrix 模式的轴增量表键名（短名 vs AXIS_RANGES
  长名）不一致导致全零退化解——已修并复跑出真解
- v9 = 3992B，sha1 a6abb5e04f99…；模拟门 40/40 PASS；负控三件套保持灵敏

---

# 里程碑追加：v5 冻结根因（取证翻车）+ v6 修复 + 运行期模拟门（2026-10-14 深夜）

> v5 实机：进度条走完后冻结（比 v1-v3 晚一阶段）。恢复=拔电池+拔卡，零残留。
> 根因不是 EXIF 槽位逻辑，而是**取证素材的基址错误**。

## 一、v5 冻结根因（已钉死）

v5 槽单里的两个"镜像模板表"地址（0xC05CD094 / 0xC0614B3C）来自
`dump/C_STD2.bin` 的相对偏移——**但该 dump 基址并非 0xC0000000**
（铁证：文件头无 ARM 向量表，`00 00 01 00…` vs 真镜像头 `18 F0 9F E5`）。
用已知基址 dump（LOC_1 @0xC0500000）复核这两个绝对地址的真实内容：

- 0xC05CD094 = **ARM 代码中段**（`str r2,[sp]` / `bl` 指令流）
- 0xC0614B3C = **Thumb 函数体内**（`ldr/bx lr` 指令流）

v5 往活代码写了 8B ASCII → 首次 apply_look 时自毁 → 全机冻结。
**流程教训（硬规则）：没有"已知基址 dump 逐字节实证"的地址，一律不进写入清单。**
D_*_heap / V_* / F_*_tail2 / C_STD2 这批 13MB 文件同头同基址，基址均不可考，
其相对偏移一律不得直接当绝对地址用。

## 二、EXIF 序列化器源确认（排除法闭环）

v4 清零了池两份副本的 DuoTone 串（未碰 0xC0CC3070 与远区）→ 空名。
⇒ 序列化器读的就是 **0xC09709xx 运行时池**（读 0xC0CC3070 则 v4 不会空，
读远区则 v4 应显示 PRT400）。池结构 = 紧缩串池 + 指针表（指针表仅索引
模式 5..0x0F，DUO 不经指针表——其名由别路直读串池，v4 空名实证）。

## 三、v6（当前 dist/fpSup.BIN，2772B，sha1 a66d40205d77…）

槽单 = 3 个**已知基址 dump 逐字节实证**的运行时地址，8B 定长写：
0xC097090C / 0xC09709F4（池 A/B，M_1+LOC_1+LOC_3+SW_* 四源一致）、
0xC0CC3070（第三运行时表，M_1/LOC_3 实证，8B 后邻接 Monochrome）。
镜像模板表地址全部剔除（不可考）。名字 ≤7 字符断言保留。

## 四、模拟门 v2（simulate_load.py 增补运行期段——堵 v5 类盲区）

装载链 20 断言后，同一 unicorn 实例继续跑 monitor_main 本体（分片驱动，
DLY 桩即时返回）：预置 MODE_MASTER=0x21 复现"DUO.M1 开机即 apply"场景，
再切 0x00 走 exit_look。**写白名单与被测 BIN 完全无关**（硬编实证地址），
池内容用 M_1.bin 真实字节。

- v6：装载链 20/20 + 运行期 9/9 PASS（apply 写对 3 副本、底色/五轴正确、
  exit 还原 DuoTone+五轴归零、零越界写）
- v5 实物负控：FAIL，精确拦截在 `越界写 @0xC05CD094 pc=0xC072EA78`
  （写 'M' 进代码地址）——与实机冻结机制逐字节对应
- v3 entry 负控：仍 FAIL（lh_unhook 野写）——三层审计全部灵敏

## 五、上机验收点（v6）

1. 换卡（AutoRun 不动）冷启动 → 进度条走完 fpSup! → 不冻结（首要验收）
2. DUO.R1 拍照 → EXIF=**PRT400**；DUO.M1 → MONO+；切回 STD → Standard
3. 分流：若名="DuoTone"（非空非配方名）= 还有第四份远端副本被读 →
   换原版 BIN 恢复 USB shell，DUO 态补 dump 0xC2DFD08C/0xC2E44ABC 区再扩槽单
4. 注意：相机若停在 DUO 变体关机，下次开机会立即触发首次应用——
   v6 的模拟门已按此场景（DUO.M1）验收

---

# 里程碑追加：v6 实机全通 + v7 快门重推自愈（2026-10-14 深夜二更）

> **v6 实机终验全通**：开机无冻结、EXIF 双向验证达成（DUO.R1 张="PRT400"、
> STD 张="Standard"）——动态改名里程碑落地。实机新踩出一条路径缺口 → v7。

## 一、缺口：快门/UI 同值重推后配方不恢复（v6）

复现：DUO.R1 生效 → 按快门 → 取景回原厂 R1 且不再自愈（切走再切回可恢复）。
机制：快门时固件把 MODE_MASTER 重推回变体值 0x18；v6 的轮询判定
`last_variant==m` → "同变体无新事件" → 永不重应用（P3 的"重推自愈"误报
源自测试混入变体切换——同值路径从未被覆盖）。

## 二、v7 修复（方案B：apply 时清 last_variant）

apply_look 末尾 `last_variant = 0` ——已应用的配方不占有变体记忆；
同值重推（快门/UI 确认/对焦）天然成为"新选择"，重新走 settle→应用。
重应用幂等（同内容重写名槽/五轴/主拷贝），用户真实重选同变体语义不变。
v7 = 2784B，sha1 4b241850e420…。

## 三、模拟门 v3：实机路径全部钉进离线断言

运行期段新增"同值重推"段（apply 后把 master 写回变体值 → 必须重新归位）。
四道实物负控/正控全部就位：

| 版本 | 缺陷 | 模拟门判定 |
|---|---|---|
| v7（当前） | — | 装载链 20 + 运行期 12 全 PASS |
| v6 实物（fpSup_v6_shuttergap.BIN） | 同值重推卡死 | FAIL 于"重推后 master=0x21"断言 |
| v5 实物（fpSup_v5_frozen.BIN） | 写活代码 | FAIL 于越界写 0xC05CD094 |
| v3 形态（--neg-control） | entry 坐标系错 | FAIL 于 lh_unhook 野写 |

## 四、上机验收点（v7）

1. 冷启动 → DUO.R1 → PRT400 生效 → **按快门 → 取景应在 ~300ms 内自动回到
   配方态**（settle 窗口），连拍/半按对焦同理自愈
2. EXIF 回归：快门后拍一张 → 名仍为 PRT400（重推不碰名槽，名槽一直持有）
3. 切走再切回、变体间直切、退出 STD —— 原有路径全部回归验证一遍
