"""verify_pool_rr: a finished model's round robin is complete, protocol-clean, and its
standings/top-5/top-1 are exactly what the records imply. Synthetic fixtures only."""
import gzip
import itertools
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/sampling"))

from mjarena.elo.core import MatchOutcome, compute_standings  # noqa: E402

import verify_pool_rr  # noqa: E402

MODEL = "m"
IDS = ["m__t00_c000", "m__t01_c000", "m__t07_c000"]
N = 3
CAP = 30000  # 300 s / 0.01 s


def _game(seed, winner, num_steps=1234, reason="ring_out", unstable=False):
    return {"seed": seed, "winner": winner, "num_steps": num_steps,
            "termination_reason": reason, "physics_unstable": unstable}


def _write_match(matches_dir, red, blue, winners, seed0=0):
    d = matches_dir / f"{red}_vs_{blue}"
    d.mkdir(parents=True)
    games = [_game(seed0 + i, w) for i, w in enumerate(winners)]
    (d / "match_result.json").write_text(json.dumps({
        "red_bot": red, "blue_bot": blue, "n_seeds": len(winners), "matches": games,
        "wins_a": sum(w == "red" for w in winners), "wins_b": sum(w == "blue" for w in winners),
        "ties": sum(w == "tie" for w in winners)}))
    return d


def _outcomes(matches_dir):
    out = []
    for p in sorted(matches_dir.rglob("match_result.json")):
        d = json.loads(p.read_text())
        for g in d["matches"]:
            w = d["red_bot"] if g["winner"] == "red" else d["blue_bot"] if g["winner"] == "blue" else "draw"
            out.append(MatchOutcome(d["red_bot"], d["blue_bot"], w))
    return out


def _write_standings(model_dir, model, n_rollouts, *, ties_at_top=None):
    standings = compute_standings(_outcomes(model_dir / "matches"))
    (model_dir / "elo.json").write_text(json.dumps(
        {"model": model, "method": "bt", "n_rollouts": n_rollouts, "standings": standings}))
    ranked = sorted(standings.items(), key=lambda kv: kv[1]["elo"], reverse=True)
    rows = []
    for rank, (aid, st) in enumerate(ranked[:5], start=1):
        idx = int(aid.split("__t")[1].split("_c")[0])
        rows.append({"rank": rank, "artifact_id": aid, "model": model, "kind": "refinement_commit",
                     "tournament_idx": idx, "commit_idx": 0, "robot_xml": "x", "controller_py": "y",
                     "qualification_score": 1.0, "intra_model_elo": st["elo"],
                     "intra_model_wld": {"wins": st["wins"], "losses": st["losses"], "draws": st["draws"]},
                     "cross_model_elo": {"k1": None, "k3": None, "k5": None},
                     "cross_model_wld": {"k1": None, "k3": None, "k5": None}})
    (model_dir / "top_5_bots.json").write_text(json.dumps(
        {"k": 5, "scope": "intra_model", "model": model, "source": {}, "bots": rows}))
    top_aid, top = ranked[0]
    top_set = [a for a, s in ranked if abs(s["elo"] - top["elo"]) <= 1e-9]
    (model_dir / "top_1.json").write_text(json.dumps(
        {"model": model, "artifact_id": top_aid, "tournament_idx": rows[0]["tournament_idx"],
         "elo": top["elo"], "wins": top["wins"], "losses": top["losses"], "draws": top["draws"],
         "games": top["games"],
         "ties_at_top": ties_at_top if ties_at_top is not None else (top_set if len(top_set) > 1 else [])}))
    return standings


def _ledger_rows(eligible_idx, n_slots=8):
    return [{"idx": i, "eligible": i in eligible_idx,
             "reason": "eligible" if i in eligible_idx else "not qualified yet"} for i in range(n_slots)]


def _build_stage_a(out, *, results=None, model=MODEL, ids=IDS, n=N, match_time=300.0):
    """results: {(red, blue): [winners]}; default = bot 0 wins everything, the others split."""
    if results is None:
        results = {(ids[0], ids[1]): ["red"] * n, (ids[0], ids[2]): ["red"] * n,
                   (ids[1], ids[2]): ["red", "blue", "tie"][:n] + ["tie"] * max(0, n - 3)}
    md = out / model
    matches = md / "matches"
    for k, ((red, blue), winners) in enumerate(results.items()):
        _write_match(matches, red, blue, winners, seed0=k * n)
    (md / "pool_ledger.json").write_text(json.dumps({
        "model": model, "run_id": "test", "n_samples": 8, "eligible": len(ids), "n_rollouts": n,
        "match_time": match_time, "ledger": _ledger_rows({int(a.split("__t")[1][:2]) for a in ids})}))
    _write_standings(md, model, n)
    return md


