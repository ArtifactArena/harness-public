"""release_readme: README.md / MISSING.md / standings/summary.json for the SH-250 pool release in the
GROUPED layout (five runs per model -> run winners -> Top-5 Round -> Champions Round), rendered only
from what pool_rr, pool_finals and merge_pack_manifests wrote (nothing hand-edited)."""
import hashlib
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/sampling"))
import release_readme  # noqa: E402

SHA_A = "a" * 40
SHA_B = "b" * 40
SHA_QUAL = "c" * 40           # a commit only the Qualification Round used: allowed in --sha, absent from the ledgers
PROMPT = "THE FROZEN PROMPT\n"
RUN_ID = "sh250-pool-deadbeef"
GENERATED_AT = "2026-09-21T10:00:00+00:00"
RUN_SIZE = 4
N_RUNS = 2
HPC_ROOT = "<user-home>/sh250/pack-a"
GPU_ROOT = "<local>/gpu/sh250-gpu/work/pack-gpu-1"


def _aid(model, idx):
    return f"{model}__t{idx:02d}_c000"


def _st(elo, w, l, d):
    return {"wins": w, "losses": l, "draws": d, "elo": elo, "games": w + l + d}


def _ledger_row(model, idx, reason):
    forfeit = reason.startswith("forfeit")
    known = reason not in ("not generated", "not qualified yet")
    return {"idx": idx, "generated": reason != "not generated", "qualified": known, "forfeit": forfeit,
            "forfeit_stage": reason.split(":", 1)[1] if forfeit else "",
            "validation_passed": (reason != "validation failed") if known else None,
            "qualification_passed": (reason == "eligible") if known else None,
            "qualification_score": 1.0 if reason == "eligible" else None,
            "wdl": [3, 0, 0] if reason == "eligible" else None,
            "eligible": reason == "eligible", "reason": reason, "artifact_id": _aid(model, idx)}


def _pool_ledger(model, k, rows, *, sha, source_root, n_rollouts=2):
    return {
        "model": model, "run_id": RUN_ID, "n_samples": RUN_SIZE * N_RUNS, "eligible": sum(1 for r in rows if r["eligible"]),
        "n_rollouts": n_rollouts, "match_time": 300.0, "inactivity": {"timeout_s": 10.0, "min_displacement_m": 0.5},
        "git_sha": sha, "config": "configs/tournaments/sh.yaml", "config_md5": "cfgmd5aaaa",
        "config_chain": [{"path": "configs/tournaments/sh.yaml", "md5": "cfgmd5aaaa"},
                         {"path": "configs/tournaments/base.yaml", "md5": "basemd5bbbb"}],
        "rules": {"score_function": "any", "physics_mode": "3d", "contact_fidelity": "high",
                  "arena_xml": "mjarena/assets/sumo_ring_env_cinematic_3d.xml", "constraints": "configs/rules/rules.yaml"},
        "source": {"root": source_root, "layout": "pack", "require_qualified": True},
        "generated_at": "2026-09-20T01:00:00+00:00", "ledger": rows,
        "slot_range": [k * RUN_SIZE, (k + 1) * RUN_SIZE], "group": f"g{k}",
    }


def _top5_row(model, idx, rank, elo, wld):
    return {"rank": rank, "artifact_id": _aid(model, idx), "model": model, "kind": "refinement_commit",
            "tournament_idx": idx, "commit_idx": 0, "robot_xml": f"{model}/c{idx:03d}/commit_0/robot.xml",
            "controller_py": f"{model}/c{idx:03d}/commit_0/controller.py", "qualification_score": None,
            "intra_model_elo": elo, "intra_model_wld": wld,
            "cross_model_elo": {"k1": None, "k3": None, "k5": None}, "cross_model_wld": {"k1": None, "k3": None, "k5": None}}


def _match_result(red, blue, winners):
    return {"red_bot": red, "blue_bot": blue, "n_seeds": len(winners),
            "matches": [{"seed": s, "winner": w, "num_steps": 100, "termination_reason": "ring_out", "physics_unstable": False}
                        for s, w in enumerate(winners)]}


