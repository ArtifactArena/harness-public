#!/usr/bin/env python3
"""Verify a finished SH-250 pool round robin: complete, protocol-clean, standings re-derived.

Stage A (`--model M`): `<out>/M/` as written by pool_rr.py.
  1. pool_ledger.json exists; its `eligible` count equals the eligible ledger rows; `matches/`
     holds exactly one match_result.json per unordered eligible pair — no extra, duplicate,
     mislabelled or baseline pairings.
  2. every match_result.json has n_seeds == n_rollouts games, each with winner in
     {red, blue, tie}, 0 < num_steps <= round(match_time / 0.01), a non-empty
     termination_reason; physics_unstable may be true (the engine rules the unstable bot the loser).
  3. elo.json equals `compute_standings` over the records (1e-9 on ratings, exact W/L/D/G);
     top_5_bots.json is the ranked head of that recomputation and top_1.json its argmax,
     with every rating tie declared.
  4. nothing under `<out>/M/` is telemetry or video (match_data.json[.gz], *.mp4, *.webm).

Stage B (`--stage b1 M` / `--stage b2` / `--stage b3 g<k>`): the stored round robins under `<out>/stage_b/`.
  Same pairing / per-game / standings checks with the participants taken from Stage A's
  top_5_bots.json (B1) or every model's top_1.json (B2); every pairing additionally needs a
  match_data.json.gz that gunzips to one record per seed whose num_steps and winner match
  match_result.json; no raw match_data.json, no video.

Exit 1 on any violation. Never imports pool_ledger / pool_rr: it judges their output only.
"""
from __future__ import annotations

import argparse
import gzip
import itertools
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mjarena.elo.core import MatchOutcome, compute_standings  # noqa: E402
from mjarena.two_stage.artifact_loader import make_artifact_id  # noqa: E402

# One env step at contact_fidelity "high" (SumoEnv.HIGH_FIDELITY_CONTACT control_timestep,
# apply_n_repeated_actions 1); Match resolves max_steps = round(match_time / frame_timestep).
CONTROL_DT = 0.01
WINNER_TOKENS = ("red", "blue", "tie")   # GameRecord.winner; a draw is "tie" in the harness
RATING_TOL = 1e-9
VIDEO_SUFFIXES = (".mp4", ".webm")
Standings = Dict[str, Dict[str, Any]]


def step_cap(match_time: float) -> int:
    return int(round(float(match_time) / CONTROL_DT))


# ── helpers ───────────────────────────────────────────────────────────────────

def _load_json(path: Path, violations: List[str]) -> Optional[Any]:
    if not path.is_file():
        violations.append(f"{path} missing")
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        violations.append(f"{path} unreadable: {exc}")
        return None


def _outcomes(records: Iterable[Dict[str, Any]]) -> List[MatchOutcome]:
    """Same derivation as mjarena.two_stage.intra_model._read_match_outcomes: red_bot/blue_bot
    are fixed for every seed of a pairing (seed parity only swaps spawn positions)."""
    out: List[MatchOutcome] = []
    for data in records:
        red, blue = data["red_bot"], data["blue_bot"]
        for m in data["matches"]:
            w = m["winner"]
            winner = red if w == "red" else blue if w == "blue" else "draw"
            out.append(MatchOutcome(player_a=red, player_b=blue, winner=winner))
    return out


def _is_baseline(artifact_id: str) -> bool:
    return artifact_id.startswith("baseline")


def _check_games(label: str, data: Dict[str, Any], n_rollouts: int, cap: int, violations: List[str]) -> None:
    n_seeds = data.get("n_seeds")
    if n_seeds != n_rollouts:
        violations.append(f"{label}: n_seeds {n_seeds!r} != {n_rollouts}")
    games = data.get("matches")
    if not isinstance(games, list):
        violations.append(f"{label}: no 'matches' list")
        return
    if len(games) != n_seeds:
        violations.append(f"{label}: {len(games)} games but n_seeds {n_seeds}")
    seeds = [g.get("seed") for g in games]
    if len(set(seeds)) != len(seeds):
        violations.append(f"{label}: repeated seeds {seeds}")
    for g in games:
        tag = f"{label} seed {g.get('seed')}"
        if g.get("winner") not in WINNER_TOKENS:
            violations.append(f"{tag}: winner {g.get('winner')!r} not in {'/'.join(WINNER_TOKENS)}")
        steps = g.get("num_steps")
        if not isinstance(steps, int) or isinstance(steps, bool) or steps <= 0:
            violations.append(f"{tag}: num_steps {steps!r} is not a positive int")
        elif steps > cap:
            violations.append(f"{tag}: num_steps {steps} > {cap}")
        reason = g.get("termination_reason")
        if not isinstance(reason, str) or not reason:
            violations.append(f"{tag}: termination_reason {reason!r} empty")
        # A physics-unstable game is a ruled outcome, not a broken record: the engine makes the bot
        # that owns the unstable DOF lose (sumo.py _qacc_loser), and the winner token above must hold.
        # It is only a violation when the flag is not a bool at all.
        if not isinstance(g.get("physics_unstable"), bool):
            violations.append(f"{tag}: physics_unstable {g.get('physics_unstable')!r} is not a bool")


