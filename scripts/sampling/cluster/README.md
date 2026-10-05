# SH-250 pool tournament — running it on a cluster

The 250-sample pool (`LOGS-SH250/<date>/`, produced by `scripts/sampling/run_pool.py`) is turned
into a scoreboard in four rounds. Names used everywhere (dashboard, README, this file):

| round | what | seeds | telemetry |
|---|---|---|---|
| **Qualification Round** | every generated sample is built and plays 3 × 20 s rounds vs the stationary block; entry rule for the pool: no round lost, or more rounds won than lost | 3 | `match_data.json.gz` per sample |
| **Top Bot per Run Round** | a model's 250 samples are 5 runs of 50 consecutive slots; inside each run every eligible bot plays every other bot, 300 s; Bradley-Terry picks the run winner | 5 | none (`ARENA_SKIP_MATCH_DATA=1`) |
| **Top-5 Round** | the five run winners of a model play each other | 11 | `match_data.json.gz` |
| **Champions Round** | every model's Top-5 Round winner plays every other model's | 11 | `match_data.json.gz` |

All rules come from `configs/tournaments/sh.yaml` → `base.yaml` (300 s, inactivity 10 s / 0.5 m, score `any`,
contact fidelity high). Nothing here changes physics; the scripts only schedule the existing runner.

## Pieces

| script | role |
|---|---|
| `scripts/sampling/pack_pool.py` | copies the round-robin-essential files of every sample (gen.json, robot.xml, controller.py, bot_artifact.json, journal, usage, qualification result) into a pack with an md5 `MANIFEST.json`; `--verify` |
| `scripts/sampling/pool_ledger.py` | who enters: `scan_pool(root, model, layout="run"|"pack")` → eligible records + per-slot reasons |
| `scripts/sampling/pool_rr.py` | one model's round robin: `--runs 5` (five runs of 50), `--run-index k` (one run, for array tasks), `--finalize-runs` (run winners → `top_5_bots.json`); needs `ARENA_SKIP_MATCH_DATA=1` |
| `scripts/sampling/verify_pool_rr.py` | completeness + protocol + standings recomputation gate; `--group k` for one run; `--stage b1 <model>` / `--stage b2` |
| `scripts/sampling/pool_finals.py` | Top-5 Round and Champions Round with telemetry, BT Elos, `stage_b/summary.json` |
| `scripts/sampling/release_readme.py`, `publish_pool.sh` | release folder (README, MISSING, manifest) and the `gcloud storage rsync` publication with md5 reconcile |
| `scripts/sampling/merge_pack_manifests.py`, `publish_pool_laptop.sh` | the laptop-side publication of a run whose pieces came from several platforms: one merged pack manifest (models tagged with the platform that qualified them, files re-hashed from the union pack), the grouped layout copied with VERIFIED gates, missing verifier reports produced locally, README/MISSING/standings rendered, rsync + md5 reconcile |
| `scripts/sampling/website/{site_ids,build_bots_dir,build_capsules,build_qual,build_thumb_src}.py` | the website-side derivation of a published run (see "Website" below) |
| `scripts/sampling/rr_dashboard.py` | the status page (`SH250_RR.html` + `.md`) from per-host mirrors and/or the HPC mirror |
| `cluster/hpc_qualify.sh` | SLURM node job: Qualification Round for a list of models from a generation-only root |
| `cluster/hpc_model_job.sh` | SLURM job, one per model: its five runs back to back, verified, run winners written |
| `cluster/hpc_stage_a.sh` | SLURM array alternative: one task per (model, run) |
| `cluster/hpc_after_qual.sh` | dependency job: pack the qualified models and submit their model jobs |
| `cluster/hpc_mirror.sh` | laptop-side loop: SLURM state + results → local mirror → dashboard |
| `cluster/run_pool_rr.sh`, `rr_status.sh` | the no-scheduler variant for a single big host (tmux) |

## The HPC cluster, step by step