def _write_run(gdir, model, k, rows, standings, *, sha, source_root, pairings, ties_at_top):
    """One run g<k>: ledger, elo.json, top_1.json (iff an eligible bot exists), top_5_bots.json, matches."""
    gdir.mkdir(parents=True)
    (gdir / "pool_ledger.json").write_text(json.dumps(_pool_ledger(model, k, rows, sha=sha, source_root=source_root)))
    (gdir / "elo.json").write_text(json.dumps({"model": model, "method": "bt", "n_rollouts": 2,
                                               "tie_break": "lowest tournament_idx", "ties_at_top": ties_at_top,
                                               "standings": standings}))
    order = sorted(standings.items(), key=lambda kv: (-kv[1]["elo"], int(re.search(r"__t(\d+)_", kv[0]).group(1))))
    bots = [_top5_row(model, int(re.search(r"__t(\d+)_", aid).group(1)), i + 1, st["elo"],
                      {"wins": st["wins"], "losses": st["losses"], "draws": st["draws"]}) for i, (aid, st) in enumerate(order)]
    (gdir / "top_5_bots.json").write_text(json.dumps({
        "k": 5, "scope": "intra_model", "model": model, "generated_at": GENERATED_AT,
        "source": {"logs_root": None, "pool_ledger": "pool_ledger.json", "intra_model_elo": "elo.json",
                   "top_n_qualified": len(order), "n_rollouts": 2, "elo_method": "bt",
                   "tie_break": "lowest tournament_idx", "ties_at_cut": []}, "bots": bots}))
    winner = None
    if order:
        aid, st = order[0]
        winner = {"model": model, "artifact_id": aid, "tournament_idx": int(re.search(r"__t(\d+)_", aid).group(1)),
                  "elo": st["elo"], "wins": st["wins"], "losses": st["losses"], "draws": st["draws"], "games": st["games"],
                  "ties_at_top": ties_at_top, "tie_break": "lowest tournament_idx"}
        (gdir / "top_1.json").write_text(json.dumps(winner))
    for red, blue, winners in pairings:
        d = gdir / "matches" / f"{red}_vs_{blue}"
        d.mkdir(parents=True)
        (d / "match_result.json").write_text(json.dumps(_match_result(red, blue, winners)))
    return winner


def _finalize(model_dir, model, winners_by_run, eligible_by_run):
    """runs.json + the model's top_5_bots.json as pool_rr.finalize_runs writes them."""
    groups = []
    for k in range(N_RUNS):
        w = winners_by_run[k]
        groups.append({"group": f"g{k}", "slot_range": [k * RUN_SIZE, (k + 1) * RUN_SIZE], "eligible": eligible_by_run[k],
                       "winner": w["artifact_id"] if w else None, "winner_elo": w["elo"] if w else None,
                       "ties_at_top": w["ties_at_top"] if w else []})
    (model_dir / "runs.json").write_text(json.dumps({"model": model, "runs": N_RUNS, "run_size": RUN_SIZE, "n_rollouts": 2,
                                                     "rule": "each run's full round robin winner (BT) is the run's bot",
                                                     "groups": groups}))
    ws = sorted((w for w in winners_by_run if w), key=lambda w: (-w["elo"], w["tournament_idx"]))
    bots = [_top5_row(model, w["tournament_idx"], i + 1, w["elo"], {"wins": w["wins"], "losses": w["losses"], "draws": w["draws"]})
            for i, w in enumerate(ws)]
    (model_dir / "top_5_bots.json").write_text(json.dumps({
        "k": 5, "scope": "intra_model", "model": model, "generated_at": GENERATED_AT,
        "source": {"logs_root": None, "rule": "one winner per run", "runs": N_RUNS, "run_size": RUN_SIZE, "n_rollouts": 2,
                   "groups": [g["group"] for g in groups if g["winner"]], "tie_break": "lowest tournament_idx"}, "bots": bots}))
    (model_dir / "VERIFIED").write_text("")