@pytest.fixture
def out(tmp_path):
    o = tmp_path / "out"
    _build_stage_a(o)
    return o


def _v(out, **kw):
    kw.setdefault("n_rollouts", N)
    kw.setdefault("match_time", 300.0)
    return verify_pool_rr.verify(out, MODEL, **kw)


# ── stage A ───────────────────────────────────────────────────────────────────

def test_clean_model_has_no_violations(out):
    assert _v(out) == []


def test_missing_pairing_is_the_only_violation(out):
    shutil.rmtree(out / MODEL / "matches/m__t00_c000_vs_m__t01_c000")
    assert _v(out) == ["missing pairing m__t00_c000 vs m__t01_c000"]


def test_step_cap_is_enforced(out):
    p = out / MODEL / "matches/m__t00_c000_vs_m__t01_c000/match_result.json"
    d = json.loads(p.read_text())
    d["matches"][1]["num_steps"] = CAP + 1
    p.write_text(json.dumps(d))
    v = _v(out)
    assert len(v) == 1 and "num_steps 30001 > 30000" in v[0]
    assert verify_pool_rr.step_cap(300.01) == 30001   # the cap follows match_time
    led = out / MODEL / "pool_ledger.json"
    led.write_text(json.dumps({**json.loads(led.read_text()), "match_time": 300.01}))
    assert _v(out, match_time=300.01) == []
    v = _v(out, match_time=300.0)                     # ledger and operator disagree on the protocol
    assert any("pool_ledger.json match_time 300.01 != 300.0" in s for s in v)


def test_wrong_rating_in_elo_json_is_caught(out):
    p = out / MODEL / "elo.json"
    d = json.loads(p.read_text())
    d["standings"][IDS[1]]["elo"] += 1e-6
    p.write_text(json.dumps(d))
    v = _v(out)
    assert any("elo.json standings differ from recomputation" in s for s in v)
    d["standings"][IDS[1]]["elo"] -= 1e-6 - 1e-12    # inside the 1e-9 tolerance
    p.write_text(json.dumps(d))
    assert _v(out) == []


def test_ledger_count_and_row_set_must_agree_with_pairings(out):
    p = out / MODEL / "pool_ledger.json"
    d = json.loads(p.read_text())
    d["eligible"] = 4
    p.write_text(json.dumps(d))
    v = _v(out)
    assert any("eligible" in s and "4" in s for s in v)
    d["eligible"] = 3
    d["ledger"][2]["eligible"] = True                 # t02 declared eligible but never played
    p.write_text(json.dumps(d))
    v = _v(out)
    assert "missing pairing m__t00_c000 vs m__t02_c000" in v
    assert any("eligible" in s for s in v)           # count 3 vs 4 ids


def test_extra_and_baseline_pairs_are_rejected(out):
    _write_match(out / MODEL / "matches", IDS[0], "baseline__baseline-pusher", ["red"] * N, seed0=90)
    _write_match(out / MODEL / "matches", IDS[0], "m__t02_c000", ["red"] * N, seed0=93)   # never eligible
    v = _v(out)
    assert any("baseline bot baseline__baseline-pusher" in s for s in v)
    assert any("m__t02_c000 not eligible" in s for s in v)
    assert not any("missing pairing" in s for s in v)


def test_duplicate_reverse_pair_is_rejected(out):
    _write_match(out / MODEL / "matches", IDS[1], IDS[0], ["blue"] * N, seed0=90)
    v = _v(out)
    assert any("duplicate pairing" in s for s in v)


def test_dir_name_must_match_participants(out):
    d = out / MODEL / "matches/m__t00_c000_vs_m__t01_c000"
    d.rename(out / MODEL / "matches/m__t00_c000_vs_m__t09_c000")
    v = _v(out)
    assert any("directory name" in s for s in v)


def test_per_game_protocol_fields(out):
    p = out / MODEL / "matches/m__t00_c000_vs_m__t07_c000/match_result.json"
    d = json.loads(p.read_text())
    d["matches"][0]["winner"] = "draw"                # harness token is "tie"
    d["matches"][1]["termination_reason"] = ""
    d["matches"][2]["physics_unstable"] = "yes"   # a non-bool flag; True itself is a ruled outcome
    d["matches"].append(_game(99, "red"))             # 4 games but n_seeds 3
    p.write_text(json.dumps(d))
    v = _v(out)
    joined = "\n".join(v)
    assert "winner 'draw'" in joined
    assert "termination_reason" in joined
    assert "physics_unstable" in joined
    assert "4 games" in joined and "n_seeds" in joined