**Storage (2026-09-22 lesson):** the home directory has a hard quota and it filled up mid-run (78 Field Round
shards died with `Disk quota exceeded`). Keep only the code and the conda env in `$HOME/sh250` (harness trees); put every
pack, run root, `rr-<run-id>` output tree and the SLURM logs under the group storage
`<hpc-data>/sh250`. The job scripts default `PACK`/`OUT` to that root via
`DATA=${SH250_DATA:-<hpc-data>/sh250}`; `hpc_mirror.sh` reads `REMOTE_DATA` the same way.
Pass `-o/-e` log paths under `$DATA/logs`. Shard logs are verbose (a Field Round shard writes ~250 MB): 80 shards = 22 GB.


Open a shared session once and leave it open; every command below rides through it:

```bash
mkdir -p ~/.ssh/cm_socket && ssh -M -S ~/.ssh/cm_socket/hpc -o ControlPersist=yes <user>@hpc-login.example.org
ES="ssh -o BatchMode=yes -S ~/.ssh/cm_socket/hpc <user>@hpc-login.example.org"
```

1. **Ship the code** (the harness repo is private; the cluster gets a `git archive` of the exact commit):
   ```bash
   git archive --format=tar HEAD | $ES 'mkdir -p ~/sh250/harness ~/sh250/logs && tar x -C ~/sh250/harness'
   $ES "echo $(git rev-parse HEAD) > ~/sh250/harness/SHIPPED_SHA"
   ```
2. **Environment** (Python 3.10 to match the laptop env; MuJoCo has no GL on the nodes → `MUJOCO_GL=disable`):
   ```bash
   $ES 'module load miniforge; mamba create -y -n sh250 python=3.10; mamba activate sh250;
        pip install -r ~/sh250/harness/pip_requirements.txt pytest;
        MUJOCO_GL=disable python -c "import mujoco, dspy; print(mujoco.__version__)"'
   ```
