#!/usr/bin/env python3
"""Per-model full round robin over the SH-250 pool (Stage A of the pool tournament).

    ARENA_SKIP_MATCH_DATA=1 python scripts/sampling/pool_rr.py --root <pack or run root> --out <out> \
        --model gpt-5.5 --n-rollouts 5 --n-parallel-matches 90 [--match-time 300] \
        [--config configs/tournaments/sh.yaml] [--layout run|pack] [--all-with-xml] [--run-id <id>]

Who plays comes from `pool_ledger.scan_pool` (decision D5: validated + qualified + non-forfeit).
The games are played by `mjarena.two_stage.intra_model.run_intra_rr_for_model` under the match
rules of the tournament config (arena, 300 s, inactivity rule, score function, contact fidelity)
with only `n_rollouts` and the video flags overridden, and with `ARENA_SKIP_MATCH_DATA=1` so no
`match_data.json` is written — without both, 2.4 M games write terabytes. The run refuses to start
otherwise.

Written under `<out>/<model>/`:
  pool_ledger.json   provenance (git sha, config md5, rules, inactivity) + one row per slot, with the
                     slot -> artifact_id mapping; written BEFORE the first game.
  matches/<a>_vs_<b>/match_result.json   one per unordered eligible pair (from run_round_robin).
  elo.json           Bradley-Terry standings re-derived from every match_result.json (method "bt").
  top_5_bots.json    ranked head of those standings, `top_{k}_bots.json` shape (write_top_k_bots).
  top_1.json         the argmax, with every rating tie declared in `ties_at_top`. Not written when
                     no bot is eligible: downstream (pool_finals, the verifier's Stage B2) reads
                     "no top_1.json" as "this model did not enter".

Ranking is deterministic: rating descending, then lowest tournament_idx. Exact ties are declared,
never hidden (`elo.json["ties_at_top"]`, `top_1.json["ties_at_top"]`, `top_5_bots.json["source"]
["ties_at_cut"]`).

Resumability: `run_round_robin` skips pairings whose match_result.json exists — but only on its
parallel branch (`n_parallel_matches > 1`). This script additionally recognises a complete round
robin on disk and re-derives the standings without touching the matches, whatever the worker count.
With 0 or 1 eligible bots there is no round robin; elo.json and top_5_bots.json are still written
(one 1000.0 row, or empty), top_1.json only for the single bot.
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT, ROOT / "scripts/sampling"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import pool_ledger  # noqa: E402
import mjarena.core.unified_builder  # noqa: E402,F401  (import order: breaks the dspy_core/design_shop cycle)
if os.environ.get("ARENA_OBS_ACCEL") == "1":                      # opt-in exact-observation accelerator (the upstream Cython kernels)
    from mjarena.envs.observation_accel import install as _install_obs_accel  # noqa: E402
    _install_obs_accel()
from mjarena.elo.core import compute_standings  # noqa: E402
from mjarena.two_stage.artifact_loader import TopKBotRecord, make_artifact_id, write_top_k_bots  # noqa: E402
from mjarena.two_stage.intra_model import _read_match_outcomes, run_intra_rr_for_model  # noqa: E402
from mjarena.two_stage.intra_model import _build_artifacts_for_model  # noqa: E402
from mjarena.tournament.tournament import run_round_robin  # noqa: E402
from mjarena.two_stage.match_config import TwoStageMatchConfig, load_tournament_config  # noqa: E402

logger = logging.getLogger("pool_rr")

DEFAULT_CONFIG = ROOT / "configs/tournaments/sh.yaml"
K_MAX = 5
RATING_TOL = 1e-9
TIE_BREAK = "lowest tournament_idx"
SKIP_ENV = "ARENA_SKIP_MATCH_DATA"

Standings = Dict[str, Dict[str, Any]]


# ── guards + provenance ───────────────────────────────────────────────────────

def require_skip_match_data() -> None:
    """Refuse to run unless telemetry is off. Checked before any work."""
    if os.environ.get(SKIP_ENV) != "1":
        sys.exit(
            f"{SKIP_ENV}=1 is required: without it every game writes a match_data.json "
            f"(2.4 M games = terabytes). Export {SKIP_ENV}=1 and rerun."
        )


def build_match_config(config: Path, match_time: Optional[float]) -> TwoStageMatchConfig:
    """The tournament config with only the video flags (and optionally match_time) overridden."""
    cfg = load_tournament_config(Path(config))
    overrides: Dict[str, Any] = {"save_video": False, "save_all_videos": False}
    if match_time is not None:
        overrides["match_time"] = float(match_time)
    return dataclasses.replace(cfg, **overrides)


def git_sha(repo: Path) -> str:
    """HEAD of the checkout the games are played from (the harness clone on the cluster)."""
    proc = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True)
    if proc.returncode != 0:
        shipped = repo / "SHIPPED_SHA"      # a `git archive` tree on the cluster carries its commit here
        if shipped.exists() and shipped.read_text().strip():
            return shipped.read_text().strip()
        raise RuntimeError(f"git rev-parse HEAD failed in {repo}: {proc.stderr.strip()} — run from a git checkout "
                           "or ship the tree with a SHIPPED_SHA file")
    return proc.stdout.strip()


def _md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def config_chain(config: Path) -> List[Dict[str, str]]:
    """The config file and every `base:` it inherits from, each with its md5."""
    import yaml
    chain: List[Dict[str, str]] = []
    path = Path(config).resolve()
    seen = set()
    while path not in seen:
        seen.add(path)
        chain.append({"path": pool_ledger._rel(path, ROOT), "md5": _md5(path)})
        raw = yaml.safe_load(path.read_text()) or {}
        if "base" not in raw:
            break
        path = (path.parent / raw["base"]).resolve()
    return chain


def _rows_with_artifact_ids(model: str, ledger_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Every slot's artifact id (`<model>__tNNN_c000`) — the release README maps slots to ids."""
    return [{**row, "artifact_id": make_artifact_id(model, int(row["idx"]), 0)} for row in ledger_rows]


