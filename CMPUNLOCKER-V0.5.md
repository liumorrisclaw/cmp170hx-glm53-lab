# cmpunlocker v0.5 升级说明与致谢（2026-10-06）

中文 | [English](CMPUNLOCKER-V0.5_EN.md)

本机（4× CMP 170HX 64GB，Gen2 x4，GLM-5.3-Flash 推理生产机，驱动 610.43.03 锁定）已于 2026-10-06 从 bendy2 gen2 分支构建（74 SM + ForceP2P，2026-08-13 merge）升级到 **upstream cmpunlocker v0.5**。升级目标有三个：拿到 v0.5 新解锁的 **ECC**（DRAM + SRAM 纠错）、把 P2P 从"有无"改成"**按部署一键开关**"、回归上游活跃维护线。最终结果：**零回退，ECC 首次生效，ForceP2P 成为运行时可选项**。本文是升级与运维说明；逐条实验记录见 [`notebooks/2026-10-06-cmpunlocker-v05-ecc-upgrade.md`](notebooks/2026-10-06-cmpunlocker-v05-ecc-upgrade.md)。

## 1. 上游链接

- 仓库：<https://github.com/amoghmunikote/cmpunlocker>
- 本次安装版本：[Release v0.5](https://github.com/amoghmunikote/cmpunlocker/releases/tag/v0.5)（2026-10-05 发布，发布注记：New features — Error-Correcting Code (ECC) DRAM and SRAM、+4 more SMs）
- 安装基线：v0.5 @ 驱动 610.43.03，`sudo ./install.sh --profile=8gb --no-iommu --no-passthrough`，本机构建共 **15 补丁**（v0.5 原生 14 补丁 + 移植自 Morrowmake fork 的 P2P 补丁，见 §4）
- 前置条件核查（装机自检）：Secure Boot 已关闭、`linux-headers-$(uname -r)` 在位、免密 sudo、4× `10de:20c2` 全部被 v0.5 白名单按 PCI ID 逐卡识别

## 2. 升级前后对比（本机实测）

| 项 | 升级前（bendy2 gen2 @ ebcb14e） | v0.5 后 | 结论 |
|---|---|---|---|
| ECC Mode | N/A（驱动根本不暴露） | **Enabled**（Current + Pending），SRAM Correctable / Uncorrectable Parity / Uncorrectable SEC-DED / DRAM Correctable / DRAM Uncorrectable 计数器全套暴露且可编程查询 | **净新增益，本次升级的核心价值** |
| SM 数 | 74 × 4 | 74 × 4 | 发布注记的 "+4 more SMs" 是相对 v0.4 的 70 基线；本机此前已是 74，不增不减 |
| 64GB 显存 / PCIe Gen2 / BAR1 | 正常 | 正常 | 无回退；BAR1 64/64/32/8 GB 与升级前快照逐卡一致（是主板 MMIO 窗口既有限制，dmesg 的 BAR1 assign 告警升级前就存在） |
| P2P | 无条件强开（fork 行为） | 上游无 P2P 特性；移植 fork 补丁并**新增 ForceP2P 注册表运行时闸门** | `sudo cmp-forcep2p on/off` + 重启切换；content check 108/108 PASS |
| 多卡支持 | fork 的 guarded multi-GPU 分支 | 上游原生（lspci 逐卡分类，inventory 标记落盘） | 不再依赖 fork |
| 维护性 | 冻结在 2026-08-13 | 上游活跃维护 | 后续跟版本 = git pull + 重装 |

## 3. ECC：验证方法与严谨性边界

ECC 是 v0.5 最重要的新解锁，但我们刻意把"验证生效"和"证明纠错"分开说：

**四层集成验证（全部通过）：**

| 层 | 方法 | 结果 |
|---|---|---|
| L1 报告层 | `nvidia-smi -q -d ECC` + 可编程查询字段 | 4 卡 Current/Pending 均 Enabled；A100 式完整计数器结构暴露并返回真值 |
| L2 控制层 | root 下 `nvidia-smi -e 0`（尝试禁用） | 返回 **Not Supported**——`ecc-fbpa-static` 补丁把 ECC 静态焊死在开启，禁用通道被有意关死（副作用：无法做 ECC on/off 的 A/B 对照） |
| L3 硬件层 | 补丁代码 ↔ dmesg 对证 | 构建含 ecc-enable / ecc-fbpa-static / ecc-reporting / booter-verify 四补丁；dmesg `PLM[1] FBPA(0x9a0148) status=0xffff` = ECC 静态配置写入被 GSP 固件接受 |
| L4 负载层 | 每卡 1GB 确定性图样填充 → 20 轮整卡拷贝 → 回读逐位校验 | 4 卡全 PASS；拷贝聚合带宽 ~1585 GB/s（HBM2e side-band ECC 不占用户带宽）；压测期间计数器零增长、无 Xid |

**严谨性边界（重要）**：要直接证明"纠错路径真的在纠错"，需要**故障注入工具**（如按行激发/注入 ECC 事件的诊断手段），目前不具备该条件。因此当前结论止步于"集成验证 OK"。已部署的观测手段：`cmp-ecc-snapshot` 每 5 分钟（root cron）记录 4 卡计数器到 `/var/log/cmp-ecc-snapshot.log`——`aggregate correctable` 出现增长即纠错路径在真实流量下工作的直接证据，`uncorrectable > 0` 立即 ERROR；同时持续观察是否存在"**比特跳变但未触发 ECC**"的静默错误（此类只能靠输出侧一致性抽查捕捉）。观察期数天，有结论会更新本文。

**性能代价（TP4 · P2P off · 同脚本同口径，对照 2026-10-04 矩阵）：**

| 口径 | ECC off（10-04 基线） | ECC on（本次） | Δ |
|---|---:|---:|---:|
| c1 structured | 293.2 | 293.5 | +0.1% |
| c1 coding | 223.1 | 222.9 | −0.1% |
| c1 prose | 143.4 | 143.3 | −0.1% |
| c8 聚合（墙钟） | 462.8 | 461.5 | −0.3% |

全部 |Δ|≤0.3%，噪声级，**保留 ECC 无需权衡**。GPU KV 池 1,197,473 tokens（不缩水，inline ECC 不吃显存）。回执：`data/decode_c1_*_ecc_on_p2poff.json`、`data/decode_c8_structured_ecc_on_p2poff.json`。

## 4. ForceP2P：从"无效占位"到"真开关"

移植 fork 的 `p2p-unlock.patch` 到 v0.5 时发现两件事，记录给后来者：

1. **原 conf 里的 `ForceP2P=0x11` 是无效占位**——fork 补丁代码里根本没有读这个注册表键，P2P 在 fork 模块里是无条件强开的。所谓"开关"此前从未存在。
2. **v0.5 丢失了 `trap31_plm` 载荷项**。fork 的 SEC2 特权掩码载荷表含 `{ 0x0012277cU, 0xffffffffU, "TRAP31_PLM" }`，v0.5 把它漏了。没有它，P2P 补丁的安全护栏检测到 trap31 的 PRIV_LEVEL_MASK 不可写（本机实测 0xffffff8f），会正确拒绝强制 P2P caps——护栏是对的：补丁作者实测过在不可写部件上强开 P2P，33,554,432 字节里 33,423,360 字节（99.6%）搬错。

**修复与改造**：把 `trap31_plm` 加回载荷表 + `constants.yaml` 补声明；给补丁加真正的运行时闸门——`gpu.c` 的 caps 强制处与 `kern_bus_gm200.c` 的 trap 武装处各读一次 `osReadRegistryDword(pGpu, "ForceP2P", ...)`，bit0=1 才启用。机内配了开关脚本：

```bash
sudo cmp-forcep2p on     # LLM 部署档(TP4 单流):写入 ForceP2P=0x11,重启生效
sudo cmp-forcep2p off    # PP4/聚合档:P2P 不可用,NCCL 自动走 host-shm
sudo cmp-forcep2p status # 显示 conf 状态 + dmesg 运行时判定
```

验证：dmesg 4× `CMPUNLOCK: PCIe P2P caps forced to OK (devid 0x20c2)`；字节级内容校验 **108/108 PASS**（9 尺寸 × 12 有序对）；P2P on 后单流 structured 293.2 → **302.2 tok/s（+3.1%）**。引擎侧 `.env` 保持 `P2P=auto`（先 content check 再启用）。

## 5. 引擎同步跟进 1.7.2

同日把 Morrowmake 配方从 1.7.0 升到 **1.7.2**：我们上报的 BOOT_CHECK 时序 bug 已修复（引擎初始化期的连接错误/503 重试至 READY_TIMEOUT，错答案与鉴权错误仍立即失败，投递不确定的生成不重发）。删掉 `BOOT_CHECK=0` 绕过后真实冷启动验证：权重加载 ~16 分钟全程重试直到 HEALTH OK，不再误杀。

作者同口径复测（PP4 · P2P off · MAX_LEN=524288 · 8 用户 × 10 轮，本机 x4 · 74 SM · ECC on）：

| 口径（8 用户聚合） | 1.6.0/1.7.0 基线 | 1.7.2 | Δ |
|---|---:|---:|---:|
| structured | 645.3–645.8 | **643.1** | −0.3%（噪声内） |
| coding | （此前未测） | **503.2** | 新基线 |
| prose | （此前未测） | **396.7** | 新基线 |
| 单流 structured | 216.9–219.8 | **218.0** | 持平 |

**x4 上零回退，生产定格 1.7.2**。一个有价值的观察：本机 x4 的 8 用户 structured 聚合（643.1）与作者 x16 的 1.7.1（639.5）几乎一致——PP4 每层只传一次激活，聚合吞吐不吃链路带宽；窄链路伤的是 TP 和单流。回执：`data/decode_c8_*_v172_pp4512k_p2poff.json`。

## 6. 慢链路装机坑全集（照抄可避）

1. **内核模块源码下载**：`install.sh` 需下载 open-gpu-kernel-modules 源码包，本机 DNS 解析 `codeload.github.com` 失败、本地 Clash 对其 SSL EOF → Mac 侧经代理下载（27.4MB）后 scp 到 `driver/.build/`，install.sh 检测到即跳过；
2. **gcc 版本**：Ubuntu 6.8 内核需要 gcc-12（默认 gcc 11.4 不认 `-ftrivial-auto-var-init=zero`），`driver/build.sh` 的 `CC_CMD` 两处改 `gcc-12`（上游至今未修，10-04 与本次两次踩中）；
3. **root 残留**：首次 sudo 运行把 `driver/.build` 建成 root 所有，hym 用户写不进 → `chown -R` 修复；
4. **uv/PyPI 慢链路**（1.7.2 升级）：uv 拉 torch 2.13 构建依赖只有 ~20 KB/s → `UV_DEFAULT_INDEX`/`UV_INDEX_URL` 切清华镜像；flashinfer-cubin 1.5GB 复用机内既有本地 wheel 手动装（配方的 flashinfer 步骤见已满足自动跳过）；
5. **305MB 预编译 vLLM wheel**：setup.py 的 urllib 下载无断点续传，两次 `ContentTooShortError` → Mac 侧完整下载后 scp，`VLLM_PRECOMPILED_WHEEL_LOCATION` 指向本地文件（setup.py 原生支持）；
6. **regen 补丁必须覆盖其触碰的全部文件**——sec2 补丁碰 `g_kernel_gsp_nvoc.h` + `kernel_gsp.c` 两个文件，只 regen 单文件会丢 NVOC 成员声明，构建报 `no member named stockSignatureSize`；
7. **`install.sh` 每次运行覆写 `/etc/modprobe.d/cmp-pcie-gen2.conf`** → 重装后必须补 `sudo cmp-forcep2p on` 再重启；
8. **DKMS 被安装器移除** → 内核升级后必须重跑 `install.sh`，否则驱动起不来（本机已 `apt-mark hold` 内核 metas + `cmp-driver-status` 自检脚本兜底）；
9. **非交互 SSH 启动服务**：PATH 不含 `~/.local/bin`，配方 `start.sh` 会卡在 "uv not found" → `PATH="$HOME/.local/bin:$PATH"` 前置。

## 7. 回退链与备份

- 本次升级前完整备份：`/root/cmpunlocker_backup_20261006_pre_v05/`（bendy2 模块全套 + conf + 4 个 systemd 单元 + `nvidia-smi -q` 快照 + SM 基线）；
- v0.5 无 P2P 纯净态：`/root/cmpunlocker_v05_ecc_nop2p_20261006_modules/`；
- 10-04 二期备份仍在：`/root/cmpunlocker_backup_20261004/`；
- 源码保留：`/home/hym/cmpunlocker-v05`（v0.5，已打 gcc-12 + ForceP2P 闸门 + trap31_plm 补丁）、`/home/hym/cmpunlocker-gen2`（bendy2）、`/root/cmpunlocker`（Morrowmake）。
- 任一层：恢复文件 + 重启即回退；`remove.sh` 可完整卸载。

## 8. 致谢（Credits）

- **[amoghmunikote/cmpunlocker](https://github.com/amoghmunikote/cmpunlocker)** —— 上游解锁器本体。v0.5 的 ECC 工作（ecc-enable / ecc-fbpa-static / ecc-reporting / booter-verify 四补丁）是本次升级的核心价值；P2P 补丁护栏注释里"宁要诚实的 unsupported，不要静默搬坏数据"的设计哲学，让我们在移植时避免了一次静默数据损坏事故。
- **[Morrowmake/glm53-flash-cmp170hx-recipe](https://github.com/Morrowmake/glm53-flash-cmp170hx-recipe)** —— 引擎配方与 vLLM fork（本机 1.4.1 → 1.6.0 → 1.7.0 → 1.7.2 全程跟进）；`p2p-unlock.patch` 与 trap31 方案源自其 cmpunlocker fork；BOOT_CHECK 时序 bug 报告后一个版本内修复，并主动提供 8 用户对比数据邀请我们在 x4 复测——罕见的问题响应速度。
- **[bendy2/cmpunlocker](https://github.com/bendy2/cmpunlocker)**（`combined-multiple-cards-gen2` 分支）—— 2026 年 8 月至 10 月间本机的生产驱动，其 guarded multi-GPU retrain 稳定服役近两个月，为本次平滑升级留出了完整备份。
- **[PixelML/club-170hx](https://github.com/PixelML/club-170hx)** —— 独立实验与 PLX 拓扑 P2P 负优化的先见记录（本机 x4 上复现了同样结论）；本仓库的实验记录风格以其为参照。
- **[MiaAI-Lab](https://github.com/MiaAI-Lab)** —— `bench_decode.py` 测量协议（T=0、thinking off、400 token、预热后取中位），全部口径的可比性基础。
- **canada-quant** —— GLM-5.3-Flash-W4A16-MTP 权重；**incoai** —— DFlash2 drafter。
- **智谱 / Z.ai** —— 开放 GLM-5.3-Flash 本体。

本仓库是上述开源工作在一台 4× CMP 170HX（Gen2 x4）机器上的复现、测量与运维记录。基准回执见 [`data/`](data/)，图表见 [`assets/charts/`](assets/charts/)，逐日实验记录见 [`notebooks/`](notebooks/)。
