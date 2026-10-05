#!/usr/bin/env python3
"""Render README.md, MISSING.md and standings/summary.json for the SH-250 pool release folder.

Everything here is derived from files other scripts wrote — nothing is typed in by hand:

    <release>/pool_rr/<model>/runs.json top_5_bots.json                     (pool_rr.py --finalize-runs: the run winners)
    <release>/pool_rr/<model>/g<k>/pool_ledger.json elo.json top_1.json top_5_bots.json matches/*/match_result.json
                                                                          (pool_rr.py: Top Bot per Run Round, one run of 50 slots)
    <release>/stage_b/top5/<model>/{elo.json | SKIPPED.json}              (pool_finals.py: the Top-5 Round)
    <release>/stage_b/top1/{elo.json, skipped.json}                       (pool_finals.py: the Champions Round)
    <release>/pack-MANIFEST.json                                          (merge_pack_manifests.py: models{n_samples, eligible,
                                                                           ledger, qualified_on}, prompt_md5)
    <release>/sampling_prompt.md                                          (md5 must equal the pack manifest's prompt_md5)

    python scripts/sampling/release_readme.py --release <dir> --run-id <id> --sha <sha> [--sha <sha> ...] \
        --champions-platform hpc --forfeit-causes laptop=<json> --forfeit-causes hpc=<json> \
        --gen-root <sampling run root> [--rr <dir>] [--stage-b <dir>] [--pack-manifest <file>]

Refuses (exit 1) when a ledger names a harness sha outside `--sha`, when the frozen prompt's md5
disagrees with the pack manifest, when the models' match rules disagree, when a run's record count
disagrees with its eligible count, when a run winner is not the run's top_1, when a champion has no
Champions Round standing, when a forfeit-cause file disagrees with the pack ledger it is
authoritative for, or when a packed model has no round robin and no declared reason (MISSING.md
must explain every absence). Missing keys raise: no silent defaults. Never imports mjarena.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

# The four rounds, worded exactly as scripts/sampling/cluster/README.md words them.
ROUNDS_TABLE = [
    "| round | what | seeds | telemetry |",
    "|---|---|---|---|",
    "| **Qualification Round** | every generated sample is built and plays 3 × 20 s rounds vs the stationary block; entry rule for the pool: no round lost, or more rounds won than lost | 3 | `match_data.json.gz` per sample |",
    "| **Top Bot per Run Round** | a model's 250 samples are 5 runs of 50 consecutive slots; inside each run every eligible bot plays every other bot, 300 s; Bradley-Terry picks the run winner | 5 | none (`ARENA_SKIP_MATCH_DATA=1`) |",
    "| **Top-5 Round** | the five run winners of a model play each other | 11 | `match_data.json.gz` |",
    "| **Champions Round** | every model's Top-5 Round winner plays every other model's | 11 | `match_data.json.gz` |",
]
SELECTION_RULE = "\n".join(ROUNDS_TABLE)
ROUND_NAMES = ("Qualification Round", "Top Bot per Run Round", "Top-5 Round", "Champions Round")

# Packed or generated models that deliberately have no tournament. Anything else absent from pool_rr/ is an error.
NOT_RUN = {
    "claude-opus-4-7-high": "killed by operator 2026-09-18",
}

# Where things ran. Keys are what merge_pack_manifests.py records as `qualified_on` and what the
# ledgers' `source.root` resolves to below; values are the wording the README uses.
PLATFORMS = {
    "laptop": "laptop (macOS arm64, MuJoCo 3.10.0)",
    "hpc": "HPC cluster (x86-64 Linux, SLURM nodes, MuJoCo 3.10.0)",
    "gpu": "GPU cluster (x86-64 Linux, MuJoCo 3.10.0)",
}
# A round robin's platform is read off its ledger's `source.root` (the pack path the games were loaded from).
RR_PLATFORM_BY_SOURCE_ROOT = (
    ("<user-home>/sh250/", "hpc"),
    ("<local>/gpu/", "gpu"),
)
# Forfeit-cause files: a model qualified on `laptop` or `hpc` has an authoritative cause file from that
# platform (its forfeit total must equal the pack ledger's); a model qualified on `gpu` has only the
# laptop's PARTIAL build of the same outputs (labelled so; the pack ledger's total is the count).
FORFEIT_CAUSE_FILE_BY_QUALIFIED_ON = {"laptop": ("laptop", False), "hpc": ("hpc", False), "gpu": ("laptop", True)}
# Cause notes read off the build ledgers (design_ledger.txt) where the forfeit_stage the harness recorded is
# misleading: (cause key in the cause file, the ledger's FAIL detail, what it means). The count comes from the file.
FORFEIT_CAUSE_NOTES = {
    "claude-opus-5-high": ("Apply Material Properties", "Cannot compute volume for geom (type='sdf'): mesh must be closed",
                           "mesh failures, i.e. morphology failures, not controller failures"),
}
HARNESS_RANGE_NOTE = (
    "The only `mjarena/` change across that range outside the opt-in observation accelerator "
    "(`mjarena/envs/observation_accel`, validated bit-identical on 30 real games) is a worker-initializer hook in "
    "`mjarena/eval/match_runner.py` — no physics or rules change; the tournament config md5 is identical in every ledger."
)
GPU_REPORTS = (
    "gs://<bucket>/sh250/gpu-cluster/results/provenance/",
    "gs://<bucket>/sh250/gpu-cluster/results/recovery/",
)

# Ledger `reason` values (pool_ledger.py). "qualification failed (W. D. L.)" collapses onto "qualification failed".
PLAIN_REASONS = ("not generated", "not qualified yet", "validation failed", "qualification failed")
FORFEIT_STAGE_ORDER = ("morphology", "controller")
BUCKET_PREFIX = "gs://<bucket>/sh250"


def _read(path: Path) -> Any:
    if not path.is_file():
        raise FileNotFoundError(f"{path} is missing")
    return json.loads(path.read_text())


def _md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def _wld(st: Dict[str, Any]) -> Dict[str, int]:
    return {"wins": int(st["wins"]), "losses": int(st["losses"]), "draws": int(st["draws"])}


def _fmt_wld(w: Dict[str, int]) -> str:
    return f"{w['wins']}-{w['losses']}-{w['draws']}"


def _short(aid: str, model: str) -> str:
    """`<model>__t30_c000` -> `t30` (the artifact id abbreviated inside a row that names the model)."""
    prefix = f"{model}__"
    if not aid.startswith(prefix) or not aid.endswith("_c000"):
        raise ValueError(f"{aid} is not a `{model}__tNNN_c000` artifact id")
    return aid[len(prefix):-len("_c000")]


def _model_dirs(rr_dir: Path) -> List[Path]:
    dirs = [d for d in sorted(rr_dir.iterdir()) if d.is_dir() and d.name != "stage_b" and not d.name.startswith("_")]
    if not dirs:
        raise FileNotFoundError(f"no model directories under {rr_dir}")
    return dirs


def base_reason(reason: str) -> str:
    """Collapse "qualification failed (W1 D0 L2)" onto "qualification failed"; other reasons unchanged."""
    for plain in PLAIN_REASONS:
        if reason == plain or reason.startswith(plain + " ("):
            return plain
    return reason


def _exclusions(ledger_rows: Sequence[Dict[str, Any]]) -> Dict[str, int]:
    """Non-eligible slots by collapsed ledger reason ("forfeit:<stage>", "qualification failed", ...)."""
    return dict(Counter(base_reason(str(r["reason"])) for r in ledger_rows if not r["eligible"]))


# ── one model ─────────────────────────────────────────────────────────────────

def _run_games(model: str, group: str, matches_dir: Path, eligible: int, n_rollouts: int) -> Dict[str, int]:
    """Pairings and games of one run's round robin, counted from its records; must equal C(eligible, 2)
    pairings x n_rollouts games (0 or 1 eligible bots: no round robin, no matches dir)."""
    expected_pairings = eligible * (eligible - 1) // 2
    if not matches_dir.is_dir():
        if expected_pairings:
            raise RuntimeError(f"{model}/{group}: {expected_pairings} pairings expected but {matches_dir} is missing")
        return {"pairings": 0, "games": 0}
    records = sorted(matches_dir.rglob("match_result.json"))
    games = sum(int(_read(p)["n_seeds"]) for p in records)
    if len(records) != expected_pairings or games != expected_pairings * n_rollouts:
        raise RuntimeError(
            f"{model}/{group}: {len(records)} match_result.json / {games} games on disk, expected "
            f"{expected_pairings} pairings x {n_rollouts} seeds = {expected_pairings * n_rollouts} games"
        )
    return {"pairings": len(records), "games": games}


def _run(model: str, gdir: Path, k: int, run_size: int) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """One run g<k> of the Top Bot per Run Round: (summary row, its ledger)."""
    group = f"g{k}"
    ledger = _read(gdir / "pool_ledger.json")
    if ledger["model"] != model or ledger["group"] != group:
        raise RuntimeError(f"{gdir}: pool_ledger.json says model {ledger['model']!r} group {ledger['group']!r}")
    lo, hi = (int(x) for x in ledger["slot_range"])
    if (lo, hi) != (k * run_size, (k + 1) * run_size) or len(ledger["ledger"]) != run_size:
        raise RuntimeError(f"{gdir}: slot_range {ledger['slot_range']} / {len(ledger['ledger'])} rows for run {k} of {run_size}")
    eligible = int(ledger["eligible"])
    if eligible != sum(1 for r in ledger["ledger"] if r["eligible"]):
        raise RuntimeError(f"{gdir}: eligible {eligible} != eligible ledger rows")
    n_rollouts = int(ledger["n_rollouts"])
    elo = _read(gdir / "elo.json")
    if len(elo["standings"]) != eligible:
        raise RuntimeError(f"{gdir}: elo.json rates {len(elo['standings'])} bots, {eligible} eligible")
    games = _run_games(model, group, gdir / "matches", eligible, n_rollouts)
    top1_path = gdir / "top_1.json"
    if top1_path.is_file() != (eligible >= 1):
        raise RuntimeError(f"{gdir}: top_1.json {'present' if top1_path.is_file() else 'absent'} with {eligible} eligible bots")
    winner = None
    if top1_path.is_file():
        t = _read(top1_path)
        winner = {"artifact_id": str(t["artifact_id"]), "tournament_idx": int(t["tournament_idx"]),
                  "elo": float(t["elo"]), "wld": _wld(t), "games": int(t["games"]), "ties_at_top": list(t["ties_at_top"])}
    row = {"group": group, "slot_range": [lo, hi], "eligible": eligible, "n_rollouts": n_rollouts, **games,
           "round_robin": eligible >= 2, "winner": winner, "ties_at_top": list(elo["ties_at_top"]),
           "git_sha": ledger["git_sha"], "source_root": ledger["source"]["root"]}
    return row, ledger


def _top5_round(stage_b_dir: Path, model: str, winners: Sequence[str]) -> Dict[str, Any]:
    d = stage_b_dir / "top5" / model
    if (d / "elo.json").is_file():
        elo = _read(d / "elo.json")
        if sorted(elo["participants"]) != sorted(winners):
            raise RuntimeError(f"{model}: Top-5 Round participants {elo['participants']} != run winners {list(winners)}")
        return {"played": True, "skipped": None, "n_games": int(elo["n_games"]), "n_rollouts": int(elo["n_rollouts"]),
                "participants": list(elo["participants"]), "standings": elo["standings"],
                "ties": elo["ties"], "ties_at_top": elo["ties_at_top"]}
    if (d / "SKIPPED.json").is_file():
        skipped = _read(d / "SKIPPED.json")
        if sorted(skipped["bots"]) != sorted(winners):
            raise RuntimeError(f"{model}: SKIPPED.json bots {skipped['bots']} != run winners {list(winners)}")
        return {"played": False, "skipped": str(skipped["reason"]), "n_games": 0, "n_rollouts": None,
                "participants": list(skipped["bots"]), "standings": {}, "ties": [], "ties_at_top": []}
    raise FileNotFoundError(f"{model}: neither {d / 'elo.json'} nor {d / 'SKIPPED.json'} exists — Top-5 Round not run")


def _champions_round(stage_b_dir: Path) -> Dict[str, Any]:
    """stage_b/top1/elo.json (+ skipped.json). Scratch directories pool_finals saw beside the model dirs
    (`_clean_artifacts`: "no top_1.json") are not models and are dropped from `not_entered`."""
    d = stage_b_dir / "top1"
    elo = _read(d / "elo.json")
    not_entered = {m: str(r) for m, r in _read(d / "skipped.json").items() if not m.startswith("_")}
    return {"n_games": int(elo["n_games"]), "n_rollouts": int(elo["n_rollouts"]), "match_time": float(elo["match_time"]),
            "participants": list(elo["participants"]), "standings": elo["standings"],
            "ties": elo["ties"], "ties_at_top": elo["ties_at_top"], "not_entered": not_entered}


def top5_winner(standings: Dict[str, Dict[str, Any]]) -> str:
    """pool_finals.b1_winner: rating descending, then artifact id — the Top-5 Round's champion."""
    return sorted(standings.items(), key=lambda kv: (-float(kv[1]["elo"]), kv[0]))[0][0]


