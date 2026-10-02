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

## 目录结构

```
├── README.md            中文报告(本文件)
├── README_EN.md         English version
├── notebooks/           按日期的实验记录(环境 pin、数据表、复现)
├── data/                脱敏原始 JSON(bench 归档)
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
