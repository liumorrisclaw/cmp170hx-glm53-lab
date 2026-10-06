# cmpunlocker v0.5 upgrade notes & credits (2026-10-06)

[中文](CMPUNLOCKER-V0.5.md) | English

This rig (4× CMP 170HX 64GB, Gen2 x4, GLM-5.3-Flash inference production box) moved from the bendy2 gen2-branch build (74 SM + ForceP2P) to **upstream cmpunlocker v0.5** on 2026-10-06: zero regression, ECC live for the first time. Full experiment log and data: [`notebooks/2026-10-06-cmpunlocker-v05-ecc-upgrade.md`](notebooks/2026-10-06-cmpunlocker-v05-ecc-upgrade.md).

## Upstream links

- Repository: <https://github.com/amoghmunikote/cmpunlocker>
- Version installed: [Release v0.5](https://github.com/amoghmunikote/cmpunlocker/releases/tag/v0.5) (2026-10-05; new: ECC DRAM and SRAM, +4 more SMs)
- Install baseline: v0.5 @ driver 610.43.03, `--profile=8gb --no-iommu --no-passthrough`, 15-patch local build (v0.5's native 14 patches + the ported P2P patch)

## What v0.5 actually changed on this rig

| Item | Before (bendy2 gen2 @ ebcb14e) | After v0.5 | Verdict |
|---|---|---|---|
| ECC | N/A (not exposed) | **Enabled**, full SRAM/DRAM correctable & uncorrectable counters | net new gain |
| SM | 74 × 4 | 74 × 4 | the "+4 SMs" in the release notes is relative to v0.4's 70 baseline — unchanged here |
| 64GB / Gen2 / BAR1 | fine | fine | no regression (BAR1 64/64/32/8 identical per card; motherboard MMIO window limit) |
| P2P | unconditionally forced (fork behaviour) | upstream has no P2P feature; ported the fork patch and **added a `ForceP2P` registry runtime gate** | `cmp-forcep2p on/off` one-liner switch; content check 108/108 PASS |

### ECC rigour note

The current ECC conclusion is **integration-level**: reporting layer (complete counter structure, programmable queries), control layer (`nvidia-smi -e 0` returns Not Supported — statically forced by the patches), hardware layer (SEC2 payload FBPA writes corroborated by dmesg), and load layer (per-GPU 1 GB deterministic pattern ×20 full-card copies bit-verified PASS, ~1585 GB/s aggregate). **Directly proving the correction path works requires fault-injection tooling, which we do not have.** A 5-minute ECC counter snapshot cron is deployed (aggregate correctable growth = direct evidence of correction working; uncorrectable ≠ 0 = ERROR) and we are watching for silent bit-flips that never trigger ECC.

### Performance impact (TP4 · P2P off · same script, same protocol)

structured 293.5 vs 293.2, coding 222.9 vs 223.1, prose 143.3 vs 143.4, 8-user aggregate 461.5 vs 462.8 — all |Δ| ≤ 0.3%, noise level. With P2P on: single-stream structured 302.2 (+3.1% vs off).

## Ops notes (gotchas)

1. `install.sh` rewrites `/etc/modprobe.d/cmp-pcie-gen2.conf` on every run → re-arm `sudo cmp-forcep2p on` after any reinstall, then reboot;
2. The installer removes the DKMS modules → **after a kernel upgrade you must rerun `install.sh`** or the driver will not load (kernel metas are `apt-mark hold` here, plus a `cmp-driver-status` self-check);
3. v0.5's SEC2 payload table dropped `trap31_plm` (0x0012277c), so the P2P patch's safety guard correctly refused to force the caps — the register is restored in our payload table and declared in `constants.yaml`;
4. Slow-link builds: pre-download the open-gpu-kernel-modules tarball and use a PyPI mirror for uv (see the notebook for details).

## Credits

- **[amoghmunikote/cmpunlocker](https://github.com/amoghmunikote/cmpunlocker)** — the unlocker itself; v0.5's ECC work (ecc-enable / ecc-fbpa-static / ecc-reporting / booter-verify) is the core value of this upgrade. The guard-comment philosophy — "a truthful *not supported* beats silent corruption" — saved us from a bad P2P port.
- **[Morrowmake/glm53-flash-cmp170hx-recipe](https://github.com/Morrowmake/glm53-flash-cmp170hx-recipe)** — the engine recipe and vLLM fork (followed 1.4.1 → 1.7.2); the `p2p-unlock.patch` originates from their cmpunlocker fork; the BOOT_CHECK timing bug was fixed within one release of our report.
- **[bendy2/cmpunlocker](https://github.com/bendy2/cmpunlocker)** (`combined-multiple-cards-gen2` branch) — this rig's production driver from Aug to Oct 2026; its guarded multi-GPU retrain served flawlessly for nearly two months.
- **[PixelML/club-170hx](https://github.com/PixelML/club-170hx)** — independent experiments and the prescient PLX-topology P2P pessimization notes; style reference for this repo.
- **MiaAI-Lab** — the `bench_decode.py` measurement protocol.
- **canada-quant** (GLM-5.3-Flash-W4A16-MTP weights), **incoai** (DFlash2 drafter).
- **Zhipu / Z.ai** — for open-sourcing GLM-5.3-Flash.

This repository is a reproduction, measurement and ops record of the above open-source work on a 4× CMP 170HX (Gen2 x4) machine. Bench receipts in [`data/`](data/), charts in [`assets/charts/`](assets/charts/).