def build_model(md: Path, stage_b_dir: Path, champions: Dict[str, Any]) -> Dict[str, Any]:
    model = md.name
    runs_doc = _read(md / "runs.json")
    if runs_doc["model"] != model:
        raise RuntimeError(f"{md}: runs.json says model {runs_doc['model']!r}")
    n_runs, run_size = int(runs_doc["runs"]), int(runs_doc["run_size"])
    runs: List[Dict[str, Any]] = []
    ledgers: List[Dict[str, Any]] = []
    for k in range(n_runs):
        row, ledger = _run(model, md / f"g{k}", k, run_size)
        declared = runs_doc["groups"][k]
        if declared["group"] != row["group"] or int(declared["eligible"]) != row["eligible"] or \
                declared["winner"] != (row["winner"]["artifact_id"] if row["winner"] else None):
            raise RuntimeError(f"{model}/{row['group']}: runs.json disagrees with the run's own files ({declared})")
        runs.append(row)
        ledgers.append(ledger)
    n_samples = {int(l["n_samples"]) for l in ledgers}
    if len(n_samples) != 1 or n_runs * run_size != next(iter(n_samples)):
        raise RuntimeError(f"{model}: n_samples {sorted(n_samples)} != {n_runs} runs x {run_size}")
    all_rows = [r for l in ledgers for r in l["ledger"]]

    top5_doc = _read(md / "top_5_bots.json")
    winners_by_run = {r["winner"]["artifact_id"]: r["group"] for r in runs if r["winner"]}
    run_winners = []
    for row in top5_doc["bots"]:
        aid = str(row["artifact_id"])
        if aid not in winners_by_run:
            raise RuntimeError(f"{model}: top_5_bots.json lists {aid}, which is no run's top_1")
        run_winners.append({"rank": int(row["rank"]), "artifact_id": aid, "group": winners_by_run[aid],
                            "tournament_idx": int(row["tournament_idx"]),
                            "run_elo": float(row["intra_model_elo"]), "run_wld": dict(row["intra_model_wld"])})
    if len(run_winners) != len(winners_by_run):
        raise RuntimeError(f"{model}: top_5_bots.json lists {len(run_winners)} bots, {len(winners_by_run)} runs have a winner")
    winner_ids = [w["artifact_id"] for w in run_winners]

    top5 = _top5_round(stage_b_dir, model, winner_ids)
    for w in run_winners:
        st = top5["standings"].get(w["artifact_id"]) if top5["played"] else None
        w["top5_elo"] = float(st["elo"]) if st else None
        w["top5_wld"] = _wld(st) if st else None

    if top5["played"]:
        champion_id = top5_winner(top5["standings"])
        champion_source = "Top-5 Round winner"
    elif len(winner_ids) == 1:
        lone = _read(md / "top_1.json")
        if str(lone["artifact_id"]) != winner_ids[0]:
            raise RuntimeError(f"{model}: top_1.json names {lone['artifact_id']}, the lone run winner is {winner_ids[0]}")
        champion_id = winner_ids[0]
        champion_source = "lone run winner (Top-5 Round skipped)"
    else:
        raise RuntimeError(f"{model}: Top-5 Round skipped with {len(winner_ids)} run winners — no champion")
    if champion_id not in champions["standings"]:
        raise RuntimeError(f"{model}: champion {champion_id} has no Champions Round standing")
    c_st = champions["standings"][champion_id]
    champion = {"artifact_id": champion_id, "source": champion_source, "top5_ties_at_top": list(top5["ties_at_top"]),
                "champions_elo": float(c_st["elo"]), "champions_wld": _wld(c_st), "champions_games": int(c_st["games"])}

    return {
        "n_samples": next(iter(n_samples)), "n_runs": n_runs, "run_size": run_size,
        "eligible": sum(r["eligible"] for r in runs), "eligible_per_run": [r["eligible"] for r in runs],
        "runs": runs,
        "top_bot_per_run": {"pairings": sum(r["pairings"] for r in runs), "games": sum(r["games"] for r in runs),
                            "n_rollouts": runs[0]["n_rollouts"],
                            "runs_without_round_robin": [r["group"] for r in runs if not r["round_robin"]],
                            "runs_without_winner": [r["group"] for r in runs if r["winner"] is None]},
        "run_winners": run_winners,
        "top5_round": {k: top5[k] for k in ("played", "skipped", "n_games", "n_rollouts", "ties", "ties_at_top")},
        "champion": champion,
        "exclusions": _exclusions(all_rows),
        "exclusion_reasons_raw": dict(Counter(str(r["reason"]) for r in all_rows if not r["eligible"])),
        "git_shas": sorted({r["git_sha"] for r in runs}),
        "source_roots": sorted({r["source_root"] for r in runs}),
    }