def test_n_seeds_must_equal_n_rollouts(out):
    v = _v(out, n_rollouts=5)
    assert any("n_seeds 3 != 5" in s for s in v)
    assert any("pool_ledger.json n_rollouts 3 != 5" in s for s in v)


def test_top1_must_be_argmax_and_declare_ties(tmp_path):
    o = tmp_path / "out"
    ids = IDS
    results = {(ids[0], ids[1]): ["tie"] * N, (ids[0], ids[2]): ["tie"] * N, (ids[1], ids[2]): ["tie"] * N}
    md = _build_stage_a(o, results=results)
    assert _v(o) == []
    t1 = json.loads((md / "top_1.json").read_text())
    assert sorted(t1["ties_at_top"]) == sorted(ids)
    t1["ties_at_top"] = []
    (md / "top_1.json").write_text(json.dumps(t1))
    v = _v(o)
    assert any("ties_at_top" in s for s in v)
    t1["ties_at_top"] = ids
    t1["artifact_id"] = "m__t99_c000"
    (md / "top_1.json").write_text(json.dumps(t1))
    v = _v(o)
    assert any("top_1.json" in s and "argmax" in s for s in v)


def test_top5_must_be_the_ranked_head(out):
    p = out / MODEL / "top_5_bots.json"
    d = json.loads(p.read_text())
    d["bots"][0], d["bots"][1] = d["bots"][1], d["bots"][0]   # rank order broken
    p.write_text(json.dumps(d))
    v = _v(out)
    assert any("top_5_bots.json" in s for s in v)
    d = json.loads(p.read_text())
    d["bots"] = d["bots"][:2]                                 # 3 bots but only 2 listed
    p.write_text(json.dumps(d))
    v = _v(out)
    assert any("top_5_bots.json" in s and "2" in s for s in v)


def test_top5_tie_at_the_cut_is_a_violation(tmp_path):
    o = tmp_path / "out"
    ids = [f"m__t{i:02d}_c000" for i in range(6)]
    results = {(a, b): ["red"] * N if a == ids[0] else ["tie"] * N for a, b in itertools.combinations(ids, 2)}
    md = _build_stage_a(o, results=results, ids=ids)         # five bots tied at ranks 2..6
    v = _v(o)
    assert any("tie at the top-5 cut" in s and "undeclared" in s for s in v)
    p = md / "top_5_bots.json"
    d = json.loads(p.read_text())
    d["source"]["ties_at_cut"] = ids[1:]                     # pool_rr's declaration: every bot at the cut rating
    p.write_text(json.dumps(d))
    assert _v(o) == []
    d["source"]["ties_at_cut"] = ids[1:5]                    # the unlisted 6th bot left out
    p.write_text(json.dumps(d))
    assert any("source.ties_at_cut" in s for s in _v(o))


def test_telemetry_and_video_are_forbidden(out):
    d = out / MODEL / "matches/m__t00_c000_vs_m__t01_c000"
    (d / "match_data.json").write_text("{}")
    (d / "seed_0.mp4").write_bytes(b"x")
    (out / MODEL / "match.webm").write_bytes(b"x")
    v = _v(out)
    joined = "\n".join(v)
    assert "match_data.json" in joined and "seed_0.mp4" in joined and "match.webm" in joined


def test_missing_files_are_reported_not_raised(tmp_path):
    v = verify_pool_rr.verify(tmp_path, "nope", n_rollouts=N, match_time=300.0)
    assert v and all("nope" in s for s in v)


def test_cli_exit_codes(out, capsys):
    rc = verify_pool_rr.main(["--out", str(out), "--model", MODEL, "--n-rollouts", str(N), "--match-time", "300"])
    assert rc == 0
    assert "OK" in capsys.readouterr().out
    rc_default = verify_pool_rr.main(["--out", str(out), "--model", MODEL])   # n_rollouts from the ledger
    assert rc_default == 0
    shutil.rmtree(out / MODEL / "matches/m__t01_c000_vs_m__t07_c000")
    rc = verify_pool_rr.main(["--out", str(out), "--model", MODEL, "--n-rollouts", str(N)])
    assert rc == 1
    assert "missing pairing" in capsys.readouterr().out


# ── stage B ───────────────────────────────────────────────────────────────────

def _write_match_data_gz(pair_dir, *, drift=0):
    d = json.loads((pair_dir / "match_result.json").read_text())
    payload = {f"seed_{g['seed']}": {"seed": g["seed"], "winner": g["winner"],
                                     "num_steps": g["num_steps"] + drift} for g in d["matches"]}
    with gzip.open(pair_dir / "match_data.json.gz", "wb") as f:
        f.write(json.dumps(payload).encode())


