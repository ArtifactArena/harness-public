#!/usr/bin/env python
"""Dump what the simulator does to a robot, for cross-checkout comparison. Run from the repo root.

The same probe runs in this harness checkout and in the reference checkout
(`arena-main` at 16726431). Both write the same JSON shape, so
`tests/test_parity_with_arena_main.py` can diff them section by section:

    {"checkout": ..., "validation": {...}, "model": {...},
     "composition": {...}, "matches": [...]}

The two checkouts' `run_match` signatures differ in exactly one parameter: this
harness carries the runtime size limit (`size_limits`), a rule arena-main does
not have. The probe dispatches on that explicitly — it inspects `run_match`'s
signature once, at import, and passes `size_limits=None` only where the
parameter exists, so the rule is disarmed and the outcomes stay comparable.

The two checkouts' baseline blocks also differ (this harness's is the palette
plastic slab of Task 14; arena-main's is the old foam block), and `BLOCK` is a
path relative to whichever checkout the probe runs in. `--block <path>` pins one
absolute block file for both, so the comparison is about the simulator rather
than about the asset. It only replaces the blue side's MJCF: the block is still
composed unvalidated and still carries the `blue_` inactivity exemption, unlike
the positional `opponent`, which is a robot and is validated.
"""
import argparse
import inspect
import json
from pathlib import Path

import mujoco

import mjarena.core.unified_builder  # noqa: F401  (breaks the dspy_core/design_shop import cycle)
from mjarena.design_shop.pipelines.morphology_pipeline import validate_morphology
from mjarena.design_shop.rules.mj_validators import ModelValidationConfig
from mjarena.envs.sumo import SumoEnv, compose_sumo_model
from mjarena.policy_spec import PolicySpec
from mjarena.runner.episode import run_match

ARENA = "mjarena/assets/sumo_ring_env_studio_3d.xml"
BLOCK = "mjarena/core/assets/stationary_block_3d.xml"
RULES = "configs/rules/rules.yaml"

# Explicit checkout dispatch: this harness's run_match takes `size_limits`
# (the runtime size rule); arena-main's does not. Feature, not exception.
RUN_MATCH_PARAMS = inspect.signature(run_match).parameters
HAS_SIZE_LIMITS = "size_limits" in RUN_MATCH_PARAMS

CONTROL_DT = SumoEnv.HIGH_FIDELITY_CONTACT["control_timestep"]  # 100 Hz, both checkouts


def model_facts(source: Path) -> dict:
    """Compile an MJCF file and report every fact a rule could have touched."""
    m = mujoco.MjModel.from_xml_path(str(source))
    return {
        "nbody": m.nbody, "ngeom": m.ngeom, "nu": m.nu, "ntendon": m.ntendon,
        "total_mass": round(float(m.body_mass[1:].sum()), 6),
        "body_mass": [round(float(x), 6) for x in m.body_mass[1:]],
        "geom_condim": [int(x) for x in m.geom_condim],
        "geom_priority": [int(x) for x in m.geom_priority],
        "geom_friction": [[round(float(v), 6) for v in row] for row in m.geom_friction],
        "geom_solref": [[round(float(v), 6) for v in row] for row in m.geom_solref],
        "geom_solimp": [[round(float(v), 6) for v in row] for row in m.geom_solimp],
        "geom_margin": [round(float(x), 6) for x in m.geom_margin],
        "geom_gap": [round(float(x), 6) for x in m.geom_gap],
        "dof_damping": [round(float(x), 6) for x in m.dof_damping],
        "dof_frictionloss": [round(float(x), 6) for x in m.dof_frictionloss],
        "dof_armature": [round(float(x), 6) for x in m.dof_armature],
        "jnt_stiffness": [round(float(x), 6) for x in m.jnt_stiffness],
        "jnt_type": [int(x) for x in m.jnt_type],
        "actuator_gear": [[round(float(v), 6) for v in row] for row in m.actuator_gear],
        "npair": int(m.npair), "nexclude": int(m.nexclude),
    }


def actuator_names(xml_path: Path, prefix: str) -> list:
    """Every actuator of one side, in model order — the keys a zero policy writes."""
    m = mujoco.MjModel.from_xml_path(str(xml_path))
    names = []
    for i in range(m.nu):
        name = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_ACTUATOR, i) or ""
        if name.startswith(prefix):
            names.append(name)
    return names