def _check_pairings(
    matches_dir: Path,
    participants: Sequence[str],
    n_rollouts: int,
    match_time: float,
    violations: List[str],
    expected_pairs: Optional[Sequence[Sequence[str]]] = None,
    allow_baselines: bool = False,
) -> Tuple[List[Tuple[Path, Dict[str, Any]]], bool]:
    """Every unordered pair of `participants` exactly once, nothing else — or, with `expected_pairs`,
    exactly that explicit pairing list (Field Round). Returns the loaded records and whether the
    pairing set was exactly right (standings are only meaningful then)."""
    before = len(violations)
    expected = None if expected_pairs is None else {frozenset(pq) for pq in expected_pairs}
    records: List[Tuple[Path, Dict[str, Any]]] = []
    if len(participants) < 2:
        # 0 or 1 eligible bot: no pairing exists, so no matches dir is written — that is correct, not missing
        stray = [p for p in matches_dir.iterdir() if p.is_dir()] if matches_dir.is_dir() else []
        if stray:
            violations.append(f"{matches_dir}: {len(stray)} pairing dir(s) but only {len(participants)} eligible bot(s)")
        return records, not stray
    if not matches_dir.is_dir():
        violations.append(f"{matches_dir} missing")
        return records, False
    allowed = set(participants)
    cap = step_cap(match_time)
    seen: Dict[frozenset, str] = {}
    for d in sorted(p for p in matches_dir.iterdir() if p.is_dir()):
        data = _load_json(d / "match_result.json", violations)
        if data is None:
            continue
        red, blue = data.get("red_bot"), data.get("blue_bot")
        if not isinstance(red, str) or not isinstance(blue, str) or not red or not blue:
            violations.append(f"{d.name}: red_bot/blue_bot {red!r}/{blue!r}")
            continue
        if d.name != f"{red}_vs_{blue}":
            violations.append(f"{d.name}: directory name does not match participants {red} vs {blue}")
        if red == blue:
            violations.append(f"{d.name}: a bot paired with itself")
        for who in (red, blue):
            if _is_baseline(who) and not allow_baselines:
                violations.append(f"{d.name}: baseline bot {who} in the round robin")
            elif who not in allowed:
                violations.append(f"{d.name}: {who} not eligible (unexpected participant)")
        key = frozenset((red, blue))
        if key in seen:
            violations.append(f"{d.name}: duplicate pairing of {seen[key]}")
        else:
            seen[key] = d.name
        if expected is not None and key not in expected:
            violations.append(f"{d.name}: pairing not in the expected list")
        _check_games(d.name, data, n_rollouts, cap, violations)
        records.append((d, data))
    wanted = expected if expected is not None else {frozenset(pq) for pq in itertools.combinations(sorted(allowed), 2)}
    for key in sorted(wanted, key=lambda k: sorted(k)):
        if key not in seen:
            a, b = sorted(key)
            violations.append(f"missing pairing {a} vs {b}")
    pairing_ok = len(violations) == before
    return records, pairing_ok


def _ranked(standings: Standings) -> List[Tuple[str, Dict[str, Any]]]:
    return sorted(standings.items(), key=lambda kv: (-kv[1]["elo"], kv[0]))


def _top_set(standings: Standings) -> List[str]:
    top = max(s["elo"] for s in standings.values())
    return sorted(a for a, s in standings.items() if abs(s["elo"] - top) <= RATING_TOL)


