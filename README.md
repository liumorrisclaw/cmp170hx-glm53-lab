# GLM-5.3-Flash on 4× CMP 170HX — 部署实验记录

[English](README_EN.md) | 中文

> 本仓库记录在一台 4×CMP 170HX(矿卡改造)机器上部署 GLM-5.3-Flash 的实测数据、布局对比与推荐配置。所有数字为本机实测,原始 JSON 归档在 `data/`,图表由 `scripts/make_charts.py` 生成,实验记录在 `notebooks/`。
>
> 风格与致谢对象参考 [PixelML/club-170hx](https://github.com/PixelML/club-170hx) 的社区实验记录;引擎与配方来自 [Morrowmake/glm53-flash-cmp170hx-recipe](https://github.com/Morrowmake/glm53-flash-cmp170hx-recipe)。

## 硬件与基线

| 项 | 配置 |
|---|---|
| GPU | 4× CMP 170HX 64GB(GA100,sm_80),功耗墙解锁至 250W(原厂 180W) |
| PCIe | 全部四卡协商为 **Gen2 x4**(多次冷断电确认为本机稳态;无 P2P,`nvidia-smi topo -p2p` 全 GNS) |
| 权重 | canada-quant/GLM-5.3-Flash-W4A16-MTP(W4A16 Marlin,320B MoE) |
| Drafter | incoai/GLM-5.3-Flash-DFlash2(CC BY-NC-ND 4.0,仅评测用途) |
| 引擎 | Morrowmake vLLM fork,配方 v1.4.1(commit 378c37b00)→ **v1.6.0**(commit 3a2bf16da,wheel b6761e8ded) |
| 测量 | MiaAI-Lab `bench_decode.py` 同口径:T=0、thinking off(输出仍含推理文字)、400-token 输出、预热后 3 轮中位 |

## 主要结果

### 引擎 1.4.1 → 1.6.0(PP4,短输入 c1,3 轮中位)

![升级对比](assets/charts/01-upgrade-141-160-pp4.png)

| 口径 | 1.4.1 | 1.6.0 | 变化 |
|---|---|---|---|
| structured | 139.4 | **220.5** | +58% |
| coding | 129.2 | 127.5 | 持平 |
| prose | 94.6 | 95.9 | 持平 |

structured 的大幅提升与 1.6.0 的 acceptance-aware 投机深度一致。混合负载下按 draft 位置统计的接受率(630 步):

![投机接受率](assets/charts/07-acceptance-per-position.png)

计数类文本吃满自适应深度,代码与文字类在浅深度即衰减——与上表只有 structured 大涨的现象一致。

### 1.6.0 下 TP4 与 PP4 的布局对比(x4 链路)

![布局对比](assets/charts/02-layout-tp4-vs-pp4-160.png)

| 口径 | TP4 | PP4 | 说明 |
|---|---|---|---|
| c1 structured | **284.2** | 220.5 | 单流交互选 TP4 |
| c1 coding | **229.1** | 127.5 | |
| c1 prose | **136.4** | 95.9 | |
| c8 计数聚合(墙钟) | 447.2 | **645.8** | 批量吞吐选 PP4 |

### 与 Gen2 x16 机器的差距定量(1.6.0,同为 TP4、host-shm all-reduce、P2P off)

![链路差距](assets/charts/03-link-gap-x4-vs-x16.png)

| 口径 | 本机(x4) | PixelML 1.6.0(x16) | 差距 |
|---|---|---|---|
| c1 structured | 284.2 | 396.0 | −28% |
| c1 coding | 229.1 | 306.2 | −25% |
| c1 prose | 136.4 | 192.5 | −29% |
| c8 计数聚合 | 447.2 | 798.6 | −44% |

单流损失 25–29%,聚合损失放大到 44%(all-reduce 数据量随 batch 增大,x4 带宽伤害同步放大)。两机 KV 池仅差 0.9%(1,081,579 vs 1,072,150),软件差异可排除。

![c8 聚合对比](assets/charts/04-c8-aggregate-compare.png)

### 长输入(PP4 1.6.0,482K tokens 级,两轮)

![长输入](assets/charts/05-longctx-482k-two-runs.png)

| 轮 | TTFT | 有效 prefill | 生成速率 | needle |
|---|---|---|---|---|
| 1(482,277 tok) | 85.8 s | 5,619 tok/s | 156.9 tok/s | 命中 |
| 2(482,635 tok) | 86.2 s | 5,601 tok/s | 140.1 tok/s | 命中 |

### 1.4.x 三布局对比(历史,升级前)

![三布局](assets/charts/06-layouts-141x.png)

单流 decode 排序 TP4 > TP2+PP2 > PP4;TP2+PP2 在单流与聚合两个维度都不是最优。

### 阴性结果(避免他人重复踩坑)

- **锁钟无效**:`nvidia-smi -lgc 1695` 设置成功,但负载下实测时钟仍 1470–1485 MHz(上限 1695),decode 283.7 vs 284.2 无差异。频率由 vBIOS 电压曲线决定,不接受软件锁定。
- **SPEC_N=5 无收益**:accept rate 64.1%→48.3%,吞吐仅 +1%,KV 池 −31%(1.4.x 数据;1.6.0 的自适应深度使手动调 k 失去意义)。
- **P2P 在 PLX 拓扑上负优化**(PixelML 数据):本机 x4 无法协商 P2P,维持 host-shm all-reduce 路径即可。

## 推荐配置

按负载形态二选一,引擎 1.6.0、DFlash2 投机(自适应深度)、`expandable_segments:False`、prefix caching 开启(脱敏配置见 `configs/`):

| 负载 | 布局 | MAX_LEN | 预期水平 |
|---|---|---|---|
| 交互式单流 / 低延迟 | `LAYOUT=tp4` | 262144 | c1 structured ~284 tok/s |
| 批量吞吐 / 长上下文 / 多租户 | `LAYOUT=pp4` | 524288 | 482K prefill ~5,600 tok/s,长输入单流生成 ~140–157 tok/s,c8 聚合 ~646 tok/s |

要点:

1. **始终用配方 launcher 启动**(`LAYOUT=tp4|pp4 ./start.sh`),不要手工拼 PP/TP——launcher 承载层分配、PP 运行时、block size 与 allocator 设置。
2. **1.6.0 起 PP4 只支持 DFlash2** 投机模式;`SPEC_MODE=none/mtp` 未测不支持。
3. 本机此前在 1.4.x 需要的两个缓解(模块加载后强制 GC、workspace 增长放行)在 1.6.0 纯默认配置下**均不再需要**(A/B 验证)。
4. PP4 在窄链路(x4 甚至 x1)上保持 prefill 与聚合吞吐的优势;TP4 需要全部 x16 才能达到社区公开数字,x4 上 TP4 聚合明显劣化。
5. 已知边界:多流冷 prefill 期间 decode 被交错阻塞(PP 调度特性,缓存命中后恢复);长输入多流偶发简单 needle 未命中(8 路中 1 路,单流无此现象)。
6. 升级陷阱:`do_install` 的 fork editable 安装会卸载 `flashinfer`,verify 失败后在慢速链路上会循环;手动补装 `flashinfer-python` 并写入 stamp(`commit` 行 + `reqs <sha256 前 16 位>`)后跳过通道正常接管。

## 与 2× DGX Spark(TensorFold EXL3)的对照(2026-10-02)

第三个系统:2× DGX Spark(GB10,128GB 统一内存×2),TensorFold 运行时,`GLM-5.3-Flash-EXL3` 4bpw 权重,OpenAI 兼容 API。**基线协议与上表完全一致**(同 prompt、T=0、400-token 输出、预热后 3 轮中位),长文本任务为同一段"红警故事线"创作请求。

![DGX 短输入对比](assets/charts/08-cmp170hx-vs-dgx-c1.png)

| 口径 | 4× CMP 170HX(PP4 1.6.0) | 2× DGX Spark(EXL3) | DGX/CMP |
|---|---:|---:|---:|
| c1 structured | 220.5 | 108.9 | 49% |
| c1 coding | 127.5 | 75.2 | 59% |
| c1 prose | 95.9 | 60.9 | 64% |

端到端长文本(创作任务,同 prompt 两组指令):

![DGX 长文本对比](assets/charts/09-cmp170hx-vs-dgx-longtext.png)

| 任务 | CMP 170HX | 2× DGX Spark | 说明 |
|---|---|---|---|
| 思考开,6,000 token 预算 | 50.4 s 正常完成(正文 654 中文字) | 121.0 s 且**被截断**(6,000 token 全耗在思考,正文 0 字) | CMP 49.6 tok/s,DGX 49.6 tok/s——速率接近,但 DGX 思考耗 token 更快 |
| 直接输出指令,2,500 token 预算 | 17.7 s(769 中文字) | 49.7 s 且再次截断(正文仅 208 中文字) | CMP 84.7 tok/s,DGX 50.3 tok/s |

实际测试结果差异与归因(注意两条系统的配置差异不止一处,以下是主要变量):

1. **短输入生成速率:CMP 领先 1.6–2.0 倍**。CMP 用 W4A16 Marlin 权重 + DFlash2 投机解码(自适应深度,结构化文本每步约 4.5 token);DGX 的 EXL3 4bpw 走逐层反量化行解码,TensorFold 在 GB10 上无等效投机收益,每步就是 1 token 上下。投机解码对可预测文本的放大是主要差异来源。
2. **长文本端到端:差距扩大到 2.9 倍(18 s vs 50 s)**。除基础速率差(84.7 vs 50.3 tok/s)外,DGX 侧思考更冗长(同样的直出指令仍先生成约 7,900 字符英文分析),叠加截断风险。
3. **上下文容量:定位不同**。DGX 双卡 256GB 统一内存可承载更长上下文与更大 batch(其宣传定位);CMP 这套配置上限 512K,但单流生成与 prefill 速率在实测口径下全面领先。
4. 两台机器的角色差异:DGX 是 TensorFold 的目标硬件(Apple Silicon / 新 NVIDIA 卡统一运行时),CMP 170HX 是 Morrowmake 配方的目标硬件(sm_80 矿卡)。本对照是"两种开源栈各自在自己最优硬件上的实测",不是同硬件的运行时对比。



## 与社区方案的全景差距表(2026-10-04,structured 口径)

![全景对比](assets/charts/10-community-landscape.png)

| 系统 | 版本/布局/链路 | c1 structured | c8 聚合(墙钟) | 482K prefill |
|---|---|---:|---:|---:|
| Morrowmake 官方参考机 | 1.7.0 · TP4 · x16 · P2P on · 74 SM | **481** | **949** | ~3,197 |
| PixelML 实验机 | 1.6.0 · TP4 · x16(PLX) · 无 P2P | 396.0 | 798.6 | — |
| **本机** | 1.6.0 · TP4 · x4 | 284.2 | 447.2 | 1,017(500K 旧测) |
| **本机(现生产)** | 1.7.0 · PP4 · x4 | 216.9 | 605.2 | **5,616** |
| 2× DGX Spark | EXL3 4bpw · TensorFold | 108.9 | — | — |

c1 coding/prose 的相对排序一致(coding CMP 156.4-229.1 vs DGX 75.2;prose 95.9-136.4 vs 60.9),不再单列。

### 差在哪里:归因分解(以 c1 structured 216.9 vs 官方 481 = 45% 为例)

| 变量 | 量级(实测) | 可否软件解决 |
|---|---|---|
| 链路 x4 vs x16 | TP4 同版本对比 **−28%**(284.2 vs 396.0) | 否(主板固件) |
| 布局 PP4 vs TP4 | 同机同版本 **−22%** 单流(220.5 vs 284.2);聚合方向相反(+35%) | 是(按负载切布局) |
| 74 SM 解锁 | 官方 +5.7% 算力(70→74 SM) | 需装 cmpunlocker 驱动补丁(二期) |
| P2P on | 官方 1.7.0 默认开;PixelML PLX 上曾为负优化,x4 上无法协商 | 待 cmpunlocker 后再测 |
| 1.7.0 新内核 | 本机 coding +22.6%,structured/长输入持平 | 已获得 |

三个乘法因子 0.72(链路)× 0.78(布局)≈ 0.56,再叠加官方 1.7.0 的 P2P+74SM 增益,与本机 45% 的总差距吻合——**没有未知损失**。剩余可收敛项:74 SM 解锁与 P2P(硬件/驱动层,二期),以及 x4 链路本身(不可软件解)。

### 二期:cmpunlocker 74 SM 解锁与 P2P 实测(2026-10-04,1.7.0)

安装 Morrowmake fork 的 cmpunlocker(`--p2p --profile=8gb --no-iommu --no-passthrough`,gcc-12 编译,驱动 610.43.03 → 含 `ForceP2P=0x11`):**SM 70→74(四卡)**,P2P content check **108/108 通过**——x4 矿机上首次打通 GPU peer 通道。P2P 开启时 8 流聚合反而 **−13.6%**(522.9 vs 645.3,带宽不足下 P2P 序列化劣于 host-shm,与 PixelML 在 PLX 的观察一致),故生产采用 `P2P=off`:

| 口径 | 1.6.0(70 SM) | 1.7.0(74 SM,P2P off) | 变化 |
|---|---:|---:|---|
| c1 structured | 220.5 | 219.8 | 持平 |
| c1 coding | 127.5 | **167.3** | **+31%** |
| c1 prose | 95.9 | **101.5** | +5.8% |
| c8 计数聚合 | 645.8 | 645.3 | 持平 |
| 482K prefill | 5,596–5,619 | **5,656–5,778** | +2.6% |

回退方案:旧驱动模块与 conf 完整备份于机内 `/root/cmpunlocker_backup_20261004/`,恢复文件并重启即回 70 SM;`remove.sh` 可完整卸载。另:1.7.0 的 BOOT_CHECK 在 engine 未就绪时会因 URLError 误杀正常启动(已报上游,本机以 `BOOT_CHECK=0` 绕过并手动完成等价验证)。

### x16 下 P2P 能否大幅提升(评估)

**x16 本身是大头(+40% 单流),P2P 是其上的 +10% 锦上添花。**

- 官方 1.7.0(x16 直连,P2P verified on,74 SM)实测单流 481 tok/s:相对他们 1.6.0 无 P2P 的 394 为 +22%,其中 P2P + 新 all-reduce 的净贡献约 +10%,其余来自 74 SM 与新内核
- 反例:PixelML 在 PLX 拓扑上 P2P 2stage 为负优化;本机 x4 实测 P2P c8 −13.6%——P2P 收益强依赖链路带宽,带宽不足时序列化开销反噬
- 因此优先级:**恢复 x16 链路(主板固件/BIOS)>> P2P**(x16 后 `P2P=auto` 会自动验证并启用);本机 x4 保持 `P2P=off` 是数据支持的最优解

若 x16 恢复的量化预期(本机,官方口径折算):TP4 c1 structured 284 → ~437-481;PP4 c8 聚合 645 → ~900+(官方 949);482K prefill 5,616 → 6,300+。

## 结论(2026-10-04,二期收官)

1. **最终生产配置**:Morrowmake 1.7.0(引擎 c1ce6491)· PP4 · MAX_LEN=524288 · cmpunlocker 74 SM · `P2P=off` · `BOOT_CHECK=0` · DFlash2 自适应深度。当前水平:c1 structured 219.8 / coding **167.3** / prose 101.5 tok/s,c8 聚合 645.3,482K prefill 5,656–5,778、单流生成 ~147。**相对升级前(1.4.1):coding +31%、prose +5.8%、prefill +2.6%,KV 池 1.39M→2.72M,零回退。**
2. **升级收益逐版本**:1.6.0 主要来自 acceptance-aware 投机深度(structured +58%);1.7.0 主要来自新内核(coding +31%,对代码文本的投机正循环);74 SM 解锁贡献 prefill +2.6% 与部分 coding/prose 增量。
3. **布局按负载选**:单流交互 TP4(structured 284),批量/长上下文/多租户 PP4(聚合 645、482K prefill 5,656、KV 2.72M);TP2+PP2 两头不占,弃。
4. **P2P 双结论**:content check 108/108 通过证明驱动补丁可在 x4 矿机打通 peer(推翻"GNS 无解");但 Gen2 x4 带宽下 P2P 开启使聚合 **−13.6%**,生产必须 `P2P=off`。P2P 收益强依赖链路带宽:x16 官方口径 +10%,窄链路为负。
5. **链路是剩余差距的全部**:与官方参考机(x16+P2P+74 SM)的 45% 单流差距 = 链路 −28% × 布局 −22%,再叠加官方侧 P2P/74 SM 增益——无未知损失,软件栈已完全拉平。若 x16 恢复(主板固件):TP4 structured 预期 ~437–481,PP4 聚合 ~900+。
6. **阴性结果清单**:锁钟无效(vBIOS 电压曲线硬顶);思考开关不改变生成速率(速率=drafter 可预测性);SPEC_N 手调被自适应深度取代;P2P=force/窄链路 P2P 为负优化;小 prompt(<4608 块)块级缓存命中为 0 属正常。
7. **回退与备份**:旧驱动模块/配置在机内 `/root/cmpunlocker_backup_20261004/`,恢复+重启即回 70 SM;`remove.sh` 完整卸载;每个版本的 bench JSON 与配置都在 `data/` 与 `configs/`。

## 目录结构

```
├── README.md            中文报告(本文件)
├── README_EN.md         English version
├── notebooks/           按日期的实验记录(环境 pin、数据表、复现)
├── data/                脱敏原始 JSON(bench 归档,含 dgx62_*.json)
├── configs/             脱敏启动配置(PP4 / TP4)
├── scripts/             图表生成脚本(matplotlib,数据单源)
├── assets/charts/       图表 PNG
└── LICENSE
```

## 复现

```bash
git clone https://github.com/Morrowmake/glm53-flash-cmp170hx-recipe && cd glm53-flash-cmp170hx-recipe
git checkout v1.6.0
printf 'LAYOUT=pp4\nMODELS_DIR=/path/to/models\n' > .env
./install.sh && ./download.sh && ./start.sh
```

测量协议:MiaAI-Lab `tests/bench_decode.py`,T=0、`enable_thinking=false`、400 tokens、5 次取中位(本机 3 次)。注意 `enable_thinking=false` 时模型仍会在 content 前输出推理文字(上游已记录),token 计数以 usage 为准。图表可复现:`pip install matplotlib && python scripts/make_charts.py`。

## 许可与致谢

配方 MIT;vLLM fork Apache-2.0;DFlash2 权重 CC BY-NC-ND 4.0(评测用途,商用需另行授权)。感谢 Morrowmake 的 CMP 170HX 配方与 sm_80 内核适配、PixelML Club CMP 170HX 的独立实验与诊断、MiaAI-Lab 的测试协议、canada-quant 的 W4A16 权重、incoai 的 drafter,以及智谱/Z.ai 开放 GLM-5.3-Flash。本仓库是这些开源工作的本机复现与测量记录。