@pytest.fixture
def release(tmp_path):
    """A tiny release in the published grouped layout, two runs of four slots per model.

    `alpha` (qualified on the laptop, runs on HPC): run g0 has 3 eligible bots, two of them exactly tied
    at the top (t00 wins by lowest index); run g1 has 2 eligible bots (t05 wins). Its Top-5 Round is the two
    run winners; t05 wins it and is the champion. `solo` (qualified and run on the GPU cluster): run g0 has one
    eligible bot (winner by default), run g1 none; Top-5 Round skipped; the lone winner is its champion.
    Champions Round: alpha's t05 vs solo's t00. `claude-opus-4-7-high`: 27 gen.json in the generation root,
    not packed, no tournament."""
    rel = tmp_path / "release"
    rr = rel / "pool_rr"
    sb = rel / "stage_b"

    # ── alpha ──
    a = rr / "alpha"
    a0, a1, a2, a4, a5 = (_aid("alpha", i) for i in (0, 1, 2, 4, 5))
    g0_rows = [_ledger_row("alpha", 0, "eligible"), _ledger_row("alpha", 1, "eligible"), _ledger_row("alpha", 2, "eligible"),
               _ledger_row("alpha", 3, "forfeit:controller")]
    g0_st = {a0: _st(1050.0, 3, 1, 0), a1: _st(1050.0, 3, 1, 0), a2: _st(900.0, 0, 4, 0)}
    w0 = _write_run(a / "g0", "alpha", 0, g0_rows, g0_st, sha=SHA_A, source_root=HPC_ROOT,
                    pairings=[(a0, a1, ["red", "blue"]), (a0, a2, ["red", "red"]), (a1, a2, ["red", "red"])],
                    ties_at_top=[a0, a1])
    g1_rows = [_ledger_row("alpha", 4, "eligible"), _ledger_row("alpha", 5, "eligible"),
               _ledger_row("alpha", 6, "qualification failed (W1 D1 L1)"), _ledger_row("alpha", 7, "forfeit:morphology")]
    g1_st = {a4: _st(950.0, 0, 2, 0), a5: _st(1050.0, 2, 0, 0)}
    w1 = _write_run(a / "g1", "alpha", 1, g1_rows, g1_st, sha=SHA_B, source_root=HPC_ROOT,
                    pairings=[(a4, a5, ["blue", "blue"])], ties_at_top=[a5])
    _finalize(a, "alpha", [w0, w1], [3, 2])

    # ── solo ──
    s = rr / "solo"
    s0 = _aid("solo", 0)
    solo_g0 = [_ledger_row("solo", 0, "eligible"), _ledger_row("solo", 1, "qualification failed (W0 D0 L3)"),
               _ledger_row("solo", 2, "forfeit:controller"), _ledger_row("solo", 3, "forfeit:controller")]
    sw0 = _write_run(s / "g0", "solo", 0, solo_g0, {s0: _st(1000.0, 0, 0, 0)}, sha=SHA_A, source_root=GPU_ROOT,
                     pairings=[], ties_at_top=[s0])
    solo_g1 = [_ledger_row("solo", i, "forfeit:controller") for i in (4, 5, 6, 7)]
    sw1 = _write_run(s / "g1", "solo", 1, solo_g1, {}, sha=SHA_A, source_root=GPU_ROOT, pairings=[], ties_at_top=[])
    assert sw1 is None
    _finalize(s, "solo", [sw0, sw1], [1, 0])
    (s / "top_1.json").write_text(json.dumps({"model": "solo", "artifact_id": s0, "tournament_idx": 0, "elo": 1000.0,
                                              "wins": 0, "losses": 0, "draws": 0, "games": 0, "ties_at_top": [s0],
                                              "source": "single run winner; Top-5 Round skipped"}))

    # ── Top-5 Round ──
    b1 = sb / "top5" / "alpha"
    b1.mkdir(parents=True)
    b1_standings = {a0: _st(940.0, 1, 2, 0), a5: _st(1060.0, 2, 1, 0)}
    (b1 / "elo.json").write_text(json.dumps({
        "model": "alpha", "stage": "b1", "scope": "intra_model_top5", "method": "bt", "n_rollouts": 3,
        "match_time": 300.0, "run_id": RUN_ID, "generated_at": GENERATED_AT, "participants": [a0, a5],
        "n_games": 3, "standings": b1_standings, "ties": [], "ties_at_top": [a5]}))
    (sb / "top5" / "solo").mkdir(parents=True)
    (sb / "top5" / "solo" / "SKIPPED.json").write_text(json.dumps(
        {"model": "solo", "stage": "b1", "reason": "top_5_bots.json lists 1 bot(s); a round robin needs at least 2",
         "n_bots": 1, "bots": [s0]}))

    # ── Champions Round ──
    b2 = sb / "top1"
    b2.mkdir(parents=True)
    b2_standings = {a5: _st(1120.0, 3, 0, 0), s0: _st(880.0, 0, 3, 0)}
    (b2 / "elo.json").write_text(json.dumps({
        "scope": "cross_model_top1", "stage": "b2", "model": None, "method": "bt", "n_rollouts": 3,
        "match_time": 300.0, "run_id": RUN_ID, "generated_at": GENERATED_AT, "participants": [a5, s0],
        "n_games": 3, "standings": b2_standings, "ties": [], "ties_at_top": [a5]}))
    (b2 / "skipped.json").write_text(json.dumps({"_clean_artifacts": "no top_1.json"}))
    (sb / "summary.json").write_text(json.dumps({
        "run_id": RUN_ID, "n_rollouts": 3, "match_time": 300.0, "config": "configs/tournaments/sh.yaml",
        "method": "bt", "generated_at": GENERATED_AT,
        "top5": {"alpha": {"participants": [a0, a5], "standings": b1_standings, "ties": [], "ties_at_top": [a5]}},
        "top1": {"participants": [a5, s0], "standings": b2_standings, "ties": [], "ties_at_top": [a5],
                 "by_model": {"alpha": {"artifact_id": a5, **b2_standings[a5]}, "solo": {"artifact_id": s0, **b2_standings[s0]}},
                 "not_entered": {"_clean_artifacts": "no top_1.json"}}}))

    # ── the merged pack manifest + prompt (samples/ itself is not needed by the renderer) ──
    prompt_md5 = hashlib.md5(PROMPT.encode()).hexdigest()
    (rel / "sampling_prompt.md").write_text(PROMPT)
    manifest = {
        "merged_at": "2026-09-21T09:00:00+00:00", "pack_root": "/laptop/LOGS-SH250/pack-all", "prompt_md5": prompt_md5,
        "sources": [{"manifest": "/laptop/LOGS-SH250/pack-a/MANIFEST.json", "run_root": "LOGS-SH250/20260918",
                     "git_sha": "packsha0" * 5, "packed_at": "2026-09-19T00:00:00+00:00", "qualified_on": "laptop",
                     "models": ["alpha"], "n_files": 0, "total_bytes": 0},
                    {"manifest": "/laptop/LOGS-SH250/gpu/pack-gpu-1/MANIFEST.json", "run_root": "work/gen-gpu",
                     "git_sha": "packsha1" * 5, "packed_at": "2026-09-19T18:00:00+00:00", "qualified_on": "gpu",
                     "models": ["solo"], "n_files": 0, "total_bytes": 0}],
        "models": {"alpha": {"n_samples": 8, "eligible": 5, "ledger": g0_rows + g1_rows, "qualified_on": "laptop",
                             "source_manifest": "/laptop/LOGS-SH250/pack-a/MANIFEST.json", "git_sha": "packsha0" * 5,
                             "packed_at": "2026-09-19T00:00:00+00:00"},
                   "solo": {"n_samples": 8, "eligible": 1, "ledger": solo_g0 + solo_g1, "qualified_on": "gpu",
                            "source_manifest": "/laptop/LOGS-SH250/gpu/pack-gpu-1/MANIFEST.json", "git_sha": "packsha1" * 5,
                            "packed_at": "2026-09-19T18:00:00+00:00"}},
        "n_models": 2, "n_files": 0, "total_bytes": 0, "files": {}, "sizes": {},
    }
    (rel / "pack-MANIFEST.json").write_text(json.dumps(manifest))

    # ── the generation root: opus-4-7's 27 samples ──
    gen = tmp_path / "gen"
    for i in range(27):
        d = gen / "claude-opus-4-7-high" / f"c{i:03d}"
        d.mkdir(parents=True)
        (d / "gen.json").write_text("{}")

    # ── forfeit-cause files ──
    (tmp_path / "causes_laptop.json").write_text(json.dumps({
        "alpha": {"forfeits": 2, "causes": {"Mass Constraints": 1, "Apply Material Properties": 1}},
        "solo": {"forfeits": 4, "causes": {"Mass Constraints": 4}},          # partial build: the ledger says 6
    }))
    (tmp_path / "causes_hpc.json").write_text(json.dumps({}))
    return rel


