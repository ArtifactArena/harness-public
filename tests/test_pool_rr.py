"""pool_rr: eligibility → every pairing → BT standings, resumable, telemetry and video off."""
import json, shutil, sys
from pathlib import Path
import pytest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/sampling"))
import pool_rr  # noqa: E402

BASE = ROOT / "mjarena/core/assets/baseline_bots"
IDS = {"m__t00_c000", "m__t01_c000", "m__t07_c000"}


def _pack_slot(pack, model, idx, src):
    d = pack / model / f"c{idx:03d}"; (d / "commit_0").mkdir(parents=True)
    for name in ("robot.xml", "controller.py"):
        shutil.copy(src / name, d / "commit_0" / name); shutil.copy(src / name, d / name)
    (d / "gen.json").write_text("{}")
    (d / "bot_artifact.json").write_text(json.dumps({"forfeit": False, "forfeit_stage": ""}))
    (d / "journal.json").write_text(json.dumps({"commits": [{"validation_passed": True, "qualification_passed": True, "score": 1.0}]}))
    (d / "qualification").mkdir(exist_ok=True)
    (d / "qualification/match_result.json").write_text(json.dumps({"red_bot": "bot", "blue_bot": "", "n_seeds": 3,
        "matches": [{"seed": i, "winner": "red", "num_steps": 100, "termination_reason": "ring_out"} for i in range(3)]}))


def _srcs():
    return sorted(x for x in BASE.iterdir() if (x / "robot.xml").exists() and (x / "controller.py").exists())[:2]


@pytest.fixture
def pack(tmp_path):
    p = tmp_path / "pack"
    a, b = _srcs()
    _pack_slot(p, "m", 0, a); _pack_slot(p, "m", 1, b); _pack_slot(p, "m", 7, a)
    return p


def _run(pack, out, **kw):
    return pool_rr.run(pack, out, "m", n_rollouts=1, n_parallel_matches=1, match_time=5.0, layout="pack", **kw)


def test_refuses_without_skip_match_data(pack, tmp_path, monkeypatch):
    monkeypatch.delenv("ARENA_SKIP_MATCH_DATA", raising=False)
    with pytest.raises(SystemExit, match="ARENA_SKIP_MATCH_DATA"):
        _run(pack, tmp_path / "out")
    assert not (tmp_path / "out").exists()                      # refused before any work


def test_plays_every_pairing_and_ranks(pack, tmp_path, monkeypatch):
    monkeypatch.setenv("ARENA_SKIP_MATCH_DATA", "1")
    out = tmp_path / "out"
    _run(pack, out, run_id="sh250-pool-test")
    matches = sorted(p.parent.name for p in (out / "m/matches").rglob("match_result.json"))
    assert matches == ["m__t00_c000_vs_m__t01_c000", "m__t00_c000_vs_m__t07_c000", "m__t01_c000_vs_m__t07_c000"]
    assert not list((out / "m").rglob("match_data.json*"))
    assert not [p for p in (out / "m").rglob("*") if p.suffix in (".mp4", ".webm")]
    for p in (out / "m/matches").rglob("match_result.json"):
        games = json.loads(p.read_text())["matches"]
        assert len(games) == 1 and games[0]["num_steps"] <= 500   # 5 s at 0.01 s per step

    led = json.loads((out / "m/pool_ledger.json").read_text())
    assert led["model"] == "m" and led["run_id"] == "sh250-pool-test" and led["n_samples"] == 250
    assert led["eligible"] == 3 and led["n_rollouts"] == 1 and led["match_time"] == 5.0
    assert led["inactivity"] == {"timeout_s": 10.0, "min_displacement_m": 0.5}
    assert len(led["git_sha"]) == 40 and len(led["config_md5"]) == 32
    assert led["rules"]["score_function"] == "any" and led["rules"]["physics_mode"] == "3d"
    assert led["rules"]["contact_fidelity"] == "high" and isinstance(led["rules"]["arena_xml"], str)
    assert len(led["ledger"]) == 250
    assert {r["artifact_id"] for r in led["ledger"] if r["eligible"]} == IDS
    assert led["ledger"][7]["artifact_id"] == "m__t07_c000"

    elo = json.loads((out / "m/elo.json").read_text())
    assert elo["model"] == "m" and elo["method"] == "bt" and elo["n_rollouts"] == 1
    assert set(elo["standings"]) == IDS
    for st in elo["standings"].values():
        assert st["games"] == 2 and st["wins"] + st["losses"] + st["draws"] == 2
    top = max(s["elo"] for s in elo["standings"].values())
    assert elo["ties_at_top"] == sorted(a for a, s in elo["standings"].items() if abs(s["elo"] - top) <= 1e-9)

    top5 = json.loads((out / "m/top_5_bots.json").read_text())
    assert top5["k"] == 5 and top5["scope"] == "intra_model" and top5["model"] == "m"
    assert [r["rank"] for r in top5["bots"]] == [1, 2, 3]
    ratings = [r["intra_model_elo"] for r in top5["bots"]]
    assert ratings == sorted(ratings, reverse=True)
    assert {r["artifact_id"] for r in top5["bots"]} == IDS
    assert all(r["robot_xml"].endswith("commit_0/robot.xml") for r in top5["bots"])

    top1 = json.loads((out / "m/top_1.json").read_text())
    assert top1["model"] == "m" and top1["artifact_id"] == top5["bots"][0]["artifact_id"]
    assert top1["artifact_id"] == f"m__t{top1['tournament_idx']:02d}_c000"
    assert abs(top1["elo"] - top) <= 1e-9 and top1["games"] == 2
    assert top1["ties_at_top"] == elo["ties_at_top"] and top1["artifact_id"] in top1["ties_at_top"]
    assert top1["tie_break"] == "lowest tournament_idx"
    # among exact ties the lowest tournament_idx wins
    assert top1["tournament_idx"] == min(int(a.split("__t")[1].split("_")[0]) for a in top1["ties_at_top"])

    # resumable: a second run plays nothing new
    before = {p: p.stat().st_mtime for p in (out / "m/matches").rglob("match_result.json")}
    _run(pack, out, run_id="sh250-pool-test")
    assert {p: p.stat().st_mtime for p in (out / "m/matches").rglob("match_result.json")} == before
    assert json.loads((out / "m/elo.json").read_text())["standings"] == elo["standings"]


