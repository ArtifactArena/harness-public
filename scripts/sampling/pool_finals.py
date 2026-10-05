#!/usr/bin/env python3
"""Stage B of the SH-250 pool tournament: the STORED round robins.

Stage A (`pool_rr.py`) plays every model's full intra-model round robin without telemetry and
leaves `<rr>/<model>/top_5_bots.json` + `<rr>/<model>/top_1.json`. Stage B replays two small
round robins WITH `match_data.json` telemetry (videos still off) and rates them Bradley-Terry:

  B1  per model: the 10 pairings among its top-5 bots      -> <out>/stage_b/top5/<model>/
  B2  cross-model: every model's top-1 bot, all pairings   -> <out>/stage_b/top1/
  B3  cross-model, per run group k: every model's run-k winner (runs.json), all pairings
      -> <out>/stage_b/runs/g<k>/   (opt-in: --stages b3 [--groups k ...]; five disjoint 50-sample
      draws give five independent cross-model leaderboards — the rank-stability study)
  B4  Field Round -> <out>/stage_b/field/  (opt-in: --stages b4 --field-rule champions|full)
      champions: every NON-champion run winner vs every champion it has not met yet (not its own
                 model's champion — Top-5 Round — and not the champions of its own draw — runs/g<k>)
      full:      every pair of run winners not already stored anywhere: not the same model (Top-5
                 Round), not two champions (Champions Round), not the same draw (runs/g<k>); with
                 B1-B3 this completes the full round robin of all run winners, so ONE joint fit
                 rates all 105 bots on one scale
  B5  Baseline Round: every run winner vs the QUALIFICATION BLOCK (the same 342 kg palette-plastic
      slab every sample had to beat to qualify; mjarena.core.qualification_block), the block always
      on the blue side as in qualification, no-op controller -> <out>/stage_b/baseline/
      (opt-in: --stages b5; gives every leaderboard its "vs Block" reference)

Each stage dir holds `matches/<a>_vs_<b>/{match_result.json, match_data.json.gz}` (telemetry
gzipped in place right after the round robin, like run_pool.compact_sample) and `elo.json`
(`method: bt`, standings, every rating tie declared). `<out>/stage_b/summary.json` collects the
B1 and B2 standings. Artifact ids stay `<model>__tNNN_c000` and map to the pack slot
`<pack>/<model>/cNNN/commit_0/{robot.xml, controller.py}`.

Rules come from `configs/tournaments/sh.yaml` (-> base.yaml): 300 s, inactivity 10 s / 0.5 m,
score `any`, contact fidelity `high`, 3d. Only `n_rollouts`, the video flags and (for smoke
tests) `match_time` are overridden.

Resumable: `run_round_robin` skips pairings whose match_result.json exists (in its parallel
path, n_parallel_matches > 1 and > 1 pairing) and this script skips a round robin whose
pairings are all present; the gzip step tolerates already-gzipped files.

Refuses to run with ARENA_SKIP_MATCH_DATA=1 — Stage B exists to store the telemetry.

    python scripts/sampling/pool_finals.py --rr rr-<run> --pack <pack> --out rr-<run> \
        --n-rollouts 11 --n-parallel-matches 90 --run-id <run-id>
"""
from __future__ import annotations

import argparse
import gzip
import itertools
import json
import logging
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import mjarena.core.unified_builder  # noqa: E402,F401  (import order: breaks the dspy_core/design_shop cycle)
if os.environ.get("ARENA_OBS_ACCEL") == "1":                      # opt-in exact-observation accelerator (the upstream Cython kernels)
    from mjarena.envs.observation_accel import install as _install_obs_accel  # noqa: E402
    _install_obs_accel()
from mjarena.agents.types import BotArtifact  # noqa: E402
from mjarena.core.qualification_block import write_qualification_block  # noqa: E402
from mjarena.elo.core import MatchOutcome, compute_standings  # noqa: E402
from mjarena.tournament.tournament import run_round_robin  # noqa: E402
from mjarena.two_stage.artifact_loader import load_commit_artifact, parse_artifact_id  # noqa: E402
from mjarena.two_stage.match_config import TwoStageMatchConfig, load_tournament_config  # noqa: E402

log = logging.getLogger("pool_finals")

DEFAULT_CONFIG = REPO / "configs/tournaments/sh.yaml"
RATING_TOL = 1e-9
STAGES = ("b1", "b2", "b3", "b4", "b5")
BLOCK_ID = "baseline__block"
DEFAULT_STAGES = ("b1", "b2")   # b3 (Run Champions Rounds) is opt-in


# ── helpers ───────────────────────────────────────────────────────────────────

def refuse_if_telemetry_skipped() -> None:
    if os.environ.get("ARENA_SKIP_MATCH_DATA") == "1":
        sys.exit(
            "pool_finals: ARENA_SKIP_MATCH_DATA=1 is set, but Stage B exists to STORE the "
            "match_data.json telemetry of the top-5 and top-1 round robins. Unset it and rerun."
        )


def gzip_match_data(matches_dir: Path, only_dirs: Optional[Sequence[Path]] = None) -> int:
    """gzip every raw match_data.json under `matches_dir` in place (-> match_data.json.gz,
    compresslevel 6, raw unlinked) and return how many were compressed. Pairings that are
    already gzipped have no raw file and are left alone; a raw file next to a stale .gz (a
    crash between write and unlink) is re-gzipped from the raw file. `only_dirs` restricts the
    sweep to those pairing dirs (a shard must never touch a pairing another job is still writing)."""
    n = 0
    if only_dirs is None:
        raws = sorted(matches_dir.rglob("match_data.json"))
    else:
        raws = sorted(d / "match_data.json" for d in only_dirs if (d / "match_data.json").is_file())
    for raw in raws:
        gz = raw.with_suffix(".json.gz")
        tmp = gz.with_name(gz.name + ".tmp")
        with open(raw, "rb") as src, gzip.open(tmp, "wb", compresslevel=6) as dst:
            shutil.copyfileobj(src, dst)
        os.replace(tmp, gz)
        raw.unlink()
        n += 1
    return n


