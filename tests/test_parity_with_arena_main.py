"""The ported rules must match the upstream code, not just its tests.

Runs `scripts/parity_probe.py` in this checkout and in the reference checkout
(`arena-main` at 16726431) over the same robot XMLs — and, via `--block`, the same
baseline block — and compares validation, compiled-model facts, composition, and
zero-policy match outcomes.

Opt-in twice over: `ARENA_PARITY=1` arms it (~14 min) and `ARENA_MAIN_REF` says
where the reference checkout is. Without either it skips.
"""
import mjarena.core.unified_builder  # noqa: F401
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

# No default: the reference checkout lives wherever the person running this put
# it, so a hardcoded home directory would only ever be right on one machine.
_REF_ENV = os.environ.get("ARENA_MAIN_REF")
REF = Path(_REF_ENV) if _REF_ENV else None
HERE = Path(__file__).resolve().parents[1]
PROBE = HERE / "scripts" / "parity_probe.py"
OUTCOME_FIELDS = ("seed", "winner", "reason", "steps", "red_timer", "blue_timer")
POSITION_FIELDS = ("red_position_last", "blue_position_last")
POSITION_TOL = 2e-4  # observed drift is 1e-4 m; anything larger is a real divergence
FIXTURES = [
    "tests/fixtures/study_bot/robot.xml",
    "tests_environment/fixtures/gyrefang.xml",
    "tests_environment/fixtures/undertow.xml",
    "tests_environment/fixtures/welded_bodies.xml",
]


def _probe(root: Path, robot: Path, tmp: Path, tag: str, block: Path) -> dict:
    out = tmp / f"{tag}.json"
    done = subprocess.run(
        [sys.executable, str(PROBE), str(robot), "--block", str(block), "--out", str(out)],
        cwd=root, env={**os.environ, "PYTHONPATH": str(root)},
        capture_output=True, text=True, timeout=900,
    )
    if done.returncode != 0:
        raise AssertionError(f"probe failed in {root}:\n{done.stderr[-3000:]}")
    return json.loads(out.read_text())


@pytest.fixture(scope="module")
def parity_block(tmp_path_factory) -> Path:
    """One block file for both checkouts — the simulator is what is being compared.

    `scripts/parity_probe.py`'s `BLOCK` is a path relative to whichever checkout it
    runs in, and the two checkouts no longer hold the same asset: this harness's
    baseline block is the palette plastic slab of Task 14 (342 kg, sliding friction
    0.25), arena-main's is the old 36 kg foam block. Left alone, `composition` would
    differ on the asset rather than on any ported rule.

    What is pinned is the block exactly as qualification plays it — the palette-
    resolved XML, not the raw asset — because arena-main has no palette step for the
    block and would otherwise compose it with composition's 1.0 sliding-friction
    fallback while this harness supplies 0.25.
    """
    from mjarena.core.qualification_block import write_qualification_block
    out = tmp_path_factory.mktemp("parity_block") / "block.xml"
    return write_qualification_block(out, HERE / "configs/rules/rules.yaml", physics_mode="3d")


@pytest.mark.skipif(os.environ.get("ARENA_PARITY") != "1",
                    reason="set ARENA_PARITY=1 to run the cross-checkout parity probe (~14 min)")
@pytest.mark.skipif(REF is None,
                    reason="set ARENA_MAIN_REF to an arena-main checkout to run the parity probe")
@pytest.mark.skipif(REF is not None and not (REF / "mjarena/envs/detailed_observations.py").exists(),
                    reason=f"reference checkout absent: {REF}")
@pytest.mark.parametrize("fixture", FIXTURES)
def test_simulator_agrees_with_arena_main(fixture, tmp_path, parity_block):
    robot = (HERE / fixture).resolve()
    ours = _probe(HERE, robot, tmp_path, "harness", parity_block)
    theirs = _probe(REF, robot, tmp_path, "reference", parity_block)

    # The probe is meant to exercise the harness-only rule's disarmed path.
    assert ours["has_size_limits"] and not theirs["has_size_limits"]

    assert ours["validation"]["passed"] == theirs["validation"]["passed"], (
        ours["validation"], theirs["validation"])
    if not ours["validation"]["passed"]:
        return
    for section in ("model", "composition"):
        differing = [k for k in ours[section] if ours[section][k] != theirs[section].get(k)]
        assert ours[section] == theirs[section], f"{section} differs in {differing}"

    # Who won, why, when, and both inactivity timers must agree exactly.
    outcomes = [{k: m[k] for k in OUTCOME_FIELDS} for m in ours["matches"]]
    ref_outcomes = [{k: m[k] for k in OUTCOME_FIELDS} for m in theirs["matches"]]
    differing = [(o["seed"], [k for k in o if o[k] != t[k]])
                 for o, t in zip(outcomes, ref_outcomes) if o != t]
    assert outcomes == ref_outcomes, (
        f"zero-policy match outcomes differ from arena-main (seed, fields): {differing}")

    # Final COM positions are diagnostics, and the reference runs its detailed
    # observations every step (this harness gets them with Task 8). Those extra
    # mj_* calls disturb the solver warm start, so the two trajectories drift
    # apart by a fraction of a millimetre. The probe caps each match at 2000
    # control steps (20 s at 100 Hz) and every one of these matches ends on the
    # inactivity rule at step 1000, so that is the drift budget: the largest
    # observed gap is 1e-4 m, and POSITION_TOL sits just above it.
    for ours_m, theirs_m in zip(ours["matches"], theirs["matches"]):
        for field in POSITION_FIELDS:
            a, b = ours_m[field], theirs_m[field]
            assert (a is None) == (b is None), (field, a, b)
            if a is None:
                continue
            drift = max(abs(x - y) for x, y in zip(a, b))
            assert drift <= POSITION_TOL, (
                f"seed {ours_m['seed']} {field} drifts {drift:.6f} m from arena-main: {a} vs {b}")
