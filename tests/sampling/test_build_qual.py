"""build_qual: every sampled bot's Qualification Round (3 x 20 s vs the stationary block) becomes
qual/<aid>/result.json (the official match_result.json verbatim + per-seed rows), and — only where
the OFFICIAL telemetry sits on the laptop (platform == laptop and the laptop match_result.json is
byte-identical to the release's) — one browser-match-trace-v1 capsule per seed. Cluster / GPU-cluster
telemetry is "pending" (results only; laptop re-simulations are never used: arm64 physics diverges),
forfeits are "none". Telemetry that disagrees with the official result is refused; stale
tournament_00.stale-* dirs are skipped."""
import gzip
import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/sampling"))
from website import build_qual as Q  # noqa: E402
from website.site_ids import qual_task_id  # noqa: E402

LAPTOP = "lap-model"
CLUSTER = "clu-model"


def _result(seeds):
    return {"red_bot": "bot", "blue_bot": "", "tool_name": "stationary", "n_seeds": len(seeds), "matches": [
        {"seed": s, "winner": w, "num_steps": 100 + i, "combat_metrics": {"composite": 3.0}, "combat_metrics_b": {"composite": 1.0},
         "termination_reason": "ring_out" if w == "red" else "timeout", "initial_distance": 7.1,
         "initial_red_com": [-3.0, 0.0, 2.1], "initial_blue_com": [4.0, -1.3, 2.1], "physics_unstable": False}
        for i, (s, w) in enumerate(seeds)],
        "qualification_score": 4.14, "combat_avg_score": 4.14, "wins": sum(1 for _, w in seeds if w == "red")}


def _telemetry(qdir, res, composed="<mujoco model='q'><compiler meshdir='/abs'/></mujoco>", gz=True):
    qdir.mkdir(parents=True, exist_ok=True)
    (qdir / "composed.xml").write_text(composed)
    (qdir / "block.xml").write_text("<mujoco model='block'/>")
    data = {f"seed_{m['seed']}": {"seed": m["seed"], "winner": m["winner"], "num_steps": m["num_steps"], "winner_step": m["num_steps"] - 1,
                                   "qpos": [[0.0] * 4] * m["num_steps"], "initial_qpos": [0.0] * 4, "control_dt": 0.01,
                                   "red_actuator_names": ["m1", "m2"], "blue_actuator_names": [], "termination_reason": m["termination_reason"],
                                   "physics_unstable": False, "combat_metrics": m["combat_metrics"]} for m in res["matches"]}
    if gz:
        with gzip.open(qdir / "match_data.json.gz", "wt") as f:
            json.dump(data, f)
    else:
        (qdir / "match_data.json").write_text(json.dumps(data))
    return data


def _bot(bots, model, n, platform, *, qual, reason=None):
    aid = f"{model}__sampling__t{n:03d}_c000"
    d = bots / aid; d.mkdir(parents=True)
    w, dr, l = qual if qual else (0, 0, 0)
    passed = bool(qual and w == 3)
    if reason is None:
        reason = None if passed else ("forfeit:controller" if not qual else f"qualification failed (W{w} D{dr} L{l})")
    (d / "bot.json").write_text(json.dumps({"schema": "sh250-bot-v1", "artifact_id": aid, "model": model, "sample_index": n,
        "qualification": {"platform": platform, "wins": w, "draws": dr, "losses": l, "score": 4.14 if qual else None,
                          "passed": passed, "reason": reason}}))
    return {"artifact_id": aid, "tournament_id": f"{model}__t{n:02d}_c000", "model": model, "sample_index": n, "role": "qualified" if qual else "not-qualified", "qualified": bool(qual)}


def _laptop_qdir(gen, model, n, stale=False):
    t = "tournament_00.stale-20260918T190904Z" if stale else "tournament_00"
    return gen / model / f"c{n:03d}" / t / "round_robin_match" / "bots" / model / "refinement" / "commit_0" / "qualification"