def read_match_outcomes(matches_dir: Path) -> List[MatchOutcome]:
    """One MatchOutcome per game, derived exactly as intra_model._read_match_outcomes: red_bot /
    blue_bot are fixed for every seed of a pairing (seed parity only swaps spawn positions);
    anything that is not a red or blue win is a draw. Malformed records fail loudly."""
    outcomes: List[MatchOutcome] = []
    for match_json in sorted(matches_dir.rglob("match_result.json")):
        data = json.loads(match_json.read_text())
        red, blue = data["red_bot"], data["blue_bot"]
        for game in data["matches"]:
            winner = game["winner"]
            if winner == "red":
                outcomes.append(MatchOutcome(player_a=red, player_b=blue, winner=red))
            elif winner == "blue":
                outcomes.append(MatchOutcome(player_a=red, player_b=blue, winner=blue))
            else:
                outcomes.append(MatchOutcome(player_a=red, player_b=blue, winner="draw"))
    return outcomes


def rating_ties(standings: Dict[str, Dict[str, Any]]) -> List[List[str]]:
    """Groups of artifact ids whose BT ratings are equal to RATING_TOL (only groups of >= 2)."""
    ranked = sorted(standings.items(), key=lambda kv: (-kv[1]["elo"], kv[0]))
    groups: List[List[str]] = []
    for aid, st in ranked:
        if groups and abs(standings[groups[-1][0]]["elo"] - st["elo"]) <= RATING_TOL:
            groups[-1].append(aid)
        else:
            groups.append([aid])
    return [g for g in groups if len(g) > 1]


def ties_at_top(standings: Dict[str, Dict[str, Any]]) -> List[str]:
    top = max(st["elo"] for st in standings.values())
    tied = sorted(aid for aid, st in standings.items() if abs(st["elo"] - top) <= RATING_TOL)
    return tied if len(tied) > 1 else []


def pack_commit_dir(pack: Path, artifact_id: str) -> Path:
    """`<model>__tNNN_c000` -> `<pack>/<model>/cNNN/commit_0`."""
    parsed = parse_artifact_id(artifact_id)
    if parsed is None:
        raise ValueError(f"{artifact_id!r} is not a pool artifact id (<model>__tNNN_c000)")
    if parsed["commit_idx"] != 0:
        raise ValueError(f"{artifact_id!r}: pool samples are single-commit, expected _c000")
    return pack / parsed["model"] / f"c{parsed['tournament_idx']:03d}" / "commit_0"


def load_bot(artifact_id: str, pack: Path, cfg: TwoStageMatchConfig, clean_cache_root: Path) -> BotArtifact:
    parsed = parse_artifact_id(artifact_id)
    commit_dir = pack_commit_dir(pack, artifact_id)
    bot = load_commit_artifact(
        commit_dir=commit_dir,
        model_name=parsed["model"],
        commit_idx=0,
        tournament_idx=parsed["tournament_idx"],
        constraints_path=cfg.constraints_path,
        physics_mode=cfg.physics_mode,
        clean_cache_root=clean_cache_root,
    )
    if bot.name != artifact_id:
        raise RuntimeError(f"loaded {bot.name!r} for requested {artifact_id!r}")
    return bot


def drop_broken_pairings(pair_dirs: Sequence[Path]) -> int:
    """A pairing whose match_result.json exists but is empty or unparsable (a write cut short by a full
    disk or a killed job) must be replayed, but run_round_robin's resume only checks that the file exists.
    Remove such pairing dirs before resuming; returns how many were dropped."""
    n = 0
    for d in pair_dirs:
        res = d / "match_result.json"
        if not res.is_file():
            continue
        try:
            if res.stat().st_size == 0:
                raise ValueError("empty")
            json.loads(res.read_text())
        except (ValueError, OSError) as exc:
            log.warning("%s: match_result.json unusable (%s) — dropping the pairing so it is replayed", d.name, exc)
            shutil.rmtree(d)
            n += 1
    return n


def expected_pair_dirs(matches_dir: Path, bot_names: Sequence[str]) -> List[Path]:
    """`run_round_robin` names a pairing dir `<a>_vs_<b>` with the lower bot index first, and
    load_commit_artifact sets generator == name == artifact id."""
    return [matches_dir / f"{a}_vs_{b}" for a, b in itertools.combinations(bot_names, 2)]


# ── one stored round robin ────────────────────────────────────────────────────