def test_single_eligible_bot_skips_the_round_robin(tmp_path, monkeypatch):
    monkeypatch.setenv("ARENA_SKIP_MATCH_DATA", "1")
    pack = tmp_path / "pack"
    _pack_slot(pack, "m", 3, _srcs()[0])
    out = tmp_path / "out"
    _run(pack, out)
    assert not list((out / "m").rglob("match_result.json"))
    led = json.loads((out / "m/pool_ledger.json").read_text())
    assert led["eligible"] == 1 and led["ledger"][3]["artifact_id"] == "m__t03_c000"
    elo = json.loads((out / "m/elo.json").read_text())
    assert elo["method"] == "bt" and elo["standings"] == {
        "m__t03_c000": {"wins": 0, "losses": 0, "draws": 0, "elo": 1000.0, "games": 0}}
    top5 = json.loads((out / "m/top_5_bots.json").read_text())
    assert [r["artifact_id"] for r in top5["bots"]] == ["m__t03_c000"] and top5["bots"][0]["rank"] == 1
    top1 = json.loads((out / "m/top_1.json").read_text())
    assert top1["artifact_id"] == "m__t03_c000" and top1["tournament_idx"] == 3
    assert top1["elo"] == 1000.0 and top1["games"] == 0 and top1["ties_at_top"] == ["m__t03_c000"]


def test_no_eligible_bots_writes_empty_standings_and_no_top1(tmp_path, monkeypatch):
    monkeypatch.setenv("ARENA_SKIP_MATCH_DATA", "1")
    pack = tmp_path / "pack"
    (pack / "m").mkdir(parents=True)
    out = tmp_path / "out"
    _run(pack, out)
    led = json.loads((out / "m/pool_ledger.json").read_text())
    assert led["eligible"] == 0 and all(r["reason"] == "not generated" for r in led["ledger"])
    assert json.loads((out / "m/elo.json").read_text())["standings"] == {}
    assert json.loads((out / "m/top_5_bots.json").read_text())["bots"] == []
    assert not (out / "m/top_1.json").exists()                 # absence = "did not enter" downstream


def test_git_sha_falls_back_to_the_shipped_sha_file(tmp_path):
    """The cluster tree is shipped with `git archive` (no .git); SHIPPED_SHA records the commit."""
    with pytest.raises(RuntimeError, match="SHIPPED_SHA"):
        pool_rr.git_sha(tmp_path)
    (tmp_path / "SHIPPED_SHA").write_text("baa8ba07d0f92523992eabcdf8176dd38ca207be\n")
    assert pool_rr.git_sha(tmp_path) == "baa8ba07d0f92523992eabcdf8176dd38ca207be"