def _check_standings_file(
    path: Path, standings: Standings, n_rollouts: int, violations: List[str], *, model: Optional[str]
) -> Optional[Dict[str, Any]]:
    elo = _load_json(path, violations)
    if elo is None:
        return None
    if model is not None and elo.get("model") != model:
        violations.append(f"{path.name}: model {elo.get('model')!r} != {model!r}")
    if elo.get("method") != "bt":
        violations.append(f"{path.name}: method {elo.get('method')!r} != 'bt'")
    if elo.get("n_rollouts") != n_rollouts:
        violations.append(f"{path.name}: n_rollouts {elo.get('n_rollouts')!r} != {n_rollouts}")
    filed = elo.get("standings")
    diffs: List[str] = []
    if not isinstance(filed, dict):
        diffs.append("no 'standings' dict")
    else:
        if set(filed) != set(standings):
            diffs.append(f"bots {sorted(set(filed) ^ set(standings))} differ")
        for aid in sorted(set(filed) & set(standings)):
            f, r = filed[aid], standings[aid]
            if abs(float(f["elo"]) - r["elo"]) > RATING_TOL:
                diffs.append(f"{aid} elo {f['elo']} vs {r['elo']}")
            for k in ("wins", "losses", "draws", "games"):
                if f.get(k) != r[k]:
                    diffs.append(f"{aid} {k} {f.get(k)!r} vs {r[k]}")
    if diffs:
        violations.append(f"{path.name} standings differ from recomputation: " + "; ".join(diffs[:6]))
    return elo


def _check_ties_declared(label: str, declared: Any, standings: Standings, argmax: str, violations: List[str]) -> None:
    top_set = _top_set(standings)
    if not isinstance(declared, list):
        violations.append(f"{label}: ties_at_top {declared!r} is not a list")
        return
    # The top bot itself may or may not be listed among its ties; everyone else at the top rating must be.
    declared_set = set(declared) | ({argmax} if argmax in top_set else set())
    if declared_set != set(top_set):
        violations.append(f"{label}: ties_at_top {sorted(declared)} != bots at the top rating {top_set}")


def _check_top1(path: Path, standings: Standings, model: str, violations: List[str]) -> None:
    top1 = _load_json(path, violations)
    if top1 is None:
        return
    ranked = _ranked(standings)
    best_id, best = ranked[0]
    aid = top1.get("artifact_id")
    if aid not in standings or abs(standings[aid]["elo"] - best["elo"]) > RATING_TOL:
        violations.append(f"{path.name}: artifact_id {aid!r} is not the argmax ({best_id} at {best['elo']:.6f})")
    else:
        st = standings[aid]
        if abs(float(top1.get("elo", float("nan"))) - st["elo"]) > RATING_TOL:
            violations.append(f"{path.name}: elo {top1.get('elo')!r} != {st['elo']}")
        for k in ("wins", "losses", "draws", "games"):
            if top1.get(k) != st[k]:
                violations.append(f"{path.name}: {k} {top1.get(k)!r} != {st[k]}")
        if not isinstance(top1.get("tournament_idx"), int) or make_artifact_id(model, top1["tournament_idx"], 0) != aid:
            violations.append(f"{path.name}: tournament_idx {top1.get('tournament_idx')!r} does not match {aid}")
    if top1.get("model") != model:
        violations.append(f"{path.name}: model {top1.get('model')!r} != {model!r}")
    _check_ties_declared(path.name, top1.get("ties_at_top"), standings, aid if isinstance(aid, str) else "", violations)


