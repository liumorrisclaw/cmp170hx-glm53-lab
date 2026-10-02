# 2026-10-02 — Morrowmake 1.6.0 升级、布局对比与链路差距定量

状态:数据完整。单机观察,样本量小,不外推为普遍结论。

## 环境与版本 pin

| pin | 值 |
|---|---|
| 配方 | Morrowmake/glm53-flash-cmp170hx-recipe @ a242b4f(v1.6.0) |
| 引擎 | vLLM fork v0.1.dev21+g3a2bf16da,预编译 wheel b6761e8ded |
| 权重 | canada-quant/GLM-5.3-Flash-W4A16-MTP @ 5723f4d02a |
| drafter | incoai/GLM-5.3-Flash-DFlash2 @ bf582e4eac(acceptance-aware 自适应深度) |
| GPU | 4× CMP 170HX 64GB,250W 解锁,Gen2 **x4** 全部,无 P2P |
| 驱动 | 驱动层拒绝 GPU peer access(矿卡行为) |

## 升级过程记录

1. 1.4.x 时代引擎(378c37b00)在 PP4 启动需要两个本机缓解:模块加载后强制 GC(marlin 权重转换碎片化)与 workspace 增长放行。
2. 升级 1.6.0:reset 配方到 v1.6.0 → launcher 安装(预编译 wheel b6761e8ded)→ **纯默认配置启动成功**,上述两个缓解均未启用。
3. 安装陷阱:`do_install` 的 fork editable 安装会从 venv 卸载 `flashinfer`,verify 因缺模块失败;慢速链路上循环。处理:手动 `uv pip install flashinfer-python`,然后写 stamp(第一行 fork commit,第二行 `reqs <sha256(common.txt+cuda.txt) 前 16 位>`),跳过通道接管。
4. Morrowmake issue #1 回帖确认:预编译 wheel 为 b6761e8ded,冷断电后重测通过,缓解不再需要。

## 结果

测量协议:MiaAI-Lab 同口径,T=0、thinking off(输出仍含推理文字)、400-token 输出、预热后 3 轮中位。c8 聚合为 3,200 输出 tokens / 整批墙钟(含 TTFT)。

### 短输入 c1(1.6.0,PP4,MAX_LEN=524288)

| prompt | 中位 tok/s | 1.4.x 参照 |
|---|---:|---:|
| structured(count 1-200) | **220.5** | 139.4 |
| coding(clamp_range) | 127.5 | 129.2 |
| prose(hash map) | 95.9 | 94.6 |

### c8 计数聚合(1.6.0)

- PP4:**645.8 tok/s**(墙钟)
- TP4:447.2 tok/s(墙钟)

### 长输入(PP4,482K tokens 级,两轮)

| 轮 | TTFT | 有效 prefill | 生成速率 | needle |
|---|---:|---:|---:|---|
| 1 | 85.8 s | 5,619 tok/s | 156.9 tok/s | 命中 |
| 2 | 86.2 s | 5,601 tok/s | 140.1 tok/s | 命中 |

脚本未保存输出 token 数;needle 为子串检查,非质量评测。

### TP4 对照(1.6.0,MAX_LEN=262144,KV 池 1,081,579)

| prompt | 中位 tok/s | PixelML x16 参照 | 差距 |
|---|---:|---:|---:|
| structured | 284.2 | 396.0 | −28% |
| coding | 229.1 | 306.2 | −25% |
| prose | 136.4 | 192.5 | −29% |

c8 计数聚合:447.2(x4)vs 798.6(x16),−44%。

## 锁钟实验(阴性)

`nvidia-smi -lgc 1695` 设置成功,负载实测时钟仍 1470–1485 MHz,decode 283.7 vs 284.2(未锁)无差异。结论:频率由 vBIOS 电压曲线决定,软件锁定无效;改变曲线需要 vBIOS 修改。

## 结论与边界

- 1.6.0 的 acceptance-aware 深度对结构化文本收益显著(+58%),对代码/文字类文本中性。
- 同引擎同协议下,x4 与 x16 的差距:单流 −25~29%,聚合 −44%;本机软件栈内无法进一步收敛,需 x16 链路。
- 同 x4 链路下:单流 TP4 优于 PP4,聚合 PP4 优于 TP4,按负载选布局。
- 单机、小样本、miner 卡个体差异(vBIOS 曲线、供电)都会影响绝对数字;相对结论(布局取舍、链路差距方向)比绝对值更可迁移。

## 复现

```bash
git clone https://github.com/Morrowmake/glm53-flash-cmp170hx-recipe && cd glm53-flash-cmp170hx-recipe
git checkout v1.6.0
printf 'LAYOUT=pp4\nMODELS_DIR=/path/to/models\n' > .env   # 或 LAYOUT=tp4
./install.sh && ./download.sh && ./start.sh
```

原始数据:`../data/decode_c1_*_v160*.json`、`../data/decode_c8_structured_v160*.json`、`../data/ctx512k_v160.json`。

## English summary

Upgraded the engine from 1.4.x (378c37b00) to Morrowmake 1.6.0 (3a2bf16da, wheel b6761e8ded). The pure launcher default configuration boots cleanly on PP4 — the two local mitigations needed on 1.4.x (forced GC after module load, workspace-growth allowance) are no longer required (A/B verified). One trap: `do_install` uninstalls `flashinfer` during the editable install; on slow links the verify step then fails in a loop. Manually install `flashinfer-python` and write the stamp to hand control to the skip path.

Measured on 1.6.0 (400-token outputs, median of 3): PP4 c1 structured **220.5** (+58% vs 139.4 on 1.4.x), coding/prose flat — acceptance-aware depth pays off on structured text only. TP4 on this Gen2-x4 rig: 284.2 / 229.1 / 136.4, 8-user aggregate 447.2. Against PixelML's 1.6.0 TP4 numbers on Gen2 x16 (same engine, same protocol): −25…−29% single-stream, −44% aggregate — the PCIe link is the dominant remaining variable. Clock locking tested negative (vBIOS voltage curve ignores `-lgc`).