def declared_ties(models: Dict[str, Any], champions: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Every exact rating tie the records declare, with what it decided and how it was broken:
    at the top of a run (run winner = lowest sample index, pool_rr.TIE_BREAK), at the top of a Top-5 Round
    (champion = artifact-id order, pool_finals.b1_winner), elsewhere in a Top-5 Round (no decision rests on it),
    and in the Champions Round."""
    ties: List[Dict[str, Any]] = []
    for model, m in sorted(models.items()):
        for r in m["runs"]:
            if len(r["ties_at_top"]) > 1:
                ties.append({"where": "run", "model": model, "group": r["group"], "bots": list(r["ties_at_top"]),
                             "decided": "run winner", "chosen": r["winner"]["artifact_id"],
                             "tie_break": "lowest sample index (pool_rr.py)"})
        t5 = m["top5_round"]
        for group in t5["ties"]:
            at_top = sorted(group) == sorted(t5["ties_at_top"])
            ties.append({"where": "top5", "model": model, "group": None, "bots": list(group),
                         "decided": "champion" if at_top else "nothing (not at the top)",
                         "chosen": m["champion"]["artifact_id"] if at_top else None,
                         "tie_break": "artifact-id order (pool_finals.py b1_winner)" if at_top else None})
    for group in champions["ties"]:
        at_top = sorted(group) == sorted(champions["ties_at_top"])
        ties.append({"where": "champions", "model": None, "group": None, "bots": list(group),
                     "decided": "scoreboard rank" if at_top else "scoreboard rank (not at the top)",
                     "chosen": None, "tie_break": "listed in artifact-id order"})
    return ties


def build_summary(rr_dir: Path, stage_b_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Per model: qualified per run, Top Bot per Run Round games, the run winners with their run rating and
    Top-5 Round Elo, the champion with its Champions Round Elo/W-L-D, declared ties, exclusions by reason."""
    rr_dir = Path(rr_dir)
    stage_b_dir = Path(stage_b_dir) if stage_b_dir is not None else rr_dir / "stage_b"
    b_summary = _read(stage_b_dir / "summary.json")
    champions = _champions_round(stage_b_dir)
    models = {md.name: build_model(md, stage_b_dir, champions) for md in _model_dirs(rr_dir)}

    entered = {m["champion"]["artifact_id"] for m in models.values()}
    if entered != set(champions["participants"]):
        raise RuntimeError(f"Champions Round participants {sorted(set(champions['participants']) - entered)} are no "
                           f"model's champion / champions {sorted(entered - set(champions['participants']))} did not enter")
    scoreboard = sorted(
        ({"model": m, **v["champion"]} for m, v in models.items()),
        key=lambda r: (-r["champions_elo"], r["model"]))
    for rank, row in enumerate(scoreboard, start=1):
        row["rank"] = rank
    return {
        "models": models,
        "champions_round": {"run_id": b_summary["run_id"], "method": b_summary["method"], **champions,
                            "scoreboard": scoreboard},
        "ties": declared_ties(models, champions),
        "totals": {
            "models": len(models),
            "samples": sum(m["n_samples"] for m in models.values()),
            "eligible": sum(m["eligible"] for m in models.values()),
            "top_bot_per_run_pairings": sum(m["top_bot_per_run"]["pairings"] for m in models.values()),
            "top_bot_per_run_games": sum(m["top_bot_per_run"]["games"] for m in models.values()),
            "top5_round_games": sum(m["top5_round"]["n_games"] for m in models.values()),
            "top5_rounds_played": sum(1 for m in models.values() if m["top5_round"]["played"]),
            "champions_round_games": champions["n_games"],
        },
    }


# ── rules ─────────────────────────────────────────────────────────────────────

RULE_KEYS = ("match_time", "inactivity", "n_rollouts", "config", "config_md5", "config_chain", "rules")


def rules_from_run(rr_dir: Path, stage_b_dir: Optional[Path] = None) -> Dict[str, Any]:
    """The match rules every run's pool_ledger.json recorded (they must all agree on everything but the harness
    sha) plus the seed count and match length of the stored rounds (their match length must equal the runs')."""
    rr_dir = Path(rr_dir)
    stage_b_dir = Path(stage_b_dir) if stage_b_dir is not None else rr_dir / "stage_b"
    ref: Optional[Dict[str, Any]] = None
    ref_name = ""
    shas: Dict[str, List[str]] = {}
    for md in _model_dirs(rr_dir):
        model_shas = set()
        for gdir in sorted(p for p in md.iterdir() if p.is_dir() and p.name.startswith("g")):
            ledger = _read(gdir / "pool_ledger.json")
            got = {k: ledger[k] for k in RULE_KEYS}
            if ref is None:
                ref, ref_name = got, f"{md.name}/{gdir.name}"
            elif got != ref:
                diff = sorted(k for k in RULE_KEYS if got[k] != ref[k])
                raise RuntimeError(f"{md.name}/{gdir.name}: match rules differ from {ref_name} in {diff} — one release, one rule set")
            model_shas.add(str(ledger["git_sha"]))
        if not model_shas:
            raise FileNotFoundError(f"{md}: no g<k>/ run directories")
        shas[md.name] = sorted(model_shas)
    assert ref is not None
    b = _read(stage_b_dir / "summary.json")
    top1 = _read(stage_b_dir / "top1" / "elo.json")
    if float(b["match_time"]) != float(ref["match_time"]) or float(top1["match_time"]) != float(ref["match_time"]):
        raise RuntimeError(f"stored rounds' match_time {b['match_time']}/{top1['match_time']} != runs' {ref['match_time']}")
    if int(top1["n_rollouts"]) != int(b["n_rollouts"]):
        raise RuntimeError(f"stage_b/top1/elo.json n_rollouts {top1['n_rollouts']} != stage_b/summary.json {b['n_rollouts']}")
    return {
        "match_time": float(ref["match_time"]),
        "run_seeds": int(ref["n_rollouts"]),
        "stored_seeds": int(b["n_rollouts"]),
        "inactivity": {"timeout_s": float(ref["inactivity"]["timeout_s"]),
                       "min_displacement_m": float(ref["inactivity"]["min_displacement_m"])},
        "score_function": ref["rules"]["score_function"],
        "contact_fidelity": ref["rules"]["contact_fidelity"],
        "physics_mode": ref["rules"]["physics_mode"],
        "arena_xml": ref["rules"]["arena_xml"],
        "constraints": ref["rules"]["constraints"],
        "config": ref["config"],
        "config_md5": ref["config_md5"],
        "config_chain": list(ref["config_chain"]),
        "git_shas": sorted({s for v in shas.values() for s in v}),
        "git_shas_by_model": shas,
        "rating": "Bradley-Terry (mjarena/elo/core.py), draws counted as half a win",
    }


# ── provenance ────────────────────────────────────────────────────────────────

def rr_platform(source_roots: Sequence[str]) -> str:
    keys = set()
    for root in source_roots:
        matches = [key for prefix, key in RR_PLATFORM_BY_SOURCE_ROOT if root.startswith(prefix)]
        if len(matches) != 1:
            raise RuntimeError(f"ledger source root {root!r} matches no known platform (RR_PLATFORM_BY_SOURCE_ROOT)")
        keys.add(matches[0])
    if len(keys) != 1:
        raise RuntimeError(f"one model's runs were played on several platforms: {sorted(keys)} — never mix")
    return keys.pop()


def build_provenance(manifest: Dict[str, Any], summary: Dict[str, Any], rules: Dict[str, Any], *,
                     shas: Sequence[str], champions_platform: str) -> Dict[str, Any]:
    """Per model: where its Qualification Round ran (the pack manifest's `qualified_on`), where its runs and
    Top-5 Round ran (the ledgers' source root), the harness shas its runs record; plus the Champions Round's."""
    if champions_platform not in PLATFORMS:
        raise ValueError(f"unknown champions platform {champions_platform!r}; expected one of {sorted(PLATFORMS)}")
    bad = [s for s in shas if len(s) != 40 or any(c not in "0123456789abcdef" for c in s)]
    if bad:
        raise ValueError(f"--sha takes full 40-hex commit ids (git rev-parse), got {bad}")
    unknown = sorted(set(rules["git_shas"]) - set(shas))
    if unknown:
        raise RuntimeError(f"ledgers record harness sha(s) {unknown} that are not among --sha {list(shas)}")
    per_model = {}
    for model, m in summary["models"].items():
        entry = manifest["models"][model]
        if entry["qualified_on"] not in PLATFORMS:
            raise RuntimeError(f"{model}: pack manifest qualified_on {entry['qualified_on']!r} is not a known platform")
        per_model[model] = {"qualified_on": entry["qualified_on"], "round_robins_on": rr_platform(m["source_roots"]),
                            "git_shas": m["git_shas"], "source_pack": entry["source_manifest"]}
    counts = Counter(p["qualified_on"] for p in per_model.values())
    rr_counts = Counter(p["round_robins_on"] for p in per_model.values())
    return {
        "harness_shas": list(shas),
        "harness_shas_in_ledgers": rules["git_shas"],
        "harness_range_note": HARNESS_RANGE_NOTE,
        "champions_round_on": champions_platform,
        "models": per_model,
        "qualified_on_counts": dict(counts),
        "round_robins_on_counts": dict(rr_counts),
        "platforms": dict(PLATFORMS),
        "gpu_cluster_reports": list(GPU_REPORTS),
    }


# ── forfeit causes ────────────────────────────────────────────────────────────

def build_forfeits(summary: Dict[str, Any], provenance: Dict[str, Any], cause_files: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Per model: forfeit count from the pack/run ledgers, the cause breakdown from the platform's build ledgers
    (`cause_files[<platform>]` = {model: {forfeits, causes}}), whether that breakdown is partial."""
    out: Dict[str, Any] = {}
    for model, m in summary["models"].items():
        ledger_forfeits = sum(n for reason, n in m["exclusions"].items() if reason.startswith("forfeit:"))
        by_stage = {reason.split(":", 1)[1]: n for reason, n in m["exclusions"].items() if reason.startswith("forfeit:")}
        qualified_on = provenance["models"][model]["qualified_on"]
        file_key, partial = FORFEIT_CAUSE_FILE_BY_QUALIFIED_ON[qualified_on]
        if file_key not in cause_files:
            raise RuntimeError(f"{model}: forfeit causes come from the {file_key!r} file, which was not given (--forfeit-causes)")
        rec = cause_files[file_key].get(model)
        causes = dict(rec["causes"]) if rec else {}
        file_forfeits = int(rec["forfeits"]) if rec else 0
        if not partial and file_forfeits != ledger_forfeits:
            raise RuntimeError(f"{model}: {file_key} forfeit-cause file counts {file_forfeits} forfeits, the ledger {ledger_forfeits}")
        note = None
        if model in FORFEIT_CAUSE_NOTES:
            cause, detail, meaning = FORFEIT_CAUSE_NOTES[model]
            if cause not in causes:
                raise RuntimeError(f"{model}: FORFEIT_CAUSE_NOTES names cause {cause!r}, absent from the {file_key} cause file")
            stages = ", ".join(f"\"{s}\"" for s in sorted(by_stage))
            note = (f"its {ledger_forfeits} forfeits are recorded with forfeit_stage {stages}, but {causes[cause]} of them "
                    f"are \"{cause}: {detail}\" — {meaning}")
        out[model] = {"forfeits": ledger_forfeits, "by_stage": by_stage, "causes": causes, "causes_source": file_key,
                      "causes_partial": partial, "causes_cover": file_forfeits, "note": note}
    return out


# ── README.md ─────────────────────────────────────────────────────────────────

def _fmt_elo(x: Optional[float]) -> str:
    return "—" if x is None else f"{x:.1f}"


def _n_samples_text(summary: Dict[str, Any]) -> str:
    counts = sorted({int(m["n_samples"]) for m in summary["models"].values()})
    return str(counts[0]) if len(counts) == 1 else "/".join(map(str, counts))


def _scoreboard_table(summary: Dict[str, Any]) -> List[str]:
    lines = ["| # | model | champion | Champions Round Elo | W-L-D | games |", "|---:|---|---|---:|---:|---:|"]
    for r in summary["champions_round"]["scoreboard"]:
        mark = " †" if len(r["top5_ties_at_top"]) > 1 else ""
        lines.append(f"| {r['rank']} | {r['model']} | `{r['artifact_id']}`{mark} | {r['champions_elo']:.1f} | "
                     f"{_fmt_wld(r['champions_wld'])} | {r['champions_games']} |")
    return lines


def _per_model_table(summary: Dict[str, Any]) -> List[str]:
    lines = ["| model | samples | qualified per run (Σ) | Top Bot per Run Round games | run winners (run rating) | "
             "Top-5 Round (Elo, W-L-D) | champion (Champions Round Elo) |",
             "|---|---:|---|---:|---|---|---|"]
    for model, m in sorted(summary["models"].items()):
        per_run = " / ".join(str(e) for e in m["eligible_per_run"]) + f" ({m['eligible']})"
        winners = "<br>".join(f"{w['group']} `{_short(w['artifact_id'], model)}` {w['run_elo']:.1f}" for w in m["run_winners"])
        if m["top5_round"]["played"]:
            ranked = sorted(m["run_winners"], key=lambda w: (-w["top5_elo"], w["artifact_id"]))
            top5 = "<br>".join(f"`{_short(w['artifact_id'], model)}` {w['top5_elo']:.1f} {_fmt_wld(w['top5_wld'])}" for w in ranked)
            if m["top5_round"]["ties"]:
                top5 += "<br>ties: " + "; ".join(", ".join(f"`{_short(a, model)}`" for a in g) for g in m["top5_round"]["ties"])
        else:
            top5 = f"skipped: {m['top5_round']['skipped']}"
        c = m["champion"]
        champ = f"`{_short(c['artifact_id'], model)}` {c['champions_elo']:.1f} ({_fmt_wld(c['champions_wld'])})"
        if len(c["top5_ties_at_top"]) > 1:
            champ += " †"
        if c["source"] != "Top-5 Round winner":
            champ += f" — {c['source']}"
        lines.append(f"| {model} | {m['n_samples']} | {per_run} | {m['top_bot_per_run']['games']} | {winners} | {top5} | {champ} |")
    return lines


def _platform_table(provenance: Dict[str, Any]) -> List[str]:
    lines = ["| model | Qualification Round | Top Bot per Run Round + Top-5 Round | harness sha(s) of its runs |",
             "|---|---|---|---|"]
    for model, p in sorted(provenance["models"].items()):
        lines.append(f"| {model} | {p['qualified_on']} | {p['round_robins_on']} | " +
                     ", ".join(f"`{s[:8]}`" for s in p["git_shas"]) + " |")
    return lines


def render_readme(manifest: Dict[str, Any], summary: Dict[str, Any], rules: Dict[str, Any], provenance: Dict[str, Any], *,
                  run_id: str, prompt_md5: str, generated_at: str) -> str:
    n = _n_samples_text(summary)
    inact = rules["inactivity"]
    totals = summary["totals"]
    cr = summary["champions_round"]
    date = generated_at[:10]
    n_not_run = len(NOT_RUN)
    L: List[str] = []
    L += [f"# SH-250 pool tournament — `{run_id}`", ""]
    L += [f"This folder is one run of the ArtifactArena zero-shot sampling study: **{n} zero-shot samples per model** "
          f"for {totals['models']} models ({totals['samples']} samples; {n_not_run} further model{'s' if n_not_run != 1 else ''} "
          f"generated samples but played no tournament, see `MISSING.md`), each sample generated once from the same "
          f"**frozen prompt** (`sampling_prompt.md`, md5 `{prompt_md5}`) with no refinement, then built and qualified by "
          f"the harness and played through a four-round tournament whose scoreboard is the Champions Round below. "
          f"Every sample, every match record and every standing in this folder was produced by the scripts named in "
          f"*Provenance*; nothing is hand-edited.", ""]
    L += ["## Selection rule", "",
          "The four rounds, as `scripts/sampling/cluster/README.md` defines them:", ""]
    L += ROUNDS_TABLE
    L += ["", f"Only samples that the harness built and validated, that did not forfeit, and that passed the Qualification "
          f"Round entry rule (no round lost, or more rounds won than lost — looser than the prompt's literal \"must not lose\" "
          f"sentence: a W2 L1 bot is in, W1 D1 L1 is out) are *eligible*; `pool_rr/<model>/g<k>/pool_ledger.json` gives every "
          f"slot's verdict. A run with one eligible bot has that bot as its winner without games; a run with none has no winner, "
          f"so a model can bring fewer than five run winners to its Top-5 Round. A model with a single run winner skips the "
          f"Top-5 Round and that bot is its champion. Ratings are Bradley-Terry with draws counted as half a win; exact "
          f"rating ties are declared, never hidden (`ties_at_top` in every `elo.json` / `top_1.json`, `ties` in the stored "
          f"rounds' `elo.json`).", ""]
    L += [f"Top Bot per Run Round: {totals['top_bot_per_run_pairings']} pairings, {totals['top_bot_per_run_games']} games "
          f"({rules['run_seeds']} seeds each), stored as `match_result.json` only. Top-5 Round: {totals['top5_round_games']} "
          f"games in {totals['top5_rounds_played']} rounds; Champions Round: {cr['n_games']} games among "
          f"{len(cr['participants'])} champions ({rules['stored_seeds']} seeds each) — both with full `match_data.json.gz` "
          f"telemetry.", ""]
    L += ["## Match rules", "", "| rule | value |", "|---|---|",
          f"| match length | {rules['match_time']:.0f} s |",
          f"| Top Bot per Run Round seeds per pairing | {rules['run_seeds']} |",
          f"| Top-5 Round and Champions Round seeds per pairing | {rules['stored_seeds']} |",
          f"| inactivity | {inact['timeout_s']:.0f} s / {inact['min_displacement_m']:.1f} m (a bot whose centre of mass moves less than {inact['min_displacement_m']:.1f} m over any {inact['timeout_s']:.0f} s window loses by inactivity; both stalled: 1 cm centre-of-mass height tiebreak, else a draw) |",
          f"| score function | `{rules['score_function']}` |",
          f"| contact fidelity | `{rules['contact_fidelity']}` |",
          f"| physics | `{rules['physics_mode']}` |",
          f"| arena | `{rules['arena_xml']}` |",
          f"| constraints | `{rules['constraints']}` |",
          f"| rating | {rules['rating']}; exact ties are declared, never hidden |",
          f"| tournament config | `{rules['config']}` (md5 `{rules['config_md5']}`, identical in every ledger) |", ""]
    L += ["## Scoreboard — Champions Round", "",
          f"Every model's champion against every other's, {rules['stored_seeds']} seeds per pairing "
          f"({cr['n_games']} games), Bradley-Terry over those games. `stage_b/top1/elo.json` is the record.", ""]
    L += _scoreboard_table(summary)
    champion_ties = [t for t in summary["ties"] if t["where"] == "top5" and t["decided"] == "champion"]
    if champion_ties:
        L += ["", "† champion by tie-break: " + "; ".join(
            f"{t['model']}'s Top-5 Round ended in an exact tie at the top between " +
            ", ".join(f"`{a}`" for a in t["bots"]) + f" — `{t['chosen']}` entered ({t['tie_break']})" for t in champion_ties) + "."]
    if cr["ties_at_top"]:
        L += ["", "Tie at the top: " + ", ".join(f"`{a}`" for a in cr["ties_at_top"]) + "."]
    if cr["ties"]:
        L += ["", "Rating ties: " + "; ".join(", ".join(f"`{a}`" for a in g) for g in cr["ties"]) + "."]
    if cr["not_entered"]:
        L += ["", "Not in the Champions Round: " + "; ".join(f"{m} ({r})" for m, r in sorted(cr["not_entered"].items())) + "."]
    L += ["", "## Per model", "",
          "Qualified bots per run (five runs of 50 consecutive slots), the Top Bot per Run Round games those runs took, "
          "the five run winners with the Bradley-Terry rating that won them their run (`pool_rr/<model>/g<k>/elo.json`), "
          "their Top-5 Round Elo and W-L-D (`stage_b/top5/<model>/elo.json`), and the champion with its Champions Round "
          "Elo. Bot ids are abbreviated to `tNNN`; the artifact id is `<model>__tNNN_c000`.", ""]
    L += _per_model_table(summary)
    L += ["", "## Declared ties", "",
          "Every exact Bradley-Terry tie the records declare (`ties_at_top` / `ties` in the `elo.json` files), what it "
          "decided and how it was broken. A tie is never hidden by the tie-break.", ""]
    if summary["ties"]:
        for t in summary["ties"]:
            where = {"run": f"{t['model']} run {t['group']}", "top5": f"{t['model']} Top-5 Round",
                     "champions": "Champions Round"}[t["where"]]
            bots = ", ".join(f"`{a}`" for a in t["bots"])
            chosen = f" — `{t['chosen']}` chosen by {t['tie_break']}" if t["chosen"] else ""
            L.append(f"- {where}: {bots} tied; decides: {t['decided']}{chosen}.")
    else:
        L.append("- none.")
    L += ["", "## Provenance", "", "| item | value |", "|---|---|",
          f"| run id | `{run_id}` |",
          f"| harness commits the games were played from | " + ", ".join(f"`{s[:8]}`" for s in provenance["harness_shas"]) + " |",
          f"| harness commits recorded by the run ledgers | " + ", ".join(f"`{s[:8]}`" for s in provenance["harness_shas_in_ledgers"]) + " |",
          f"| frozen prompt md5 | `{prompt_md5}` (`sampling_prompt.md`) |"]
    for c in rules["config_chain"]:
        L.append(f"| config md5 `{c['path']}` | `{c['md5']}` |")
    L += [f"| samples packed | " + "; ".join(f"`{Path(s['manifest']).parent.name}` at {s['packed_at']} (sha `{s['git_sha'][:8]}`, "
                                           f"qualified on {s['qualified_on']}: {', '.join(s['models'])})" for s in manifest["sources"]) + " |",
          f"| Champions Round played on | {provenance['champions_round_on']} |",
          f"| release generated at | {generated_at} |",
          "| scripts | `scripts/sampling/run_pool.py` (generation + Qualification Round) → `pack_pool.py` → `pool_rr.py` "
          "(Top Bot per Run Round) → `verify_pool_rr.py` → `pool_finals.py` (Top-5 Round, Champions Round) → "
          "`merge_pack_manifests.py` → `release_readme.py` → `publish_pool_laptop.sh` |", ""]
    L += [provenance["harness_range_note"], ""]
    L += ["Platforms: " + "; ".join(f"**{k}** = {v}" for k, v in provenance["platforms"].items()) + ". "
          "A model's Qualification Round ran entirely on one platform and its five runs and Top-5 Round entirely on one "
          "platform (never mixed: the same input gives the same winners but different step counts on macOS arm64 vs "
          "x86-64 Linux). " +
          ", ".join(f"{n} model{'s' if n != 1 else ''} qualified on {k}" for k, n in sorted(provenance["qualified_on_counts"].items())) +
          "; " + ", ".join(f"{n} model{'s' if n != 1 else ''} played their round robins on {k}" for k, n in sorted(provenance["round_robins_on_counts"].items())) +
          f"; the Champions Round ran on {provenance['champions_round_on']}.", ""]
    L += _platform_table(provenance)
    L += ["", "The round robins played on the GPU cluster are documented in the recovery report and provenance bundle: " +
          ", ".join(f"`{p}`" for p in provenance["gpu_cluster_reports"]) + " (per-model verification JSONs, scheduler scripts, seed-equivalence checks).", ""]
    L += ["## Artifact ids", "",
          "A bot is `<model>__tNNN_c000`: the tournament index `tNNN` is the sample index (zero-padded to at least two "
          "digits, so `t07` for sample 7 and `t123` for sample 123) and the commit index is always `c000` (one commit "
          "per zero-shot sample). It maps to `samples/<model>/cNNN` (always three digits): "
          "`gpt-5.5__t30_c000` ↔ `samples/gpt-5.5/c030`, whose `commit_0/robot.xml` and `commit_0/controller.py` are "
          "the files the matches loaded. Run `g<k>` holds slots `c<50k>`…`c<50k+49>`.", ""]
    L += ["## Layout", "", "```",
          "README.md                      this file",
          "MISSING.md                     what is absent and why",
          "MANIFEST.json                  md5 + byte size of every object in this folder (written last)",
          "pack-MANIFEST.json             the merged pack manifest: per-model sample ledger (why each sample did or did not",
          "                               enter), which pack qualified it where, md5 of every samples/ file",
          "sampling_prompt.md             the frozen prompt",
          "samples/<model>/cNNN/          gen.json, raw_response_*.txt, raw_reasoning_*.txt, bot_artifact.json, robot.xml,",
          "                               controller.py, journal.json, usage.jsonl, commit_0/{robot.xml,controller.py,prompt.txt},",
          "                               qualification/match_result.json          (Qualification Round result)",
          "pool_rr/<model>/runs.json top_5_bots.json VERIFIED                  the five run winners",
          "pool_rr/<model>/g<k>/pool_ledger.json elo.json top_1.json top_5_bots.json    one run: ledger, BT standings, winner",
          "pool_rr/<model>/g<k>/matches/<a>_vs_<b>/match_result.json          Top Bot per Run Round, one per eligible pair",
          "stage_b/top5/<model>/elo.json | SKIPPED.json, VERIFIED               Top-5 Round standings",
          "stage_b/top5/<model>/matches/<a>_vs_<b>/{match_result.json, match_data.json.gz}",
          "stage_b/top1/elo.json skipped.json VERIFIED                          Champions Round standings (the scoreboard)",
          "stage_b/top1/matches/<a>_vs_<b>/{match_result.json, match_data.json.gz}",
          "stage_b/summary.json           pool_finals.py's own summary of its last invocation (its top5 section covers only the",
          "                               models of that invocation; the per-model stage_b/top5/<model>/ files are complete)",
          "verify/<model>.g<k>.verify.txt <model>.top5.verify.txt champions.verify.txt   verify_pool_rr.py reports",
          "standings/summary.json         everything above as one JSON: rules, provenance, per model, scoreboard, forfeits",
          "```", ""]
    L += ["## Changelog", "",
          f"- {date} — SH-250 pool tournament `{run_id}`: {totals['models']} models × {n} zero-shot samples; Top Bot per Run "
          f"Round ({totals['top_bot_per_run_games']} games, {rules['run_seeds']} seeds, {rules['match_time']:.0f} s, "
          f"Bradley-Terry), Top-5 Round and Champions Round at {rules['stored_seeds']} seeds with telemetry; harness "
          + "/".join(s[:8] for s in provenance["harness_shas"]) + f"; published to `{BUCKET_PREFIX}/{run_id}/`.", ""]
    return "\n".join(L)


# ── MISSING.md ────────────────────────────────────────────────────────────────

def _forfeit_stages(*exclusion_maps: Dict[str, int]) -> List[str]:
    seen = {k.split(":", 1)[1] for ex in exclusion_maps for k in ex if k.startswith("forfeit:")}
    return [s for s in FORFEIT_STAGE_ORDER if s in seen] + sorted(seen - set(FORFEIT_STAGE_ORDER))


def count_generated(gen_root: Path, model: str) -> int:
    """Samples the sampler produced for a model that never entered a pack: `<gen_root>/<model>/cNNN/gen.json`."""
    d = Path(gen_root) / model
    if not d.is_dir():
        raise FileNotFoundError(f"{d} is missing — cannot count {model}'s generated samples")
    return sum(1 for p in d.glob("c*/gen.json") if p.is_file())


def build_missing(manifest: Dict[str, Any], summary: Dict[str, Any], gen_root: Optional[Path]) -> Dict[str, Any]:
    """Models with no tournament (declared in NOT_RUN, generated count from the sampling root or the pack)."""
    models_run = summary["models"]
    packed = manifest["models"]
    for model in models_run:
        if model not in packed:
            raise RuntimeError(f"{model} has a round robin but is not in the pack manifest")
    not_run: Dict[str, Dict[str, Any]] = {}
    for model, entry in sorted(packed.items()):
        if model in models_run:
            continue
        if model not in NOT_RUN:
            raise RuntimeError(f"{model} is in the pack but has no round robin and no declared reason — "
                               f"add it to release_readme.NOT_RUN or run its round robin")
        not_run[model] = {"generated": sum(1 for r in entry["ledger"] if r["generated"]), "packed": True,
                          "reason": NOT_RUN[model]}
    for model, reason in sorted(NOT_RUN.items()):
        if model in models_run:
            raise RuntimeError(f"{model} is declared NOT_RUN but has a round robin")
        if model in not_run:
            continue
        if gen_root is None:
            raise RuntimeError(f"{model} is declared NOT_RUN and is not packed: --gen-root is needed to count its samples")
        not_run[model] = {"generated": count_generated(gen_root, model), "packed": False, "reason": reason}
    return not_run


def render_missing(summary: Dict[str, Any], forfeits: Dict[str, Any], not_run: Dict[str, Dict[str, Any]]) -> str:
    models_run = summary["models"]
    L: List[str] = ["# What is missing from this release, and why", ""]

    L += ["## Models without a tournament", ""]
    for model, info in sorted(not_run.items()):
        where = (f"Its samples are in `samples/{model}/`" if info["packed"]
                 else "Its samples are not in `samples/` (the pack holds the tournament models only)")
        L.append(f"- {model}: {info['generated']} samples generated, tournament not run ({info['reason']}). {where}; it has "
                 f"no `pool_rr/{model}/`, no run winners, no Top-5 Round and no champion in the Champions Round.")
    if not not_run:
        L.append("- none: every model with samples played its tournament.")
    L.append("")

    stages = _forfeit_stages(*(m["exclusions"] for m in models_run.values()))
    cols = list(PLAIN_REASONS[:2]) + [f"forfeit:{s}" for s in stages] + list(PLAIN_REASONS[2:])
    L += ["## Samples that did not enter the Top Bot per Run Round", "",
          "One row per model, samples by ledger reason (`pool_rr/<model>/g<k>/pool_ledger.json`, five runs summed). "
          "`not generated`: the sampler produced no response for that slot. `not qualified yet`: generated, never "
          "qualified. `forfeit:<stage>`: the harness rejected the sample at that build stage (see the cause table below — "
          "the stage label is the harness's, not always the true cause). `validation failed`: the bot compiled but "
          "failed the rules check. `qualification failed`: it lost the Qualification Round entry rule. Only `eligible` "
          "samples entered.", "",
          "| model | samples | eligible | " + " | ".join(cols) + " |",
          "|---|---:|---:|" + "---:|" * len(cols)]
    for model, m in sorted(models_run.items()):
        ex = m["exclusions"]
        unknown = sorted(set(ex) - set(cols))
        if unknown:
            raise RuntimeError(f"{model}: ledger reasons {unknown} have no column")
        L.append(f"| {model} | {m['n_samples']} | {m['eligible']} | " + " | ".join(str(ex.get(c, 0)) for c in cols) + " |")
    L.append("")

    L += ["## Forfeit causes", "",
          "Forfeit counts are the ledgers' (`forfeit:<stage>` above). The cause breakdown is read off the build ledgers "
          "(`design_ledger.txt`, the FAIL reason of the build) on the platform that ran the model's Qualification Round; "
          "for models qualified on the GPU cluster only the laptop's **partial** build of the same samples is available, "
          "so its breakdown covers fewer forfeits than the ledger counts.", "",
          "| model | forfeits | harness forfeit_stage | causes | source of the causes |", "|---|---:|---|---|---|"]
    for model, f in sorted(forfeits.items()):
        causes = "; ".join(f"{c} {n}" for c, n in sorted(f["causes"].items(), key=lambda kv: (-kv[1], kv[0]))) or "—"
        src = f["causes_source"] + (f" (partial build: {f['causes_cover']} of {f['forfeits']} covered)" if f["causes_partial"] else "")
        stage = ", ".join(f"{s} {n}" for s, n in sorted(f["by_stage"].items())) or "—"
        L.append(f"| {model} | {f['forfeits']} | {stage} | {causes} | {src if f['forfeits'] else '—'} |")
    notes = [(m, f["note"]) for m, f in sorted(forfeits.items()) if f["note"]]
    if notes:
        L.append("")
        for model, note in notes:
            L.append(f"- {model}: {note}.")
    L.append("")

    L += ["## Runs with fewer than two qualified bots", "",
          "A run with one eligible bot has no round robin: that bot is the run's winner by default (rating 1000.0, no "
          "games). A run with no eligible bot has no winner, so the model brings fewer than five bots to its Top-5 Round.", ""]
    rows = []
    for model, m in sorted(models_run.items()):
        for r in m["runs"]:
            if not r["round_robin"]:
                what = "no eligible bot — no winner" if r["eligible"] == 0 else f"one eligible bot — `{r['winner']['artifact_id']}` wins by default"
                rows.append(f"- {model} {r['group']} (slots {r['slot_range'][0]}–{r['slot_range'][1] - 1}): {what}.")
    L += rows or ["- none."]
    L.append("")

    L += ["## Top-5 Round skipped", ""]
    skipped = [(m, s["top5_round"]["skipped"], s["champion"]["artifact_id"]) for m, s in sorted(models_run.items()) if not s["top5_round"]["played"]]
    L += [f"- {m}: {reason}; `{aid}` is the model's champion by default and entered the Champions Round with it."
          for m, reason, aid in skipped] or ["- none: every model played its Top-5 Round."]
    L.append("")

    L += ["## Champions Round", ""]
    cr = summary["champions_round"]
    entries = [f"- {m}: {reason}." for m, reason in sorted(cr["not_entered"].items())]
    entries += [f"- {m}: tournament not run ({info['reason']})." for m, info in sorted(not_run.items())]
    L += entries or ["- every model's champion played every other."]
    L.append("")

    totals = summary["totals"]
    L += ["## Telemetry not stored", "",
          f"Top Bot per Run Round `match_data.json` is **not stored** — why: size. Its {totals['top_bot_per_run_games']} games "
          f"at 300 s would be terabytes of telemetry; only `match_result.json` per pairing (winner, steps, termination reason "
          f"and combat metrics per seed) is kept, and the Bradley-Terry standings are re-derived from those records by "
          f"`verify_pool_rr.py` (`verify/`). The Top-5 Round ({totals['top5_round_games']} games) and the Champions Round "
          f"({totals['champions_round_games']} games) carry full telemetry as `match_data.json.gz`. The Qualification Round's "
          f"per-sample `match_data.json.gz` and the composed arena XMLs were not packed (`samples/<model>/cNNN/qualification/"
          f"match_result.json` holds the result). No videos are stored anywhere in this release.", ""]
    return "\n".join(L)


# ── entry point ───────────────────────────────────────────────────────────────

def _parse_cause_files(specs: Sequence[str]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for spec in specs:
        if "=" not in spec:
            raise ValueError(f"--forfeit-causes expects <platform>=<json>, got {spec!r}")
        key, path = spec.split("=", 1)
        if key not in PLATFORMS:
            raise ValueError(f"--forfeit-causes {spec!r}: unknown platform {key!r}")
        out[key] = _read(Path(path))
    return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--release", type=Path, required=True, help="release folder (README.md, MISSING.md, standings/ are written here)")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--sha", action="append", default=[], required=True,
                    help="a harness sha the games were played from (repeatable); every ledger sha must be among them")
    ap.add_argument("--champions-platform", required=True, choices=sorted(PLATFORMS), help="where the Champions Round ran")
    ap.add_argument("--forfeit-causes", action="append", default=[], metavar="PLATFORM=JSON",
                    help="forfeit-cause file of a platform's build ledgers ({model: {forfeits, causes}}), repeatable")
    ap.add_argument("--gen-root", type=Path, default=None, help="sampling run root, to count the samples of models that were never packed")
    ap.add_argument("--rr", type=Path, default=None, help="round-robin root (default <release>/pool_rr)")
    ap.add_argument("--stage-b", type=Path, default=None, help="stored-rounds root (default <release>/stage_b)")
    ap.add_argument("--pack-manifest", type=Path, default=None, help="merged pack manifest (default <release>/pack-MANIFEST.json)")
    args = ap.parse_args(argv)

    release: Path = args.release
    rr = args.rr if args.rr is not None else release / "pool_rr"
    stage_b = args.stage_b if args.stage_b is not None else release / "stage_b"
    manifest_path = args.pack_manifest if args.pack_manifest is not None else release / "pack-MANIFEST.json"
    manifest = _read(manifest_path)

    prompt_path = release / "sampling_prompt.md"
    if not prompt_path.is_file():
        sys.exit(f"refusing: {prompt_path} is missing (the frozen prompt belongs in the release)")
    prompt_md5 = _md5(prompt_path)
    if prompt_md5 != manifest["prompt_md5"]:
        sys.exit(f"refusing: {prompt_path} md5 {prompt_md5} != pack manifest prompt_md5 {manifest['prompt_md5']}")

    try:
        cause_files = _parse_cause_files(args.forfeit_causes)
        rules = rules_from_run(rr, stage_b)
        summary = build_summary(rr, stage_b)
        provenance = build_provenance(manifest, summary, rules, shas=args.sha, champions_platform=args.champions_platform)
        forfeits = build_forfeits(summary, provenance, cause_files)
        not_run = build_missing(manifest, summary, args.gen_root)
    except (RuntimeError, ValueError, FileNotFoundError) as e:
        sys.exit(f"refusing: {e}")
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    readme = render_readme(manifest, summary, rules, provenance, run_id=args.run_id, prompt_md5=prompt_md5, generated_at=generated_at)
    missing = render_missing(summary, forfeits, not_run)
    (release / "README.md").write_text(readme)
    (release / "MISSING.md").write_text(missing)
    (release / "standings").mkdir(parents=True, exist_ok=True)
    payload = {"run_id": args.run_id, "prompt_md5": prompt_md5, "generated_at": generated_at,
               "rounds": list(ROUND_NAMES), "rules": rules, "provenance": provenance, **summary,
               "forfeits": forfeits, "not_run": not_run}
    (release / "standings/summary.json").write_text(json.dumps(payload, indent=2))
    print(f"wrote {release / 'README.md'}, {release / 'MISSING.md'}, {release / 'standings/summary.json'} "
          f"({summary['totals']['models']} models, {summary['totals']['top_bot_per_run_games']} Top Bot per Run Round games, "
          f"{summary['champions_round']['n_games']} Champions Round games)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