def _check_top5(path: Path, standings: Standings, model: str, violations: List[str]) -> None:
    top5 = _load_json(path, violations)
    if top5 is None:
        return
    rows = top5.get("bots")
    if not isinstance(rows, list):
        violations.append(f"{path.name}: no 'bots' list")
        return
    if top5.get("model") != model:
        violations.append(f"{path.name}: model {top5.get('model')!r} != {model!r}")
    k = int(top5.get("k", 5))
    expect_n = min(k, len(standings))
    if len(rows) != expect_n:
        violations.append(f"{path.name}: {len(rows)} bots listed, expected {expect_n} (k={k}, {len(standings)} rated)")
    listed: List[str] = []
    for i, row in enumerate(rows, start=1):
        aid = row.get("artifact_id")
        tag = f"{path.name} rank {i}"
        if row.get("rank") != i:
            violations.append(f"{tag}: rank field {row.get('rank')!r}")
        if aid not in standings:
            violations.append(f"{tag}: {aid!r} is not in the standings")
            continue
        listed.append(aid)
        st = standings[aid]
        if abs(float(row.get("intra_model_elo", float("nan"))) - st["elo"]) > RATING_TOL:
            violations.append(f"{tag}: intra_model_elo {row.get('intra_model_elo')!r} != {st['elo']}")
        wld = row.get("intra_model_wld") or {}
        if any(wld.get(f) != st[f] for f in ("wins", "losses", "draws")):
            violations.append(f"{tag}: intra_model_wld {wld!r} != {({f: st[f] for f in ('wins', 'losses', 'draws')})}")
        if row.get("model") != model:
            violations.append(f"{tag}: model {row.get('model')!r} != {model!r}")
        if row.get("tournament_idx") is None or make_artifact_id(model, int(row["tournament_idx"]), 0) != aid:
            violations.append(f"{tag}: tournament_idx {row.get('tournament_idx')!r} does not match {aid}")
    if len(set(listed)) != len(listed):
        violations.append(f"{path.name}: repeated artifact ids")
    for prev, cur in zip(listed, listed[1:]):
        if standings[cur]["elo"] - standings[prev]["elo"] > RATING_TOL:
            violations.append(f"{path.name}: {cur} ranked below {prev} but rated higher")
    unlisted = [a for a in standings if a not in set(listed)]
    if listed and unlisted:
        floor = min(standings[a]["elo"] for a in listed)
        best_out = max(unlisted, key=lambda a: standings[a]["elo"])
        if standings[best_out]["elo"] - floor > RATING_TOL:
            violations.append(f"{path.name}: {best_out} ({standings[best_out]['elo']:.6f}) is unlisted but outranks a listed bot ({floor:.6f})")
        elif abs(standings[best_out]["elo"] - floor) <= RATING_TOL:
            # pool_rr declares this in source.ties_at_cut: every bot (listed or not) at the cut rating.
            tied = sorted(a for a in standings if abs(standings[a]["elo"] - floor) <= RATING_TOL)
            source = top5.get("source")
            declared = source.get("ties_at_cut") if isinstance(source, dict) else None
            if declared is None:
                violations.append(f"{path.name}: tie at the top-{k} cut between {tied} — the cut is arbitrary and undeclared (no source.ties_at_cut)")
            elif not isinstance(declared, list) or sorted(declared) != tied:
                violations.append(f"{path.name}: tie at the top-{k} cut: source.ties_at_cut {declared!r} != {tied}")


def _forbidden_files(root: Path, names: Sequence[str], suffixes: Sequence[str]) -> List[Path]:
    hits = [p for p in root.rglob("*") if p.is_file() and (p.name in names or p.suffix in suffixes)]
    return sorted(hits)


# ── stage A ───────────────────────────────────────────────────────────────────

def eligible_ids_from_ledger(ledger: Dict[str, Any], model: str, violations: List[str]) -> List[str]:
    rows = ledger.get("ledger")
    if not isinstance(rows, list):
        violations.append("pool_ledger.json: no 'ledger' rows")
        return []
    ids = [make_artifact_id(model, int(r["idx"]), 0) for r in rows if r.get("eligible") is True]
    if len(set(ids)) != len(ids):
        violations.append("pool_ledger.json: repeated ledger idx")
    if ledger.get("eligible") != len(ids):
        violations.append(f"pool_ledger.json: eligible {ledger.get('eligible')!r} != {len(ids)} eligible ledger rows")
    return sorted(set(ids))


