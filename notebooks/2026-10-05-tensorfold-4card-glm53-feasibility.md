# 2026-10-05 — TensorFold 在 4×CMP 170HX 上跑 GLM-5.3-Flash:可行性评估(结论:不可行)

目标:把 hym74 上的 TensorFold POC(此前单卡跑通过 Qwen3.8-27B EXL3)扩展到 4 卡 GLM-5.3-Flash,使用最新内核(0.6.5,2026-10-03),对比能否超过 Morrowmake 1.7.0 基线(TP4·P2P on 单流 301.6 / PP4 聚合 645.3)。

结论先行:**不可行**。TensorFold 的 GLM CUDA 引擎存在三重结构性约束,任何一项都独立否决本机部署;均为源码级证据,非文档推测。

## 约束 1:rank 数硬编码为 1 或 2

`src/tensorfold/cli_args.py:125`:

```python
cuda.add_argument("--tp", type=int, choices=(1, 2), default=1, ...)
```

`choices=(1, 2)` 是 argparse 级别的硬限制——不存在 4-rank 路径。GLM 的两卡权重切分工具(`families/glm5_next/cuda/split.py`)同样只有 `--rank choices=(0, 1)`。0.6.4/0.6.5 changelog 中所有多卡工作(Flash Next `--parallel`、共享 lane rounds)均限于 1-2 rank;无 4-rank 路线图。

## 约束 2:GLM 引擎要求"两块 128GB 卡"

`families/glm5_next/__init__.py` 的启动提示原文:

> GLM-5.3-Flash runs on two NVIDIA GPUs with **128 GB each** (two DGX Sparks)

2 分片权重(164GB EXL3 ÷ 2 ≈ 82GB/片)+ KV 与运行时 → 官方口径每 rank 128GB。本机每卡 **64GB**,不足所需的一半。

## 约束 3:2-rank 架构与 4 卡物理布局不匹配

TensorFold 的 2-rank 是**跨机器**设计(`--master` 指向对端地址,NCCL/RoCE 走网络,文档示例是两台 DGX Spark 用直连电缆)。单机 4 卡既无法表达为 2 ranks(每 rank 单 GPU 语义),也没有把 2 GPU 合并为 1 rank 的数据并行分片支持。

## 本机已有的准备(为什么"差一步"却不成立)

| 项 | 状态 |
|---|---|
| glm53-tr3-4bpw 权重(164GB,官方转换) | ✅ 已下载 |
| TensorFold 源码(0.6.3)+ sm_80 适配补丁 ×3(capability floor / e4m3 asm / clusters) | ✅ 已就绪 |
| Qwen3.8-27B 单卡 POC | ✅ 曾跑通(占 GPU0 20GB) |
| 4-rank 引擎支持 | ❌ 上游不存在 |
| 64GB/卡 vs 128GB/rank | ❌ 物理容量差 2 倍 |

之前 POC 能跑 Qwen3.8-27B(单卡 20GB)恰说明补丁有效,但 GLM-320B 的权重体量把 rank 上限和显存容量两个约束同时击穿——补丁解决的是"能不能算"(sm_80),解决不了"放不放得下"(分片结构)。

## 对比基线(为什么也不必遗憾)

当前基线已是 CMP 170HX 上的强结果(1.7.0 · 74 SM · TP4 · P2P on):单流 structured **301.6** / coding 227.5 / prose 152.5。参照:2×DGX Spark(256GB 统一内存,官方支持的 2-rank 配置)同协议仅 **108.9 / 75.2 / 60.9**——TensorFold 的 EXL3 路径没有投机解码的等效收益,在同权重家族上的实测速率本就显著低于 Morrowmake fork 的 W4A16+DFlash2 路径。即使容量问题解决,超过基线的概率也很低。

## 可能的改变条件

1. 上游实现 4-rank(或任意 rank)分片——可向 ashhart/TensorFold 提 feature request(附本机 4×64GB 的硬件画像与 sm_80 补丁,作为 Ampere 支持的补充证据)
2. 128GB+ 显存的卡(如 RTX PRO 6000 96GB 仍不足;H100/B200 80-192GB 可行但已超出矿机范畴)
3. 更低位宽的 GLM 转换(3bpw ≈ 123GB,2 分片每片 62GB 勉强贴着 64GB——但精度损失未评估,且 split.py 需改造支持 3bpw 输出)

## 结论

维持基线:**Morrowmake 1.7.0 · 74 SM · TP4 · P2P on(单流 301.6/227.5/152.5)与本机各布局数据**(aggregate 645.3 @PP4)继续作为这台机器的性能上限代表。TensorFold 途径在本硬件上无路可走,除非上游引入 4-rank 分片。
