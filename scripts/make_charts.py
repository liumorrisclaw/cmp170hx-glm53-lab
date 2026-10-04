#!/usr/bin/env python3
"""Generate comparison charts from the measured data in ../data/.
All numbers are hard-coded from the archived JSON receipts (single-source)."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import os

OUT = os.path.join(os.path.dirname(__file__), "..", "assets", "charts")
os.makedirs(OUT, exist_ok=True)

INK, INK2 = "#1a1a1a", "#6b6b6b"
BLUE, ORANGE, GRAY, GREEN = "#3b6fb6", "#e08a3c", "#9aa5b1", "#4c9a6a"
plt.rcParams.update({"font.size": 10, "axes.edgecolor": INK2, "axes.labelcolor": INK,
                     "text.color": INK, "xtick.color": INK, "ytick.color": INK})

def save(fig, name):
    fig.savefig(f"{OUT}/{name}.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("wrote", name)

def label_bars(ax, bars, fmt="{:.1f}", dy=1.0):
    for b in bars:
        ax.text(b.get_x() + b.get_width()/2, b.get_height() + dy,
                fmt.format(b.get_height()), ha="center", va="bottom", fontsize=9, color=INK)

# ---- chart 1: engine upgrade 1.4.x -> 1.6.0 (PP4 c1) -----------------------
prompts = ["structured", "coding", "prose"]
v141 = [139.4, 129.2, 94.6]
v160 = [220.5, 127.5, 95.9]
x = np.arange(3); w = 0.36
fig, ax = plt.subplots(figsize=(7.2, 3.6))
b1 = ax.bar(x - w/2, v141, w, color=GRAY, label="1.4.x (k=3 fixed)")
b2 = ax.bar(x + w/2, v160, w, color=BLUE, label="1.6.0 (acceptance-aware depth)")
label_bars(ax, b1); label_bars(ax, b2)
for i in range(3):
    d = (v160[i]/v141[i] - 1) * 100
    ax.text(x[i] + w/2, v160[i] - 16, f"{d:+.0f}%", ha="center", fontsize=10,
            color="white", fontweight="bold")
ax.set_xticks(x, prompts); ax.set_ylabel("decode tok/s (median of 3, 400-tok)")
ax.set_ylim(0, 260); ax.legend(frameon=False)
ax.set_title("PP4 single-stream decode: 1.4.x vs 1.6.0")
save(fig, "01-upgrade-141-160-pp4")

# ---- chart 2: 1.6.0 TP4 vs PP4 (c1 + c8) -----------------------------------
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10.5, 3.6), gridspec_kw={"width_ratios": [3, 1.3]})
tp4 = [284.2, 229.1, 136.4]; pp4 = [220.5, 127.5, 95.9]
b1 = ax1.bar(x - w/2, tp4, w, color=BLUE, label="TP4 (x4)")
b2 = ax1.bar(x + w/2, pp4, w, color=ORANGE, label="PP4 (x4)")
label_bars(ax1, b1); label_bars(ax1, b2)
ax1.set_xticks(x, prompts); ax1.set_ylim(0, 330); ax1.legend(frameon=False)
ax1.set_title("1.6.0 single-stream decode")
c8v = [447.2, 645.8]
b3 = ax2.bar([0, 1], c8v, 0.55, color=[BLUE, ORANGE])
label_bars(ax2, b3)
ax2.set_xticks([0, 1], ["TP4", "PP4"]); ax2.set_ylim(0, 760)
ax2.set_title("8-user aggregate (wall clock)")
save(fig, "02-layout-tp4-vs-pp4-160")

# ---- chart 3: PCIe link gap (x4 vs x16, same engine TP4) -------------------
x16 = [396.0, 306.2, 192.5]
fig, ax = plt.subplots(figsize=(7.2, 3.6))
b1 = ax.bar(x - w/2, x16, w, color=GRAY, label="PixelML rig — Gen2 x16 (TP4, 1.6.0)")
b2 = ax.bar(x + w/2, tp4, w, color=BLUE, label="this rig — Gen2 x4 (TP4, 1.6.0)")
label_bars(ax, b1); label_bars(ax, b2)
for i in range(3):
    d = (tp4[i]/x16[i] - 1) * 100
    ax.text(x[i] + w/2, tp4[i] - 22, f"{d:.0f}%", ha="center", fontsize=10,
            color="white", fontweight="bold")
ax.set_xticks(x, prompts); ax.set_ylabel("decode tok/s (median of 3, 400-tok)")
ax.set_ylim(0, 450); ax.legend(frameon=False, fontsize=9)
ax.set_title("PCIe link gap, same engine & protocol (TP4): x4 vs x16")
save(fig, "03-link-gap-x4-vs-x16")

# ---- chart 4: c8 aggregate, three configurations ---------------------------
fig, ax = plt.subplots(figsize=(6.4, 3.4))
names = ["TP4 x4\n(1.6.0)", "PP4 x4\n(1.6.0)", "TP4 x16\n(PixelML 1.6.0)"]
vals = [447.2, 645.8, 798.6]
cols = [BLUE, ORANGE, GRAY]
b = ax.bar(names, vals, 0.55, color=cols)
label_bars(ax, b)
ax.set_ylabel("8-user structured aggregate tok/s")
ax.set_ylim(0, 900)
ax.set_title("8-user aggregate: layout and link effects")
save(fig, "04-c8-aggregate-compare")

# ---- chart 5: long context 482K, two runs ----------------------------------
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.6, 3.4))
runs = ["run1 (482,277 tok)", "run2 (482,635 tok)"]
pf = [5619, 5601]; dec = [156.9, 140.1]
b1 = ax1.bar(runs, pf, 0.5, color=BLUE)
label_bars(ax1, b1)
ax1.set_ylabel("effective prefill tok/s"); ax1.set_ylim(0, 6600)
ax1.set_title("482K input, TTFT 85.8/86.2 s")
b2 = ax2.bar(runs, dec, 0.5, color=ORANGE)
label_bars(ax2, b2, fmt="{:.1f}", dy=2)
ax2.set_ylabel("decode tok/s"); ax2.set_ylim(0, 200)
ax2.set_title("482K input, generation (needle hit x2)")
save(fig, "05-longctx-482k-two-runs")

# ---- chart 6: 1.4.x three layouts ------------------------------------------
t2p2 = [163.5, 149.3, 120.0]
tp4_141 = [186.5, 174.4, 127.7]; pp4_141 = [139.4, 129.2, 94.2]
fig, ax = plt.subplots(figsize=(7.6, 3.6))
b1 = ax.bar(x - w, tp4_141, w, color=BLUE, label="TP4")
b2 = ax.bar(x, t2p2, w, color=GRAY, label="TP2+PP2")
b3 = ax.bar(x + w, pp4_141, w, color=ORANGE, label="PP4")
label_bars(ax, b1); label_bars(ax, b2); label_bars(ax, b3)
ax.set_xticks(x, prompts); ax.set_ylim(0, 210); ax.legend(frameon=False, fontsize=9)
ax.set_title("1.4.x: three layouts on Gen2 x4 (single-stream decode)")
save(fig, "06-layouts-141x")

# ---- chart 7: acceptance per position (PP4 1.6.0, mixed workload) ----------
steps, acc = 630.0, [482, 308, 204, 94, 75, 52, 30]
pos_rate = [a/steps for a in acc]
fig, ax = plt.subplots(figsize=(7.2, 3.4))
ax.plot(range(1, 8), pos_rate, marker="o", ms=5, color=BLUE)
for i, r in enumerate(pos_rate):
    ax.text(i + 1, r + 0.02, f"{r:.2f}", ha="center", fontsize=9, color=INK)
ax.set_xticks(range(1, 8))
ax.set_xlabel("draft position"); ax.set_ylabel("acceptance rate")
ax.set_ylim(0, 0.92)
ax.set_title("DFlash2 acceptance per position — PP4 1.6.0, mixed prompts (630 steps)")
save(fig, "07-acceptance-per-position")

print("all charts done")

# ---- chart 8: CMP 170HX vs 2x DGX Spark (c1, same protocol) ----------------
dgx = [108.9, 75.2, 60.9]
fig, ax = plt.subplots(figsize=(7.6, 3.6))
b1 = ax.bar(x - w/2, [220.5, 127.5, 95.9], w, color=ORANGE, label="4x CMP 170HX - PP4 1.6.0 (W4A16 + DFlash2)")
b2 = ax.bar(x + w/2, dgx, w, color=GRAY, label="2x DGX Spark - TensorFold EXL3 4bpw")
label_bars(ax, b1); label_bars(ax, b2)
for i in range(3):
    r = dgx[i] / [220.5, 127.5, 95.9][i]
    ax.text(x[i] + w/2, dgx[i] - 12, f"{r*100:.0f}%", ha="center", fontsize=10,
            color="white", fontweight="bold")
ax.set_xticks(x, prompts); ax.set_ylim(0, 260); ax.legend(frameon=False, fontsize=9)
ax.set_title("Same prompts, same protocol: CMP 170HX rig vs 2x DGX Spark")
save(fig, "08-cmp170hx-vs-dgx-c1")

# ---- chart 9: long-text end-to-end (Red Alert storyline) -------------------
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10.2, 3.6))
names = ["CMP 170HX\nPP4 1.6.0", "2x DGX Spark\nEXL3"]
t_default = [50.4, 121.0]; t_direct = [17.7, 49.7]
b1 = ax1.bar([0, 1], t_default, 0.5, color=[ORANGE, GRAY])
label_bars(ax1, b1, fmt="{:.0f}s")
ax1.set_xticks([0, 1], names); ax1.set_ylim(0, 150)
ax1.set_title("thinking on: wall time (CMP finished, DGX truncated at 6k)")
b2 = ax2.bar([0, 1], t_direct, 0.5, color=[ORANGE, GRAY])
label_bars(ax2, b2, fmt="{:.0f}s")
ax2.set_xticks([0, 1], names); ax2.set_ylim(0, 70)
ax2.set_title("direct-output instruction: wall time")
save(fig, "09-cmp170hx-vs-dgx-longtext")
print("cmp/dgx charts done")

# ---- chart 10: full landscape vs community systems (1.7.0 era) -------------
fig, ax = plt.subplots(figsize=(9.2, 4.2))
systems = ["Morrowmake 1.7.0\nTP4 x16+P2P+74SM\n(official)", "PixelML 1.6.0\nTP4 x16 PLX",
           "ours 1.6.0\nTP4 x4", "ours 1.7.0\nPP4 x4", "2x DGX Spark\nEXL3 TensorFold"]
s_str = [481, 396.0, 284.2, 216.9, 108.9]
s_c8  = [949, 798.6, 447.2, 605.2, None]
xx = np.arange(len(systems)); ww = 0.38
b1 = ax.bar(xx - ww/2, s_str, ww, color=BLUE, label="single stream (structured)")
s_c8_plot = [v if v else 0 for v in s_c8]
b2 = ax.bar(xx + ww/2, s_c8_plot, ww, color=ORANGE, label="8-user aggregate (structured, wall)")
label_bars(ax, b1, fmt="{:.0f}", dy=8); label_bars(ax, b2, fmt="{:.0f}", dy=8)
ax.set_xticks(xx, systems, fontsize=8.5); ax.set_ylim(0, 1080)
ax.set_ylabel("tok/s"); ax.legend(frameon=False, fontsize=9)
ax.set_title("Community landscape, structured prompt (no bar = not measured)")
save(fig, "10-community-landscape")
print("landscape chart done")

# ---- chart 11: layout x P2P matrix on 1.7.0 (74 SM) ------------------------
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.2, 4.0))
layouts = ["TP4", "TP2+PP2", "PP4"]
off_s = [293.2, 235.9, 219.8]; on_s = [301.6, 231.4, 212.9]
off_a = [462.8, 497.1, 645.3]; on_a = [442.4, 468.4, None]
xx = np.arange(3)
b1 = ax1.bar(xx - ww/2, off_s, ww, color=GRAY, label="P2P off")
b2 = ax1.bar(xx + ww/2, on_s, ww, color=BLUE, label="P2P on")
label_bars(ax1, b1); label_bars(ax1, b2)
ax1.set_xticks(xx, layouts); ax1.set_ylim(0, 360); ax1.legend(frameon=False, fontsize=9)
ax1.set_title("single stream, structured (tok/s)")
on_a_plot = [v if v else 0 for v in on_a]
b3 = ax2.bar(xx - ww/2, off_a, ww, color=GRAY, label="P2P off")
b4 = ax2.bar(xx + ww/2, on_a_plot, ww, color=BLUE, label="P2P on")
label_bars(ax2, b3); label_bars(ax2, b4)
ax2.set_xticks(xx, layouts); ax2.set_ylim(0, 760); ax2.legend(frameon=False, fontsize=9)
ax2.set_title("8-user aggregate, structured (wall, tok/s)")
fig.suptitle("1.7.0 @ 74 SM, Gen2 x4: layout × P2P matrix", y=1.02)
fig.tight_layout()
save(fig, "11-layout-p2p-matrix")
print("matrix chart done")