def verify(out: Path, model: str, *, n_rollouts: int, match_time: float, group: Optional[int] = None) -> List[str]:
    """Violations for `<out>/<model>/` (Stage A), or for `<out>/<model>/g<group>/` (one run of a
    grouped Stage A). Empty list = clean."""
    violations: List[str] = []
    out = Path(out)
    model_dir = out / model / f"g{group}" if group is not None else out / model
    if not model_dir.is_dir():
        return [f"{model_dir} missing"]
    ledger = _load_json(model_dir / "pool_ledger.json", violations)
    if ledger is None:
        return violations
    if ledger.get("model") != model:
        violations.append(f"pool_ledger.json model {ledger.get('model')!r} != {model!r}")
    if ledger.get("n_rollouts") != n_rollouts:
        violations.append(f"pool_ledger.json n_rollouts {ledger.get('n_rollouts')!r} != {n_rollouts}")
    if not isinstance(ledger.get("match_time"), (int, float)) or abs(float(ledger["match_time"]) - float(match_time)) > 1e-9:
        violations.append(f"pool_ledger.json match_time {ledger.get('match_time')!r} != {match_time}")
    participants = eligible_ids_from_ledger(ledger, model, violations)

    records, pairing_ok = _check_pairings(model_dir / "matches", participants, n_rollouts, match_time, violations)

    if pairing_ok and records:
        standings = compute_standings(_outcomes(data for _, data in records))
        _check_standings_file(model_dir / "elo.json", standings, n_rollouts, violations, model=model)
        _check_top5(model_dir / "top_5_bots.json", standings, model, violations)
        _check_top1(model_dir / "top_1.json", standings, model, violations)
    elif pairing_ok and len(participants) < 2:
        # degenerate run: elo.json must list the (at most one) bot with 0 games; top_1.json only if there is a bot
        elo = _load_json(model_dir / "elo.json", violations)
        if elo is not None:
            st = elo.get("standings") if isinstance(elo, dict) else None
            if not isinstance(st, dict) or set(st) != set(participants):
                violations.append(f"elo.json standings {sorted(st) if isinstance(st, dict) else st!r} != eligible {participants}")
            elif any(int(v.get("games", -1)) != 0 for v in st.values()):
                violations.append("elo.json: games != 0 for a run with no pairings")
        top1 = model_dir / "top_1.json"
        if participants and not top1.is_file():
            violations.append("top_1.json missing for a one-bot run")
        if not participants and top1.is_file():
            violations.append("top_1.json present for a run with no eligible bot")

    for p in _forbidden_files(model_dir, ("match_data.json", "match_data.json.gz"), VIDEO_SUFFIXES):
        violations.append(f"forbidden telemetry/video file {p.relative_to(model_dir)}")
    return violations


# ── stage B ───────────────────────────────────────────────────────────────────

def _check_stored_telemetry(pair_dir: Path, data: Dict[str, Any], violations: List[str]) -> None:
    gz = pair_dir / "match_data.json.gz"
    if (pair_dir / "match_data.json").exists():
        violations.append(f"{pair_dir.name}: raw match_data.json present (not gzipped)")
    if not gz.is_file():
        violations.append(f"{pair_dir.name}: match_data.json.gz missing")
        return
    try:
        with gzip.open(gz, "rb") as f:
            telemetry = json.loads(f.read().decode("utf-8"))
    except (OSError, EOFError, ValueError) as exc:
        violations.append(f"{pair_dir.name}: match_data.json.gz does not gunzip to JSON ({exc})")
        return
    if not isinstance(telemetry, dict):
        violations.append(f"{pair_dir.name}: match_data.json.gz is not a seed map")
        return
    expected = {f"seed_{g.get('seed')}": g for g in data.get("matches", [])}
    if set(telemetry) != set(expected):
        violations.append(f"{pair_dir.name}: match_data.json.gz seeds {sorted(telemetry)} != {sorted(expected)}")
    for key in sorted(set(telemetry) & set(expected)):
        rec, g = telemetry[key], expected[key]
        if not isinstance(rec, dict):
            violations.append(f"{pair_dir.name}: match_data.json.gz {key} is not a record")
            continue
        if rec.get("num_steps") != g.get("num_steps"):
            violations.append(f"{pair_dir.name} {key}: match_data.json.gz num_steps {rec.get('num_steps')!r} != match_result.json {g.get('num_steps')!r}")
        if rec.get("winner") != g.get("winner"):
            violations.append(f"{pair_dir.name} {key}: match_data.json.gz winner {rec.get('winner')!r} != match_result.json {g.get('winner')!r}")


def _verify_stored_rr(
    stage_dir: Path, participants: Sequence[str], *, n_rollouts: int, match_time: float, model: Optional[str]
) -> List[str]:
    violations: List[str] = []
    if not stage_dir.is_dir():
        return [f"{stage_dir} missing"]
    if len(participants) < 2:
        violations.append(f"{stage_dir}: only {len(participants)} participants {list(participants)}")
    records, pairing_ok = _check_pairings(stage_dir / "matches", participants, n_rollouts, match_time, violations)
    for pair_dir, data in records:
        _check_stored_telemetry(pair_dir, data, violations)
    if pairing_ok and records:
        standings = compute_standings(_outcomes(data for _, data in records))
        elo = _check_standings_file(stage_dir / "elo.json", standings, n_rollouts, violations, model=model)
        if elo is not None:
            if "ties_at_top" not in elo:
                violations.append("elo.json: no ties_at_top declaration")
            else:
                _check_ties_declared("elo.json", elo["ties_at_top"], standings, _ranked(standings)[0][0], violations)
    for p in _forbidden_files(stage_dir, (), VIDEO_SUFFIXES):
        violations.append(f"forbidden video file {p.relative_to(stage_dir)}")
    return violations