def _args(release, *, shas=(SHA_A, SHA_B, SHA_QUAL)):
    tmp = release.parent
    argv = ["--release", str(release), "--run-id", RUN_ID, "--champions-platform", "hpc",
            "--forfeit-causes", f"laptop={tmp / 'causes_laptop.json'}", "--forfeit-causes", f"hpc={tmp / 'causes_hpc.json'}",
            "--gen-root", str(tmp / "gen")]
    for s in shas:
        argv += ["--sha", s]
    return argv


def _everything(release):
    manifest = json.loads((release / "pack-MANIFEST.json").read_text())
    rules = release_readme.rules_from_run(release / "pool_rr", release / "stage_b")
    summary = release_readme.build_summary(release / "pool_rr", release / "stage_b")
    provenance = release_readme.build_provenance(manifest, summary, rules, shas=[SHA_A, SHA_B, SHA_QUAL], champions_platform="hpc")
    causes = {"laptop": json.loads((release.parent / "causes_laptop.json").read_text()), "hpc": {}}
    forfeits = release_readme.build_forfeits(summary, provenance, causes)
    not_run = release_readme.build_missing(manifest, summary, release.parent / "gen")
    return manifest, rules, summary, provenance, forfeits, not_run


def test_selection_rule_is_the_cluster_readme_wording():
    cluster = (ROOT / "scripts/sampling/cluster/README.md").read_text()
    for line in release_readme.ROUNDS_TABLE:
        assert line in cluster, line
    assert release_readme.SELECTION_RULE == "\n".join(release_readme.ROUNDS_TABLE)
    assert release_readme.ROUND_NAMES == ("Qualification Round", "Top Bot per Run Round", "Top-5 Round", "Champions Round")