def play_stored_rr(
    bots: Dict[str, BotArtifact],
    stage_dir: Path,
    cfg: TwoStageMatchConfig,
    *,
    n_rollouts: int,
    n_parallel_matches: int, n_parallel_seeds: int = 1,
    match_time: float,
    season_id: str,
    tournament_id: str,
    shard: Optional[Tuple[int, int]] = None,
) -> None:
    """Play (or resume) the round robin among `bots` into `stage_dir` with telemetry, then gzip
    the telemetry. Mirrors intra_model.run_intra_rr_for_model's run_round_robin call with the
    video flags forced off. `shard=(i, n)` plays only the pairings whose index (position in the
    sorted combinations list) is congruent to i mod n and gzips only those — n such jobs on
    different nodes complete the round robin together; seeds are index-based, so the games are
    the ones a single job would have played."""
    stage_dir.mkdir(parents=True, exist_ok=True)
    matches_dir = stage_dir / "matches"
    names = list(bots)
    all_dirs = expected_pair_dirs(matches_dir, names)
    subset: Optional[List[int]] = None
    mine = all_dirs
    if shard is not None:
        i, n = shard
        if not (0 <= i < n):
            raise ValueError(f"shard {shard}: index must be in [0, n)")
        subset = [idx for idx in range(len(all_dirs)) if idx % n == i]
        mine = [all_dirs[idx] for idx in subset]
    drop_broken_pairings(mine)
    pending = [d for d in mine if not (d / "match_result.json").is_file()]
    if not pending:
        log.info("%s: all %d pairings%s already have match_result.json — nothing to play",
                 stage_dir, len(mine), f" of shard {shard[0]}/{shard[1]}" if shard else "")
    else:
        if len(pending) < len(mine) and n_parallel_matches <= 1:
            log.warning("%s: %d pairings pending but n_parallel_matches=1 — run_round_robin resumes "
                        "only in its parallel path, so finished pairings will be replayed",
                        stage_dir, len(pending))
        if shard is not None and n_parallel_matches <= 1:
            raise ValueError("shards need n_parallel_matches > 1 (run_round_robin subsets only in its parallel path)")
        arena_xml = cfg.arena_xml if cfg.arena_xml.is_absolute() else REPO / cfg.arena_xml
        log.info("%s: %d bots, %d pairings pending%s, %d seeds, match_time %.0f s, telemetry ON, video OFF",
                 stage_dir, len(names), len(pending), f" (shard {shard[0]}/{shard[1]}: {len(mine)} of {len(all_dirs)})" if shard else "",
                 n_rollouts, match_time)
        run_round_robin(
            bots=bots,
            arena_xml=arena_xml,
            out_dir=stage_dir,
            n_rollouts=n_rollouts,
            record_video=False,
            save_all_videos=False,
            highres=cfg.highres,
            verbose=True,
            trace_progress=False,
            physics_mode=cfg.physics_mode,
            score_function=cfg.score_function,
            match_time=match_time,
            contact_fidelity=cfg.contact_fidelity,
            inactivity_timeout_seconds=cfg.inactivity_timeout,
            inactivity_min_displacement=cfg.inactivity_min_displacement,
            size_limits=cfg.size_limits,
            n_parallel_matches=n_parallel_matches,
            n_parallel_seeds=n_parallel_seeds,
            camera_mode=cfg.camera,
            rendering_flags=cfg.rendering_flags or None,
            season_id=season_id,
            tournament_id=tournament_id,
            matchup_subset=subset,
        )
    n_gz = gzip_match_data(matches_dir, only_dirs=mine if shard is not None else None)
    log.info("%s: gzipped %d match_data.json", stage_dir, n_gz)


def write_elo(
    stage_dir: Path,
    participants: Sequence[str],
    *,
    head: Dict[str, Any],
    n_rollouts: int,
    match_time: float,
    run_id: Optional[str],
) -> Dict[str, Any]:
    outcomes = read_match_outcomes(stage_dir / "matches")
    standings = compute_standings(outcomes)
    missing = sorted(set(participants) - set(standings))
    if missing:
        raise RuntimeError(f"{stage_dir}: no games found for {missing}")
    payload: Dict[str, Any] = dict(head)
    payload.update({
        "method": "bt",
        "n_rollouts": n_rollouts,
        "match_time": match_time,
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "participants": list(participants),
        "n_games": len(outcomes),
        "standings": standings,
        "ties": rating_ties(standings),
        "ties_at_top": ties_at_top(standings),
    })
    (stage_dir / "elo.json").write_text(json.dumps(payload, indent=2))
    return payload


# ── participants ──────────────────────────────────────────────────────────────

def model_dirs(rr: Path, models: Optional[Sequence[str]]) -> List[Path]:
    dirs = sorted(d for d in rr.iterdir() if d.is_dir() and d.name != "stage_b")
    if models is not None:
        wanted = set(models)
        dirs = [d for d in dirs if d.name in wanted]
        unknown = wanted - {d.name for d in dirs}
        if unknown:
            raise FileNotFoundError(f"no Stage A dir under {rr} for {sorted(unknown)}")
    return dirs


def top5_ids(model_dir: Path) -> Optional[List[str]]:
    path = model_dir / "top_5_bots.json"
    if not path.is_file():
        return None
    payload = json.loads(path.read_text())
    return [str(row["artifact_id"]) for row in payload["bots"]]


def top1_id(model_dir: Path) -> Optional[str]:
    path = model_dir / "top_1.json"
    if not path.is_file():
        return None
    aid = json.loads(path.read_text())["artifact_id"]
    return None if aid is None else str(aid)


# ── stages ────────────────────────────────────────────────────────────────────

