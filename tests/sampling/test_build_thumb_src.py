"""build_thumb_src: one pairing dir per zoo roster bot (champions + run-winners), named with SITE
aids, holding the pairing's composed.xml and a one-frame match_data.json (a single seed key) so the
app's thumbnail bake (precompute-wasm-thumbnails.mjs) can compile the first frame without reading a
full 30,000-step telemetry file."""
import gzip
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/sampling"))
from website import build_thumb_src as T  # noqa: E402


def _pairing(root, red, blue, seeds):
    d = root / f"{red}_vs_{blue}"; d.mkdir(parents=True)
    (d / "composed.xml").write_text(f"<mujoco model='{red}|{blue}'><compiler meshdir='/abs'/></mujoco>")
    res = {"red_bot": red, "blue_bot": blue, "n_seeds": len(seeds), "matches": [
        {"seed": s, "winner": "red" if i % 2 == 0 else "tie", "num_steps": 10 + i, "termination_reason": "ring_out", "physics_unstable": False} for i, s in enumerate(seeds)]}
    (d / "match_result.json").write_text(json.dumps(res))
    data = {f"seed_{s}": {"seed": s, "winner": m["winner"], "num_steps": m["num_steps"], "control_dt": 0.01, "termination_reason": "ring_out",
                          "physics_unstable": False, "qpos": [[float(s)] * 3] * m["num_steps"], "initial_qpos": [0.0] * 3,
                          "red_positions": [[1.0, 2.0, 3.0]] * m["num_steps"], "blue_positions": [[4.0, 5.0, 6.0]] * m["num_steps"],
                          "red_actuator_names": ["a"], "blue_actuator_names": ["b"]} for s, m in zip(seeds, res["matches"])}
    with gzip.open(d / "match_data.json.gz", "wt") as f: json.dump(data, f)


def _roster(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema": "sh250-bots-index-v1", "bots": [
        {"artifact_id": aid, "tournament_id": tid, "model": tid.rsplit("__t", 1)[0], "role": role} for aid, tid, role in rows]}))


def test_one_dir_per_roster_bot_with_one_frame(tmp_path):
    rr = tmp_path / "rr"; top1 = rr / "stage_b" / "top1" / "matches"
    _pairing(top1, "m1__t00_c000", "m2__t05_c000", [42, 43])     # A vs B
    _pairing(top1, "m1__t00_c000", "m3__t01_c000", [42, 43])     # A vs D
    _pairing(top1, "m2__t05_c000", "m3__t01_c000", [42, 43])     # B vs D
    (top1 / "env.xml").write_text("<mujoco/>")                   # a stray file next to the pairing dirs, as in the real tree
    _pairing(rr / "stage_b" / "top5" / "m1" / "matches", "m1__t00_c000", "m1__t07_c000", [53, 54])   # A vs C (Top-5 Round)
    index = tmp_path / "bots" / "index.json"
    _roster(index, [("m1__sampling__t000_c000", "m1__t00_c000", "champion"), ("m2__sampling__t005_c000", "m2__t05_c000", "champion"),
                    ("m3__sampling__t001_c000", "m3__t01_c000", "champion"), ("m1__sampling__t007_c000", "m1__t07_c000", "run-winner"),
                    ("m1__sampling__t003_c000", "m1__t03_c000", "qualified"), ("m1__sampling__t004_c000", "m1__t04_c000", "not-qualified")])
    out = tmp_path / "thumb-src"
    assert T.build(rr, index, out) == {"roster": 4, "dirs": 4}
    dirs = sorted(p.name for p in (out / "matches").iterdir())
    assert dirs == ["m1__sampling__t000_c000_vs_m1__sampling__t007_c000", "m1__sampling__t000_c000_vs_m2__sampling__t005_c000",
                    "m1__sampling__t000_c000_vs_m3__sampling__t001_c000", "m2__sampling__t005_c000_vs_m3__sampling__t001_c000"]
    d = out / "matches" / "m1__sampling__t000_c000_vs_m2__sampling__t005_c000"
    assert d.joinpath("composed.xml").read_text().startswith("<mujoco model='m1__t00_c000|m2__t05_c000'>")
    data = json.loads(d.joinpath("match_data.json").read_text())
    assert list(data) == ["seed_42"]
    rec = data["seed_42"]
    assert rec == {"seed": 42, "winner": "red", "num_steps": 10, "control_dt": 0.01, "termination_reason": "ring_out", "physics_unstable": False,
                   "qpos": [[42.0, 42.0, 42.0]], "red_positions": [[1.0, 2.0, 3.0]], "blue_positions": [[4.0, 5.0, 6.0]],
                   "red_actuator_names": ["a"], "blue_actuator_names": ["b"]}
    top5 = json.loads((out / "matches" / "m1__sampling__t000_c000_vs_m1__sampling__t007_c000" / "match_data.json").read_text())
    assert list(top5) == ["seed_53"] and len(top5["seed_53"]["qpos"]) == 1


def test_refuses_a_roster_bot_without_a_pairing(tmp_path):
    rr = tmp_path / "rr"
    _pairing(rr / "stage_b" / "top1" / "matches", "m1__t00_c000", "m2__t05_c000", [42])
    (rr / "stage_b" / "top5").mkdir(parents=True)
    index = tmp_path / "bots" / "index.json"
    _roster(index, [("m1__sampling__t000_c000", "m1__t00_c000", "champion"), ("m1__sampling__t007_c000", "m1__t07_c000", "run-winner")])
    with pytest.raises(RuntimeError, match="m1__t07_c000"):
        T.build(rr, index, tmp_path / "thumb-src")