def test_build_summary_numbers(release):
    summary = release_readme.build_summary(release / "pool_rr", release / "stage_b")
    assert sorted(summary["models"]) == ["alpha", "solo"]
    alpha = summary["models"]["alpha"]
    assert alpha["n_samples"] == 8 and alpha["eligible"] == 5 and alpha["eligible_per_run"] == [3, 2]
    assert [r["pairings"] for r in alpha["runs"]] == [3, 1] and [r["games"] for r in alpha["runs"]] == [6, 2]
    assert alpha["top_bot_per_run"] == {"pairings": 4, "games": 8, "n_rollouts": 2, "runs_without_round_robin": [], "runs_without_winner": []}
    assert alpha["runs"][0]["winner"]["artifact_id"] == _aid("alpha", 0) and alpha["runs"][0]["ties_at_top"] == [_aid("alpha", 0), _aid("alpha", 1)]
    assert [w["artifact_id"] for w in alpha["run_winners"]] == [_aid("alpha", 0), _aid("alpha", 5)]   # rating 1050 both, lowest index first
    assert {w["artifact_id"]: w["group"] for w in alpha["run_winners"]} == {_aid("alpha", 0): "g0", _aid("alpha", 5): "g1"}
    assert alpha["run_winners"][0]["run_elo"] == 1050.0 and alpha["run_winners"][0]["top5_elo"] == 940.0
    assert alpha["run_winners"][1]["top5_elo"] == 1060.0 and alpha["run_winners"][1]["top5_wld"] == {"wins": 2, "losses": 1, "draws": 0}
    assert alpha["top5_round"]["played"] is True and alpha["top5_round"]["n_games"] == 3
    assert alpha["champion"]["artifact_id"] == _aid("alpha", 5) and alpha["champion"]["source"] == "Top-5 Round winner"
    assert alpha["champion"]["champions_elo"] == 1120.0 and alpha["champion"]["champions_wld"] == {"wins": 3, "losses": 0, "draws": 0}
    assert alpha["exclusions"] == {"forfeit:controller": 1, "forfeit:morphology": 1, "qualification failed": 1}
    assert alpha["exclusion_reasons_raw"]["qualification failed (W1 D1 L1)"] == 1
    assert alpha["git_shas"] == [SHA_A, SHA_B] and alpha["source_roots"] == [HPC_ROOT]

    solo = summary["models"]["solo"]
    assert solo["eligible_per_run"] == [1, 0] and solo["top_bot_per_run"]["games"] == 0
    assert solo["top_bot_per_run"]["runs_without_round_robin"] == ["g0", "g1"] and solo["top_bot_per_run"]["runs_without_winner"] == ["g1"]
    assert len(solo["run_winners"]) == 1 and solo["run_winners"][0]["top5_elo"] is None
    assert solo["top5_round"]["played"] is False and "at least 2" in solo["top5_round"]["skipped"]
    assert solo["champion"]["artifact_id"] == _aid("solo", 0) and solo["champion"]["source"].startswith("lone run winner")
    assert solo["champion"]["champions_elo"] == 880.0
    assert solo["exclusions"] == {"qualification failed": 1, "forfeit:controller": 6}

    cr = summary["champions_round"]
    assert cr["n_games"] == 3 and cr["n_rollouts"] == 3 and cr["participants"] == [_aid("alpha", 5), _aid("solo", 0)]
    assert cr["not_entered"] == {}                       # the scratch dir entry is dropped
    assert [(r["rank"], r["model"]) for r in cr["scoreboard"]] == [(1, "alpha"), (2, "solo")]
    assert summary["totals"] == {"models": 2, "samples": 16, "eligible": 6, "top_bot_per_run_pairings": 4, "top_bot_per_run_games": 8,
                                 "top5_round_games": 3, "top5_rounds_played": 1, "champions_round_games": 3}
    ties = summary["ties"]
    assert ties == [{"where": "run", "model": "alpha", "group": "g0", "bots": [_aid("alpha", 0), _aid("alpha", 1)],
                     "decided": "run winner", "chosen": _aid("alpha", 0), "tie_break": "lowest sample index (pool_rr.py)"}]


