"""Exact match parity through the real serial and spawned entry points.

Run after scripts/setup_acceleration.py on the validated Linux environment.
"""
from concurrent.futures import ProcessPoolExecutor
import hashlib
import multiprocessing
import os
from pathlib import Path
import platform

import pytest


ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(
    platform.system() != "Linux" or platform.machine() != "x86_64"
    or not (ROOT / "mjarena/envs/match_accel/arena_serial.so").is_file(),
    reason="build the default Linux accelerator first",
)


def _probe(mode, xml, out):
    import mujoco
    import numpy as np
    # Follow the harness dependency import order.
    import mjarena.core.unified_builder
    from mjarena.runner.episode import Match, run_match
    from mjarena.envs import match_accel
    from mjarena.envs import detailed_observations

    if mode == "auto":
        os.environ.pop("ARENA_MATCH_ACCEL", None)
    else:
        os.environ["ARENA_MATCH_ACCEL"] = mode
    os.environ.pop("ARENA_SKIP_MATCH_DATA", None)
    before_affinity = os.sched_getaffinity(0)
    observer = detailed_observations.DetailedObservations
    original = Match.single_match_step
    original_step = mujoco.mj_step
    digest = hashlib.sha256()
    backends = set()

    def step(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        backends.add(match_accel._INSTALLED is not None)
        spec = mujoco.mjtState.mjSTATE_INTEGRATION
        state = np.empty(mujoco.mj_stateSize(self.env.model, spec))
        mujoco.mj_getState(self.env.model, self.env.data, state, spec)
        digest.update(state.tobytes())
        for name in ("qacc", "qfrc_constraint", "sensordata"):
            digest.update(getattr(self.env.data, name).tobytes())
        for name in ("dist", "pos", "frame", "geom1", "geom2"):
            digest.update(getattr(self.env.data.contact, name)[:self.env.data.ncon].tobytes())
        return result

    Match.single_match_step = step
    try:
        record = run_match(
            Path(xml), lambda obs: {"red_drive": .3},
            lambda obs: {"blue_drive": -.2}, Path(out),
            max_steps=100, use_gui=False, save_video=False,
            camera_mode="tracking", quiet=True, seed=42,
            inactivity_timeout_seconds=None,
        )
    finally:
        Match.single_match_step = original
    assert match_accel._INSTALLED is None
    assert mujoco.mj_step is original_step
    assert detailed_observations.DetailedObservations is observer
    assert os.sched_getaffinity(0) == before_affinity
    assert backends == {mode != "0"}
    return record.to_dict(), digest.hexdigest()


@pytest.mark.parametrize("sdf", [False, True])
def test_serial_and_spawned_exact_parity(tmp_path, sdf):
    from environment_fixtures import arena_xml, box_mesh

    xml = tmp_path / "arena.xml"
    content = arena_xml(articulated=True)
    if sdf:
        content = content.replace("<worldbody>", "<asset>" + box_mesh(half=(.2, .2, .1))
                                  + "</asset><worldbody>")
        content = content.replace('type="box" size=".2 .2 .1"', 'type="sdf" mesh="surface"')
    xml.write_text(content)
    reference = _probe("0", str(xml), str(tmp_path))
    try:
        assert _probe("auto", str(xml), str(tmp_path)) == reference
        # Repeated serial matches must not retain the preceding model's contexts.
        assert _probe("auto", str(xml), str(tmp_path)) == reference
        with ProcessPoolExecutor(max_workers=2, mp_context=multiprocessing.get_context("spawn")) as pool:
            futures = [pool.submit(_probe, "auto", str(xml), str(tmp_path)) for _ in range(2)]
            assert all(f.result(timeout=120) == reference for f in futures)
    finally:
        os.environ.pop("ARENA_MATCH_ACCEL", None)