def pool_ledger_payload(
    *, model: str, run_id: Optional[str], n_samples: int, eligible: List[Dict[str, Any]],
    ledger_rows: List[Dict[str, Any]], n_rollouts: int, cfg: TwoStageMatchConfig, config: Path,
    root: Path, layout: str, require_qualified: bool, repo: Path,
) -> Dict[str, Any]:
    return {
        "model": model,
        "run_id": run_id,
        "n_samples": n_samples,
        "eligible": len(eligible),
        "n_rollouts": n_rollouts,
        "match_time": float(cfg.match_time),
        "inactivity": {"timeout_s": cfg.inactivity_timeout, "min_displacement_m": cfg.inactivity_min_displacement},
        "git_sha": git_sha(repo),
        "config": pool_ledger._rel(Path(config).resolve(), ROOT),
        "config_md5": _md5(Path(config)),
        "config_chain": config_chain(config),
        "rules": {
            "score_function": cfg.score_function,
            "physics_mode": cfg.physics_mode,
            "contact_fidelity": cfg.contact_fidelity,
            "arena_xml": str(cfg.arena_xml),
            "constraints": str(cfg.constraints_path),
        },
        "source": {"root": str(root), "layout": layout, "require_qualified": require_qualified},
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "ledger": _rows_with_artifact_ids(model, ledger_rows),
    }


# ── standings ─────────────────────────────────────────────────────────────────

def _tournament_idx(artifact_id: str) -> int:
    return int(artifact_id.rsplit("__t", 1)[1].split("_c", 1)[0])


def ranked(standings: Standings) -> List[Tuple[str, Dict[str, Any]]]:
    """Rating descending, exact ties broken by lowest tournament_idx (deterministic)."""
    return sorted(standings.items(), key=lambda kv: (-float(kv[1]["elo"]), _tournament_idx(kv[0])))


def tied_with(standings: Standings, rating: float) -> List[str]:
    return sorted(a for a, s in standings.items() if abs(float(s["elo"]) - rating) <= RATING_TOL)


def standings_from_records(matches_dir: Path, ids: List[str]) -> Standings:
    """BT standings over every match_result.json; bots that played nothing get the 1000.0 row."""
    outcomes = _read_match_outcomes(matches_dir) if matches_dir.is_dir() else []
    standings = compute_standings(outcomes)
    for aid in ids:
        if aid not in standings:
            standings[aid] = {"wins": 0, "losses": 0, "draws": 0, "elo": 1000.0, "games": 0}
    return standings