def _tree(tmp_path):
    gen = tmp_path / "gen"; rel = tmp_path / "release"; bots = tmp_path / "bots"; assets = tmp_path / "assets"
    assets.mkdir(); (assets / "octagon_platform.obj").write_bytes(b"v 0 0 0\n"); (assets / "octagon_surface.obj").write_bytes(b"v 1 1 1\n")
    rows = []
    # laptop sample 0: official telemetry (gz), 3 wins
    res0 = _result([(0, "red"), (1, "red"), (2, "red")])
    q0 = _laptop_qdir(gen, LAPTOP, 0); _telemetry(q0, res0)
    (q0 / "match_result.json").write_text(json.dumps(res0))
    r0 = rel / "samples" / LAPTOP / "c000" / "qualification"; r0.mkdir(parents=True); (r0 / "match_result.json").write_text(json.dumps(res0))
    rows.append(_bot(bots, LAPTOP, 0, "laptop", qual=(3, 0, 0)))
    # laptop sample 1: official telemetry as plain match_data.json, 1 win 1 draw 1 loss; plus a stale dir with garbage
    res1 = _result([(0, "red"), (1, "tie"), (2, "blue")])
    q1 = _laptop_qdir(gen, LAPTOP, 1); _telemetry(q1, res1, gz=False)
    (q1 / "match_result.json").write_text(json.dumps(res1))
    qs = _laptop_qdir(gen, LAPTOP, 1, stale=True); _telemetry(qs, _result([(0, "blue"), (1, "blue"), (2, "blue")]))
    (qs / "match_result.json").write_text("{}")
    r1 = rel / "samples" / LAPTOP / "c001" / "qualification"; r1.mkdir(parents=True); (r1 / "match_result.json").write_text(json.dumps(res1))
    rows.append(_bot(bots, LAPTOP, 1, "laptop", qual=(1, 1, 1)))
    # laptop sample 2: forfeit (never fought)
    rows.append(_bot(bots, LAPTOP, 2, "laptop", qual=None))
    # laptop sample 3: the round was played, a seed went physics-unstable → the harness scored -inf and
    # ruled forfeit:controller (ledger W-D-L null → bot.json 0-0-0); official telemetry exists
    res3 = _result([(0, "blue"), (1, "blue"), (2, "blue")]); res3["qualification_score"] = -1.0
    res3["matches"][2]["physics_unstable"] = True; res3["matches"][2]["termination_reason"] = "qacc"
    q3 = _laptop_qdir(gen, LAPTOP, 3); _telemetry(q3, res3)
    (q3 / "match_result.json").write_text(json.dumps(res3))
    r3 = rel / "samples" / LAPTOP / "c003" / "qualification"; r3.mkdir(parents=True); (r3 / "match_result.json").write_text(json.dumps(res3))
    rows.append(_bot(bots, LAPTOP, 3, "laptop", qual=None, reason="forfeit:controller"))
    # cluster sample 0: official result only (a laptop replay exists but must be ignored)
    res2 = _result([(0, "red"), (1, "red"), (2, "red")])
    r2 = rel / "samples" / CLUSTER / "c000" / "qualification"; r2.mkdir(parents=True); (r2 / "match_result.json").write_text(json.dumps(res2))
    qc = _laptop_qdir(gen, CLUSTER, 0); _telemetry(qc, _result([(0, "blue"), (1, "red"), (2, "red")]))
    (qc / "match_result.json").write_text(json.dumps(_result([(0, "blue"), (1, "red"), (2, "red")])))
    rows.append(_bot(bots, CLUSTER, 0, "hpc", qual=(3, 0, 0)))
    (bots / "index.json").write_text(json.dumps({"schema": "sh250-bots-index-v1", "run_id": "final-sh250-5ac92bc7", "bots": rows}))
    return gen, rel, bots, assets


