"""Artifact ids keep the t00..t99 shape and also carry three-digit sample indices (t100..t249)."""
from mjarena.two_stage.artifact_loader import make_artifact_id, parse_artifact_id


def test_two_and_three_digit_tournament_indices_round_trip():
    for idx in (0, 7, 99, 100, 249):
        aid = make_artifact_id("gpt-5.5", idx, 0)
        assert parse_artifact_id(aid) == {"model": "gpt-5.5", "tournament_idx": idx, "commit_idx": 0}, aid
    assert make_artifact_id("m", 5, 0) == "m__t05_c000"
    assert make_artifact_id("m", 249, 0) == "m__t249_c000"
