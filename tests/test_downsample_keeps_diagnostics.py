"""MatchupResult.downsample() must keep the per-game diagnostic fields.

GameRecord.downsample() emits qacc_loser, qacc_dof_index, qacc_body_name,
initial_qpos and controller_errors. The matchup-level downsample rebuilds each
GameRecord and every qualify_round return path goes through it, so a caller
reading the verifier result must see the same five values on the rebuilt record.
"""
from mjarena.design_shop.types import GameRecord, MatchupResult

QACC_LOSER = "blue"
QACC_DOF_INDEX = 7
QACC_BODY_NAME = "blue_left_flipper"
INITIAL_QPOS = [0.1, -0.2, 0.3, 1.0, 0.0, 0.0, 0.0, 0.42]
CONTROLLER_ERRORS = [
    {"color": "red", "step": 3, "type": "ZeroDivisionError", "message": "division by zero"},
]

N_STEPS = 5


def _record() -> GameRecord:
    vec = [[0.0, 0.0, 0.0]] * N_STEPS
    ori = [{"yaw": 0.0, "pitch": 0.0, "roll": 0.0}] * N_STEPS
    flat = [0.0] * N_STEPS
    flags = [False] * N_STEPS
    acts = [{"drive": 0.0}] * N_STEPS
    return GameRecord(
        seed=11,
        winner="blue",
        num_steps=N_STEPS,
        winner_step=4,
        progress=0.0,
        ring_radius=3.0,
        red_mass=100.0,
        blue_mass=342.0,
        red_bounding_radius=0.5,
        blue_bounding_radius=0.5,
        red_actuator_names=["drive"],
        blue_actuator_names=[],
        red_positions=vec,
        blue_positions=vec,
        red_orientations=ori,
        blue_orientations=ori,
        red_velocities=vec,
        blue_velocities=vec,
        red_angular_velocities=vec,
        blue_angular_velocities=vec,
        distances_to_opponent=flat,
        red_edge_distances=flat,
        blue_edge_distances=flat,
        contacts=flags,
        contact_forces=flat,
        red_tipping=flat,
        blue_tipping=flat,
        red_ground_contacts=flags,
        blue_ground_contacts=flags,
        blue_displacements=flat,
        red_actions=acts,
        blue_actions=acts,
        physics_unstable=True,
        qacc_warning_steps=[3, 4],
        initial_red_pos=[-1.0, 0.0, 0.1],
        initial_blue_pos=[1.0, 0.0, 0.1],
        initial_distance=2.0,
        termination_reason="qacc",
        qacc_loser=QACC_LOSER,
        qacc_dof_index=QACC_DOF_INDEX,
        qacc_body_name=QACC_BODY_NAME,
        initial_qpos=list(INITIAL_QPOS),
        controller_errors=[dict(e) for e in CONTROLLER_ERRORS],
    )


def test_matchup_downsample_keeps_the_five_diagnostic_fields():
    original = _record()
    matchup = MatchupResult(
        game_records=[original],
        combat_scores=[None],
        seed_scores=[0.0],
        elapsed_sec=1.0,
    )

    rebuilt = matchup.downsample(replay_hz=2.0, control_hz=100.0).game_records[0]

    assert rebuilt.qacc_loser == QACC_LOSER
    assert rebuilt.qacc_dof_index == QACC_DOF_INDEX
    assert rebuilt.qacc_body_name == QACC_BODY_NAME
    assert rebuilt.initial_qpos == INITIAL_QPOS
    assert rebuilt.controller_errors == CONTROLLER_ERRORS


def test_matchup_downsample_agrees_with_record_downsample():
    original = _record()
    matchup = MatchupResult(
        game_records=[original],
        combat_scores=[None],
        seed_scores=[0.0],
        elapsed_sec=1.0,
    )
    step_interval = round(100.0 / 2.0)

    per_record = original.downsample(step_interval)
    rebuilt = matchup.downsample(replay_hz=2.0, control_hz=100.0).game_records[0]

    for name in ("qacc_loser", "qacc_dof_index", "qacc_body_name", "controller_errors"):
        assert getattr(rebuilt, name) == per_record[name], name
    # GameRecord.downsample() does not emit initial_qpos (it is Blender-only data),
    # so the rebuilt record is checked against the source record directly.
    assert rebuilt.initial_qpos == original.initial_qpos


def test_matchup_downsample_copies_rather_than_aliases_the_lists():
    original = _record()
    matchup = MatchupResult(
        game_records=[original],
        combat_scores=[None],
        seed_scores=[0.0],
        elapsed_sec=1.0,
    )

    rebuilt = matchup.downsample().game_records[0]

    assert rebuilt.initial_qpos is not original.initial_qpos
    assert rebuilt.controller_errors is not original.controller_errors