def verify_stage_b1(out: Path, model: str, *, n_rollouts: int, match_time: float) -> List[str]:
    """B1: `<out>/stage_b/top5/<model>/` — the round robin among `<out>/<model>/top_5_bots.json`."""
    out = Path(out)
    violations: List[str] = []
    top5 = _load_json(out / model / "top_5_bots.json", violations)
    if top5 is None:
        return violations
    participants = [str(r["artifact_id"]) for r in top5["bots"]]
    stage_dir = out / "stage_b" / "top5" / model
    if len(participants) < 2:
        # a model with a single run winner has no Top-5 Round to play; pool_finals records SKIPPED.json and
        # that one bot is the model's champion (top_1.json) — clean as long as nothing was played
        skipped = _load_json(stage_dir / "SKIPPED.json", violations)
        if skipped is None:
            return violations
        if sorted(skipped.get("bots", [])) != sorted(participants):
            violations.append(f"{stage_dir}/SKIPPED.json bots {skipped.get('bots')} != top_5 {participants}")
        if (stage_dir / "matches").is_dir() and any(p.is_dir() for p in (stage_dir / "matches").iterdir()):
            violations.append(f"{stage_dir}: pairing dirs present although only {len(participants)} participant(s)")
        return violations
    return violations + _verify_stored_rr(stage_dir, participants, n_rollouts=n_rollouts, match_time=match_time, model=model)


def verify_stage_b2(out: Path, *, n_rollouts: int, match_time: float) -> List[str]:
    """B2: `<out>/stage_b/top1/` — the cross-model round robin of every model's champion."""
    out = Path(out)
    violations: List[str] = []
    participants: List[str] = []
    # a model's champion is the Bradley-Terry winner of its Top-5 Round when that round was played
    # (stage_b/top5/<model>/elo.json; ties broken by the lowest sample index, as pool_finals does);
    # otherwise its <model>/top_1.json (a lone run winner, or an ungrouped run)
    for md in sorted(p for p in out.iterdir() if p.is_dir() and p.name != "stage_b" and not p.name.startswith("_")):
        elo_path = out / "stage_b" / "top5" / md.name / "elo.json"
        if elo_path.is_file():
            elo = _load_json(elo_path, violations)
            st = elo.get("standings") if isinstance(elo, dict) else None
            if isinstance(st, dict) and st:
                participants.append(sorted(st.items(), key=lambda kv: (-float(kv[1]["elo"]), kv[0]))[0][0])
                continue
        top1 = _load_json(md / "top_1.json", violations) if (md / "top_1.json").is_file() else None
        if top1 is not None and top1.get("artifact_id"):
            participants.append(str(top1["artifact_id"]))
    if not participants:
        violations.append(f"{out}: no champion found (no stage_b/top5/<model>/elo.json or <model>/top_1.json)")
    return violations + _verify_stored_rr(
        out / "stage_b" / "top1", participants, n_rollouts=n_rollouts, match_time=match_time, model=None)


def verify_stage_b3(out: Path, group: int, *, n_rollouts: int, match_time: float) -> List[str]:
    """B3: `<out>/stage_b/runs/g<k>/` — the cross-model round robin of every model's run-k winner, read
    from `<out>/<model>/runs.json` (groups[k].winner; a model whose run k had no winner is not entered).
    participants.json must declare exactly that set."""
    out = Path(out)
    violations: List[str] = []
    gname = f"g{group}"
    participants: List[str] = []
    for md in sorted(p for p in out.iterdir() if p.is_dir() and p.name != "stage_b" and not p.name.startswith("_")):
        runs = _load_json(md / "runs.json", violations) if (md / "runs.json").is_file() else None
        if runs is None:
            continue
        for g in runs.get("groups", []):
            if g.get("group") == gname and g.get("winner"):
                participants.append(str(g["winner"]))
    if not participants:
        violations.append(f"{out}: no run-{group} winner found in any <model>/runs.json")
    stage_dir = out / "stage_b" / "runs" / gname
    declared = _load_json(stage_dir / "participants.json", violations)
    if isinstance(declared, dict):
        if sorted(declared.get("by_model", {}).values()) != sorted(participants):
            violations.append(f"{stage_dir}/participants.json by_model {sorted(declared.get('by_model', {}).values())} "
                              f"!= runs.json winners {sorted(participants)}")
        if declared.get("group") != gname:
            violations.append(f"{stage_dir}/participants.json group {declared.get('group')!r} != {gname!r}")
    return violations + _verify_stored_rr(stage_dir, participants, n_rollouts=n_rollouts, match_time=match_time, model=None)


