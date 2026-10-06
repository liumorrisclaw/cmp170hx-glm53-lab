# 2026-10-06 — cmpunlocker upstream v0.5 升级(ECC 生效)与回归验证

状态:升级完成,零回退;ECC 首次在本机生效。待 ECC-on 基线重测。

## 环境与版本 pin

| pin | 值 |
|---|---|
| cmpunlocker | upstream [amoghmunikote/cmpunlocker](https://github.com/amoghmunikote/cmpunlocker) **v0.5**(2026-10-05 发布) |
| 原驱动 | bendy2/cmpunlocker `combined-multiple-cards-gen2` @ ebcb14e(2026-08-13 merge,74 SM + ForceP2P P2P 分支;即 10-04 二期安装物) |
| 驱动/内核 | 610.43.03 / 6.8.0-138-generic(Secure Boot off,内核头在位) |
| GPU | 4× CMP 170HX 64GB(10de:20c2,rev a1) |
| 安装参数 | `sudo ./install.sh --profile=8gb --no-iommu --no-passthrough` |
| 引擎 | Morrowmake 1.7.0 · LAYOUT=tp4 · MAX_LEN=262144 · DFlash2 · port 8000(未动) |

## v0.5 内容评估(相对本机原状态)

v0.5 发布注记:**ECC DRAM and SRAM**、**+4 more SMs**;README 解锁表含 64GB/40GB geometry、Gen2、BAR1 64GB、JTAG、VFIO passthrough、profiling、persistent-sw-state。驱动补丁共 14 个(`build.sh` PATCH_ORDER),ECC 由 `ecc-enable` + `ecc-fbpa-static` + `ecc-reporting` + `booter-verify` 四补丁实现。

| 维度 | 升级前(bendy2 2026-08 merge) | v0.5 | 结论 |
|---|---|---|---|
| SM | 74(torch 实测) | 74(torch 实测) | **不增不减**;注记的 "+4 SMs" 是相对 v0.4 基线(70),本机 bendy2 已是 74 |
| ECC | N/A(驱动不暴露) | **Enabled**(SRAM/DRAM Correctable/Uncorrectable 计数器全暴露) | **净新增益,本次升级的主要价值** |
| 64GB / Gen2 / BAR1 | 正常 | 正常 | 无回退 |
| P2P | ForceP2P=0x11(fork 私有) | **无此特性**(上游无 ForceP2P) | conf 被覆写清除;`P2P=auto` 自动降级 host-shm,生产本就 P2P=off,仅 TP4 单流 −3%(301.6→293.2)为已知代价 |
| 多卡支持 | gen2 分支的 guarded multi-GPU | 上游原生(lspci 逐卡分类,4× 8gb inventory) | 无需再依赖 fork |
| 维护性 | 冻结在 8-13 | 上游活跃维护 | 后续跟进 v0.6+ 只需 git pull 重装 |

## 安装记录(坑与解法)

1. **DNS 陷阱**:`install.sh` 下载 `codeload.github.com` 时本机 DNS 解析失败;机器本地 Clash(127.0.0.1:7897)对该域名 SSL EOF。解法:Mac 侧经 Clash 通道下载 `open-gpu-kernel-modules-610.43.03.tar.gz`(27.4MB)后 scp 到 `driver/.build/`,install.sh 检测到文件存在即跳过下载。
2. **gcc 坑(同 10-04 坑①,上游未修)**:系统 gcc 11.4 不认内核 `-ftrivial-auto-var-init=zero`;`driver/build.sh` L195/L197 `CC_CMD` 手改 `gcc-12` 后构建通过。
3. **root 残留**:首次 sudo 运行把 `driver/.build` 建成 root 所有,hym 写入报 curl error 23;`chown -R hym:hym` 修复。
4. install.sh 不卸载运行中模块、无交互提示:构建+落盘全程 vLLM 继续带载,**停机窗口只有重启+权重冷加载**。
5. conf 覆写即清理:`cmp-pcie-gen2.conf` 被上游重写为 `RmForceEnableGen2=1;RMPcieLinkSpeed=0x1`,ForceP2P 残留参数自动消失(避免换模块后 unknown parameter)。
6. `gen2.service` 被上游版本接管(ExecStart=/usr/local/sbin/gen2-hammer);`cmp170hx-boot-init/cmp170hx-gen2/gen2-hammer` 三个旧单元保留 enabled(与升级前共存的格局一致)。
7. **DKMS 被移除**:今后内核升级后必须重跑 `install.sh` 重建模块,否则驱动失效。

## 重启后验证(2026-10-06 16:05,普通 reboot 即生效)

| 项 | 结果 |
|---|---|
| nvidia-smi | 4× CMP 170HX,65536 MiB,610.43.03,全部 GPU 正常 |
| PCIe | 全部 (current,max)=(2,2);gen2.service ExecStart 成功退出 |
| SM | **74 × 4**(torch multi_processor_count;SM-RECONFIG GPC 覆盖日志正常) |
| ECC | **Current=Enabled,Pending=Enabled**;volatile/aggregate 计数器暴露,初始全 0 |
| BAR1 | 64GB/64GB/32GB/8GB —— **与升级前快照逐卡一致**(dmesg 的 BAR1 assign 告警为主板 MMIO 窗口既有限制,非本次引入) |
| CUDA 自检 | 4 卡各 1024 元素求和全对 |
| 解锁日志 | `dmesg | grep SEC2_DEBUG`:WPR/PLM/FBPA/FEAT 写入 status=0xffff,GSP 正常启动 |

## 服务恢复

`./stop.sh`(SIGINT 进程组,4s)→ `sudo reboot` → 回来后 `PATH="$HOME/.local/bin:$PATH" ./start.sh`。
坑:非交互 SSH 的 PATH 不含 `~/.local/bin`,preflight 卡在 "uv not found";带 PATH 即可。权重冷加载 ~16 分钟(11 分片 × ~87s,page cache 被重启清空),CUDA graphs + KDA/MoE warmup 再 ~8 分钟。`.env` 未动(`P2P=auto` 自动降级)。

恢复后实测(16:33):`/health` OK;chat 请求 HTTP 200(0.77s,「1+1等于几」→「2」);**GPU KV cache size 1,197,473 tokens**(TP4@262144,高于 1.6.0 时代同口径的 1,081,579 —— ECC 未吃显存,GA100 HBM2e 为 inline ECC);4 worker 各 ~60.2GB 常驻,空闲 37-38°C / ~40W。日志里 16:01 的 `EngineDeadError` 为旧实例 stop 时留下的关机噪音,与新实例无关。

## 回退

- 本次升级前完整备份:`/root/cmpunlocker_backup_20261006_pre_v05/`(bendy2 模块全套 + conf + 4 个 systemd 单元 + `nvidia-smi -q` 快照 + SM 基线)。恢复文件 + 重启即回 74 SM + ForceP2P 状态。
- 10-04 备份仍在:`/root/cmpunlocker_backup_20261004/`。
- 源码保留:`/home/hym/cmpunlocker-gen2`(bendy2)、`/root/cmpunlocker`、`/home/hym/cmpunlocker-v05`(v0.5,已打 gcc-12 补丁)。

## ECC 生效性验证(2026-10-06 16:40,四层阶梯,不停服不重启)

| 层 | 测试 | 结果 |
|---|---|---|
| L1 报告层 | `nvidia-smi --query-gpu=ecc.mode.*` + `-q -d ECC` | 4× Current=Enabled/Pending=Enabled;完整 A100 式计数器结构(Volatile+Aggregate:SRAM Correctable / Uncorrectable Parity / Uncorrectable SEC-DED / DRAM Correctable / DRAM Uncorrectable / SRAM Threshold Exceeded / SRAM L2),可编程查询返回真值 |
| L2 控制层 | root `nvidia-smi -e 0` / `-e 1` | `-e 1`→"already Enabled";`-e 0`→**Not Supported**:ecc-enable/ecc-fbpa-static 补丁将 ECC **静态强制开启**,禁用通道有意关死。副作用:无法做 ECC on/off 的 A/B 带宽对照 |
| L3 硬件层 | 补丁↔dmesg 对证 | 构建含 ecc-enable / ecc-fbpa-static / booter-verify 三补丁;dmesg `PLM[1] FBPA(0x9a0148) attempt=0 status=0xffff` = FBPA(ECC 静态配置)写入被 GSP 接受 |
| L4 负载层 | 每卡 1GB 确定性图样填充 → 20 轮整卡拷贝 → 回读校验 | 4 卡全部 **PASS**;拷贝聚合带宽 ~1583–1588 GB/s(HBM2e 为 side-band ECC,不吃用户带宽,与 1.5TB/s 规格吻合);压测期间 correctable/uncorrectable 计数零增长,无 Xid |

未证明项(无公开工具可做):HBM2e 单比特故障的在线注入。生产标准做法是把计数器纳入长期监控——**Aggregate DRAM Correctable 出现首次非零即证明纠错路径在生产流量下真实工作**。

监控建议(5 分钟快照追加):
```bash
nvidia-smi --query-gpu=index,ecc.errors.corrected.volatile.total,ecc.errors.corrected.aggregate.total,ecc.errors.uncorrected.volatile.total,ecc.errors.uncorrected.aggregate.total --format=csv,noheader
```
volatile 随驱动重载清零,aggregate 持久累积——长期看 aggregate;uncorrectable 任何非零即告警(Xid 48/63/64 同步查 dmesg)。

## Addendum:ForceP2P 做成可选项并移植到 v0.5(2026-10-06 晚,已生效)

需求:TP4 单流交互时 P2P +3~6%(301.6 vs 293.2),PP4/聚合场景要关——做成部署级开关而非固定行为。

### 移植过程与两个关键发现

1. **p2p-unlock.patch 的真实机制**(来自 Morrowmake fork `/root/cmpunlocker`):`gpu.c` 对 0x20C2/0x2082 强制 `pcieP2PReadCaps/WriteCaps=0(OK)`,`kern_bus_gm200.c` 在 mailbox setup RPC 外围武装 PRI trap31 重打特权级。**代码里没有 ForceP2P 注册表键**——10-04 conf 里的 `ForceP2P=0x11` 其实是无效占位(RM 忽略未知注册表键),fork 模块里 P2P 是无条件开启的。
2. **v0.5 直接装上后 P2P 不工作的根因**:补丁的安全护栏读 trap31 PLM(0x0012277c)发现 `0xffffff8f`(不可写)→ 正确拒绝强制 caps。护栏是防静默搬坏数据的:作者实测在 PLM 0xFFFFFF8F 的部件上强开 P2P,33,554,432 字节里 33,423,360 字节是错的。
3. **v0.5 相对 Morrowmake fork 丢失了 `trap31_plm`**:fork 的 SEC2 特权掩码载荷表含 `{ 0x0012277cU, 0xffffffffU, "TRAP31_PLM" }`,v0.5 的 `sec2-postbl-plm-ss-cfg.patch` 把它漏了。把它加回载荷表 + yaml 同步后,trap31 可武装,护栏通过。
4. **运行时闸门(本次新增)**:给 p2p-unlock.patch 加 `osReadRegistryDword(pGpu, "ForceP2P", &forceP2P)` 检查(gpu.c caps 强制处 + kern_bus 的 `_cmpP2PTrapArm`),bit0=1 才启用。缺省 off,不影其他用途。

### 机内改动清单

- `/home/hym/cmpunlocker-v05/driver/patches/p2p-unlock.patch`:带闸门版本(从 fork 原版程序化改造,virgin 树 dry-run 通过)
- `/home/hym/cmpunlocker-v05/driver/patches/sec2-postbl-plm-ss-cfg.patch`:载荷表加回 TRAP31_PLM 行(git 恢复原版后全量 regen,含 g_kernel_gsp_nvoc.h)
- `common/constants.yaml`:补 `p2p_unlock` 与 `trap31_plm` 声明(校验器要求)
- `driver/build.sh`:PATCH_ORDER 追加 p2p-unlock(共 15 个);CC_CMD 改 gcc-12(沿用 10-04 坑①修法)
- `/usr/local/bin/cmp-forcep2p {on|off|status}`:开关脚本,写 conf + 读 dmesg 运行时判定
- 备份:`/root/cmpunlocker_v05_ecc_nop2p_20261006_modules/`(无 P2P 的 v0.5 纯净态)

### 坑(下次照抄)

1. **install.sh 每次都会覆写 `/etc/modprobe.d/cmp-pcie-gen2.conf`** → 重装后必须补 `sudo cmp-forcep2p on` 再重启。
2. **regen 补丁必须覆盖其触碰的全部文件**——sec2 补丁碰 `g_kernel_gsp_nvoc.h` + `kernel_gsp.c` 两个文件,只 regen 单文件会丢 NVOC 成员声明(`stockSignatureSize`),构建报 no member。regen 前先 `grep '^\+\+\+ '` 拿全清单。
3. cmp-forcep2p 的 conf 行引号要包住整个 RegistryDwords 值(第一版引号位置错,ForceP2P 落在引号外,行为未定义但 modprobe 容忍了——已修)。

### 验证(2026-10-06 晚)

| 项 | 结果 |
|---|---|
| ForceP2P=0x11(armed) | dmesg 4× `CMPUNLOCK: PCIe P2P caps forced to OK (devid 0x20c2)` |
| ForceP2P 缺省(off 态,dmesg 实证) | 4× `CMPUNLOCK: P2P left unsupported, trap31 PLM 0xffffff8f...`(修复前),闸门 off 分支文案已验证存在 |
| P2P content check | **108/108 PASS**(9 尺寸 × 12 有序对,字节级) |
| ECC / SM / 64GB / Gen2 | Enabled / 74×4 / 65536 MiB / (2,2) —— 零回退 |
| **c1 structured 正式口径**(3 轮中位) | **302.2 tok/s**(301.8/302.2/302.3;accept 0.967,6.69 tok/步)——对照 10-04 矩阵:P2P on 301.6 / P2P off 293.2。**P2P-on 收益 +3.1% 在 v0.5+ECC 基座上完整复现,ECC 零损耗。** 回执:`data/decode_c1_structured_v05p2p.json` |

### 用法

```bash
# LLM 部署(TP4 单流,默认建议):开
sudo cmp-forcep2p on && sudo reboot
# 引擎侧 .env 保持 P2P=auto,launcher 会自动验证并启用

# PP4/聚合/长上下文(或不用 P2P 时):关
sudo cmp-forcep2p off && sudo reboot   # NCCL 走 host-shm all-reduce

# 查状态(含运行时判定)
sudo cmp-forcep2p status
```

注意:`cmp-forcep2p on` 只在驱动层"使 P2P 可用";引擎是否真的走 P2P 由 `.env` 的 `P2P=auto` 决定(auto 会先 content check 再启用)。TRAP31_PLM 载荷解锁在 on/off 两态都存在(off 态只是不强制 caps,不写 trap 配置)。

## Addendum:引擎 1.7.0 → 1.7.2(2026-10-06 晚,生产定格 1.7.2)

背景:Morrowmake 回复邮件确认 BOOT_CHECK 时序 bug 已在 1.7.2 修复(连接错误/503 重试至 READY_TIMEOUT;错答案与鉴权错误仍立即失败;投递不确定的生成不重发),并给出其 x16 参考机上 1.6.0→1.7.1 的 PP4 8 用户增益(structured 580.5→639.5),请我们在 x4 上以同口径复测。

### 升级过程(慢链路三连坑,全部绕过)

1. `./start.sh update` 先被 vllm-src 三个文件的 1.4.x 时代本地缓解挡住(GC 补丁/REPACK-PROBE/workspace 放行)→ `git stash`(注释"obsolete per 2026-10-04 A/B")后放行。
2. uv editable 安装需拉 `torch==2.13.0` 构建依赖 + FlashInfer:直连 Fastly 只有 ~20 KB/s。**解法:`UV_DEFAULT_INDEX`/`UV_INDEX_URL` 指向清华镜像**(flashinfer-python 32MB 秒下),flashinfer-cubin 1.5GB 用机内既有 `/home/hym/flashinfer_cubin-0.7.0-py3-none-any.whl` 手动装(配方步骤见已满足自动跳过)。
3. setup.py 的预编译 vLLM wheel(305MB,wheels.vllm.ai)用 urllib 下载无断点续传,Clash 链路两次 ContentTooShort → **Mac 侧完整下载后 scp,`VLLM_PRECOMPILED_WHEEL_LOCATION=/home/hym/wheels/vllm-...whl` 指向本地文件**(setup.py 原生支持)。
4. **BOOT_CHECK 修复实测通过**:`.env` 移除 `BOOT_CHECK=0` 后冷启动(权重 16 分钟 + warmup),update 流程全程重试连接错误直至 HEALTH OK,不再误杀启动。

### PP4 8 用户对比(作者口径:P2P off · MAX_LEN=524288 · 10 轮;本机 1.7.2 @ 74 SM + ECC + Gen2 x4)

| 口径(8 用户) | 本机 1.6.0/1.7.0 基线 | **1.7.2** | Δ |
|---|---:|---:|---:|
| structured 聚合 | 645.3–645.8 | **643.1** | −0.3%(噪声内) |
| coding 聚合 | (无旧版 8u 记录) | **503.2** | 新基线 |
| prose 聚合 | (无旧版 8u 记录) | **396.7** | 新基线 |
| 单流 structured | 216.9–219.8 | **218.0** | 持平 |

结论:**x4 上 1.7.2 无回退**。作者 x16 的 8 用户增益(580→639)在我们机器上不构成"窄链路回退"——本机 x4 本就被链路压在同一水平(645 vs 他 1.6.0 的 580.5 受益于 64GB 卡 PP4 传输量更大?不,差异主因是他 x16),1.7.2 保持即通过。回执:`data/decode_c8_*_v172_pp4512k_p2poff.json`、`data/decode_c1_structured_v172_pp4512k_p2poff.json`。

### 生产定格(2026-10-06 起)

引擎 **1.7.2**(fork ab60b723,wheel b6761e8ded 复用)· TP4 · 262144 · P2P=auto · DFlash2 自适应 · `BOOT_CHECK` 默认开启(修复后行为)。`.env` 备份链:`.env.bak_20261006_prod_tp4`(升级前 TP4 生产)、`.env.bak_20261006_bench_pp4_512k`(基准口径)。vllm-src 的 stash 在 `git stash list`(如 1.7.2 下复现 1.4.x 症状再取用)。

## 待办

1. ~~**ECC-on 基线重测**~~ **已完成(2026-10-06 晚,引擎 P2P=off · ECC on · 74 SM,对照 10-04 矩阵同一脚本同一口径)**:

   | 口径 | 10-04(ECC off) | 本次(ECC on) | Δ |
   |---|---:|---:|---:|
   | c1 structured | 293.2 | 293.5 | +0.1% |
   | c1 coding | 223.1 | 222.9 | −0.1% |
   | c1 prose | 143.4 | 143.3 | −0.1% |
   | c8 聚合(墙钟) | 462.8 | 461.5 | −0.3% |

   **全部 \|Δ\|≤0.3%,远低于 5% 权衡门禁——保留 ECC,无需再议。** 与 HBM2e side-band ECC 不占用户带宽一致。回执:`data/decode_c1_*_ecc_on_p2poff.json`、`data/decode_c8_structured_ecc_on_p2poff.json`。phase 名 `ecc_s1/ecc_c1/ecc_p1/ecc_s8`。
2. ~~ECC 计数器纳入 5 分钟监控快照~~ **已完成**:`/usr/local/bin/cmp-ecc-snapshot`(root cron `*/5`),日志 `/var/log/cmp-ecc-snapshot.log`(8MB 自动裁剪);aggregate correctable 增长→WARN,uncorrectable>0→ERROR;附带驱动/内核匹配检查(状态变化才记 ERROR,防刷屏)。
3. ~~内核升级防护~~ **已完成**:`cmp-driver-status` 自检(FAIL 时直接给出修复命令序列);`linux-*-generic-hwe-22.04` 等 metas 已 `apt-mark hold`(恢复:`sudo apt-mark unhold <pkg>`)。
4. x16 链路恢复(主板固件)优先级不变:恢复后 P2P 由上游 gen2 probe-retrain + 引擎 `P2P=auto` 自动接管。
5. 建议上游:把 `trap31_plm` 载荷项与 ForceP2P 闸门补回 upstream(cmpunlocker v0.5 丢失前者导致 P2P 不可用;闸门使 P2P 从"有无"变成"按部署切换")。可整理成 patch 邮件/Discord 帖。

## 致谢

本次升级站在这些项目与人们的工作上,一并致谢:

- **[amoghmunikote/cmpunlocker](https://github.com/amoghmunikote/cmpunlocker)([v0.5](https://github.com/amoghmunikote/cmpunlocker/releases/tag/v0.5))** —— ECC 四补丁(ecc-enable / ecc-fbpa-static / ecc-reporting / booter-verify)是本篇的核心增益;护栏注释"宁要诚实的 unsupported,不要静默搬坏数据"的设计,让我们在移植 P2P 时避开了一次静默数据损坏。
- **[Morrowmake/glm53-flash-cmp170hx-recipe](https://github.com/Morrowmake/glm53-flash-cmp170hx-recipe)** —— 引擎配方与 vLLM fork;`p2p-unlock.patch` 与 trap31 方案源自其 cmpunlocker fork;BOOT_CHECK bug 一个版本内修复,并主动给出 x16 8 用户对比数据邀请复测。
- **[bendy2/cmpunlocker](https://github.com/bendy2/cmpunlocker)** —— gen2 多卡分支稳定服役近两个月(2026-08~10),为平滑升级留出完整备份。
- **[PixelML/club-170hx](https://github.com/PixelML/club-170hx)** —— 独立实验与 PLX P2P 负优化先见;本仓库风格参照。
- **MiaAI-Lab** —— bench_decode.py 测量协议。**canada-quant** —— W4A16 权重。**incoai** —— DFlash2 drafter。**智谱 / Z.ai** —— 开放 GLM-5.3-Flash。

完整致谢与升级运维说明见 [`../../CMPUNLOCKER-V0.5.md`](../../CMPUNLOCKER-V0.5.md)([English](../../CMPUNLOCKER-V0.5_EN.md))。