3. **Ship the data.** Models already qualified on the laptop go as a pack; models to qualify on the cluster go as a
   generation-only root (gen.json + raw responses + the run's `manifest.json`):
   ```bash
   python scripts/sampling/pack_pool.py --root LOGS-SH250/<date> --out LOGS-SH250/<date>-pack-a --models <finished models>
   (cd LOGS-SH250 && COPYFILE_DISABLE=1 tar czf - <date>-pack-a) | $ES 'cd ~/sh250 && tar xzf - && find <date>-pack-a -name "._*" -delete'
   $ES 'module load miniforge; mamba activate sh250; cd ~/sh250/harness && python scripts/sampling/pack_pool.py --verify ../<date>-pack-a'
   ```
   Never mix: a model's Qualification Round runs entirely on one platform (laptop or cluster).
4. **Submit** (from `~/sh250`, with absolute log paths — a relative `logs/` that does not exist kills a job in 2 s):
   ```bash
   $ES 'cd ~/sh250; S=harness/scripts/sampling/cluster; D=<hpc-data>/sh250; L=$D/logs; P=group_low
        # Qualification Round for models shipped as a generation root (3 models per node job)
        jid=$(sbatch --parsable -p $P -o $L/qual_%j.out -e $L/qual_%j.err --export=ALL,ROOT=$D/<date>-gen,MODELS="m1 m2 m3" $S/hpc_qualify.sh); echo "$jid m1 m2 m3" >> plan-q.txt
        # Top Bot per Run Round: one 96-core job per already-packed model
        jid=$(sbatch --parsable -p $P -o $L/model_%j.out -e $L/model_%j.err --export=ALL,MODEL=gpt-5.5,RUN_ID=<run-id>,SEEDS=5,RUNS=5,PACK=$D/<date>-pack-a,OUT=$D/rr-<run-id> $S/hpc_model_job.sh); echo "$jid gpt-5.5" >> plan-m.txt
        # after the qualification jobs: pack those models and submit their model jobs
        sbatch -p $P -o $L/pack_%j.out -e $L/pack_%j.err --dependency=afterok:<qual ids> --export=ALL,RUN_ID=<run-id>,PARTITION=$P,MODELS="m1 m2 m3" $S/hpc_after_qual.sh'
   ```
   `plan-q.txt` / `plan-m.txt` map job ids to models for the dashboard. `RUN_ID` = `sh250-pool-` + first 8 hex of
   sha256 of the run root's `manifest.json`.
5. **Watch** — on the laptop:
   ```bash
   bash scripts/sampling/cluster/hpc_mirror.sh <run-id> LOGS-SH250/rr-<run-id>/hpc 300   # loop
   # writes SH250_RR.html / SH250_RR.md every 5 min; open the html and press Refresh
   ```
6. **Finals** once every model dir has `VERIFIED`:
   ```bash
   $ES 'cd ~/sh250/harness; module load miniforge; mamba activate sh250; MUJOCO_GL=disable python scripts/sampling/pool_finals.py --rr ../rr-<run-id> --pack ../<pack> --out ../rr-<run-id> --n-rollouts 11 --n-parallel-matches 96 --run-id <run-id>'
   ```
   then `verify_pool_rr.py --stage b1 <model>` for every model and `--stage b2`.
7. **Pull everything back to the laptop** (one full copy always lives there) and publish with `publish_pool.sh`.

## Measured (2026-09-19)

- Per game: ~250 CPU-s; the simulation runs at ~4 wall-s per simulated second, ring-outs end
  games in seconds, no-contact games run all 300 s. Runs-of-50 at 5 seeds ≈ 12,500 CPU-h for the whole pool.
- Qualification: ~90 CPU-s per sample.
- Same input on macOS arm64 vs x86-64 Linux: same winners in most games, different step counts, occasional
  flipped draw — hence "never mix" above. Two x86 hosts (host-e vs host-a) agree exactly.

## Website (artifactarena.ai)

The site does not read the release tree directly; `scripts/sampling/website/` derives what it needs, and the app's
`scripts/build-sh250-site-export.mjs` / `verify-sh250-site-export.mjs` (in the arena app repo) turn that into the
hydrated site export. Ids: tournament `<model>__t<N>_c000` ↔ site `<model>__sampling__t<NNN>_c000` (`site_ids.py`).

| script | output |
|---|---|
| `build_bots_dir.py --rr <rr> --pack <pack> --manifest <pack-MANIFEST.json> --out site/bots` | `bots/<aid>/{bot.json,robot.xml,controller.py}` for every sample (name, design texts, usage, build verdict, qualification W-D-L + reason, rank/Elo/W-L-D in every round, role), `bots/index.json`, `bots/by-model/<model>.json` |
| `build_capsules.py --rr <rr> --assets mjarena/assets --out site` | one `browser-match-trace-v1` capsule per Top-5 Round / Champions Round game (`replays/<sha256(task_id)>.json.gz`, task id `final-<run>:pair:<i>:<k>`), `pairings.json`, `capsules-<run>.txt` |
| `build_qual.py --gen <gen root> --release <release> --bots site/bots --assets mjarena/assets --out site/qual` | `qual/<aid>/result.json` for every sample (official `match_result.json` verbatim; `telemetry: official|pending|none`) + `seed_<k>.json.gz` capsules where the official Qualification Round telemetry is on this machine (never a re-simulation from another platform: arm64 vs x86 physics diverge) |
| `build_thumb_src.py --rr <rr> --bots site/bots/index.json --out site/thumb-src` | one-frame `matches/<siteRed>_vs_<siteBlue>/{composed.xml,match_data.json}` per roster bot for the app's thumbnail bake |

MuJoCo `sdf` geoms (mesh-defined collision shapes, used by 28 of the 105 SH-250 roster bots) collide normally with the
deck and with opponents; only the browser renderer needed teaching to draw them (app commit 7f15869d).