def verify_stage_b4(out: Path, *, n_rollouts: int, match_time: float) -> List[str]:
    """B4: `<out>/stage_b/field/` — the explicit pairing list of pool_finals.field_pairings (every
    non-champion run winner vs every champion not already met), rebuilt here from runs.json +
    stage_b/top1/elo.json and compared with pairings.json and the pairing dirs."""
    out = Path(out)
    violations: List[str] = []
    stage_dir = out / "stage_b" / "field"
    champs = _load_json(out / "stage_b" / "top1" / "elo.json", violations)
    if champs is None:
        return violations
    champs = sorted(str(a) for a in champs["participants"])
    group_of: Dict[str, str] = {}
    for md in sorted(p for p in out.iterdir() if p.is_dir() and p.name != "stage_b" and not p.name.startswith("_")):
        runs = _load_json(md / "runs.json", violations) if (md / "runs.json").is_file() else None
        if runs is None:
            continue
        for g in runs.get("groups", []):
            if g.get("winner"):
                group_of[str(g["winner"])] = str(g["group"])
    winners = sorted(group_of)
    champ_set = set(champs)
    declared = _load_json(stage_dir / "pairings.json", violations)
    rule = declared.get("field_rule", "champions") if isinstance(declared, dict) else "champions"
    if rule not in ("champions", "full"):
        return violations + [f"{stage_dir}/pairings.json: unknown field_rule {rule!r}"]
    if rule == "champions":
        candidates = [(w, c) for w in winners if w not in champ_set for c in champs]
    else:
        candidates = list(itertools.combinations(winners, 2))
    expected: List[Tuple[str, str]] = []
    for a, b in candidates:
        if a.split("__")[0] == b.split("__")[0] or (a in champ_set and b in champ_set) or group_of[a] == group_of[b]:
            continue
        expected.append(tuple(sorted((a, b), key=winners.index)))
    if isinstance(declared, dict):
        if sorted(map(tuple, declared.get("pairs", []))) != sorted(expected):
            violations.append(f"{stage_dir}/pairings.json pairs differ from the rule ({len(declared.get('pairs', []))} vs {len(expected)})")
        if declared.get("bots") != winners:
            violations.append(f"{stage_dir}/pairings.json bots != sorted run winners")
    if not stage_dir.is_dir():
        return violations + [f"{stage_dir} missing"]
    records, pairing_ok = _check_pairings(stage_dir / "matches", winners, n_rollouts, match_time, violations,
                                          expected_pairs=expected)
    for pair_dir, data in records:
        _check_stored_telemetry(pair_dir, data, violations)
    if pairing_ok and records:
        standings = compute_standings(_outcomes(data for _, data in records))
        _check_standings_file(stage_dir / "elo.json", standings, n_rollouts, violations, model=None)
    for p in _forbidden_files(stage_dir, (), VIDEO_SUFFIXES):
        violations.append(f"forbidden video file {p.relative_to(stage_dir)}")
    return violations


