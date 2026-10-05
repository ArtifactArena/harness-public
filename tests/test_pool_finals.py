"""pool_finals: Stage B stored round robins — top-5 per model (B1) and cross-model top-1 (B2),
telemetry gzipped in place, BT standings with ties declared, resumable, refuses to run
without telemetry."""
import gzip
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/sampling"))
import pool_finals  # noqa: E402

BASE = ROOT / "mjarena/core/assets/baseline_bots"
MODELS = ("ma", "mb")


def _aid(model, idx):
    return f"{model}__t{idx:02d}_c000"


def _pack_slot(pack, model, idx, src):
    d = pack / model / f"c{idx:03d}"
    (d / "commit_0").mkdir(parents=True)
    for name in ("robot.xml", "controller.py"):
        shutil.copy(src / name, d / "commit_0" / name)
        shutil.copy(src / name, d / name)
    (d / "gen.json").write_text("{}")
    (d / "bot_artifact.json").write_text(json.dumps({"forfeit": False}))
    (d / "journal.json").write_text(json.dumps(
        {"commits": [{"validation_passed": True, "qualification_passed": True, "score": 1.0}]}))
    (d / "qualification").mkdir(exist_ok=True)
    (d / "qualification/match_result.json").write_text(json.dumps({"red_bot": "bot", "blue_bot": "", "n_seeds": 3,
        "matches": [{"seed": i, "winner": "red", "num_steps": 100, "termination_reason": "ring_out"} for i in range(3)]}))


def _top5_row(model, idx, rank):
    return {"rank": rank, "artifact_id": _aid(model, idx), "model": model, "kind": "refinement_commit",
            "tournament_idx": idx, "commit_idx": 0, "robot_xml": f"{model}/c{idx:03d}/commit_0/robot.xml",
            "controller_py": f"{model}/c{idx:03d}/commit_0/controller.py", "qualification_score": 1.0,
            "intra_model_elo": 1000.0 - rank, "intra_model_wld": {"wins": 1, "losses": 0, "draws": 0},
            "cross_model_elo": {"k1": None, "k3": None, "k5": None},
            "cross_model_wld": {"k1": None, "k3": None, "k5": None}}


def _stage_a_model(rr, model, idxs, *, top1_idx):
    md = rr / model
    md.mkdir(parents=True)
    (md / "top_5_bots.json").write_text(json.dumps(
        {"k": 5, "scope": "intra_model", "model": model, "source": {},
         "bots": [_top5_row(model, i, r) for r, i in enumerate(idxs, start=1)]}))
    if top1_idx is not None:
        (md / "top_1.json").write_text(json.dumps(
            {"model": model, "artifact_id": _aid(model, top1_idx), "tournament_idx": top1_idx,
             "elo": 1001.0, "wins": 1, "losses": 0, "draws": 0, "games": 1, "ties_at_top": []}))


@pytest.fixture
def fixture(tmp_path):
    """Pack: two models x two slots (the two baseline solids). Stage A: both bots in each model's
    top-5, slot 0 as top-1; plus a third model `mc` with a one-bot top-5 and no top_1.json yet (its
    Stage A never finished) — skipped by both stages. `out` is the Stage A root, as on the cluster
    (`--rr rr-$RUN --out rr-$RUN` → `rr-$RUN/stage_b/`)."""
    pack = tmp_path / "pack"
    rr = tmp_path / "rr"
    srcs = sorted(x for x in BASE.iterdir() if (x / "robot.xml").exists())[:2]
    for model in MODELS:
        _pack_slot(pack, model, 0, srcs[0])
        _pack_slot(pack, model, 1, srcs[1])
        _stage_a_model(rr, model, [0, 1], top1_idx=0)
    _pack_slot(pack, "mc", 3, srcs[0])
    _stage_a_model(rr, "mc", [3], top1_idx=None)
    return pack, rr, rr


def test_refuses_when_telemetry_is_skipped(fixture, monkeypatch):
    pack, rr, out = fixture
    monkeypatch.setenv("ARENA_SKIP_MATCH_DATA", "1")
    with pytest.raises(SystemExit, match="ARENA_SKIP_MATCH_DATA"):
        pool_finals.run(rr, pack, out, n_rollouts=1, n_parallel_matches=1, match_time=5.0)
    assert not (out / "stage_b").exists()


def _pairings(matches_dir):
    return sorted(p.parent for p in matches_dir.rglob("match_result.json"))