def _build_stage_b(stage_dir, ids, n, *, model=None):
    matches = stage_dir / "matches"
    for k, (a, b) in enumerate(itertools.combinations(ids, 2)):
        d = _write_match(matches, a, b, ["red"] * n, seed0=k * n)
        _write_match_data_gz(d)
    standings = compute_standings(_outcomes(matches))
    top = max(standings.values(), key=lambda s: s["elo"])["elo"]
    ties = sorted(a for a, s in standings.items() if abs(s["elo"] - top) <= 1e-9)
    (stage_dir / "elo.json").write_text(json.dumps(
        {"model": model, "method": "bt", "n_rollouts": n, "standings": standings,
         "ties_at_top": ties if len(ties) > 1 else []}))


@pytest.fixture
def stage_b(tmp_path):
    o = tmp_path / "out"
    _build_stage_a(o)
    _build_stage_a(o, model="n", ids=["n__t03_c000", "n__t04_c000", "n__t05_c000"])
    top5_m = [r["artifact_id"] for r in json.loads((o / "m/top_5_bots.json").read_text())["bots"]]
    _build_stage_b(o / "stage_b/top5/m", top5_m, 2, model="m")
    top1 = [json.loads(p.read_text())["artifact_id"] for p in sorted(o.glob("*/top_1.json"))]
    assert len(top1) == 2
    _build_stage_b(o / "stage_b/top1", top1, 2)
    return o


def test_stage_b_clean(stage_b):
    assert verify_pool_rr.verify_stage_b1(stage_b, "m", n_rollouts=2, match_time=300.0) == []
    assert verify_pool_rr.verify_stage_b2(stage_b, n_rollouts=2, match_time=300.0) == []
    assert verify_pool_rr.main(["--out", str(stage_b), "--stage", "b1", "m", "--n-rollouts", "2"]) == 0
    assert verify_pool_rr.main(["--out", str(stage_b), "--stage", "b2", "--n-rollouts", "2"]) == 0


def test_stage_b_requires_gzipped_telemetry_matching_the_record(stage_b):
    pair = next((stage_b / "stage_b/top5/m/matches").iterdir())
    (pair / "match_data.json.gz").unlink()
    v = verify_pool_rr.verify_stage_b1(stage_b, "m", n_rollouts=2, match_time=300.0)
    assert any("match_data.json.gz missing" in s for s in v)
    _write_match_data_gz(pair, drift=7)
    v = verify_pool_rr.verify_stage_b1(stage_b, "m", n_rollouts=2, match_time=300.0)
    assert any("num_steps" in s and "match_data.json.gz" in s for s in v)
    (pair / "match_data.json").write_text("{}")           # raw telemetry left behind
    v = verify_pool_rr.verify_stage_b1(stage_b, "m", n_rollouts=2, match_time=300.0)
    assert any("match_data.json" in s and "gzip" in s for s in v)


def test_stage_b_participants_come_from_stage_a(stage_b):
    d = stage_b / "stage_b/top1/matches"
    extra = _write_match(d, "m__t00_c000", "zz__t00_c000", ["red"] * 2, seed0=50)
    _write_match_data_gz(extra)
    v = verify_pool_rr.verify_stage_b2(stage_b, n_rollouts=2, match_time=300.0)
    assert any("zz__t00_c000" in s for s in v)
    shutil.rmtree(extra)
    e = json.loads((stage_b / "stage_b/top1/elo.json").read_text())
    e["ties_at_top"] = ["m__t00_c000", "n__t03_c000"]
    (stage_b / "stage_b/top1/elo.json").write_text(json.dumps(e))
    v = verify_pool_rr.verify_stage_b2(stage_b, n_rollouts=2, match_time=300.0)
    assert any("ties_at_top" in s for s in v)
    assert verify_pool_rr.main(["--out", str(stage_b), "--stage", "b2", "--n-rollouts", "2"]) == 1