def test_builds_results_and_official_capsules(tmp_path):
    gen, rel, bots, assets = _tree(tmp_path)
    out = tmp_path / "qual"
    counts = Q.build(gen, rel, bots, assets, out)
    assert counts["total"] == {"samples": 5, "fought": 4, "official": 3, "pending": 1, "none": 1}
    assert counts["models"][LAPTOP] == {"samples": 4, "fought": 3, "official": 3, "pending": 0, "none": 1}
    assert counts["models"][CLUSTER] == {"samples": 1, "fought": 1, "official": 0, "pending": 1, "none": 0}
    idx = json.loads((out / "index.json").read_text())
    assert idx["schema"] == "sh250-qual-index-v1" and idx["total"] == counts["total"] and idx["models"] == counts["models"]

    a0 = f"{LAPTOP}__sampling__t000_c000"
    r = json.loads((out / a0 / "result.json").read_text())
    assert r["schema"] == "sh250-qual-v1" and r["artifact_id"] == a0 and r["model"] == LAPTOP and r["sample_index"] == 0
    assert r["platform"] == "laptop" and r["fought"] is True and r["telemetry"] == "official" and r["pending_reason"] is None and r["reason"] is None
    assert r["result"] == json.loads((rel / "samples" / LAPTOP / "c000" / "qualification" / "match_result.json").read_text())
    assert (r["wins"], r["draws"], r["losses"], r["passed"]) == (3, 0, 0, True)
    assert [s["capsule"] for s in r["seeds"]] == [f"qual/{a0}/seed_{i}.json.gz" for i in range(3)]
    assert r["seeds"][1] == {"seed_idx": 1, "seed": 1, "winner": "red", "num_steps": 101, "termination_reason": "ring_out",
                             "physics_unstable": False, "capsule": f"qual/{a0}/seed_1.json.gz"}
    cap = json.load(gzip.open(out / a0 / "seed_1.json.gz", "rt"))
    assert cap["qpos_log"] and "qpos" not in cap and cap["initial_qpos"] == [0.0] * 4 and cap["num_steps"] == 101
    assert cap["composed_xml"].startswith("<mujoco model='q'") and set(cap["assets"]) == {"assets/octagon_platform.obj", "assets/octagon_surface.obj"}
    assert cap["mujoco_version"] == Q.MUJOCO_VERSION == "3.10.0" and cap["wall_seconds"] is None and cap["fixture"].startswith("ft-")
    assert cap["meta"] == {"name": f"{a0}_vs_stationary-block", "red_bot": a0, "blue_bot": "stationary-block", "seed": 1, "max_steps": 2000,
                           "red_actuators": ["m1", "m2"], "blue_actuators": [], "red_xml_pipeline": "sh250", "blue_xml_pipeline": "sh250-block",
                           "assets": ["octagon_platform.obj", "octagon_surface.obj"], "round": "qualification",
                           "task_id": "final-sh250-5ac92bc7:qual:0:1"}
    assert cap["meta"]["task_id"] == qual_task_id(0, 1)

    # plain match_data.json + stale dir skipped: sample 1 gets capsules from the live dir, W-D-L 1-1-1, not passed
    a1 = f"{LAPTOP}__sampling__t001_c000"
    r1 = json.loads((out / a1 / "result.json").read_text())
    assert r1["telemetry"] == "official" and (r1["wins"], r1["draws"], r1["losses"], r1["passed"]) == (1, 1, 1, False)
    assert r1["reason"] == "qualification failed (W1 D1 L1)"
    assert [s["winner"] for s in r1["seeds"]] == ["red", "tie", "blue"]
    cap1 = json.load(gzip.open(out / a1 / "seed_0.json.gz", "rt"))
    assert cap1["winner"] == "red" and cap1["meta"]["task_id"] == "final-sh250-5ac92bc7:qual:1:0"

    # forfeit: never fought
    a2 = f"{LAPTOP}__sampling__t002_c000"
    r2 = json.loads((out / a2 / "result.json").read_text())
    assert r2["fought"] is False and r2["telemetry"] == "none" and r2["result"] is None and r2["seeds"] == [] and r2["pending_reason"] is None
    assert (r2["wins"], r2["draws"], r2["losses"], r2["passed"]) == (0, 0, 0, False) and r2["reason"] == "forfeit:controller"
    assert not list((out / a2).glob("seed_*"))

    # played-then-ruled-forfeit: fought, official capsules, result verbatim (score -1.0, unstable seed), W-D-L 0-0-0 from bot.json
    a4 = f"{LAPTOP}__sampling__t003_c000"
    r4 = json.loads((out / a4 / "result.json").read_text())
    assert r4["fought"] is True and r4["telemetry"] == "official" and r4["reason"] == "forfeit:controller" and r4["passed"] is False
    assert (r4["wins"], r4["draws"], r4["losses"]) == (0, 0, 0) and r4["result"]["qualification_score"] == -1.0
    assert [s["winner"] for s in r4["seeds"]] == ["blue"] * 3 and r4["seeds"][2]["physics_unstable"] is True
    assert all(s["capsule"] == f"qual/{a4}/seed_{i}.json.gz" for i, s in enumerate(r4["seeds"]))

    # cluster: official result verbatim, no capsules, laptop replay ignored
    a3 = f"{CLUSTER}__sampling__t000_c000"
    r3 = json.loads((out / a3 / "result.json").read_text())
    assert r3["platform"] == "hpc" and r3["fought"] is True and r3["telemetry"] == "pending"
    assert r3["pending_reason"] == ("official telemetry recorded on hpc; not yet mirrored to the laptop — "
                                    "laptop replays are not used because arm64 physics diverges")
    assert [s["winner"] for s in r3["seeds"]] == ["red", "red", "red"] and all(s["capsule"] is None for s in r3["seeds"])
    assert not list((out / a3).glob("seed_*"))

    listing = (out / "capsules.txt").read_text().split()
    assert listing == [f"qual/{a}/seed_{i}.json.gz" for a in (a0, a1, a4) for i in range(3)]