def run_b1(rr: Path, pack: Path, stage_b: Path, cfg: TwoStageMatchConfig, *, n_rollouts: int,
           n_parallel_matches: int, match_time: float, run_id: Optional[str],
           models: Optional[Sequence[str]], n_parallel_seeds: int = 1) -> Dict[str, Any]:
    clean_cache_root = stage_b / "_clean_cache"
    results: Dict[str, Any] = {}
    for md in model_dirs(rr, models):
        model = md.name
        ids = top5_ids(md)
        if ids is None:
            log.info("B1 %s: no top_5_bots.json — Stage A not finished, skipping", model)
            continue
        stage_dir = stage_b / "top5" / model
        if len(ids) < 2:
            reason = f"top_5_bots.json lists {len(ids)} bot(s); a round robin needs at least 2"
            log.warning("B1 %s: %s — skipped", model, reason)
            stage_dir.mkdir(parents=True, exist_ok=True)
            (stage_dir / "SKIPPED.json").write_text(json.dumps(
                {"model": model, "stage": "b1", "reason": reason, "n_bots": len(ids), "bots": ids}, indent=2))
            results[model] = {"skipped": reason, "n_bots": len(ids), "bots": ids}
            if len(ids) == 1:
                # a single run winner is the model's champion by default (user ruling 2026-09-20):
                # write the model-level top_1.json so the Champions Round enters it
                parsed = parse_artifact_id(ids[0]) or {}
                (md / "top_1.json").write_text(json.dumps({
                    "model": model, "artifact_id": ids[0], "tournament_idx": parsed.get("tournament_idx"),
                    "elo": 1000.0, "wins": 0, "losses": 0, "draws": 0, "games": 0, "ties_at_top": [ids[0]],
                    "source": "single run winner; Top-5 Round skipped"}, indent=2))
                log.info("B1 %s: single run winner %s is the champion by default", model, ids[0])
            continue
        bots = {aid: load_bot(aid, pack, cfg, clean_cache_root) for aid in ids}
        play_stored_rr(bots, stage_dir, cfg, n_rollouts=n_rollouts, n_parallel_matches=n_parallel_matches,
                       n_parallel_seeds=n_parallel_seeds,
                       match_time=match_time, season_id=f"sh250_stage_b/top5/{model}", tournament_id="top5")
        elo = write_elo(stage_dir, ids, head={"model": model, "stage": "b1", "scope": "intra_model_top5"},
                        n_rollouts=n_rollouts, match_time=match_time, run_id=run_id)
        results[model] = {"participants": elo["participants"], "standings": elo["standings"],
                          "ties": elo["ties"], "ties_at_top": elo["ties_at_top"]}
        log.info("B1 %s: %s", model, ", ".join(
            f"{aid} {st['elo']:.1f}" for aid, st in sorted(elo["standings"].items(), key=lambda kv: -kv[1]["elo"])))
    return results



def b1_winner(elo_path: Path) -> Optional[str]:
    """Top-rated bot of a Stage B1 elo.json (ties broken by lowest tournament index in the artifact id)."""
    st = json.loads(elo_path.read_text()).get("standings") or {}
    if not st:
        return None
    return sorted(st.items(), key=lambda kv: (-float(kv[1]["elo"]), kv[0]))[0][0]


def run_b2(rr: Path, pack: Path, stage_b: Path, cfg: TwoStageMatchConfig, *, n_rollouts: int,
           n_parallel_matches: int, match_time: float, run_id: Optional[str],
           models: Optional[Sequence[str]], n_parallel_seeds: int = 1) -> Dict[str, Any]:
    clean_cache_root = stage_b / "_clean_cache"
    stage_dir = stage_b / "top1"
    stage_dir.mkdir(parents=True, exist_ok=True)
    by_model: Dict[str, str] = {}
    skipped: Dict[str, str] = {}
    for md in model_dirs(rr, models):
        b1_elo = stage_b / "top5" / md.name / "elo.json"
        if b1_elo.is_file():                       # B1 was played: its BT winner is the model's top-1
            aid = b1_winner(b1_elo)
            if aid is None:
                skipped[md.name] = "B1 elo.json has no standings"
                continue
            by_model[md.name] = aid
            continue
        if not (md / "top_1.json").is_file():
            skipped[md.name] = "no top_1.json"
            continue
        aid = top1_id(md)
        if aid is None:
            skipped[md.name] = "top_1.json has no artifact_id"
            continue
        by_model[md.name] = aid
    (stage_dir / "skipped.json").write_text(json.dumps(skipped, indent=2, sort_keys=True))
    for model, reason in skipped.items():
        log.warning("B2: %s skipped — %s", model, reason)
    ids = [by_model[m] for m in sorted(by_model)]
    if len(ids) < 2:
        reason = f"only {len(ids)} model(s) have a top-1 bot; a round robin needs at least 2"
        log.warning("B2: %s — skipped", reason)
        (stage_dir / "SKIPPED.json").write_text(json.dumps(
            {"stage": "b2", "reason": reason, "participants": ids}, indent=2))
        return {"skipped": reason, "participants": ids, "by_model": {}, "not_entered": skipped}
    bots = {aid: load_bot(aid, pack, cfg, clean_cache_root) for aid in ids}
    play_stored_rr(bots, stage_dir, cfg, n_rollouts=n_rollouts, n_parallel_matches=n_parallel_matches,
                   n_parallel_seeds=n_parallel_seeds,
                   match_time=match_time, season_id="sh250_stage_b/top1", tournament_id="top1")
    elo = write_elo(stage_dir, ids, head={"scope": "cross_model_top1", "stage": "b2", "model": None},
                    n_rollouts=n_rollouts, match_time=match_time, run_id=run_id)
    log.info("B2: %s", ", ".join(
        f"{aid} {st['elo']:.1f}" for aid, st in sorted(elo["standings"].items(), key=lambda kv: -kv[1]["elo"])))
    return {
        "participants": elo["participants"],
        "standings": elo["standings"],
        "ties": elo["ties"],
        "ties_at_top": elo["ties_at_top"],
        "by_model": {m: {"artifact_id": aid, **elo["standings"][aid]} for m, aid in sorted(by_model.items())},
        "not_entered": skipped,
    }


def run_winners_by_group(rr: Path, models: Optional[Sequence[str]]) -> Dict[int, Dict[str, str]]:
    """{k: {model: run-k winner artifact id}} from every model's `runs.json` (a run without a winner —
    no eligible bot — is simply absent for that model). Models without runs.json are skipped."""
    by_k: Dict[int, Dict[str, str]] = {}
    for md in model_dirs(rr, models):
        path = md / "runs.json"
        if not path.is_file():
            log.warning("B3 %s: no runs.json — skipping", md.name)
            continue
        for g in json.loads(path.read_text())["groups"]:
            k = int(str(g["group"])[1:])
            if g.get("winner"):
                by_k.setdefault(k, {})[md.name] = str(g["winner"])
    return by_k