def test_run_games_must_match_the_records(release):
    extra = release / "pool_rr/alpha/g1/matches/x_vs_y"
    extra.mkdir()
    (extra / "match_result.json").write_text(json.dumps(_match_result("x", "y", ["red", "red"])))
    with pytest.raises(RuntimeError, match="alpha/g1"):
        release_readme.build_summary(release / "pool_rr", release / "stage_b")


def test_run_winner_must_be_the_runs_top1(release):
    p = release / "pool_rr/alpha/top_5_bots.json"
    doc = json.loads(p.read_text())
    doc["bots"][0]["artifact_id"] = _aid("alpha", 1)     # the other half of the tie, not the declared winner
    p.write_text(json.dumps(doc))
    with pytest.raises(RuntimeError, match="no run's top_1"):
        release_readme.build_summary(release / "pool_rr", release / "stage_b")


def test_champion_needs_a_champions_round_standing(release):
    p = release / "stage_b/top1/elo.json"
    doc = json.loads(p.read_text())
    doc["standings"].pop(_aid("solo", 0))
    p.write_text(json.dumps(doc))
    with pytest.raises(RuntimeError, match="solo"):
        release_readme.build_summary(release / "pool_rr", release / "stage_b")


def test_rules_come_from_the_ledgers_and_must_agree_except_the_sha(release):
    rules = release_readme.rules_from_run(release / "pool_rr", release / "stage_b")
    assert rules["match_time"] == 300.0 and rules["run_seeds"] == 2 and rules["stored_seeds"] == 3
    assert rules["inactivity"] == {"timeout_s": 10.0, "min_displacement_m": 0.5}
    assert rules["score_function"] == "any" and rules["contact_fidelity"] == "high" and rules["physics_mode"] == "3d"
    assert rules["git_shas"] == [SHA_A, SHA_B] and rules["git_shas_by_model"] == {"alpha": [SHA_A, SHA_B], "solo": [SHA_A]}
    assert [c["md5"] for c in rules["config_chain"]] == ["cfgmd5aaaa", "basemd5bbbb"]
    p = release / "pool_rr/solo/g1/pool_ledger.json"
    bad = json.loads(p.read_text())
    bad["match_time"] = 120.0
    p.write_text(json.dumps(bad))
    with pytest.raises(RuntimeError, match="solo/g1"):
        release_readme.rules_from_run(release / "pool_rr", release / "stage_b")


def test_provenance_platforms_and_shas(release):
    manifest, rules, summary, provenance, _, _ = _everything(release)
    assert provenance["models"]["alpha"] == {"qualified_on": "laptop", "round_robins_on": "hpc", "git_shas": [SHA_A, SHA_B],
                                             "source_pack": "/laptop/LOGS-SH250/pack-a/MANIFEST.json"}
    assert provenance["models"]["solo"]["qualified_on"] == "gpu" and provenance["models"]["solo"]["round_robins_on"] == "gpu"
    assert provenance["qualified_on_counts"] == {"laptop": 1, "gpu": 1} and provenance["round_robins_on_counts"] == {"hpc": 1, "gpu": 1}
    assert provenance["champions_round_on"] == "hpc" and provenance["harness_shas_in_ledgers"] == [SHA_A, SHA_B]
    with pytest.raises(RuntimeError, match="not among --sha"):
        release_readme.build_provenance(manifest, summary, rules, shas=[SHA_A], champions_platform="hpc")
    with pytest.raises(ValueError, match="40-hex"):
        release_readme.build_provenance(manifest, summary, rules, shas=[SHA_A[:8], SHA_B], champions_platform="hpc")
    p = release / "pool_rr/alpha/g1/pool_ledger.json"
    doc = json.loads(p.read_text())
    doc["source"]["root"] = GPU_ROOT                                   # alpha's runs would then span two platforms
    p.write_text(json.dumps(doc))
    summary2 = release_readme.build_summary(release / "pool_rr", release / "stage_b")
    with pytest.raises(RuntimeError, match="never mix"):
        release_readme.build_provenance(manifest, summary2, rules, shas=[SHA_A, SHA_B], champions_platform="hpc")