def write_standings(
    model_dir: Path, *, model: str, standings: Standings, eligible: List[Dict[str, Any]],
    n_rollouts: int, k_max: int = K_MAX,
) -> None:
    """elo.json + top_{k}_bots.json + top_1.json from one ranking, ties declared."""
    order = ranked(standings)
    ties_at_top = tied_with(standings, float(order[0][1]["elo"])) if order else []

    (model_dir / "elo.json").write_text(json.dumps({
        "model": model,
        "method": "bt",
        "n_rollouts": n_rollouts,
        "tie_break": TIE_BREAK,
        "ties_at_top": ties_at_top,
        "standings": standings,
    }, indent=2))

    by_id = {make_artifact_id(model, int(r["tournament_idx"]), int(r["commit_idx"])): r for r in eligible}
    unknown = [aid for aid, _ in order if aid not in by_id]
    if unknown:
        raise RuntimeError(f"{model}: standings name bots that are not eligible: {unknown[:5]} — stale matches/?")

    head = order[:k_max]
    rows: List[Dict[str, Any]] = []
    for rank, (aid, st) in enumerate(head, start=1):
        rec = by_id[aid]
        rows.append(TopKBotRecord(
            rank=rank,
            artifact_id=aid,
            model=model,
            kind="refinement_commit",
            tournament_idx=int(rec["tournament_idx"]),
            commit_idx=int(rec["commit_idx"]),
            robot_xml=f"{rec['commit_dir']}/robot.xml",
            controller_py=f"{rec['commit_dir']}/controller.py",
            qualification_score=float(rec["qualification_score"]),
            intra_model_elo=float(st["elo"]),
            intra_model_wld={"wins": int(st["wins"]), "losses": int(st["losses"]), "draws": int(st["draws"])},
            cross_model_elo={"k1": None, "k3": None, "k5": None},
            cross_model_wld={"k1": None, "k3": None, "k5": None},
        ).to_dict())
    ties_at_cut: List[str] = []
    if len(order) > k_max:
        floor = float(head[-1][1]["elo"])
        tied = tied_with(standings, floor)
        if any(aid not in {a for a, _ in head} for aid in tied):
            ties_at_cut = tied
    write_top_k_bots(
        model_dir / f"top_{k_max}_bots.json",
        k=k_max,
        scope="intra_model",
        model=model,
        source={
            "logs_root": None,
            "pool_ledger": "pool_ledger.json",
            "intra_model_elo": "elo.json",
            "top_n_qualified": len(eligible),
            "n_rollouts": n_rollouts,
            "elo_method": "bt",
            "tie_break": TIE_BREAK,
            "ties_at_cut": ties_at_cut,
        },
        bots=rows,
    )

    top1_path = model_dir / "top_1.json"
    if not order:
        # No entrant: no top_1.json at all (its absence is the "did not enter" signal downstream).
        top1_path.unlink(missing_ok=True)
        return
    aid, st = order[0]
    top1 = {
        "model": model,
        "artifact_id": aid,
        "tournament_idx": int(by_id[aid]["tournament_idx"]),
        "elo": float(st["elo"]),
        "wins": int(st["wins"]),
        "losses": int(st["losses"]),
        "draws": int(st["draws"]),
        "games": int(st["games"]),
        "ties_at_top": ties_at_top,
        "tie_break": TIE_BREAK,
    }
    top1_path.write_text(json.dumps(top1, indent=2))


# ── the run ───────────────────────────────────────────────────────────────────