def run_b3(rr: Path, pack: Path, stage_b: Path, cfg: TwoStageMatchConfig, *, n_rollouts: int,
           n_parallel_matches: int, match_time: float, run_id: Optional[str],
           models: Optional[Sequence[str]], n_parallel_seeds: int = 1,
           groups: Optional[Sequence[int]] = None, shard: Optional[Tuple[int, int]] = None) -> Dict[str, Any]:
    """Run Champions Rounds: for each run group g<k>, the cross-model round robin of every model's run-k
    winner, stored with telemetry under `<out>/stage_b/runs/g<k>/` (participants.json, matches/, elo.json).
    Run winners are disjoint across k, so the groups can be played by concurrent jobs (`--groups k`);
    one group's pairings can be split further across jobs with `shard=(i, n)` — shard jobs only play
    (no elo.json); a final unsharded call finds every pairing present and writes elo.json."""
    clean_cache_root = stage_b / "_clean_cache"
    by_k = run_winners_by_group(rr, models)
    wanted = sorted(by_k) if groups is None else [int(k) for k in groups]
    results: Dict[str, Any] = {}
    for k in wanted:
        by_model = dict(sorted(by_k.get(k, {}).items()))
        gname = f"g{k}"
        stage_dir = stage_b / "runs" / gname
        stage_dir.mkdir(parents=True, exist_ok=True)
        entered = [md.name for md in model_dirs(rr, models)]
        not_entered = sorted(set(entered) - set(by_model))
        ptmp = stage_dir / f".participants.{os.getpid()}.tmp"
        ptmp.write_text(json.dumps({
            "group": gname, "stage": "b3", "scope": "cross_model_run_winners",
            "rule": "each model's run-k winner (runs.json groups[k].winner); models whose run k had no winner are not entered",
            "by_model": by_model, "not_entered": not_entered}, indent=2))
        os.replace(ptmp, stage_dir / "participants.json")     # identical content from every shard; atomic
        ids = [by_model[m] for m in sorted(by_model)]
        if len(ids) < 2:
            reason = f"only {len(ids)} model(s) have a run-{k} winner; a round robin needs at least 2"
            log.warning("B3 %s: %s — skipped", gname, reason)
            (stage_dir / "SKIPPED.json").write_text(json.dumps(
                {"stage": "b3", "group": gname, "reason": reason, "participants": ids}, indent=2))
            results[gname] = {"skipped": reason, "participants": ids, "by_model": {}, "not_entered": not_entered}
            continue
        bots = {aid: load_bot(aid, pack, cfg, clean_cache_root) for aid in ids}
        play_stored_rr(bots, stage_dir, cfg, n_rollouts=n_rollouts, n_parallel_matches=n_parallel_matches,
                       n_parallel_seeds=n_parallel_seeds, match_time=match_time,
                       season_id=f"sh250_stage_b/runs/{gname}", tournament_id=f"runs-{gname}", shard=shard)
        if shard is not None:
            log.info("B3 %s: shard %d/%d played — elo.json is written by the final unsharded call", gname, *shard)
            results[gname] = {"shard": list(shard), "participants": ids, "not_entered": not_entered}
            continue
        elo = write_elo(stage_dir, ids, head={"scope": "cross_model_run_winners", "stage": "b3", "model": None, "group": gname},
                        n_rollouts=n_rollouts, match_time=match_time, run_id=run_id)
        log.info("B3 %s: %s", gname, ", ".join(
            f"{aid} {st['elo']:.1f}" for aid, st in sorted(elo["standings"].items(), key=lambda kv: -kv[1]["elo"])))
        results[gname] = {
            "participants": elo["participants"],
            "standings": elo["standings"],
            "ties": elo["ties"],
            "ties_at_top": elo["ties_at_top"],
            "by_model": {m: {"artifact_id": aid, **elo["standings"][aid]} for m, aid in by_model.items()},
            "not_entered": not_entered,
        }
    return results


def champions_of(stage_b: Path) -> List[str]:
    """The Champions Round participants (stage_b/top1/elo.json), one bot per model."""
    return [str(a) for a in json.loads((stage_b / "top1" / "elo.json").read_text())["participants"]]


FIELD_RULES = ("champions", "full")


def field_pairings(rr: Path, stage_b: Path, models: Optional[Sequence[str]], rule: str = "champions") -> Dict[str, Any]:
    """The Field Round pairing list (unordered pairs; the dict also names the sorted bot list whose
    combinations index the pairs).
      rule="champions": (run winner w, champion c) for every non-champion w and every champion c, EXCEPT
                        c of w's own model (Top-5 Round) and the champions of w's own draw (runs/g<k>).
      rule="full":      every pair of run winners EXCEPT same model (Top-5 Round), both champions
                        (Champions Round) and same draw (runs/g<k>) — i.e. every pairing of the full
                        run-winner round robin that no stored round has played."""
    if rule not in FIELD_RULES:
        raise ValueError(f"unknown field rule {rule!r}; expected one of {FIELD_RULES}")
    champs = sorted(champions_of(stage_b))
    by_k = run_winners_by_group(rr, models)
    group_of: Dict[str, int] = {w: k for k, d in by_k.items() for w in d.values()}
    missing = [c for c in champs if c not in group_of]
    if missing:
        raise RuntimeError(f"champions without a run group in runs.json: {missing}")
    winners = sorted(group_of)
    champ_set = set(champs)
    non = [w for w in winners if w not in champ_set]
    pairs: List[Tuple[str, str]] = []
    skipped = {"same_model_top5_round": 0, "both_champions_champions_round": 0, "same_draw_runs_round": 0}
    if rule == "champions":
        candidates = [(w, c) for w in non for c in champs]
    else:
        candidates = list(itertools.combinations(winners, 2))
    for a, b in candidates:
        if a.split("__")[0] == b.split("__")[0]:
            skipped["same_model_top5_round"] += 1
            continue
        if a in champ_set and b in champ_set:
            skipped["both_champions_champions_round"] += 1
            continue
        if group_of[a] == group_of[b]:
            skipped["same_draw_runs_round"] += 1
            continue
        pairs.append(tuple(sorted((a, b), key=winners.index)))
    text = {"champions": "every non-champion run winner vs every champion, except its own model's champion "
                         "(Top-5 Round) and the champions of its own draw (stage_b/runs/g<k>)",
            "full": "every pair of run winners except same model (Top-5 Round), both champions (Champions Round) "
                    "and same draw (stage_b/runs/g<k>) — completes the full run-winner round robin"}[rule]
    return {"stage": "b4", "scope": "field_round", "field_rule": rule, "bots": winners, "champions": champs,
            "rule": text, "n_bots": len(winners), "n_non_champions": len(non), "n_pairs": len(pairs),
            "n_candidates": len(candidates), "skipped": skipped, "pairs": [list(pq) for pq in pairs]}