def test_stage_b_round_robins_with_stored_telemetry(fixture, monkeypatch):
    pack, rr, out = fixture
    monkeypatch.delenv("ARENA_SKIP_MATCH_DATA", raising=False)
    pool_finals.run(rr, pack, out, n_rollouts=1, n_parallel_matches=1, match_time=5.0, run_id="test-run")
    sb = out / "stage_b"

    # B1: one pairing per model, telemetry stored gzipped, never raw
    for model in MODELS:
        pairs = _pairings(sb / "top5" / model / "matches")
        assert [p.name for p in pairs] == [f"{_aid(model, 0)}_vs_{_aid(model, 1)}"]
        assert (pairs[0] / "match_data.json.gz").is_file()
        assert not (pairs[0] / "match_data.json").exists()
        elo = json.loads((sb / "top5" / model / "elo.json").read_text())
        assert elo["model"] == model and elo["stage"] == "b1" and elo["method"] == "bt"
        assert elo["n_rollouts"] == 1 and elo["run_id"] == "test-run"
        assert set(elo["standings"]) == {_aid(model, 0), _aid(model, 1)} == set(elo["participants"])
        assert isinstance(elo["ties"], list) and isinstance(elo["ties_at_top"], list)
    skipped = json.loads((sb / "top5" / "mc" / "SKIPPED.json").read_text())
    assert skipped["n_bots"] == 1 and "reason" in skipped
    assert not (sb / "top5" / "mc" / "matches").exists()

    # mc's single run winner is its champion by default (user ruling 2026-09-20): B1 writes its top_1.json
    mc_top1 = json.loads((rr / "mc" / "top_1.json").read_text())
    assert mc_top1["artifact_id"] == _aid("mc", 3) and mc_top1["games"] == 0
    # B2: all three champions play each other (3 pairings), telemetry stored
    pairs = _pairings(sb / "top1" / "matches")
    assert sorted(p.name for p in pairs) == sorted([f"{_aid('ma', 0)}_vs_{_aid('mb', 0)}", f"{_aid('ma', 0)}_vs_{_aid('mc', 3)}",
                                                    f"{_aid('mb', 0)}_vs_{_aid('mc', 3)}"])
    assert all((p / "match_data.json.gz").is_file() and not (p / "match_data.json").exists() for p in pairs)
    elo2 = json.loads((sb / "top1" / "elo.json").read_text())
    assert elo2["scope"] == "cross_model_top1" and elo2["stage"] == "b2" and elo2["method"] == "bt"
    assert set(elo2["standings"]) == {_aid("ma", 0), _aid("mb", 0), _aid("mc", 3)}
    assert json.loads((sb / "top1" / "skipped.json").read_text()) == {}

    # nothing else stored: no videos anywhere
    assert not list(sb.rglob("*.mp4")) and not list(sb.rglob("*.webm"))

    # summary
    summary = json.loads((sb / "summary.json").read_text())
    assert summary["run_id"] == "test-run" and summary["n_rollouts"] == 1
    assert set(summary["top5"]) == {"ma", "mb", "mc"} and "skipped" in summary["top5"]["mc"]
    assert set(summary["top5"]["ma"]["standings"]) == {_aid("ma", 0), _aid("ma", 1)}
    assert set(summary["top1"]["standings"]) == {_aid("ma", 0), _aid("mb", 0), _aid("mc", 3)}
    assert summary["top1"]["by_model"]["ma"]["artifact_id"] == _aid("ma", 0)

    # the verifier's Stage B modes accept the output (they read the Stage A files under `out`)
    verify_pool_rr = pytest.importorskip("verify_pool_rr")
    for model in MODELS:
        assert verify_pool_rr.verify_stage_b1(out, model, n_rollouts=1, match_time=5.0) == []
    assert verify_pool_rr.verify_stage_b2(out, n_rollouts=1, match_time=5.0) == []

    # resumable: a second run plays nothing new and leaves the gzipped telemetry alone
    tracked = list(sb.rglob("match_result.json")) + list(sb.rglob("match_data.json.gz"))
    before = {p: p.stat().st_mtime_ns for p in tracked}
    pool_finals.run(rr, pack, out, n_rollouts=1, n_parallel_matches=1, match_time=5.0, run_id="test-run")
    assert {p: p.stat().st_mtime_ns for p in tracked} == before
    assert not list(sb.rglob("match_data.json"))


def test_gzip_tolerates_already_gzipped_and_raw_leftovers(tmp_path):
    pair = tmp_path / "matches" / "a_vs_b"
    pair.mkdir(parents=True)
    (pair / "match_data.json").write_text('{"seed_0": {"num_steps": 1}}')
    assert pool_finals.gzip_match_data(tmp_path / "matches") == 1
    assert (pair / "match_data.json.gz").is_file() and not (pair / "match_data.json").exists()
    assert pool_finals.gzip_match_data(tmp_path / "matches") == 0            # nothing raw left
    # a raw file re-appearing next to a stale .gz (crash between write and unlink) is re-gzipped
    (pair / "match_data.json").write_text('{"seed_0": {"num_steps": 2}}')
    assert pool_finals.gzip_match_data(tmp_path / "matches") == 1

    with gzip.open(pair / "match_data.json.gz", "rb") as f:
        assert json.loads(f.read())["seed_0"]["num_steps"] == 2