def play_full_round_robin(model: str, eligible: List[Dict[str, Any]], model_dir: Path, out: Path,
                          cfg: TwoStageMatchConfig, *, n_rollouts: int, n_parallel_matches: int,
                          n_parallel_seeds: int = 1) -> None:
    """run_round_robin over every pairing of `eligible`, matches under `<model_dir>/matches/` — the same
    call `run_intra_rr_for_model` makes, for output dirs that are not `<out>/<model>`."""
    bots = _build_artifacts_for_model(eligible, model, ROOT, clean_cache_root=out / "_clean_artifacts",
                                      constraints_path=cfg.constraints_path, physics_mode=cfg.physics_mode)
    arena = cfg.arena_xml if cfg.arena_xml.is_absolute() else ROOT / cfg.arena_xml
    run_round_robin(
        bots=bots, arena_xml=arena, out_dir=model_dir, n_rollouts=n_rollouts,
        record_video=cfg.save_video, save_all_videos=cfg.save_all_videos, highres=cfg.highres,
        verbose=True, trace_progress=False, physics_mode=cfg.physics_mode, score_function=cfg.score_function,
        match_time=cfg.match_time, contact_fidelity=cfg.contact_fidelity,
        inactivity_timeout_seconds=cfg.inactivity_timeout, inactivity_min_displacement=cfg.inactivity_min_displacement,
        size_limits=cfg.size_limits, n_parallel_matches=n_parallel_matches, n_parallel_seeds=n_parallel_seeds,
        camera_mode=cfg.camera, rendering_flags=cfg.rendering_flags or None,
        season_id=f"sh250_runs/{model}/{model_dir.name}", tournament_id="intra_run",
    )


def pairings_on_disk(matches_dir: Path, ids: List[str]) -> Tuple[int, int]:
    """(existing, total) unordered pairings, in run_round_robin's `<a>_vs_<b>` order."""
    pairs = list(combinations(ids, 2))
    existing = sum(1 for a, b in pairs if (matches_dir / f"{a}_vs_{b}" / "match_result.json").is_file())
    return existing, len(pairs)


def run(
    root: Path, out: Path, model: str, *, n_rollouts: int = 5, n_parallel_matches: int = 8,
    match_time: Optional[float] = None, config: Path = DEFAULT_CONFIG, require_qualified: bool = True,
    layout: str = "run", run_id: Optional[str] = None, n_samples: int = 250,
    slot_range: Optional[Tuple[int, int]] = None, subdir: Optional[str] = None, n_parallel_seeds: int = 1,
) -> Path:
    """Play one model's full round robin and write its standings. Returns the model dir.

    `slot_range=(lo, hi)` restricts the participants to sample slots lo <= idx < hi (one "run" of the
    model's 250 samples, see `run_in_groups`); `subdir` puts the output under `<out>/<model>/<subdir>/`."""
    require_skip_match_data()
    root, out, config = Path(root), Path(out), Path(config)

    cfg = build_match_config(config, match_time)
    eligible, ledger_rows = pool_ledger.scan_pool(
        root, model, n_samples=n_samples, require_qualified=require_qualified, repo=ROOT, layout=layout
    )
    if slot_range is not None:
        lo, hi = slot_range
        eligible = [r for r in eligible if lo <= int(r["tournament_idx"]) < hi]
        ledger_rows = [r for r in ledger_rows if lo <= int(r["idx"]) < hi]
    ids = [make_artifact_id(model, int(r["tournament_idx"]), int(r["commit_idx"])) for r in eligible]

    model_dir = out / model / subdir if subdir else out / model
    model_dir.mkdir(parents=True, exist_ok=True)
    if run_id is None:
        logger.warning("%s: no --run-id given; pool_ledger.json records run_id null", model)
    payload = pool_ledger_payload(
        model=model, run_id=run_id, n_samples=n_samples, eligible=eligible, ledger_rows=ledger_rows,
        n_rollouts=n_rollouts, cfg=cfg, config=config, root=root, layout=layout,
        require_qualified=require_qualified, repo=ROOT,
    )
    if slot_range is not None:
        payload["slot_range"] = [int(slot_range[0]), int(slot_range[1])]
        payload["group"] = subdir
    (model_dir / "pool_ledger.json").write_text(json.dumps(payload, indent=2))
    logger.info("%s: %d/%d eligible, %d rollouts, match_time %.0f s, videos off, telemetry off",
                model, len(eligible), n_samples, n_rollouts, cfg.match_time)

    matches_dir = model_dir / "matches"
    if len(eligible) < 2:
        logger.warning("%s: %d eligible bots: no round robin", model, len(eligible))
    else:
        existing, total = pairings_on_disk(matches_dir, ids)
        if existing == total:
            logger.info("%s: all %d pairings already on disk — nothing to play, re-deriving standings", model, total)
        else:
            if existing and n_parallel_matches <= 1:
                logger.warning("%s: %d/%d pairings exist but n_parallel_matches=1 replays them — "
                               "run_round_robin resumes only with n_parallel_matches >= 2", model, existing, total)
            logger.info("%s: playing %d pairings (%d already on disk)", model, total - existing, existing)
            if subdir:
                play_full_round_robin(model, eligible, model_dir, out, cfg, n_rollouts=n_rollouts,
                                      n_parallel_matches=n_parallel_matches, n_parallel_seeds=n_parallel_seeds)
            else:
                run_intra_rr_for_model(
                    model, eligible, out, ROOT, cfg,
                    k_max=K_MAX, n_rollouts=n_rollouts, n_parallel_matches=n_parallel_matches,
                    n_parallel_seeds=n_parallel_seeds, clean_cache_root=out / "_clean_artifacts",
                )

    standings = standings_from_records(matches_dir, ids)
    write_standings(model_dir, model=model, standings=standings, eligible=eligible, n_rollouts=n_rollouts)
    top1_path = model_dir / "top_1.json"
    if top1_path.exists():
        top1 = json.loads(top1_path.read_text())
        logger.info("%s: top-1 %s (elo %s, ties %s)", model, top1["artifact_id"], top1["elo"], top1["ties_at_top"])
    else:
        logger.warning("%s: no eligible bot — no top_1.json (the model does not enter Stage B)", model)
    return model_dir