def run_b4(rr: Path, pack: Path, stage_b: Path, cfg: TwoStageMatchConfig, *, n_rollouts: int,
           n_parallel_matches: int, match_time: float, run_id: Optional[str],
           models: Optional[Sequence[str]], n_parallel_seeds: int = 1,
           shard: Optional[Tuple[int, int]] = None, field_rule: str = "champions") -> Dict[str, Any]:
    """Field Round: the explicit pairing list of `field_pairings` played among ALL run winners, stored
    with telemetry under `<out>/stage_b/field/` (pairings.json, matches/, elo.json). Implemented as the
    105-bot round robin restricted to those pairings (run_round_robin matchup_subset), so pairing dirs
    and seeds follow the same index scheme as every other stored round; `--shard I N` splits further."""
    clean_cache_root = stage_b / "_clean_cache"
    spec = field_pairings(rr, stage_b, models, rule=field_rule)
    stage_dir = stage_b / "field"
    existing = stage_dir / "pairings.json"
    if existing.is_file():
        prev = json.loads(existing.read_text())
        if prev.get("field_rule", "champions") != field_rule:
            raise RuntimeError(f"{existing} was written with field_rule={prev.get('field_rule', 'champions')!r}; "
                               f"refusing to mix with {field_rule!r} (use a fresh --out or the same rule)")
    stage_dir.mkdir(parents=True, exist_ok=True)
    ptmp = stage_dir / f".pairings.{os.getpid()}.tmp"
    ptmp.write_text(json.dumps(spec, indent=2))
    os.replace(ptmp, stage_dir / "pairings.json")
    names = spec["bots"]
    all_pairs = list(itertools.combinations(names, 2))
    index = {pq: i for i, pq in enumerate(all_pairs)}
    wanted = [index[tuple(pq)] for pq in spec["pairs"]]
    if shard is not None:
        i, n = shard
        wanted = [idx for j, idx in enumerate(sorted(wanted)) if j % n == i]
    matches_dir = stage_dir / "matches"
    mine = [matches_dir / f"{a}_vs_{b}" for a, b in (all_pairs[idx] for idx in sorted(wanted))]
    drop_broken_pairings(mine)
    pending = [d for d in mine if not (d / "match_result.json").is_file()]
    log.info("B4 field (%s): %d bots, %d pairings in the rule%s, %d pending", field_rule, len(names), spec["n_pairs"],
             f" (shard {shard[0]}/{shard[1]}: {len(mine)})" if shard else "", len(pending))
    if pending:
        bots = {aid: load_bot(aid, pack, cfg, clean_cache_root) for aid in names}
        arena_xml = cfg.arena_xml if cfg.arena_xml.is_absolute() else REPO / cfg.arena_xml
        run_round_robin(
            bots=bots, arena_xml=arena_xml, out_dir=stage_dir, n_rollouts=n_rollouts, record_video=False,
            save_all_videos=False, highres=cfg.highres, verbose=True, trace_progress=False,
            physics_mode=cfg.physics_mode, score_function=cfg.score_function, match_time=match_time,
            contact_fidelity=cfg.contact_fidelity, inactivity_timeout_seconds=cfg.inactivity_timeout,
            inactivity_min_displacement=cfg.inactivity_min_displacement, size_limits=cfg.size_limits,
            n_parallel_matches=max(2, n_parallel_matches), n_parallel_seeds=n_parallel_seeds,
            camera_mode=cfg.camera, rendering_flags=cfg.rendering_flags or None,
            season_id="sh250_stage_b/field", tournament_id="field", matchup_subset=set(wanted),
        )
    n_gz = gzip_match_data(matches_dir, only_dirs=mine)
    log.info("%s: gzipped %d match_data.json", stage_dir, n_gz)
    if shard is not None:
        return {"shard": list(shard), "n_pairs": spec["n_pairs"], "played": len(mine)}
    elo = write_elo(stage_dir, names, head={"scope": "field_round", "stage": "b4", "model": None, "field_rule": field_rule,
                                             "note": "standings of the Field Round games alone; the joint fit over B1-B4 is the rating of record"},
                    n_rollouts=n_rollouts, match_time=match_time, run_id=run_id)
    return {"participants": elo["participants"], "n_pairs": spec["n_pairs"], "n_games": elo["n_games"],
            "standings": elo["standings"], "ties": elo["ties"], "ties_at_top": elo["ties_at_top"]}


