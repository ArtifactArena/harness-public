"""Skyhook Bailiff must not get external thrust by actuating its root freejoint.

The reduced fixture keeps the nine root motors' exact gears from Astra's bot.
Primitive geometry isolates the actuation exploit from missing SDF support.
These tests use existing public entry points, so they collect on the old engine.
"""
from pathlib import Path
from types import SimpleNamespace

import mujoco
import pytest

from mjarena.agents.runtime import BotRuntime
from mjarena.design_shop.rules.mj_validators import validate_control_constraints
from mjarena.envs.sumo import SumoEnv

FIXTURE = Path(__file__).parent / "fixtures/flying_astra_root_actuation.xml"


def test_flying_astra_root_motors_rejected_by_validation():
    model = mujoco.MjModel.from_xml_path(str(FIXTURE))
    assert model.nu == 9
    for actuator in range(model.nu):
        joint = model.actuator_trnid[actuator, 0]
        assert model.jnt_type[joint] == mujoco.mjtJoint.mjJNT_FREE
    config = SimpleNamespace(max_dof_damping=600.0, max_frictionloss=600.0,
                             max_actuator_gear=None)
    result = validate_control_constraints(model, config)
    assert not result.passed, (
        "Flying Astra exploit: all nine direct root-force/torque motors passed validation"
    )
    assert any("root" in error.lower() for error in result.errors), result.errors


def test_flying_astra_preprocessed_match_rejected_at_runtime():
    model = mujoco.MjModel.from_xml_path(str(FIXTURE))
    data = mujoco.MjData(model)
    red = BotRuntime(model, data, lambda obs: {}, "red_")
    blue = BotRuntime(model, data, lambda obs: {}, "blue_")
    with pytest.raises(ValueError, match="(?i)root.*actuation|actuation.*root"):
        env = SumoEnv(model, data, str(FIXTURE), red, blue, max_steps=1)
        env.close()