def test_runs_mode_plays_a_full_round_robin_inside_each_run_and_names_run_winners(tmp_path, monkeypatch):
    """4 samples as 2 runs of 2: g0 = {c000, c001}, g1 = {c002, c003}; one pairing each; the model's
    top_5_bots.json lists the two run winners and there is no model-level top_1.json."""
    monkeypatch.setenv("ARENA_SKIP_MATCH_DATA", "1")
    p = tmp_path / "pack"; a, b = _srcs()[:2]
    for idx, src in ((0, a), (1, b), (2, a), (3, b)):
        _pack_slot(p, "m", idx, src)
    out = tmp_path / "out"
    pool_rr.run_in_groups(p, out, "m", runs=2, n_samples=4, n_rollouts=1, n_parallel_matches=1,
                          match_time=5.0, layout="pack", run_id="t")
    for k, pair in ((0, "m__t00_c000_vs_m__t01_c000"), (1, "m__t02_c000_vs_m__t03_c000")):
        g = out / "m" / f"g{k}"
        assert (g / "matches" / pair / "match_result.json").is_file()
        assert sorted(d.name for d in (g / "matches").iterdir() if d.is_dir()) == [pair]
        led = json.loads((g / "pool_ledger.json").read_text())
        assert led["eligible"] == 2 and led["slot_range"] == [2 * k, 2 * k + 2] and led["group"] == f"g{k}"
        assert (g / "top_1.json").is_file() and (g / "elo.json").is_file()
    runs = json.loads((out / "m/runs.json").read_text())
    assert [g["group"] for g in runs["groups"]] == ["g0", "g1"] and all(g["winner"] for g in runs["groups"])
    top5 = json.loads((out / "m/top_5_bots.json").read_text())
    ids = [r["artifact_id"] for r in top5["bots"]]
    assert len(ids) == 2 and set(ids) == {g["winner"] for g in runs["groups"]}
    assert not (out / "m/top_1.json").exists()
    import verify_pool_rr
    assert verify_pool_rr.verify(out, "m", n_rollouts=1, match_time=5.0, group=0) == []
    assert verify_pool_rr.verify(out, "m", n_rollouts=1, match_time=5.0, group=1) == []


def test_run_index_and_finalize_split_the_grouped_run_for_slurm(tmp_path, monkeypatch):
    monkeypatch.setenv("ARENA_SKIP_MATCH_DATA", "1")
    p = tmp_path / "pack"; a, b = _srcs()[:2]
    for idx, src in ((0, a), (1, b), (2, a), (3, b)):
        _pack_slot(p, "m", idx, src)
    out = tmp_path / "out"
    kw = dict(n_rollouts=1, n_parallel_matches=1, match_time=5.0, layout="pack", run_id="t")
    with pytest.raises(RuntimeError, match="has not been played"):
        pool_rr.finalize_runs(p, out, "m", runs=2, n_samples=4, **kw)
    for k in (0, 1):                                              # what two array tasks do
        pool_rr.run(p, out, "m", n_samples=4, slot_range=(2 * k, 2 * k + 2), subdir=f"g{k}", **kw)
    pool_rr.finalize_runs(p, out, "m", runs=2, n_samples=4, **kw)
    top5 = json.loads((out / "m/top_5_bots.json").read_text())
    assert len(top5["bots"]) == 2 and (out / "m/runs.json").exists() and not (out / "m/top_1.json").exists()


def test_parallel_seeds_give_the_same_games_as_sequential(tmp_path, monkeypatch):
    """Playing a pairing's seeds concurrently must not change any game (same seeds, fresh env per game)."""
    monkeypatch.setenv("ARENA_SKIP_MATCH_DATA", "1")
    p = tmp_path / "pack"; a, b = _srcs()[:2]
    _pack_slot(p, "m", 0, a); _pack_slot(p, "m", 1, b)
    outs = {}
    for label, nps in (("seq", 1), ("par", 3)):
        out = tmp_path / label
        pool_rr.run(p, out, "m", n_rollouts=3, n_parallel_matches=1, match_time=20.0, layout="pack", run_id="t",
                    n_parallel_seeds=nps)
        r = json.loads(next((out / "m/matches").rglob("match_result.json")).read_text())
        outs[label] = [(g["seed"], g["winner"], g["num_steps"]) for g in r["matches"]]
    assert outs["seq"] == outs["par"], outs