def block_artifact(cfg: TwoStageMatchConfig, stage_b: Path) -> BotArtifact:
    """The qualification block as a tournament participant: the palette-resolved slab XML written by
    the same function qualification uses, a zero-action controller, no actuators."""
    d = stage_b / "_clean_cache" / BLOCK_ID
    d.mkdir(parents=True, exist_ok=True)
    xml = d / "robot.xml"
    if not xml.is_file():
        tmp = d / f".robot.xml.{os.getpid()}.tmp"
        write_qualification_block(tmp, cfg.constraints_path, cfg.physics_mode)
        try:
            os.link(tmp, xml)
        except FileExistsError:
            pass
        finally:
            tmp.unlink(missing_ok=True)
    ctrl = d / "controller.py"
    if not ctrl.is_file():
        tmp = d / f".controller.py.{os.getpid()}.tmp"
        tmp.write_text('"""Zero-action policy: the qualification block does nothing."""\n\n\ndef policy_step(obs) -> dict:\n    return {}\n')
        try:
            os.link(tmp, ctrl)
        except FileExistsError:
            pass
        finally:
            tmp.unlink(missing_ok=True)
    return BotArtifact(name=BLOCK_ID, generator=BLOCK_ID, morphology_xml=xml, controller_code=ctrl, actuator_names=[],
                       morphology_score=1.0, morphology_verified=True, controller_verified=True,
                       metadata={"two_stage_kind": "baseline", "model": "baseline", "source": "mjarena.core.qualification_block"})


def run_b5(rr: Path, pack: Path, stage_b: Path, cfg: TwoStageMatchConfig, *, n_rollouts: int,
           n_parallel_matches: int, match_time: float, run_id: Optional[str],
           models: Optional[Sequence[str]], n_parallel_seeds: int = 1,
           shard: Optional[Tuple[int, int]] = None) -> Dict[str, Any]:
    """Baseline Round: every run winner vs the qualification block, stored with telemetry under
    `<out>/stage_b/baseline/` (pairings.json, matches/, elo.json). The block is listed LAST so it is
    always the blue side of the pairing dir `<winner>_vs_baseline__block`, as in qualification."""
    clean_cache_root = stage_b / "_clean_cache"
    by_k = run_winners_by_group(rr, models)
    winners = sorted({w for d in by_k.values() for w in d.values()})
    names = winners + [BLOCK_ID]
    stage_dir = stage_b / "baseline"
    stage_dir.mkdir(parents=True, exist_ok=True)
    spec = {"stage": "b5", "scope": "baseline_round", "bots": names, "baseline": BLOCK_ID,
            "rule": "every run winner vs the qualification block (mjarena.core.qualification_block: palette plastic "
                    "1.2 x 1.2 x 0.25 m, 342 kg), block on the blue side, zero-action controller",
            "n_pairs": len(winners), "pairs": [[w, BLOCK_ID] for w in winners]}
    ptmp = stage_dir / f".pairings.{os.getpid()}.tmp"
    ptmp.write_text(json.dumps(spec, indent=2))
    os.replace(ptmp, stage_dir / "pairings.json")
    all_pairs = list(itertools.combinations(names, 2))
    index = {pq: i for i, pq in enumerate(all_pairs)}
    wanted = sorted(index[(w, BLOCK_ID)] for w in winners)
    if shard is not None:
        i, n = shard
        wanted = [idx for j, idx in enumerate(wanted) if j % n == i]
    matches_dir = stage_dir / "matches"
    mine = [matches_dir / f"{a}_vs_{b}" for a, b in (all_pairs[idx] for idx in wanted)]
    drop_broken_pairings(mine)
    pending = [d for d in mine if not (d / "match_result.json").is_file()]
    log.info("B5 baseline: %d run winners vs %s%s, %d pending", len(winners), BLOCK_ID,
             f" (shard {shard[0]}/{shard[1]}: {len(mine)})" if shard else "", len(pending))
    if pending:
        bots = {aid: load_bot(aid, pack, cfg, clean_cache_root) for aid in winners}
        bots[BLOCK_ID] = block_artifact(cfg, stage_b)
        arena_xml = cfg.arena_xml if cfg.arena_xml.is_absolute() else REPO / cfg.arena_xml
        run_round_robin(
            bots=bots, arena_xml=arena_xml, out_dir=stage_dir, n_rollouts=n_rollouts, record_video=False,
            save_all_videos=False, highres=cfg.highres, verbose=True, trace_progress=False,
            physics_mode=cfg.physics_mode, score_function=cfg.score_function, match_time=match_time,
            contact_fidelity=cfg.contact_fidelity, inactivity_timeout_seconds=cfg.inactivity_timeout,
            inactivity_min_displacement=cfg.inactivity_min_displacement, size_limits=cfg.size_limits,
            n_parallel_matches=max(2, n_parallel_matches), n_parallel_seeds=n_parallel_seeds,
            camera_mode=cfg.camera, rendering_flags=cfg.rendering_flags or None,
            season_id="sh250_stage_b/baseline", tournament_id="baseline", matchup_subset=set(wanted),
        )
    n_gz = gzip_match_data(matches_dir, only_dirs=mine)
    log.info("%s: gzipped %d match_data.json", stage_dir, n_gz)
    if shard is not None:
        return {"shard": list(shard), "n_pairs": len(winners), "played": len(mine)}
    elo = write_elo(stage_dir, names, head={"scope": "baseline_round", "stage": "b5", "model": None, "baseline": BLOCK_ID,
                                             "note": "standings of the Baseline Round games alone (every run winner vs the block)"},
                    n_rollouts=n_rollouts, match_time=match_time, run_id=run_id)
    return {"participants": elo["participants"], "n_pairs": len(winners), "n_games": elo["n_games"],
            "standings": elo["standings"], "ties": elo["ties"], "ties_at_top": elo["ties_at_top"]}


# ── entry point ───────────────────────────────────────────────────────────────