def test_runs_with_fewer_than_two_bots_are_clean_without_a_matches_dir(tmp_path):
    """A run of 50 samples can have 0 or 1 qualified bots: no pairings, no matches dir, no violation."""
    import verify_pool_rr, json
    def ledger(model_dir, n):
        rows = [{"idx": i, "eligible": i < n, "artifact_id": f"m__t{i:02d}_c000"} for i in range(3)]
        (model_dir / "pool_ledger.json").write_text(json.dumps({"model": "m", "n_rollouts": 5, "match_time": 300.0,
                                                                 "eligible": n, "ledger": rows}))
    one = tmp_path / "one" / "m"; one.mkdir(parents=True); ledger(one, 1)
    (one / "elo.json").write_text(json.dumps({"model": "m", "method": "bt", "n_rollouts": 5, "ties_at_top": ["m__t00_c000"],
                                              "standings": {"m__t00_c000": {"elo": 1000.0, "wins": 0, "losses": 0, "draws": 0, "games": 0}}}))
    (one / "top_1.json").write_text(json.dumps({"model": "m", "artifact_id": "m__t00_c000", "tournament_idx": 0, "elo": 1000.0,
                                                "wins": 0, "losses": 0, "draws": 0, "games": 0, "ties_at_top": ["m__t00_c000"]}))
    assert verify_pool_rr.verify(tmp_path / "one", "m", n_rollouts=5, match_time=300.0) == []
    zero = tmp_path / "zero" / "m"; zero.mkdir(parents=True); ledger(zero, 0)
    (zero / "elo.json").write_text(json.dumps({"model": "m", "method": "bt", "n_rollouts": 5, "ties_at_top": [], "standings": {}}))
    assert verify_pool_rr.verify(tmp_path / "zero", "m", n_rollouts=5, match_time=300.0) == []
    (zero / "matches" / "a_vs_b").mkdir(parents=True)
    assert any("pairing dir" in v for v in verify_pool_rr.verify(tmp_path / "zero", "m", n_rollouts=5, match_time=300.0))


def test_physics_unstable_games_are_ruled_outcomes_not_violations(tmp_path):
    """MuJoCo instability makes the owning bot lose (sumo.py); the record is valid with its winner."""
    import verify_pool_rr, json
    from mjarena.elo.core import MatchOutcome, compute_standings
    md = tmp_path / "m"; (md / "matches" / "m__t00_c000_vs_m__t01_c000").mkdir(parents=True)
    rows = [{"idx": i, "eligible": i < 2, "artifact_id": f"m__t{i:02d}_c000"} for i in range(2)]
    (md / "pool_ledger.json").write_text(json.dumps({"model": "m", "n_rollouts": 1, "match_time": 300.0, "eligible": 2, "ledger": rows}))
    (md / "matches/m__t00_c000_vs_m__t01_c000/match_result.json").write_text(json.dumps({
        "red_bot": "m__t00_c000", "blue_bot": "m__t01_c000", "n_seeds": 1,
        "matches": [{"seed": 42, "winner": "red", "num_steps": 120, "termination_reason": "physics_unstable", "physics_unstable": True}]}))
    st = compute_standings([MatchOutcome("m__t00_c000", "m__t01_c000", "m__t00_c000")])
    (md / "elo.json").write_text(json.dumps({"model": "m", "method": "bt", "n_rollouts": 1, "ties_at_top": ["m__t00_c000"], "standings": st}))
    (md / "top_1.json").write_text(json.dumps({"model": "m", "artifact_id": "m__t00_c000", "tournament_idx": 0, "ties_at_top": ["m__t00_c000"], **st["m__t00_c000"]}))
    (md / "top_5_bots.json").write_text(json.dumps({"k": 5, "scope": "intra_model", "model": "m", "source": {"ties_at_cut": []},
        "bots": [{"rank": r + 1, "artifact_id": a, "model": "m", "tournament_idx": int(a[4:6]), "intra_model_elo": st[a]["elo"],
                  "intra_model_wld": {"wins": st[a]["wins"], "losses": st[a]["losses"], "draws": st[a]["draws"]}}
                 for r, a in enumerate(sorted(st, key=lambda k: -st[k]["elo"]))]}))
    v = verify_pool_rr.verify(tmp_path, "m", n_rollouts=1, match_time=300.0)
    assert not [x for x in v if "physics_unstable" in x], v


def test_single_run_winner_skips_the_top5_round_cleanly(tmp_path):
    import verify_pool_rr, json
    md = tmp_path / "m"; sd = tmp_path / "stage_b/top5/m"; md.mkdir(parents=True); sd.mkdir(parents=True)
    (md / "top_5_bots.json").write_text(json.dumps({"bots": [{"artifact_id": "m__t235_c000"}]}))
    (sd / "SKIPPED.json").write_text(json.dumps({"model": "m", "stage": "b1", "reason": "1 bot", "n_bots": 1, "bots": ["m__t235_c000"]}))
    assert verify_pool_rr.verify_stage_b1(tmp_path, "m", n_rollouts=11, match_time=300.0) == []
    (sd / "matches" / "a_vs_b").mkdir(parents=True)
    assert verify_pool_rr.verify_stage_b1(tmp_path, "m", n_rollouts=11, match_time=300.0)