def test_refuses_mismatched_telemetry(tmp_path):
    gen, rel, bots, assets = _tree(tmp_path)
    p = _laptop_qdir(gen, LAPTOP, 0) / "match_data.json.gz"
    d = json.load(gzip.open(p, "rt")); d["seed_2"]["winner"] = "blue"
    with gzip.open(p, "wt") as f:
        json.dump(d, f)
    with pytest.raises(RuntimeError, match="winner"):
        Q.build(gen, rel, bots, assets, tmp_path / "qual")


def test_refuses_laptop_result_that_is_not_the_official_one(tmp_path):
    """A laptop-platform sample whose laptop match_result.json differs from the release's is not
    'official' — and since the release says it was qualified on the laptop, that is an inventory
    error, not a pending mirror: refuse."""
    gen, rel, bots, assets = _tree(tmp_path)
    lr = _laptop_qdir(gen, LAPTOP, 0) / "match_result.json"
    d = json.loads(lr.read_text()); d["qualification_score"] = 9.99
    lr.write_text(json.dumps(d))
    with pytest.raises(RuntimeError, match="md5"):
        Q.build(gen, rel, bots, assets, tmp_path / "qual")


def test_refuses_wdl_disagreeing_with_bot_json(tmp_path):
    gen, rel, bots, assets = _tree(tmp_path)
    bj = bots / f"{CLUSTER}__sampling__t000_c000" / "bot.json"
    d = json.loads(bj.read_text()); d["qualification"]["wins"] = 2; d["qualification"]["losses"] = 1
    bj.write_text(json.dumps(d))
    with pytest.raises(RuntimeError, match="W-D-L"):
        Q.build(gen, rel, bots, assets, tmp_path / "qual")


def test_refuses_forfeit_ruling_without_an_unstable_seed(tmp_path):
    """bot.json says forfeit (0-0-0) but the official result is an ordinary 0-0-3 with stable physics:
    the forfeit ruling is unexplained → refuse."""
    gen, rel, bots, assets = _tree(tmp_path)
    rr = rel / "samples" / LAPTOP / "c003" / "qualification" / "match_result.json"
    d = json.loads(rr.read_text()); d["matches"][2]["physics_unstable"] = False; d["qualification_score"] = 0.0
    rr.write_text(json.dumps(d))
    lr = _laptop_qdir(gen, LAPTOP, 3) / "match_result.json"; lr.write_text(json.dumps(d))
    with pytest.raises(RuntimeError, match="forfeit"):
        Q.build(gen, rel, bots, assets, tmp_path / "qual")


def test_cluster_root_makes_its_platform_official(tmp_path):
    """A second telemetry root, keyed by platform, turns that platform's samples official —
    the laptop's replay of the same sample is still never consulted."""
    gen, rel, bots, assets = _tree(tmp_path)
    hpc_state = tmp_path / "gen-hpc"
    res2 = json.loads((rel / "samples" / CLUSTER / "c000" / "qualification" / "match_result.json").read_text())
    qe = _laptop_qdir(hpc_state, CLUSTER, 0); _telemetry(qe, res2)
    (qe / "match_result.json").write_text(json.dumps(res2))
    out = tmp_path / "qual"
    counts = Q.build({"laptop": gen, "hpc": hpc_state}, rel, bots, assets, out)
    assert counts["models"][CLUSTER] == {"samples": 1, "fought": 1, "official": 1, "pending": 0, "none": 0}
    r = json.loads((out / f"{CLUSTER}__sampling__t000_c000" / "result.json").read_text())
    assert r["telemetry"] == "official" and r["pending_reason"] is None and r["seeds"][0]["capsule"] == f"qual/{CLUSTER}__sampling__t000_c000/seed_0.json.gz"
    cap = json.load(gzip.open(out / f"{CLUSTER}__sampling__t000_c000" / "seed_0.json.gz", "rt"))
    assert cap["winner"] == "red" and cap["meta"]["red_bot"] == f"{CLUSTER}__sampling__t000_c000"


def test_cluster_root_missing_a_sample_is_refused(tmp_path):
    gen, rel, bots, assets = _tree(tmp_path)
    hpc_state = tmp_path / "gen-hpc"; hpc_state.mkdir()
    with pytest.raises(RuntimeError, match="no telemetry"):
        Q.build({"laptop": gen, "hpc": hpc_state}, rel, bots, assets, tmp_path / "qual")

