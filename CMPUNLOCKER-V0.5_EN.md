# cmpunlocker v0.5 upgrade notes & credits (2026-10-06)

[中文](CMPUNLOCKER-V0.5.md) | English

This rig (4× CMP 170HX 64GB, Gen2 x4, GLM-5.3-Flash inference production box, driver locked at 610.43.03) moved from the bendy2 gen2-branch build (74 SM + ForceP2P, 2026-08-13 merge) to **upstream cmpunlocker v0.5** on 2026-10-06. Three goals: pick up v0.5's newly unlocked **ECC** (DRAM + SRAM correction), turn P2P from an on/off accident into a **deliberate per-deployment switch**, and return to the actively maintained upstream line. Result: **zero regression, ECC live for the first time, ForceP2P now a runtime option**. This page is the upgrade & ops reference; the day-by-day experiment log lives in [`notebooks/2026-10-06-cmpunlocker-v05-ecc-upgrade.md`](notebooks/2026-10-06-cmpunlocker-v05-ecc-upgrade.md).

## 1. Upstream links

- Repository: <https://github.com/amoghmunikote/cmpunlocker>
- Version installed: [Release v0.5](https://github.com/amoghmunikote/cmpunlocker/releases/tag/v0.5) (2026-10-05; notes: Error-Correcting Code (ECC) DRAM and SRAM, +4 more SMs)
- Install baseline: v0.5 @ driver 610.43.03, `sudo ./install.sh --profile=8gb --no-iommu --no-passthrough`, a **15-patch local build** (v0.5's native 14 patches + the P2P patch ported from the Morrowmake fork, see §4)
- Preflight checks: Secure Boot off, `linux-headers-$(uname -r)` present, passwordless sudo, all 4× `10de:20c2` classified per-card by PCI ID (v0.5 native multi-GPU support)

## 2. Before / after on this rig (measured)

| Item | Before (bendy2 gen2 @ ebcb14e) | After v0.5 | Verdict |
|---|---|---|---|
| ECC mode | N/A (not exposed at all) | **Enabled** (Current + Pending); SRAM Correctable / Uncorrectable Parity / Uncorrectable SEC-DED / DRAM Correctable / DRAM Uncorrectable counters fully exposed and queryable | **net new gain — the core value of this upgrade** |
| SM count | 74 × 4 | 74 × 4 | the "+4 more SMs" in the release notes is relative to v0.4's 70 baseline; this rig was already at 74 |
| 64GB VRAM / PCIe Gen2 / BAR1 | fine | fine | no regression; BAR1 64/64/32/8 GB identical per card vs the pre-upgrade snapshot (motherboard MMIO window limit — the dmesg BAR1 assign warnings predate this upgrade) |
| P2P | unconditionally forced (fork behaviour) | upstream has no P2P feature; ported the fork patch and **added a `ForceP2P` registry runtime gate** | `sudo cmp-forcep2p on/off` + reboot; content check 108/108 PASS |
| Multi-GPU support | fork's guarded multi-GPU branch | native upstream (per-card lspci classification, inventory marker on disk) | fork dependency removed |
| Maintainability | frozen at 2026-08-13 | actively maintained upstream | future updates = git pull + reinstall |

## 3. ECC: verification method and its rigour boundary

ECC is the headline of v0.5, so we deliberately separate "verified live" from "proven correcting":

**Four-layer integration verification (all passed):**

| Layer | Method | Result |
|---|---|---|
| L1 reporting | `nvidia-smi -q -d ECC` + programmable query fields | all 4 GPUs Current/Pending Enabled; full A100-style counter set exposed, queries return real values |
| L2 control | root `nvidia-smi -e 0` (attempt disable) | returns **Not Supported** — `ecc-fbpa-static` welds ECC statically on, the disable path is intentionally dead (side effect: no ECC on/off A/B comparison possible) |
| L3 hardware | patch source ↔ dmesg cross-check | build contains ecc-enable / ecc-fbpa-static / ecc-reporting / booter-verify; dmesg shows `PLM[1] FBPA(0x9a0148) status=0xffff` — the ECC static-config write accepted by GSP firmware |
| L4 load | per-GPU 1 GB deterministic pattern fill → 20 full-card copy rounds → bit-exact verify | all 4 PASS; ~1585 GB/s aggregate copy bandwidth (HBM2e side-band ECC does not consume user bandwidth); counters zero-growth under stress, no Xid |

**Rigour boundary (important)**: directly proving "the correction path actually corrects" requires **fault-injection tooling**, which we do not have — so the current claim stops at integration-level. Observability in place: `cmp-ecc-snapshot` cron every 5 minutes logging all counters to `/var/log/cmp-ecc-snapshot.log` — first growth in `aggregate correctable` is direct evidence of correction working under real traffic, `uncorrectable > 0` pages immediately; we are also watching for "**bit flips that never trigger ECC**" (silent errors, catchable only by output-side consistency checks). Observation window: several days; this document will be updated.

**Performance cost (TP4 · P2P off · same script, same protocol, vs the 2026-10-04 matrix):**

| Workload | ECC off (10-04 baseline) | ECC on (this run) | Δ |
|---|---:|---:|---:|
| c1 structured | 293.2 | 293.5 | +0.1% |
| c1 coding | 223.1 | 222.9 | −0.1% |
| c1 prose | 143.4 | 143.3 | −0.1% |
| 8-user aggregate (wall) | 462.8 | 461.5 | −0.3% |

All |Δ| ≤ 0.3%, noise level — **ECC kept, no trade-off**. GPU KV pool 1,197,473 tokens (unchanged; inline ECC costs no VRAM). Receipts: `data/decode_c1_*_ecc_on_p2poff.json`, `data/decode_c8_structured_ecc_on_p2poff.json`.

## 4. ForceP2P: from "inert placeholder" to "real switch"

Two discoveries while porting the fork's `p2p-unlock.patch` onto v0.5, recorded for the next person:

1. **The old `ForceP2P=0x11` in the modprobe conf was an inert placeholder** — the fork patch never reads that registry key; P2P was unconditionally forced in the fork module. The "switch" never existed.
2. **v0.5 dropped the `trap31_plm` payload register.** The fork's SEC2 privilege-mask payload table contains `{ 0x0012277cU, 0xffffffffU, "TRAP31_PLM" }`; v0.5 lost it. Without it, the P2P patch's safety guard reads the trap's PRIV_LEVEL_MASK, finds it unwritable (measured 0xffffff8f here) and correctly refuses to force the caps — and the guard is right: the patch author measured 33,423,360 of 33,554,432 bytes (99.6%) corrupted when P2P is forced on such parts.

**Fix and improvement**: restored `trap31_plm` to the payload table + declared it in `constants.yaml`; added a real runtime gate — both the caps-forcing site in `gpu.c` and the trap-arming site in `kern_bus_gm200.c` read `osReadRegistryDword(pGpu, "ForceP2P", ...)` and only engage on bit0 = 1. A toggle script ships on the rig:

```bash
sudo cmp-forcep2p on     # LLM serving (TP4 single-stream): writes ForceP2P=0x11, reboot
sudo cmp-forcep2p off    # PP4 / aggregate serving: P2P unavailable, NCCL falls back to host-shm
sudo cmp-forcep2p status # conf state + dmesg runtime verdict
```

Verification: dmesg 4× `CMPUNLOCK: PCIe P2P caps forced to OK (devid 0x20c2)`; byte-level content check **108/108 PASS** (9 sizes × 12 ordered pairs); with P2P on, single-stream structured 293.2 → **302.2 tok/s (+3.1%)**. The engine keeps `P2P=auto` (content check first, then enable).

## 5. Engine follow-up to 1.7.2 the same day

Moved the Morrowmake recipe from 1.7.0 to **1.7.2**: the BOOT_CHECK timing bug we reported is fixed (connection errors / HTTP 503 during engine init are retried until READY_TIMEOUT; wrong answers and auth errors still fail fast; generations with uncertain delivery are not resent). We removed our `BOOT_CHECK=0` workaround and verified on a real cold boot: ~16 min of checkpoint loading retried throughout until HEALTH OK — no more false kills.

Author-protocol retest (PP4 · P2P off · MAX_LEN=524288 · 8 users × 10 rounds, on this x4 box @ 74 SM · ECC on):

| Workload (8-user aggregate) | 1.6.0/1.7.0 baseline | 1.7.2 | Δ |
|---|---:|---:|---:|
| structured | 645.3–645.8 | **643.1** | −0.3% (noise) |
| coding | (not measured before) | **503.2** | new baseline |
| prose | (not measured before) | **396.7** | new baseline |
| single-user structured | 216.9–219.8 | **218.0** | flat |

**Zero regression on x4; production pinned to 1.7.2.** A useful observation: our 8-user structured aggregate on x4 (643.1) is nearly identical to the author's 1.7.1 number on x16 (639.5) — PP4 aggregate is not link-bound (one activation transfer per stage hop); narrow links hurt TP and single-stream. Receipts: `data/decode_c8_*_v172_pp4512k_p2poff.json`.

## 6. Slow-link build gotchas, complete list (copy to avoid)

1. **Kernel module source download**: `install.sh` fetches the open-gpu-kernel-modules tarball; on this box DNS for `codeload.github.com` failed and the local proxy hit SSL EOF → downloaded on the Mac (27.4 MB) and scp'd into `driver/.build/`; install.sh skips when the file exists;
2. **gcc version**: Ubuntu's 6.8 kernel needs gcc-12 (stock gcc 11.4 rejects `-ftrivial-auto-var-init=zero`); patch `CC_CMD` in `driver/build.sh` (two sites) — still unfixed upstream, hit on both 10-04 and today;
3. **root leftovers**: the first sudo run creates `driver/.build` as root; `chown -R` fixes it;
4. **uv/PyPI on a slow link** (1.7.2 upgrade): uv pulling the torch 2.13 build-dep set crawled at ~20 KB/s → point `UV_DEFAULT_INDEX`/`UV_INDEX_URL` at a mirror; flashinfer-cubin 1.5 GB reused a local wheel from a previous install (the recipe's flashinfer step then sees satisfied pins and skips);
5. **305 MB precompiled vLLM wheel**: setup.py downloads via urllib with no resume, died twice with `ContentTooShortError` → downloaded fully on the Mac, scp'd over, `VLLM_PRECOMPILED_WHEEL_LOCATION` pointing at the local file (natively supported by setup.py);
6. **Regenerating a patch must cover every file it touches** — the sec2 patch spans `g_kernel_gsp_nvoc.h` + `kernel_gsp.c`; regenerating a single file drops NVOC member declarations and the build fails with `no member named stockSignatureSize`;
7. **`install.sh` rewrites `/etc/modprobe.d/cmp-pcie-gen2.conf` on every run** → re-arm `sudo cmp-forcep2p on` after any reinstall, then reboot;
8. **The installer removes DKMS** → after a kernel upgrade you must rerun `install.sh` or the driver will not load (kernel metas `apt-mark hold` here, plus a `cmp-driver-status` self-check);
9. **Starting the service over non-interactive SSH**: PATH lacks `~/.local/bin`, so `start.sh` dies on "uv not found" → prefix `PATH="$HOME/.local/bin:$PATH"`.

## 7. Rollback chain & backups

- Full pre-upgrade backup: `/root/cmpunlocker_backup_20261006_pre_v05/` (bendy2 module set + conf + 4 systemd units + `nvidia-smi -q` snapshot + SM baseline);
- Clean v0.5 without P2P: `/root/cmpunlocker_v05_ecc_nop2p_20261006_modules/`;
- Phase-2 backup still in place: `/root/cmpunlocker_backup_20261004/`;
- Source trees kept: `/home/hym/cmpunlocker-v05` (v0.5, patched with gcc-12 + ForceP2P gate + trap31_plm), `/home/hym/cmpunlocker-gen2` (bendy2), `/root/cmpunlocker` (Morrowmake).
- Any layer: restore files + reboot; `remove.sh` uninstalls completely.

## 8. Credits

- **[amoghmunikote/cmpunlocker](https://github.com/amoghmunikote/cmpunlocker)** — the unlocker itself. v0.5's ECC work (ecc-enable / ecc-fbpa-static / ecc-reporting / booter-verify) is the core gain of this upgrade; the guard-comment philosophy — "a truthful *not supported* beats silent corruption" — kept our P2P port from becoming a silent data-corruption incident.
- **[Morrowmake/glm53-flash-cmp170hx-recipe](https://github.com/Morrowmake/glm53-flash-cmp170hx-recipe)** — the engine recipe and vLLM fork (followed 1.4.1 → 1.6.0 → 1.7.0 → 1.7.2 on this rig); the `p2p-unlock.patch` and trap31 approach originate from their cmpunlocker fork; the BOOT_CHECK bug was fixed within one release of our report, with 8-user comparison data offered for an x4 retest — a rare response time.
- **[bendy2/cmpunlocker](https://github.com/bendy2/cmpunlocker)** (`combined-multiple-cards-gen2` branch) — this rig's production driver for nearly two months (Aug–Oct 2026); its guarded multi-GPU retrain served flawlessly and left us a complete backup path.
- **[PixelML/club-170hx](https://github.com/PixelML/club-170hx)** — independent experiments and the prescient PLX-topology P2P pessimization notes (reproduced on our x4); style reference for this repo.
- **[MiaAI-Lab](https://github.com/MiaAI-Lab)** — the `bench_decode.py` measurement protocol (T=0, thinking off, 400 tokens, post-warmup median) — the basis of comparability for every number here.
- **canada-quant** — GLM-5.3-Flash-W4A16-MTP weights; **incoai** — DFlash2 drafter.
- **Zhipu / Z.ai** — for open-sourcing GLM-5.3-Flash.

This repository is a reproduction, measurement and ops record of the above open-source work on a 4× CMP 170HX (Gen2 x4) machine. Bench receipts in [`data/`](data/), charts in [`assets/charts/`](assets/charts/), day-by-day logs in [`notebooks/`](notebooks/).
