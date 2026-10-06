# cmpunlocker v0.5 升级说明与致谢（2026-10-06）

本机（4× CMP 170HX 64GB，Gen2 x4，GLM-5.3-Flash 推理生产机）已于 2026-10-06 从 bendy2 gen2 分支构建（74 SM + ForceP2P）升级到 **cmpunlocker upstream v0.5**，零回退，ECC 首次生效。实验细节与全部数据见 [`notebooks/2026-10-06-cmpunlocker-v05-ecc-upgrade.md`](notebooks/2026-10-06-cmpunlocker-v05-ecc-upgrade.md)。

## 上游链接

- 仓库：<https://github.com/amoghmunikote/cmpunlocker>
- 本次安装的版本：[Release v0.5](https://github.com/amoghmunikote/cmpunlocker/releases/tag/v0.5)（2026-10-05 发布，新特性：ECC DRAM and SRAM、+4 more SMs）
- 安装基线：v0.5 @ 驱动 610.43.03，`--profile=8gb --no-iommu --no-passthrough`，本机构建 15 补丁（v0.5 原生 14 补丁 + 移植的 P2P 补丁）

## v0.5 在本机的实际变化

| 项 | 升级前（bendy2 gen2 @ ebcb14e） | v0.5 后 | 结论 |
|---|---|---|---|
| ECC | N/A（驱动不暴露） | **Enabled**，SRAM/DRAM 纠错计数器全暴露 | 净新增益 |
| SM | 74 × 4 | 74 × 4 | 注记的 "+4 SMs" 相对 v0.4 基线 70，本机不变 |
| 64GB / Gen2 / BAR1 | 正常 | 正常 | 无回退（BAR1 64/64/32/8 与升级前逐卡一致，主板 MMIO 窗口既有限制） |
| P2P | 无条件强开（fork 行为） | 上游无 P2P 特性；移植 fork 补丁并新增 `ForceP2P` 注册表运行时闸门 | `cmp-forcep2p on/off` 一键切换；content check 108/108 PASS |

### ECC 严谨性说明

目前的 ECC 结论是**集成验证**层面：报告层（计数器结构完整且可编程查询）、控制层（`nvidia-smi -e 0` 返回 Not Supported，补丁静态强制）、硬件层（SEC2 载荷表 FBPA 写入与 dmesg 对证）、负载层（每卡 1GB 确定图样 ×20 拷贝逐位校验 PASS，聚合带宽 ~1585 GB/s）。**直接证明纠错路径工作需要故障注入工具，现阶段不具备该条件**；已部署每 5 分钟 ECC 计数器快照（aggregate correctable 增长 = 纠错工作的直接证据；uncorrectable 非零 = ERROR），并持续观察是否存在"比特跳变但未触发 ECC"的静默错误。

### 性能影响（TP4 · P2P off · 同脚本同口径）

structured 293.5 vs 293.2、coding 222.9 vs 223.1、prose 143.3 vs 143.4、c8 聚合 461.5 vs 462.8——全部 |Δ|≤0.3%，噪声级。P2P on 后单流 structured 302.2（+3.1% vs off）。

## 运维要点（踩坑记录）

1. `install.sh` 每次运行都会覆写 `/etc/modprobe.d/cmp-pcie-gen2.conf` → 重装后必须补 `sudo cmp-forcep2p on` 再重启；
2. 安装器会移除 DKMS 模块 → **内核升级后必须重跑 `install.sh`**，否则驱动起不来（本机已 `apt-mark hold` 内核 metas 并部署 `cmp-driver-status` 自检）；
3. v0.5 的 SEC2 载荷表缺失 `trap31_plm`（0x0012277c）导致 P2P 补丁安全护栏正确拒绝强制 caps——已把该寄存器加回载荷表并在 `constants.yaml` 补声明；
4. 慢链路构建：open-gpu-kernel-modules 源码包与 uv/PyPI 依赖建议预下载/镜像（详见 notebook）。

## 致谢（Credits）

- **[amoghmunikote/cmpunlocker](https://github.com/amoghmunikote/cmpunlocker)** —— 上游解锁器本体；v0.5 的 ECC 工作（ecc-enable / ecc-fbpa-static / ecc-reporting / booter-verify）是本次升级的核心价值。护栏注释里"宁要诚实的 unsupported，不要静默搬坏数据"的设计让我们在移植 P2P 时少踩了坑。
- **[Morrowmake/glm53-flash-cmp170hx-recipe](https://github.com/Morrowmake/glm53-flash-cmp170hx-recipe)** —— 引擎配方与 vLLM fork（1.4.1 → 1.7.2 全程跟进）；`p2p-unlock.patch` 来自其 cmpunlocker fork；BOOT_CHECK 时序 bug 报告后一个版本内修复。
- **[bendy2/cmpunlocker](https://github.com/bendy2/cmpunlocker)**（`combined-multiple-cards-gen2` 分支）—— 2026-08 至 10 月间本机生产驱动，其多卡 guarded retrain 工作稳定服役近两个月。
- **[PixelML/club-170hx](https://github.com/PixelML/club-170hx)** —— 独立实验与 PLX 拓扑 P2P 负优化的先见记录，本仓库风格参照。
- **MiaAI-Lab** —— `bench_decode.py` 测量协议。
- **canada-quant**（GLM-5.3-Flash-W4A16-MTP 权重）、**incoai**（DFlash2 drafter）。
- **智谱 / Z.ai** —— 开放 GLM-5.3-Flash。

本仓库是上述开源工作在一台 4× CMP 170HX（Gen2 x4）机器上的复现、测量与运维记录。回执 JSON 见 [`data/`](data/)，图表见 [`assets/charts/`](assets/charts/)。
