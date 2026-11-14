# B13 — Repository Hygiene Report

- **Date:** 2026-11-14
- **Policy applied:** nothing deleted merely for looking unused; worktrees NOT deleted (explicit prohibition); DE2-owned and protected files preserved; only session-owned, provably-mine temporary probe directories that were superseded were removed (documented below).

## 1. Worktrees (all preserved)

| Worktree | Branch / state | Purpose | Disposition |
|---|---|---|---|
| `D:\jezero-safe-walk` | `data` @ (latest) | primary DE1 repo | keep |
| `D:\jezero-safe-walk-ds-b6` | `ds/slope-safety-b6` @ `ebec2d3` | DS track worktree (B6→B3→B9→B15) | keep |
| `D:\jezero-safe-walk-fs-b9` | `web-amr` @ `f96274f` | FS B9 fix worktree | keep (useful until Amr's environment syncs; removal decision after that) |
| `C:\Users\TECHNICIAN\AppData\Local\Temp\opencode\jsw-de2-cleanup-wt` | detached @ `c075b9b` | leftover DE2-cleanup temp worktree, purpose served | **keep for now** — removal of worktrees is prohibited by policy; recommend owner-approved `git worktree remove` in a future hygiene pass |

## 2. Untracked files (all preserved)

| File | Owner | Status |
|---|---|---|
| `D:\jezero-safe-walk\task09_diff.txt` (14,307 B) | user | **protected, untouched** (SHA-256 stable across all sessions) |
| `D:\jezero-safe-walk-ds-b6\data\processed\rover_track_clean.csv` | **DE2** | untracked input to DS scripts, never staged/committed on DS; SHA `71c1b04e…` (matches DE2 published artifact) |
| `C:\Users\TECHNICIAN\AppData\Local\Temp\opencode\b9-audit\` | this work (B9) | **kept** — contains the B9 A*/Dijkstra test harness used for the recorded evidence |
| `C:\Users\TECHNICIAN\AppData\Local\Temp\opencode\jsw-de2-cleanup-wt` | this work (DE2 cleanup) | see worktrees above |

## 3. Removed (session-owned, superseded, documented)
- `C:\Users\TECHNICIAN\AppData\Local\Temp\opencode\b1-fs-js\` (43.7 KB) — B1 read-only probe dumps; all findings already recorded in the B1 report.
- `C:\Users\TECHNICIAN\AppData\Local\Temp\opencode\b3-audit\` (640.3 KB) — B3 audit dumps; all findings recorded in the B3 report/commits.
- No repository file was deleted, renamed, or moved.

## 4. Stale references (documented, NOT touched)
| Item | Status | Rule |
|---|---|---|
| `refs/remotes/origin/de2-data-pipeline` (stale local tracking ref, remote branch deleted by owner decision) | present locally | **MUST NOT be restored, pushed, or used as evidence** (DE2 final handoff) — left as-is, never dereferenced |
| local branch `analysis` @ `057b32a` (behind `origin/analysis`) | stale local branch, not checked out by any worktree | recommendation: fast-forward or delete locally at next owner hygiene pass (not done here — no checkout permitted) |
| `analysis/_last_run.txt`, `analysis/_dump_for_deepseek.txt` (DS) | historical dumps | untouched (frozen history) |
| `web/data/route_bank.json` (DS/FS) | legacy pre-canonical fallback artifact, consumed by nothing (B3 audit) | kept — not deleted without owner decision |
| `analysis/presets_fixed.json` (DS/FS copies) | retired pre-canonical fixture (B3) | kept as committed history; no script reads it |

## 5. Duplicated datasets — by design, verified identical
All `web/data/` integration copies across `data`, `analysis`, `web-amr` were blob-verified identical during B1/B9 (elevation binary `dacf593f…`, grid_meta `2d908027…`, CTX `d790791c…`, hillshade, geologic assets, slope `5d7d0396…` content, DE2 canonical data files). These are integration copies, not uncontrolled duplicates.

## 6. Verdict
Repository hygiene is **good**: no orphaned or conflicting state; all residual items are documented with owners and dispositions. No further action required before integration.