def run_in_groups(
    root: Path, out: Path, model: str, *, runs: int, n_samples: int = 250, **kw: Any,
) -> Path:
    """Treat the model's `n_samples` samples as `runs` independent runs of n_samples/runs consecutive
    slots (c000–c049, c050–c099, …); play the full round robin INSIDE each run under
    `<out>/<model>/g<k>/`, then write the model's `top_5_bots.json` as the five run winners (rank =
    run order of rating) and `runs.json`. No model-level top_1.json: the stored Stage B1 round robin
    among the winners decides the model's top-1 (release rule: five bots = the best of five runs)."""
    if n_samples % runs:
        raise ValueError(f"n_samples {n_samples} not divisible by runs {runs}")
    size = n_samples // runs
    for k in range(runs):
        lo, hi = k * size, (k + 1) * size
        run(root, out, model, n_samples=n_samples, slot_range=(lo, hi), subdir=f"g{k}", **kw)
    return finalize_runs(root, out, model, runs=runs, n_samples=n_samples, **kw)


def finalize_runs(root: Path, out: Path, model: str, *, runs: int, n_samples: int = 250, **kw: Any) -> Path:
    """runs.json + the model's top_5_bots.json (the run winners) from finished `<out>/<model>/g<k>/` dirs."""
    size = n_samples // runs
    model_dir = Path(out) / model
    model_dir.mkdir(parents=True, exist_ok=True)
    winners: List[Dict[str, Any]] = []
    summary: List[Dict[str, Any]] = []
    for k in range(runs):
        lo, hi = k * size, (k + 1) * size
        gdir = model_dir / f"g{k}"
        if not (gdir / "pool_ledger.json").exists():
            raise RuntimeError(f"{model}: run g{k} has not been played ({gdir}/pool_ledger.json missing)")
        ledger = json.loads((gdir / "pool_ledger.json").read_text())
        top1 = json.loads((gdir / "top_1.json").read_text()) if (gdir / "top_1.json").exists() else None
        summary.append({"group": f"g{k}", "slot_range": [lo, hi], "eligible": ledger["eligible"],
                        "winner": top1["artifact_id"] if top1 else None,
                        "winner_elo": top1["elo"] if top1 else None,
                        "ties_at_top": top1["ties_at_top"] if top1 else []})
        if top1:
            winners.append({"group": f"g{k}", **top1})
    (model_dir / "runs.json").write_text(json.dumps({
        "model": model, "runs": runs, "run_size": size, "n_rollouts": kw.get("n_rollouts"),
        "rule": "each run's full round robin winner (BT) is the run's bot; the five run winners are the "
                "model's top-5 pool; Stage B1 ranks them and names the top-1",
        "groups": summary}, indent=2))
    winners.sort(key=lambda w: (-float(w["elo"]), int(w["tournament_idx"])))
    rows = []
    for i, w in enumerate(winners):
        cdir = _commit_dir_of(root, model, int(w["tournament_idx"]), kw.get("layout", "run"))
        rows.append(TopKBotRecord(
            rank=i + 1, artifact_id=w["artifact_id"], model=model, kind="refinement_commit",
            tournament_idx=int(w["tournament_idx"]), commit_idx=0,
            robot_xml=str(cdir / "robot.xml"), controller_py=str(cdir / "controller.py"),
            qualification_score=None, intra_model_elo=float(w["elo"]),
            intra_model_wld={"wins": int(w["wins"]), "losses": int(w["losses"]), "draws": int(w["draws"])},
            cross_model_elo={"k1": None, "k3": None, "k5": None},
            cross_model_wld={"k1": None, "k3": None, "k5": None}))
    write_top_k_bots(model_dir / f"top_{K_MAX}_bots.json", k=K_MAX, scope="intra_model", model=model,
                     source={"logs_root": None, "rule": "one winner per run (full round robin inside each run, BT)",
                             "runs": runs, "run_size": size, "n_rollouts": kw.get("n_rollouts"),
                             "groups": [g["group"] for g in summary if g["winner"]], "tie_break": TIE_BREAK},
                     bots=[r.to_dict() for r in rows])
    stale = model_dir / "top_1.json"
    if stale.exists():
        stale.unlink()
    logger.info("%s: %d run winners -> top_%d_bots.json (%s)", model, len(rows), K_MAX,
                ", ".join(f"{g['group']}:{g['winner']}" for g in summary))
    return model_dir