def run(
    rr: Path,
    pack: Path,
    out: Path,
    *,
    n_rollouts: int = 11,
    n_parallel_matches: int = 8,
    n_parallel_seeds: int = 1,
    match_time: Optional[float] = None,
    config: Path = DEFAULT_CONFIG,
    run_id: Optional[str] = None,
    models: Optional[Sequence[str]] = None,
    stages: Sequence[str] = DEFAULT_STAGES,
    groups: Optional[Sequence[int]] = None,
    shard: Optional[Tuple[int, int]] = None,
    field_rule: str = "champions",
) -> Path:
    """Play Stage B into `<out>/stage_b/` from Stage A's `<rr>/<model>/top_5_bots.json` and
    `top_1.json`, with bots loaded from `<pack>/<model>/cNNN/commit_0/`. `match_time=None` takes
    the config's (300 s); `models` restricts both stages (smoke runs). Returns the stage_b dir."""
    refuse_if_telemetry_skipped()
    rr, pack, out, config = Path(rr), Path(pack), Path(out), Path(config)
    unknown = set(stages) - set(STAGES)
    if unknown:
        raise ValueError(f"unknown stages {sorted(unknown)}; expected a subset of {STAGES}")
    if not rr.is_dir():
        raise FileNotFoundError(f"Stage A root {rr} is not a directory")
    if not pack.is_dir():
        raise FileNotFoundError(f"pack {pack} is not a directory")
    cfg = load_tournament_config(config)
    match_time = float(cfg.match_time if match_time is None else match_time)
    stage_b = out / "stage_b"
    stage_b.mkdir(parents=True, exist_ok=True)
    common = dict(n_rollouts=n_rollouts, n_parallel_matches=n_parallel_matches, n_parallel_seeds=n_parallel_seeds,
                  match_time=match_time, run_id=run_id, models=models)
    log.info("Stage B -> %s (rr=%s, pack=%s, config=%s, %d seeds, %.0f s, %d parallel)",
             stage_b, rr, pack, config, n_rollouts, match_time, n_parallel_matches)

    played: Dict[str, Any] = {}
    if "b1" in stages:
        played["top5"] = run_b1(rr, pack, stage_b, cfg, **common)
    if "b2" in stages:
        played["top1"] = run_b2(rr, pack, stage_b, cfg, **common)
    if shard is not None and not set(stages) <= {"b3", "b4", "b5"}:
        raise ValueError("--shard applies to stages b3/b4/b5 only")
    if "b3" in stages:
        played["runs"] = run_b3(rr, pack, stage_b, cfg, groups=groups, shard=shard, **common)
    if "b4" in stages:
        played["field"] = run_b4(rr, pack, stage_b, cfg, shard=shard, field_rule=field_rule, **common)
    if "b5" in stages:
        played["baseline"] = run_b5(rr, pack, stage_b, cfg, shard=shard, **common)
    if shard is not None:
        log.info("shard %d/%d done — summary.json untouched (the final unsharded call writes it)", *shard)
        return stage_b
    # summary.json is re-read right before the write: concurrent B3 group jobs each add their own
    # g<k> entry (each g<k>/elo.json stays the record of truth)
    summary_path = stage_b / "summary.json"
    summary: Dict[str, Any] = json.loads(summary_path.read_text()) if summary_path.is_file() else {}
    summary.update({
        "run_id": run_id,
        "n_rollouts": n_rollouts,
        "match_time": match_time,
        "config": str(config.relative_to(REPO)) if config.is_relative_to(REPO) else str(config),
        "method": "bt",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    for key in ("top5", "top1", "field", "baseline"):
        if key in played:
            summary[key] = played[key]
    if "runs" in played:
        summary.setdefault("runs", {}).update(played["runs"])
    tmp = summary_path.with_name(summary_path.name + ".tmp")
    tmp.write_text(json.dumps(summary, indent=2))
    os.replace(tmp, summary_path)
    log.info("wrote %s", summary_path)
    return stage_b


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rr", required=True, type=Path, help="Stage A output root (holds <model>/top_5_bots.json, top_1.json)")
    ap.add_argument("--pack", required=True, type=Path, help="pack root (<model>/cNNN/commit_0/{robot.xml,controller.py})")
    ap.add_argument("--out", required=True, type=Path, help="output root; Stage B lands in <out>/stage_b/ (normally == --rr)")
    ap.add_argument("--n-rollouts", type=int, default=11, help="seeds per pairing (Stage B decision T1: 11)")
    ap.add_argument("--n-parallel-matches", type=int, default=8)
    ap.add_argument("--n-parallel-seeds", type=int, default=1, help="games of one pairing played concurrently")
    ap.add_argument("--match-time", type=float, default=None, help="override the config's match length (smoke tests only)")
    ap.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--models", nargs="*", default=None, help="restrict both stages to these models (smoke runs)")
    ap.add_argument("--stages", nargs="+", default=list(DEFAULT_STAGES), choices=STAGES,
                    help="b1 Top-5 Round, b2 Champions Round (default both), b3 Run Champions Rounds, b4 Field Round, b5 Baseline Round (opt-in)")
    ap.add_argument("--groups", nargs="*", type=int, default=None,
                    help="with b3: play only these run groups k (default: every group in runs.json)")
    ap.add_argument("--field-rule", choices=FIELD_RULES, default="champions",
                    help="b4 pairing rule: champions = run winners vs the 23 champions; full = complete the 105-bot round robin")
    ap.add_argument("--shard", nargs=2, type=int, metavar=("I", "N"), default=None,
                    help="with b3: play only pairings with index %% N == I (one of N concurrent jobs); no elo.json")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    run(args.rr, args.pack, args.out, n_rollouts=args.n_rollouts, n_parallel_matches=args.n_parallel_matches,
        n_parallel_seeds=args.n_parallel_seeds,
        match_time=args.match_time, config=args.config, run_id=args.run_id, models=args.models, stages=args.stages,
        groups=args.groups, shard=tuple(args.shard) if args.shard else None, field_rule=args.field_rule)
    return 0


if __name__ == "__main__":
    sys.exit(main())
