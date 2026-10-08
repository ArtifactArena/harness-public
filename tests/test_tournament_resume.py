import itertools
import json
from types import SimpleNamespace

import pytest

import mjarena.core.unified_builder
from mjarena.tournament import tournament


def saved_pair(path, a="Robot A", b="Robot B", ids=(0, 1), seeds=(42, 43)):
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(red_bot=a, blue_bot=b, red_id=ids[0], blue_id=ids[1],
                   tool_name="tournament", n_seeds=len(seeds),
                   matches=[dict(seed=s, winner="red", num_steps=100) for s in seeds])
    path.write_text(json.dumps(payload))
    return payload


@pytest.mark.parametrize("workers", [1, 2])
def test_resume_preserves_order_seeds_results_and_files(tmp_path, monkeypatch, workers):
    names = ["Robot A", "Robot B", "Robot C"]
    bots = {n: SimpleNamespace(generator=f"model-{i}", morphology_xml=tmp_path/n/"robot.xml")
            for i, n in enumerate(names)}
    out = tmp_path / "tournament"
    files = []
    for i, (a, b) in enumerate(itertools.combinations(names, 2)):
        path = out / "matches" / f"{bots[a].generator}_vs_{bots[b].generator}" / "match_result.json"
        saved_pair(path, a, b, (names.index(a), names.index(b)), (42 + 2*i, 43 + 2*i))
        files.append((path, path.read_bytes(), path.stat().st_mtime_ns))
    arena = tmp_path / "arena.xml"
    arena.write_text("<mujoco/>")

    def unexpected_simulation(**kwargs):
        raise AssertionError("completed pairing must not simulate again")

    monkeypatch.setattr(tournament, "run_matchup", unexpected_simulation)
    result = tournament.run_round_robin(
        dict(reversed(list(bots.items()))), arena, out, n_rollouts=2,
        record_video=False, verbose=False, trace_progress=False,
        n_parallel_matches=workers, raise_on_error=True,
    )
    assert result.metadata["bot_names"] == names
    assert len(result.matches) == 6
    assert [m.seed for m in result.matches] == list(range(42, 48))
    assert result.standings["model-0"]["wins"] == 4
    for path, content, mtime in files:
        assert path.read_bytes() == content
        assert path.stat().st_mtime_ns == mtime


def test_incomplete_and_changed_seeds_are_replayed(tmp_path):
    path = tmp_path / "match_result.json"
    saved_pair(path, seeds=(42,))
    assert tournament._completed_matchup(path, "Robot A", "Robot B", [42, 43]) is None
    assert tournament._completed_matchup(path, "Robot A", "Robot B", [99]) is None
    path.write_text('{"matches":')
    assert tournament._completed_matchup(path, "Robot A", "Robot B", [42]) is None


def test_conflicting_saved_ids_fail_before_replaying(tmp_path):
    saved_pair(tmp_path / "one/match_result.json")
    saved_pair(tmp_path / "two/match_result.json", ids=(1, 0))
    with pytest.raises(ValueError, match="Conflicting"):
        tournament._resume_bot_order({"Robot A": None, "Robot B": None}, tmp_path)


def test_dashboard_counts_reused_pairings_and_estimates_remaining_time():
    states = {0: dict(status="skipped", label="cached", seed_range="0", submitted_at=0,
                      started_at=0, duration=0, result="preexisting"),
              1: dict(status="completed", label="new", seed_range="1", submitted_at=0,
                      started_at=0, duration=10, result="1-0-0"),
              2: dict(status="queued", label="next", seed_range="2", submitted_at=0,
                      started_at=None, duration=None, result="")}
    text = tournament._render_dashboard(states, done_count=1, total_count=3,
                                        workers=1, tournament_elapsed=10)
    assert "2/3 finished" in text
    assert "ETA= 10.0s" in text