def test_forfeit_causes_by_platform(release):
    _, _, summary, provenance, forfeits, _ = _everything(release)
    assert forfeits["alpha"] == {"forfeits": 2, "by_stage": {"controller": 1, "morphology": 1},
                                 "causes": {"Mass Constraints": 1, "Apply Material Properties": 1}, "causes_source": "laptop",
                                 "causes_partial": False, "causes_cover": 2, "note": None}
    assert forfeits["solo"]["forfeits"] == 6 and forfeits["solo"]["causes_partial"] is True and forfeits["solo"]["causes_cover"] == 4
    # an authoritative file that disagrees with the ledger is refused
    with pytest.raises(RuntimeError, match="alpha"):
        release_readme.build_forfeits(summary, provenance, {"laptop": {"alpha": {"forfeits": 3, "causes": {}}, "solo": {"forfeits": 4, "causes": {}}}})
    # a note's cause must exist in the file (the count is read from it)
    release_readme.FORFEIT_CAUSE_NOTES["alpha"] = ("Apply Material Properties", "mesh must be closed", "mesh failures")
    try:
        got = release_readme.build_forfeits(summary, provenance, {"laptop": json.loads((release.parent / "causes_laptop.json").read_text())})
        assert got["alpha"]["note"] == ('its 2 forfeits are recorded with forfeit_stage "controller", "morphology", but 1 of them are '
                                        '"Apply Material Properties: mesh must be closed" — mesh failures')
    finally:
        del release_readme.FORFEIT_CAUSE_NOTES["alpha"]


def test_render_readme_contains_the_contract(release):
    manifest, rules, summary, provenance, _, _ = _everything(release)
    text = release_readme.render_readme(manifest, summary, rules, provenance, run_id=RUN_ID,
                                        prompt_md5=manifest["prompt_md5"], generated_at=GENERATED_AT)
    assert release_readme.SELECTION_RULE in text
    for name in release_readme.ROUND_NAMES:
        assert name in text
    assert "Stage A" not in text and "Stage B" not in text and "stage A" not in text
    assert "zero-shot samples per model" in text and "frozen prompt" in text
    # the rule table
    for cell in ("300 s", "| 2 |", "| 3 |", "10 s / 0.5 m", "`any`", "`high`", "`3d`", "draws counted as half a win", "cfgmd5aaaa"):
        assert cell in text, cell
    # the scoreboard: Champions Round rows sorted by Elo
    assert "## Scoreboard — Champions Round" in text
    i_alpha = text.index(f"| 1 | alpha | `{_aid('alpha', 5)}` | 1120.0 | 3-0-0 | 3 |")
    i_solo = text.index(f"| 2 | solo | `{_aid('solo', 0)}` | 880.0 | 0-3-0 | 3 |")
    assert i_alpha < i_solo
    # the per-model table: qualified per run, run winners with run rating, Top-5 Round Elos, champion
    assert "| alpha | 8 | 3 / 2 (5) | 8 | g0 `t00` 1050.0<br>g1 `t05` 1050.0 | `t05` 1060.0 2-1-0<br>`t00` 940.0 1-2-0 | `t05` 1120.0 (3-0-0) |" in text
    assert "| solo | 8 | 1 / 0 (1) | 0 | g0 `t00` 1000.0 | skipped: top_5_bots.json lists 1 bot(s); a round robin needs at least 2 | `t00` 880.0 (0-3-0) — lone run winner (Top-5 Round skipped) |" in text
    # declared ties
    assert "## Declared ties" in text and f"alpha run g0: `{_aid('alpha', 0)}`, `{_aid('alpha', 1)}` tied" in text
    assert "lowest sample index" in text
    # provenance: every sha, the range note, the prompt md5, config md5s, platforms per model, the GPU-cluster reports
    for s in (SHA_A, SHA_B, SHA_QUAL):
        assert f"`{s[:8]}`" in text
    assert release_readme.HARNESS_RANGE_NOTE in text
    assert manifest["prompt_md5"] in text and "basemd5bbbb" in text and "configs/tournaments/base.yaml" in text
    assert "| alpha | laptop | hpc | `aaaaaaaa`, `bbbbbbbb` |" in text
    assert "| solo | gpu | gpu | `aaaaaaaa` |" in text
    assert "the Champions Round ran on hpc" in text
    for url in release_readme.GPU_REPORTS:
        assert url in text
    assert GENERATED_AT in text and RUN_ID in text
    # artifact-id mapping + layout
    assert "`<model>__tNNN_c000`" in text and "`samples/<model>/cNNN`" in text
    assert "pool_rr/<model>/g<k>/matches/<a>_vs_<b>/match_result.json" in text
    assert "stage_b/top1/elo.json" in text and "standings/summary.json" in text and "verify/" in text
    # changelog, dated from generated_at
    assert "## Changelog" in text and f"- 2026-09-21 — SH-250 pool tournament `{RUN_ID}`" in text
    assert "<fill in>" not in text and "TODO" not in text


