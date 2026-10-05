"""build_capsules: every Top-5 Round + Champions Round game's telemetry record becomes one
browser-match-trace-v1 capsule (no re-simulation), plus pairings.json (the Node builder's only
input for matches/) and the bare-sha capsule listing. Telemetry that disagrees with
match_result.json is refused."""
import gzip
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/sampling"))
from website import build_capsules as C  # noqa: E402
from website.site_ids import capsule_sha  # noqa: E402


def _pairing(root, red, blue, seeds):
    d = root / f"{red}_vs_{blue}"; d.mkdir(parents=True)
    (d / "composed.xml").write_text("<mujoco model='x'><compiler meshdir='/abs'/></mujoco>")
    res = {"red_bot": red, "blue_bot": blue, "n_seeds": len(seeds), "matches": [
        {"seed": s, "winner": "red" if i % 2 == 0 else "tie", "num_steps": 10 + i, "termination_reason": "ring_out", "physics_unstable": False} for i, s in enumerate(seeds)]}
    (d / "match_result.json").write_text(json.dumps(res))
    data = {f"seed_{s}": {"seed": s, "winner": m["winner"], "num_steps": m["num_steps"], "winner_step": 1, "qpos": [[0.0] * 3] * m["num_steps"],
                          "initial_qpos": [0.0] * 3, "red_actuator_names": ["a"], "blue_actuator_names": ["b"], "termination_reason": "ring_out",
                          "physics_unstable": False} for s, m in zip(seeds, res["matches"])}
    with gzip.open(d / "match_data.json.gz", "wt") as f: json.dump(data, f)


def _assets(tmp_path):
    a = tmp_path / "assets"; a.mkdir()
    (a / "octagon_platform.obj").write_bytes(b"v 0 0 0\n"); (a / "octagon_surface.obj").write_bytes(b"v 1 1 1\n")
    return a


def test_capsules_and_pairings(tmp_path):
    rr = tmp_path / "rr"; assets = _assets(tmp_path)
    _pairing(rr / "stage_b" / "top1" / "matches", "m1__t00_c000", "m2__t05_c000", [42, 43])
    _pairing(rr / "stage_b" / "top5" / "m1" / "matches", "m1__t00_c000", "m1__t07_c000", [53, 54])
    out = tmp_path / "site"
    assert C.build(rr, assets, out, n_seeds=2) == {"pairings": 2, "games": 4}
    pairings = json.loads((out / "pairings.json").read_text())["pairings"]
    assert [p["round"] for p in pairings] == ["champions", "top5"] and [p["pair_idx"] for p in pairings] == [0, 1]
    assert pairings[0]["red"] == "m1__sampling__t000_c000" and pairings[0]["blue"] == "m2__sampling__t005_c000" and pairings[1]["model"] == "m1"
    s0 = pairings[0]["seeds"][0]
    assert s0 == {"seed_idx": 0, "seed": 42, "task_id": "final-sh250-5ac92bc7:pair:0:0", "sha": capsule_sha("final-sh250-5ac92bc7:pair:0:0"),
                  "winner": "red", "num_steps": 10, "termination_reason": "ring_out", "physics_unstable": False}
    cap = json.load(gzip.open(out / "replays" / f"{s0['sha']}.json.gz", "rt"))
    assert cap["qpos_log"] and "qpos" not in cap and cap["initial_qpos"] == [0.0] * 3
    assert cap["composed_xml"].startswith("<mujoco") and set(cap["assets"]) == {"assets/octagon_platform.obj", "assets/octagon_surface.obj"}
    assert cap["meta"]["red_bot"] == "m1__sampling__t000_c000" and cap["meta"]["seed"] == 42 and cap["meta"]["task_id"] == s0["task_id"] and cap["meta"]["round"] == "champions"
    listing = (out / "capsules-final-sh250-5ac92bc7.txt").read_text().split()
    assert len(listing) == 4 and listing[0] == s0["sha"]


def test_refuses_mismatched_telemetry(tmp_path):
    rr = tmp_path / "rr"; assets = _assets(tmp_path)
    _pairing(rr / "stage_b" / "top1" / "matches", "m1__t00_c000", "m2__t05_c000", [42, 43])
    p = rr / "stage_b" / "top1" / "matches" / "m1__t00_c000_vs_m2__t05_c000" / "match_data.json.gz"
    d = json.load(gzip.open(p, "rt")); d["seed_42"]["winner"] = "blue"
    with gzip.open(p, "wt") as f: json.dump(d, f)
    with pytest.raises(RuntimeError, match="winner"):
        C.build(rr, assets, tmp_path / "site", n_seeds=2)


def test_refuses_wrong_seed_count(tmp_path):
    rr = tmp_path / "rr"; assets = _assets(tmp_path)
    _pairing(rr / "stage_b" / "top1" / "matches", "m1__t00_c000", "m2__t05_c000", [42])
    with pytest.raises(RuntimeError, match="seeds"):
        C.build(rr, assets, tmp_path / "site", n_seeds=2)