def verify_stage_b5(out: Path, *, n_rollouts: int, match_time: float) -> List[str]:
    """B5: `<out>/stage_b/baseline/` — every run winner (runs.json) vs `baseline__block`, block on the
    blue side, exactly once each; pairings.json must declare that list."""
    out = Path(out)
    violations: List[str] = []
    stage_dir = out / "stage_b" / "baseline"
    block = "baseline__block"
    winners: List[str] = []
    for md in sorted(p for p in out.iterdir() if p.is_dir() and p.name != "stage_b" and not p.name.startswith("_")):
        runs = _load_json(md / "runs.json", violations) if (md / "runs.json").is_file() else None
        if runs is None:
            continue
        winners += [str(g["winner"]) for g in runs.get("groups", []) if g.get("winner")]
    winners = sorted(winners)
    expected = [(w, block) for w in winners]
    declared = _load_json(stage_dir / "pairings.json", violations)
    if isinstance(declared, dict):
        if sorted(map(tuple, declared.get("pairs", []))) != sorted(expected):
            violations.append(f"{stage_dir}/pairings.json pairs differ from the rule ({len(declared.get('pairs', []))} vs {len(expected)})")
        if declared.get("baseline") != block:
            violations.append(f"{stage_dir}/pairings.json baseline {declared.get('baseline')!r} != {block!r}")
    if not stage_dir.is_dir():
        return violations + [f"{stage_dir} missing"]
    records, pairing_ok = _check_pairings(stage_dir / "matches", winners + [block], n_rollouts, match_time, violations,
                                          expected_pairs=expected, allow_baselines=True)
    for pair_dir, data in records:
        if data.get("blue_bot") != block:
            violations.append(f"{pair_dir.name}: the block must be the blue side (as in qualification)")
        _check_stored_telemetry(pair_dir, data, violations)
    if pairing_ok and records:
        standings = compute_standings(_outcomes(data for _, data in records))
        _check_standings_file(stage_dir / "elo.json", standings, n_rollouts, violations, model=None)
    for p in _forbidden_files(stage_dir, (), VIDEO_SUFFIXES):
        violations.append(f"forbidden video file {p.relative_to(stage_dir)}")
    return violations


# ── CLI ───────────────────────────────────────────────────────────────────────

def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True, type=Path, help="pool_rr output root (holds <model>/ and stage_b/)")
    ap.add_argument("--model", help="Stage A model to verify (or the B1 model)")
    ap.add_argument("--n-rollouts", type=int, default=None,
                    help="games per pairing; Stage A defaults to pool_ledger.json's value, Stage B requires it")
    ap.add_argument("--match-time", type=float, default=300.0, help="seconds; step cap = round(match_time / 0.01)")
    ap.add_argument("--group", type=int, default=None, help="verify one run of a grouped Stage A: <out>/<model>/g<k>/")
    ap.add_argument("--stage", nargs="+", metavar=("STAGE", "MODEL"),
                    help="'b1 <model>', 'b2', 'b3 g<k>' or 'b4' for the stored Stage B rounds")
    args = ap.parse_args(argv)

    if args.stage:
        stage = args.stage[0].lower()
        if args.n_rollouts is None:
            ap.error("--n-rollouts is required for --stage")
        if stage == "b1":
            model = args.stage[1] if len(args.stage) > 1 else args.model
            if not model:
                ap.error("--stage b1 needs a model")
            label = f"stage B1 {model}"
            violations = verify_stage_b1(args.out, model, n_rollouts=args.n_rollouts, match_time=args.match_time)
        elif stage == "b2":
            label = "stage B2"
            violations = verify_stage_b2(args.out, n_rollouts=args.n_rollouts, match_time=args.match_time)
        elif stage == "b3":
            if len(args.stage) < 2:
                ap.error("--stage b3 needs a run group (g<k> or k)")
            group = int(str(args.stage[1]).lstrip("gG"))
            label = f"stage B3 g{group}"
            violations = verify_stage_b3(args.out, group, n_rollouts=args.n_rollouts, match_time=args.match_time)
        elif stage == "b4":
            label = "stage B4 field"
            violations = verify_stage_b4(args.out, n_rollouts=args.n_rollouts, match_time=args.match_time)
        elif stage == "b5":
            label = "stage B5 baseline"
            violations = verify_stage_b5(args.out, n_rollouts=args.n_rollouts, match_time=args.match_time)
        else:
            ap.error(f"unknown stage {args.stage[0]!r} (b1 <model> | b2 | b3 g<k> | b4 | b5)")
    else:
        if not args.model:
            ap.error("--model is required for Stage A")
        n_rollouts = args.n_rollouts
        if n_rollouts is None:
            ledger_path = args.out / args.model / "pool_ledger.json"
            if not ledger_path.is_file():
                print(f"FAIL: {ledger_path} missing (cannot infer --n-rollouts)")
                return 1
            n_rollouts = int(json.loads(ledger_path.read_text())["n_rollouts"])
            print(f"n_rollouts {n_rollouts} taken from {ledger_path}")
        label = f"stage A {args.model}"
        violations = verify(args.out, args.model, n_rollouts=n_rollouts, match_time=args.match_time, group=args.group)

    for v in violations:
        print(f"VIOLATION: {v}")
    if violations:
        print(f"FAIL: {label} — {len(violations)} violation(s)")
        return 1
    print(f"OK: {label} clean (step cap {step_cap(args.match_time)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