def test_render_missing_lists_every_absence(release):
    _, _, summary, _, forfeits, not_run = _everything(release)
    assert not_run == {"claude-opus-4-7-high": {"generated": 27, "packed": False, "reason": "killed by operator 2026-09-18"}}
    text = release_readme.render_missing(summary, forfeits, not_run)
    assert "claude-opus-4-7-high: 27 samples generated, tournament not run (killed by operator 2026-09-18)" in text
    # per-model exclusion counts by reason, forfeits by stage
    assert "forfeit:morphology" in text and "forfeit:controller" in text
    assert "| alpha | 8 | 5 | 0 | 0 | 1 | 1 | 0 | 1 |" in text
    assert "| solo | 8 | 1 | 0 | 0 | 0 | 6 | 0 | 1 |" in text
    # forfeit causes with their source, the partial build labelled
    assert "| alpha | 2 | controller 1, morphology 1 | Apply Material Properties 1; Mass Constraints 1 | laptop |" in text
    assert "| solo | 6 | controller 6 | Mass Constraints 4 | laptop (partial build: 4 of 6 covered) |" in text
    # runs of 0 / 1 bots, the skipped Top-5 Round, the Champions Round
    assert "solo g0 (slots 0–3): one eligible bot" in text and "solo g1 (slots 4–7): no eligible bot" in text
    assert "## Top-5 Round skipped" in text and "solo: top_5_bots.json lists 1 bot(s)" in text and "champion by default" in text
    assert "## Champions Round" in text and "claude-opus-4-7-high: tournament not run" in text
    # telemetry
    assert "Top Bot per Run Round `match_data.json` is **not stored**" in text and "size" in text
    assert "Stage A" not in text and "Stage B" not in text
    assert "<fill in>" not in text


def test_build_missing_refuses_an_unexplained_absent_model(release):
    manifest = json.loads((release / "pack-MANIFEST.json").read_text())
    manifest["models"]["ghost"] = {"n_samples": 2, "eligible": 0, "qualified_on": "laptop",
                                   "ledger": [_ledger_row("ghost", 0, "not qualified yet"), _ledger_row("ghost", 1, "not generated")]}
    summary = release_readme.build_summary(release / "pool_rr", release / "stage_b")
    with pytest.raises(RuntimeError, match="ghost"):
        release_readme.build_missing(manifest, summary, release.parent / "gen")
    del manifest["models"]["ghost"]
    with pytest.raises(RuntimeError, match="gen-root"):
        release_readme.build_missing(manifest, summary, None)


def test_main_writes_the_three_files(release):
    rc = release_readme.main(_args(release))
    assert rc == 0
    readme = (release / "README.md").read_text()
    missing = (release / "MISSING.md").read_text()
    summary = json.loads((release / "standings/summary.json").read_text())
    assert release_readme.SELECTION_RULE in readme and RUN_ID in readme
    assert "claude-opus-4-7-high: 27 samples generated" in missing
    assert summary["run_id"] == RUN_ID and summary["rounds"] == list(release_readme.ROUND_NAMES)
    assert summary["provenance"]["harness_shas"] == [SHA_A, SHA_B, SHA_QUAL]
    assert summary["models"]["alpha"]["champion"]["champions_elo"] == 1120.0
    assert summary["champions_round"]["scoreboard"][0]["model"] == "alpha"
    assert summary["forfeits"]["solo"]["causes_partial"] is True
    assert summary["not_run"]["claude-opus-4-7-high"]["generated"] == 27
    assert summary["prompt_md5"] == json.loads((release / "pack-MANIFEST.json").read_text())["prompt_md5"]


def test_main_refuses_a_sha_or_prompt_mismatch(release):
    with pytest.raises(SystemExit, match="not among --sha"):
        release_readme.main(_args(release, shas=(SHA_A,)))
    (release / "sampling_prompt.md").write_text("tampered")
    with pytest.raises(SystemExit, match="prompt"):
        release_readme.main(_args(release))
