# 2026-10-04 — 布局 × P2P 全矩阵测试与默认配置切换(TP4 · P2P on)

状态:数据完整,4 组配置每组独立启动。本篇为二期(74 SM)收尾记录,并宣布默认配置变更。

## 决策:默认配置切换为 TP4 · P2P on

本日矩阵测试完成后,生产默认从 PP4 · P2P off 切换为:

```
LAYOUT=tp4 · MAX_LEN=262144 · P2P=auto · BOOT_CHECK=0
```

理由:该组合拿到**全场单流最高分**(structured 301.6 / coding 227.5 / prose 152.5),P2P content check 在本机已稳定通过(缓存命中后 0.06s)。代价是 8 流聚合 442.4(TP4 off 的 −4.4%)与上下文上限 262144——对单流为主的交互式使用是净收益。混合/批量负载仍可选 PP4 · P2P off(聚合 645.3、512K 上下文),或 TP2+PP2 · P2P off(均衡型,聚合 497.1)。

切换脚本:`LAYOUT=tp4 MAX_LEN=262144 P2P=auto ./start.sh`(.env 已同步)。

## 矩阵完整数据

四组配置,每组独立启动(1.7.0 · 74 SM · Gen2 x4 · dflash k=自适应 · 同协议 3 轮中位,400-token 输出;c8 为 3,200 输出/整批墙钟):

| 布局 × P2P | c1 structured | c1 coding | c1 prose | c8 聚合 | KV 池 |
|---|---:|---:|---:|---:|---:|
| **TP4 · P2P on(新默认)** | **301.6** | **227.5** | **152.5** | 442.4 | 1,079,741 |
| TP4 · P2P off | 293.2 | 223.1 | 143.4 | 462.8 | 1,081,579 |
| TP2+PP2 · P2P on | 231.4 | 188.4 | 123.2 | 468.4 | ~1.39M |
| TP2+PP2 · P2P off | 235.9 | 188.2 | 125.2 | 497.1 | ~1.39M |
| PP4 · P2P off(原默认,512K) | 219.8 | 167.3 | 101.5 | **645.3** | 2,715,062 @524288 |
| PP4 · P2P on | 212.9 | 163.2 | 98.9 | 522.9 | 2,717,737 @524288 |

P2P 状态判定:`[p2p] P2P enabled: content check passed`(每对字节级验证);TP4 的 check 走 boot 缓存(0.06-0.07s)。

## 矩阵结论

1. **P2P 的方向由布局通信量决定**:
   - TP4(all-reduce 密集):单流 +3~6%(293.2→301.6 structured),聚合 −4.4%——单流净赚,批量净亏
   - TP2+PP2(混合通信):基本中性(−2% 内)
   - PP4(stage hop):单流转负(−3%),聚合 −19.1%——最不该开 P2P 的布局
   - Gen2 x4 带宽下无任何一行严格正收益;唯一可辩护的开启场景是 TP4 单流极致压榨
2. **1.7.0 改写了布局格局**(推翻我们 1.4.x 时的结论):
   - TP2+PP2 复活:单流 235.9 > PP4 219.8,coding 188.2 > PP4 167.3,聚合 497.1 > TP4 462.8
   - 单流排序:TP4(301.6) > TP2+PP2(235.9) > PP4(219.8)
   - 聚合排序:PP4(645.3) > TP2+PP2(497.1) > TP4(462.8)
   - 新内核(compiled Marlin、KDA tile、tuned GEMM/mHC)对中间布局的收益大于两端
3. **74 SM 的贡献贯穿所有布局**:coding 相对 1.6.0 同布局提升 +22~47%。

## 与社区参照(structured 单流)

| 系统 | 配置 | 单流 | 聚合 |
|---|---|---:|---:|
| Morrowmake 官方 | 1.7.0 · TP4 · x16 · P2P · 74 SM | 481 | 949 |
| PixelML | 1.6.0 · TP4 · x16 PLX | 396.0 | 798.6 |
| 本机(新默认) | 1.7.0 · TP4 · x4 · P2P · 74 SM | **301.6** | 442.4 |
| 本机 | 1.7.0 · PP4 · x4 · 74 SM | 219.8 | 645.3 |
| 2× DGX Spark | EXL3 · TensorFold | 108.9 | — |

本机 TP4 · P2P on 与 PixelML x16 的差距收窄到 **−23.8%**(此前 PP4/1.6.0 口径为 −45%)——74 SM + P2P + 1.7.0 三项把软件/固件层全部拉平,剩余纯为链路带宽。

## 原始数据

`../data/decode_c1_{structured,coding,prose}_{tp4v170poff,tp4v170p2p,t2p2off,t2p2on}.json` 与对应 `decode_c8_*`(16 份);图表 `../assets/charts/11-layout-p2p-matrix.png`。

## 复现

```bash
cd glm53-flash-cmp170hx-recipe && git checkout v1.7.0
LAYOUT=tp4 MAX_LEN=262144 P2P=auto ./start.sh    # 新默认
LAYOUT=pp4 MAX_LEN=524288 P2P=off ./start.sh     # 吞吐/长上下文备选
```