def run_one(composed: Path, out_dir: Path, seed: int, match_time: float,
            exempt: list) -> dict:
    kwargs = dict(
        composed_xml=composed,
        red_policy_py=PolicySpec.zero(actuator_names(composed, "red_")).build_callable(),
        blue_policy_py=PolicySpec.zero(actuator_names(composed, "blue_")).build_callable(),
        out_dir=out_dir,
        # Both checkouts get the step cap explicitly: arena-main resolves
        # match_time only inside the Match wrapper, so its env would otherwise
        # keep max_steps=None and its detailed observations would divide by it.
        max_steps=int(match_time / CONTROL_DT),
        use_gui=False,
        save_video=False,
        camera_mode="tracking",
        quiet=True,
        seed=seed,
        match_time=match_time,
        inactivity_timeout_seconds=10.0,
        inactivity_min_displacement=0.5,
        inactivity_exempt_prefixes=exempt,
    )
    if HAS_SIZE_LIMITS:
        # Disarm the harness-only runtime size rule so both checkouts judge the
        # same set of rules. The probe fixtures never exceed the box anyway.
        kwargs["size_limits"] = None
    rec = run_match(**kwargs)
    return {
        "seed": seed,
        "winner": rec.winner,
        "reason": rec.termination_reason,
        "steps": rec.num_steps,
        "red_timer": round(float(rec.red_inactivity_timers[-1]), 3) if rec.red_inactivity_timers else None,
        "blue_timer": round(float(rec.blue_inactivity_timers[-1]), 3) if rec.blue_inactivity_timers else None,
        "red_position_last": [round(float(v), 4) for v in rec.red_positions[-1]] if rec.red_positions else None,
        "blue_position_last": [round(float(v), 4) for v in rec.blue_positions[-1]] if rec.blue_positions else None,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("robot")
    ap.add_argument("opponent", nargs="?")
    ap.add_argument("--seeds", default="0,1,2")
    ap.add_argument("--match-time", type=float, default=20.0)
    ap.add_argument("--block", help="baseline block MJCF to compose as blue when no positional "
                                    "opponent is given; overrides this checkout's own BLOCK asset "
                                    "so both checkouts play the identical block file. Composed "
                                    "unvalidated, and still exempt from inactivity.")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    out = {"checkout": Path.cwd().name, "has_size_limits": HAS_SIZE_LIMITS}
    cfg = ModelValidationConfig(Path(RULES), physics_mode="3d")
    res = validate_morphology(Path(a.robot).read_text(), cfg)
    out["validation"] = {"passed": res.passed, "feedback_head": res.feedback[:400]}
    if not res.passed:
        Path(a.out).write_text(json.dumps(out, indent=1))
        return
    # compose_sumo_model reads MJCF files, so the validated XML goes to disk first.
    red_path = Path(a.out).with_suffix(".red.xml")
    red_path.write_text(res.processed_xml)
    out["model"] = model_facts(red_path)

    if a.opponent:
        opp = validate_morphology(Path(a.opponent).read_text(), cfg)
        blue_path = Path(a.out).with_suffix(".blue.xml")
        blue_path.write_text(opp.processed_xml)
        exempt = []
    else:
        # --block only swaps the file; the block is never validated (it is an arena
        # asset, not an authored robot) and keeps its inactivity exemption.
        blue_path = Path(a.block).resolve() if a.block else Path(BLOCK).resolve()
        exempt = ["blue_"]  # the block has no motors and is exempt from inactivity

    composed = Path(a.out).with_suffix(".composed.xml")
    compose_sumo_model(ARENA, str(red_path), str(blue_path), str(composed),
                       randomize_spawn_3d=True, spawn_seed=0)
    out["composition"] = model_facts(composed)

    match_dir = composed.parent / f"{composed.stem}_matches"
    match_dir.mkdir(parents=True, exist_ok=True)
    out["matches"] = [
        run_one(composed, match_dir, int(s), a.match_time, exempt)
        for s in a.seeds.split(",")
    ]
    Path(a.out).write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