def _commit_dir_of(root: Path, model: str, idx: int, layout: str) -> Path:
    return pool_ledger.slot_paths(Path(root), model, idx, layout)["commit"]


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, required=True, help="pack dir or sampling run root")
    ap.add_argument("--out", type=Path, required=True, help="output root; writes <out>/<model>/")
    ap.add_argument("--model", required=True)
    ap.add_argument("--n-rollouts", type=int, default=5)
    ap.add_argument("--n-parallel-matches", type=int, default=8)
    ap.add_argument("--n-parallel-seeds", type=int, default=1,
                    help="games of one pairing played concurrently (cuts the tail: a pairing of long games no longer "
                         "takes n_rollouts x one game); total processes = matches x seeds")
    ap.add_argument("--match-time", type=float, default=None, help="seconds; default from the config (300)")
    ap.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    ap.add_argument("--all-with-xml", action="store_true", help="sensitivity check only: lift the D5 gate")
    ap.add_argument("--layout", choices=pool_ledger.LAYOUTS, default="run")
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--n-samples", type=int, default=250)
    ap.add_argument("--runs", type=int, default=None,
                    help="treat the samples as this many independent runs of consecutive slots; full RR inside each run")
    ap.add_argument("--run-index", type=int, default=None,
                    help="with --runs: play only run k (SLURM array tasks); the model-level top_5/runs.json are written by --finalize-runs")
    ap.add_argument("--finalize-runs", action="store_true",
                    help="with --runs: skip playing; write runs.json + top_5_bots.json from the finished g<k>/ dirs")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    kw = dict(n_rollouts=args.n_rollouts, n_parallel_matches=args.n_parallel_matches, match_time=args.match_time,
              n_parallel_seeds=args.n_parallel_seeds,
              config=args.config, require_qualified=not args.all_with_xml, layout=args.layout, run_id=args.run_id)
    if args.runs and args.run_index is not None:
        size = args.n_samples // args.runs
        run(args.root, args.out, args.model, n_samples=args.n_samples,
            slot_range=(args.run_index * size, (args.run_index + 1) * size), subdir=f"g{args.run_index}", **kw)
    elif args.runs and args.finalize_runs:
        finalize_runs(args.root, args.out, args.model, runs=args.runs, n_samples=args.n_samples, **kw)
    elif args.runs:
        run_in_groups(args.root, args.out, args.model, runs=args.runs, n_samples=args.n_samples, **kw)
    else:
        run(args.root, args.out, args.model, n_samples=args.n_samples, **kw)
    return 0


if __name__ == "__main__":
    sys.exit(main())
