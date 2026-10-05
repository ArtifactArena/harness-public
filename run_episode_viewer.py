#!/usr/bin/env python3
"""
Interactive MuJoCo Episode Viewer with Camera Control

Launch an interactive viewer to watch robot battles with full camera control.
Press 'R' to reset the episode, 'Q' or close window to quit.

Usage:
    # Load from app match data:
    python run_episode_viewer.py --match-id match-001

    # Load from files directly:
    python run_episode_viewer.py --arena mjarena/assets/sumo_ring_env.xml \
        --red-morphology path/to/red.xml --red-policy path/to/red_controller.py \
        --blue-morphology path/to/blue.xml --blue-policy path/to/blue_controller.py

    # Headless mode (save MP4):
    python run_episode_viewer.py --headless \
        --arena mjarena/assets/sumo_ring_env_studio_3d.xml \
        --red-morphology red.xml --red-policy red.py \
        --blue-morphology blue.xml --blue-policy blue.py \
        --video-path output.mp4 --camera tracking
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path
from typing import Optional, Callable, Mapping, Tuple

import mujoco
import mujoco.viewer
import numpy as np

from mjarena.envs.sumo import compose_sumo_model, SumoEnv
from mjarena.envs.utils import _mj_load
from mjarena.agents.runtime import BotRuntime
from mjarena.agents.types import BotObservation
from mjarena.eval.runtime import build_policy_callable
from mjarena.dspy_core import get_actuator_names
import shutil
from mjarena.utils.file import ensure_dir
from mjarena.design_shop.utils import (
    sanitize_robot_xml, apply_material_properties, inject_motor_mass,
)
from mjarena.design_shop.rules.mj_validators import ModelValidationConfig

logger = logging.getLogger(__name__)

_FORBIDDEN_ROOT_TAGS = {"option"}

_DEFAULT_CONSTRAINTS = Path(__file__).parent / "configs" / "rules" / "rules.yaml"


def _process_robot_xml(xml_str: str, constraints_path: Path) -> str:
    """Apply the material pipeline (sanitize → materials → motor mass) to raw robot XML."""
    config = ModelValidationConfig(constraints_path, physics_mode="3d")
    xml_str = sanitize_robot_xml(xml_str, _FORBIDDEN_ROOT_TAGS)
    xml_str, _, _ = apply_material_properties(
        xml_str, config.material_palette, default_material=config.default_material,
    )
    xml_str = inject_motor_mass(xml_str, config.motor_mass_per_gear)
    return xml_str


def _generate_zero_policy_code(actuator_names: list[str]) -> str:
    """Generate Python code for a zero-action policy."""
    return f'''"""Zero-action policy (immobile)."""

def policy_step(obs: dict) -> dict:
    """Return zero for all actuators."""
    return {{{", ".join(f'"{name}": 0.0' for name in actuator_names)}}}
'''


class InteractiveViewer:
    """Interactive MuJoCo viewer with reset capability and camera control."""

    def __init__(
        self,
        composed_xml: Path,
        red_policy: Callable[[BotObservation], Mapping[str, float]],
        blue_policy: Callable[[BotObservation], Mapping[str, float]],
        max_steps: int = 10000,
        action_history_len: int = 10,
        camera_mode: str = "free",
        size_limits: Optional[Tuple[float, float, float]] = None,
    ):
        self.composed_xml = composed_xml
        self.red_policy = red_policy
        self.blue_policy = blue_policy
        self.max_steps = max_steps
        self.action_history_len = action_history_len
        self.camera_mode = camera_mode
        self.size_limits = size_limits

        # State
        self.model: Optional[mujoco.MjModel] = None
        self.data: Optional[mujoco.MjData] = None
        self.env: Optional[SumoEnv] = None
        self.bot_red: Optional[BotRuntime] = None
        self.bot_blue: Optional[BotRuntime] = None
        self.viewer = None

        self.running = False
        self.paused = False
        self.step_count = 0
        self.winner = None
        self.reset_requested = False
        self.seed = 0

    def _load_model(self):
        """Load or reload the MuJoCo model."""
        self.model, self.data = _mj_load(self.composed_xml)

        # Create bot runtimes
        self.bot_red = BotRuntime(
            model=self.model,
            data=self.data,
            policy_callable=self.red_policy,
            prefix="red_",
            history_len=self.action_history_len,
            obs_lookback=20,
            action_lookback=20,
        )
        self.bot_blue = BotRuntime(
            model=self.model,
            data=self.data,
            policy_callable=self.blue_policy,
            prefix="blue_",
            history_len=self.action_history_len,
            obs_lookback=20,
            action_lookback=20,
        )

        # Create environment (without built-in viewer, we manage our own)
        self.env = SumoEnv(
            model=self.model,
            data=self.data,
            xml_path=str(self.composed_xml),
            red_contender=self.bot_red,
            blue_contender=self.bot_blue,
            max_steps=self.max_steps,
            render_mode=None,  # We manage viewer ourselves
            size_limits=self.size_limits,
        )

    def _setup_viewer(self):
        """Initialize the MuJoCo viewer."""
        if self.viewer is not None:
            return

        self.viewer = mujoco.viewer.launch_passive(
            self.model,
            self.data,
            key_callback=self._key_callback,
        )

        # Configure camera
        with self.viewer.lock():
            self.viewer.cam.type = mujoco.mjtCamera.mjCAMERA_FREE

            if self.camera_mode == "topdown":
                self.viewer.cam.distance = float(self.model.stat.extent) * 1.5
                self.viewer.cam.azimuth = 45
                self.viewer.cam.elevation = -90
            elif self.camera_mode == "side":
                self.viewer.cam.lookat[:] = self.model.stat.center
                self.viewer.cam.distance = float(self.model.stat.extent) * 2.0
                self.viewer.cam.azimuth = 0
                self.viewer.cam.elevation = -15
            else:  # free - default starting position
                self.viewer.cam.lookat[:] = self.model.stat.center
                self.viewer.cam.distance = float(self.model.stat.extent) * 1.8
                self.viewer.cam.azimuth = 135
                self.viewer.cam.elevation = -25

            # Enable various rendering options
            try:
                self.viewer.opt.flags[mujoco.mjtVisFlag.mjVIS_CONTACTPOINT] = False
                self.viewer.opt.flags[mujoco.mjtVisFlag.mjVIS_CONTACTFORCE] = False
                self.viewer.opt.flags[mujoco.mjtVisFlag.mjVIS_JOINT] = False # True
                self.viewer.opt.flags[mujoco.mjtVisFlag.mjVIS_AUTOCONNECT] = False # True
                self.viewer.opt.flags[mujoco.mjtVisFlag.mjVIS_COM] = False
            except:
                pass

    def _key_callback(self, key):
        """Handle keyboard input."""
        # Key codes (ASCII)
        KEY_R = 82  # 'R' - reset
        KEY_r = 114  # 'r' - reset
        KEY_SPACE = 32  # Space - pause/unpause
        KEY_Q = 81  # 'Q' - quit
        KEY_q = 113  # 'q' - quit
        KEY_P = 80  # 'P' - pause
        KEY_p = 112  # 'p' - pause

        if key in (KEY_R, KEY_r):
            logger.info("Reset requested")
            self.reset_requested = True
        elif key in (KEY_SPACE, KEY_P, KEY_p):
            self.paused = not self.paused
            logger.info(f"{'Paused' if self.paused else 'Resumed'}")
        elif key in (KEY_Q, KEY_q):
            logger.info("Quit requested")
            self.running = False

    def _build_observation(self, for_red: bool) -> BotObservation:
        """Build full 3D observation for a bot."""
        my_bot = self.bot_red if for_red else self.bot_blue
        opp_bot = self.bot_blue if for_red else self.bot_red

        my_pos = my_bot.com_position
        opp_pos = opp_bot.com_position
        my_prefix = my_bot.prefix

        my_edge = self.env.closest_distance_to_boundary(my_pos)
        opp_edge = self.env.closest_distance_to_boundary(opp_pos)

        # Contact info
        opp_contact, opp_force, gnd_contact = self.env.get_contact_info(my_prefix)

        return BotObservation(
            my_pos=np.array(my_pos, dtype=np.float32),
            opponent_pos=np.array(opp_pos, dtype=np.float32),
            my_yaw=float(my_bot.yaw),
            my_pitch=float(my_bot.pitch),
            my_roll=float(my_bot.roll),
            opponent_yaw=float(opp_bot.yaw),
            opponent_pitch=float(opp_bot.pitch),
            opponent_roll=float(opp_bot.roll),
            my_velocity=np.array(my_bot.velocity, dtype=np.float32),
            my_angular_velocity=np.array(my_bot.angular_velocity, dtype=np.float32),
            opponent_velocity=np.array(opp_bot.velocity, dtype=np.float32),
            opponent_angular_velocity=np.array(opp_bot.angular_velocity, dtype=np.float32),
            distance_to_opponent=float(np.linalg.norm(my_pos - opp_pos)),
            my_edge_distance=float(my_edge),
            opponent_edge_distance=float(opp_edge),
            opponent_contact=bool(opp_contact),
            opponent_contact_force=float(opp_force),
            ground_contact=bool(gnd_contact),
            is_tipping=float(my_bot.is_tipping),
            t=int(self.step_count),
            max_t=int(self.max_steps),
        )

    def _check_winner(self, info: dict) -> Optional[str]:
        """Check if there's a winner."""
        red_hit_floor = info.get("red_hit_floor", False)
        blue_hit_floor = info.get("blue_hit_floor", False)

        if red_hit_floor and not blue_hit_floor:
            return "blue"
        elif blue_hit_floor and not red_hit_floor:
            return "red"
        return None

    def _step(self):
        """Execute one simulation step."""
        if self.winner is not None:
            # Just sync viewer, don't step physics
            return

        # Build observations
        red_obs = self._build_observation(for_red=True)
        blue_obs = self._build_observation(for_red=False)

        # Get actions from policies
        actions_red = self.bot_red.act(red_obs)
        actions_blue = self.bot_blue.act(blue_obs)

        # Step environment
        _, _, terminated, truncated, info = self.env.step({
            "red": actions_red,
            "blue": actions_blue
        })

        self.step_count += 1

        # Check for winner
        winner = self._check_winner(info)
        if winner:
            self.winner = winner
            self.env.set_winner_lighting(winner)
            logger.info(f"Winner: {winner.upper()} at step {self.step_count}")

    def reset(self):
        """Reset the episode."""
        self.seed += 1
        self.step_count = 0
        self.winner = None
        self.paused = False
        self.reset_requested = False

        # Reset environment
        self.env.reset(seed=self.seed)

        # Reset bot histories
        self.bot_red.action_history.reset()
        self.bot_blue.action_history.reset()

        logger.info(f"Episode reset (seed={self.seed})")

    def run(self):
        """Run the interactive viewer loop."""
        print("\n" + "="*60)
        print("  ARENA - Interactive Episode Viewer")
        print("="*60)
        print("\nControls:")
        print("  Mouse drag    - Rotate camera")
        print("  Scroll        - Zoom in/out")
        print("  Right-drag    - Pan camera")
        print("  R             - Reset episode")
        print("  Space / P     - Pause/Resume")
        print("  Q             - Quit")
        print("="*60 + "\n")

        # Load model and setup viewer
        self._load_model()
        self._setup_viewer()

        # Initial reset
        self.env.reset(seed=self.seed)

        self.running = True

        try:
            while self.running and self.viewer.is_running():
                # Handle reset
                if self.reset_requested:
                    self.reset()

                # Step simulation if not paused
                if not self.paused:
                    self._step()

                # Sync viewer
                self.viewer.sync()

                # Control simulation speed (~100 Hz control)
                time.sleep(0.01)

        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        finally:
            if self.viewer is not None:
                self.viewer.close()
            logger.info("Viewer closed")


def _save_app_match_logs(
    matchup: "MatchupResult",
    match_logs_dir: Path,
    red_name: str,
    blue_name: str,
    red_xml_path: Path,
    blue_xml_path: Path,
    red_policy_path: Optional[Path],
    blue_policy_path: Optional[Path],
    composed_xml_path: Path,
):
    """Save match results in the format the Next.js app expects.

    Creates:
      <match_logs_dir>/tournament_00/round_robin_match/
        bots/0_<red>/  and  bots/1_<blue>/   (robot.xml, controller.py, bot_artifact.json)
        matches/0_vs_1/                       (match_result.json, match_data.json, composed.xml, match.mp4)

    The match_logs_dir name becomes the season name in the app.
    Point MATCH_LOGS_DIR to the parent directory.
    """
    import datetime
    from mjarena.eval.match_runner import save_matchup_to_disk

    tournament = "tournament_00"
    base = ensure_dir(match_logs_dir / tournament / "round_robin_match")

    # ── Bots ──
    for idx, (name, xml_path, policy_path) in enumerate([
        (red_name, red_xml_path, red_policy_path),
        (blue_name, blue_xml_path, blue_policy_path),
    ]):
        bot_dir = ensure_dir(base / "bots" / f"{idx}_{name}")
        shutil.copy2(str(xml_path), str(bot_dir / "robot.xml"))
        if policy_path and policy_path.exists():
            shutil.copy2(str(policy_path), str(bot_dir / "controller.py"))
        artifact = {
            "name": name,
            "generator": name,
            "overview": f"Loaded from {xml_path.name}",
        }
        (bot_dir / "bot_artifact.json").write_text(json.dumps(artifact, indent=2))

    # ── Match ──
    match_dir = ensure_dir(base / "matches" / "0_vs_1")

    # composed.xml
    if composed_xml_path.exists():
        shutil.copy2(str(composed_xml_path), str(match_dir / "composed.xml"))

    # Use save_matchup_to_disk for match_result.json + match_data.json + per-seed videos
    red_wins = matchup.n_wins("red")
    blue_wins = matchup.n_wins("blue")
    save_matchup_to_disk(
        matchup,
        match_dir,
        red_bot=red_name,
        blue_bot=blue_name,
        extra_match_result_fields={
            "red_model": red_name,
            "blue_model": blue_name,
            "red_id": 0,
            "blue_id": 1,
            "timestamp": datetime.datetime.now().isoformat(),
            "wins_a": red_wins,
            "wins_b": blue_wins,
            "ties": matchup.n_ties,
        },
    )

    logger.info(f"Match logs saved to: {match_logs_dir}")


def _print_summary(matchup: "MatchupResult", seeds: list[int], video_path: Path):
    """Print a table of per-seed results and aggregate win counts."""
    n = len(seeds)
    print(f"\n{'=' * 60}")
    print(f"  Match Results ({n} seed{'s' if n > 1 else ''})")
    print(f"{'=' * 60}")

    red_wins = blue_wins = draws = 0
    for seed, record in zip(seeds, matchup.game_records):
        winner = record.winner
        step = record.winner_step or record.num_steps
        if winner == "red":
            label = "\033[31mred wins\033[0m"
            red_wins += 1
        elif winner == "blue":
            label = "\033[34mblue wins\033[0m"
            blue_wins += 1
        else:
            label = "\033[33mdraw\033[0m"
            draws += 1
        print(f"  Seed {seed}: {label}  (step {step})")

    print(f"{'-' * 60}")
    print(f"  Red: {red_wins}  |  Blue: {blue_wins}  |  Draw: {draws}")
    for seed in seeds:
        print(f"  Video: {video_path.parent / f'seed_{seed}.mp4'}")
    print(f"{'=' * 60}\n")


def run_headless(
    composed_xml: Path,
    red_policy: Callable[[BotObservation], Mapping[str, float]],
    blue_policy: Callable[[BotObservation], Mapping[str, float]],
    *,
    video_path: Path,
    max_steps: int = 1000,
    camera: str = "tracking",
    width: int = 1280,
    height: int = 720,
    seeds: list[int],
    score_function: str = "any",
    save_match_logs: Optional[Path] = None,
    red_name: str = "red",
    blue_name: str = "blue",
    red_xml_path: Optional[Path] = None,
    blue_xml_path: Optional[Path] = None,
    red_policy_path: Optional[Path] = None,
    blue_policy_path: Optional[Path] = None,
    match_time: Optional[float] = None,
    inactivity_timeout: Optional[float] = None,
    inactivity_min_displacement: float = 0.5,
    size_limits: Optional[Tuple[float, float, float]] = None,
    rendering_flags: Optional[dict] = None,
):
    """Run headless matches across multiple seeds and save concatenated MP4."""
    from mjarena.runner.episode import run_match
    from mjarena.runner.recording import VideoOverlayInfo
    from mjarena.eval.match_runner import run_seeds, save_matchup_to_disk

    out_dir = ensure_dir(video_path.parent)

    # Build a run_match_fn closure compatible with run_seeds():
    #   run_match_fn(policy_callable, seed=int) -> GameRecord
    def _run_match_fn(red_policy_callable, seed: int = 0):
        seed_video = str(out_dir / f"seed_{seed}.mp4")
        logger.info(f"  Seed {seed}...")

        return run_match(
            composed_xml=composed_xml,
            red_policy_py=red_policy_callable,
            blue_policy_py=blue_policy,
            out_dir=out_dir,
            max_steps=max_steps,
            use_gui=False,
            save_video=True,
            camera_mode=camera,
            video_path=seed_video,
            seed=seed,
            video_width=width,
            video_height=height,
            score_function=score_function,
            overlay_info=VideoOverlayInfo(seed=seed),
            match_time=match_time,
            inactivity_timeout_seconds=inactivity_timeout,
            inactivity_min_displacement=inactivity_min_displacement,
            size_limits=size_limits,
            rendering_flags=rendering_flags,
        )

    matchup = run_seeds(
        run_match_fn=_run_match_fn,
        policy_callable=red_policy,
        seeds=seeds,
    )

    _print_summary(matchup, seeds, video_path)

    # Save app-compatible match logs if requested
    if save_match_logs and red_xml_path and blue_xml_path:
        _save_app_match_logs(
            matchup=matchup,
            match_logs_dir=save_match_logs,
            red_name=red_name,
            blue_name=blue_name,
            red_xml_path=red_xml_path,
            blue_xml_path=blue_xml_path,
            red_policy_path=red_policy_path,
            blue_policy_path=blue_policy_path,
            composed_xml_path=composed_xml,
        )


def load_match_from_app(match_id: str, app_dir: Path) -> dict:
    """Load match data from the app's match-logs."""
    match_file = app_dir / "match-logs" / "matches" / f"{match_id}.json"

    if not match_file.exists():
        raise FileNotFoundError(f"Match not found: {match_file}")

    with open(match_file) as f:
        return json.load(f)


def run_from_match_id(
    match_id: str,
    app_dir: Path,
    arena_xml: Optional[Path] = None,
    camera_mode: str = "free",
    constraints_path: Path = _DEFAULT_CONSTRAINTS,
    process_xml: bool = True,
    headless: bool = False,
    video_path: Optional[Path] = None,
    width: int = 1280,
    height: int = 720,
    seeds: list[int] | None = None,
    max_steps: int = 1000,
    score_function: str = "any",
    match_time: Optional[float] = None,
    inactivity_timeout: Optional[float] = None,
    inactivity_min_displacement: float = 0.5,
    size_limits: Optional[Tuple[float, float, float]] = None,
    rendering_flags: Optional[dict] = None,
):
    """Load and run a match from the app's data."""
    logger.info(f"Loading match: {match_id}")

    match_data = load_match_from_app(match_id, app_dir)

    # Create temp directory for composed model
    out_dir = ensure_dir(Path("logs/viewer_temp"))

    # Get arena XML
    if arena_xml is None:
        arena_xml = Path(__file__).parent / "mjarena" / "assets" / "sumo_ring_env.xml"

    # Process robot XMLs through material pipeline
    red_raw = match_data["red"]["morphology_xml"]
    blue_raw = match_data["blue"]["morphology_xml"]
    if process_xml:
        red_raw = _process_robot_xml(red_raw, constraints_path)
        blue_raw = _process_robot_xml(blue_raw, constraints_path)

    # Write robot XMLs
    red_xml_path = out_dir / "red_robot.xml"
    blue_xml_path = out_dir / "blue_robot.xml"
    red_xml_path.write_text(red_raw)
    blue_xml_path.write_text(blue_raw)

    # Get actuator names
    red_actuator_names = get_actuator_names(str(red_xml_path))
    blue_actuator_names = get_actuator_names(str(blue_xml_path))

    # Build policy callables
    red_policy = build_policy_callable(
        controller_code=match_data["red"]["controller_code"],
        actuator_names=red_actuator_names,
    )
    blue_policy = build_policy_callable(
        controller_code=match_data["blue"]["controller_code"],
        actuator_names=blue_actuator_names,
    )

    # Compose arena
    composed_xml = out_dir / "composed_viewer.xml"
    compose_sumo_model(
        env_xml=str(arena_xml),
        robot_red_xml=str(red_xml_path),
        robot_blue_xml=str(blue_xml_path),
        out_path=str(composed_xml),
    )

    logger.info(f"Composed arena: {composed_xml}")

    if seeds is None:
        seeds = [0]

    if headless:
        run_headless(
            composed_xml=composed_xml,
            red_policy=red_policy,
            blue_policy=blue_policy,
            video_path=video_path or Path("output.mp4"),
            camera=camera_mode,
            width=width,
            height=height,
            seeds=seeds,
            max_steps=max_steps,
            score_function=score_function,
            match_time=match_time,
            inactivity_timeout=inactivity_timeout,
            inactivity_min_displacement=inactivity_min_displacement,
            size_limits=size_limits,
            rendering_flags=rendering_flags,
        )
    else:
        viewer = InteractiveViewer(
            composed_xml=composed_xml,
            red_policy=red_policy,
            blue_policy=blue_policy,
            max_steps=max_steps,
            camera_mode=camera_mode,
            size_limits=size_limits,
        )
        viewer.run()


def run_from_files(
    arena_xml: Path,
    red_morphology: Path,
    blue_morphology: Path,
    red_policy_file: Path,
    blue_policy_file: Optional[Path] = None,
    camera_mode: str = "free",
    constraints_path: Path = _DEFAULT_CONSTRAINTS,
    process_xml: bool = True,
    headless: bool = False,
    video_path: Optional[Path] = None,
    width: int = 1280,
    height: int = 720,
    seeds: list[int] | None = None,
    max_steps: int = 1000,
    score_function: str = "any",
    save_match_logs: Optional[Path] = None,
    match_time: Optional[float] = None,
    inactivity_timeout: Optional[float] = None,
    inactivity_min_displacement: float = 0.5,
    size_limits: Optional[Tuple[float, float, float]] = None,
    rendering_flags: Optional[dict] = None,
):
    """Load and run from individual files."""
    out_dir = ensure_dir(Path("logs/viewer_temp"))

    # Read and optionally process robot XMLs through material pipeline
    red_raw = red_morphology.read_text()
    blue_raw = blue_morphology.read_text()
    if process_xml:
        red_raw = _process_robot_xml(red_raw, constraints_path)
        blue_raw = _process_robot_xml(blue_raw, constraints_path)

    # Write processed XMLs to temp directory
    red_xml = out_dir / "red.xml"
    blue_xml = out_dir / "blue.xml"
    red_xml.write_text(red_raw)
    blue_xml.write_text(blue_raw)

    # Get actuator names
    red_actuator_names = get_actuator_names(red_xml)
    blue_actuator_names = get_actuator_names(blue_xml)

    # Load policies
    red_code = red_policy_file.read_text()
    red_policy = build_policy_callable(
        controller_code=red_code,
        actuator_names=red_actuator_names,
    )

    if blue_policy_file:
        blue_code = blue_policy_file.read_text()
        blue_policy = build_policy_callable(
            controller_code=blue_code,
            actuator_names=blue_actuator_names,
        )
    else:
        # Zero policy
        blue_code = _generate_zero_policy_code(blue_actuator_names)
        blue_policy = build_policy_callable(
            controller_code=blue_code,
            actuator_names=blue_actuator_names,
        )

    # Compose arena
    composed_xml = out_dir / "composed_viewer.xml"
    compose_sumo_model(
        env_xml=str(arena_xml),
        robot_red_xml=str(red_xml),
        robot_blue_xml=str(blue_xml),
        out_path=str(composed_xml),
    )

    logger.info(f"Composed arena: {composed_xml}")

    if seeds is None:
        seeds = [0]

    # Derive bot names from file paths
    red_name = red_morphology.parent.name if red_morphology.parent.name != "." else red_morphology.stem
    blue_name = blue_morphology.parent.name if blue_morphology.parent.name != "." else blue_morphology.stem
    # Avoid duplicate names
    if red_name == blue_name:
        red_name = f"{red_name}-red"
        blue_name = f"{blue_name}-blue"

    if headless:
        run_headless(
            composed_xml=composed_xml,
            red_policy=red_policy,
            blue_policy=blue_policy,
            video_path=video_path or Path("output.mp4"),
            camera=camera_mode,
            width=width,
            height=height,
            seeds=seeds,
            max_steps=max_steps,
            score_function=score_function,
            save_match_logs=save_match_logs,
            red_name=red_name,
            blue_name=blue_name,
            red_xml_path=red_xml,
            blue_xml_path=blue_xml,
            red_policy_path=red_policy_file,
            blue_policy_path=blue_policy_file,
            match_time=match_time,
            inactivity_timeout=inactivity_timeout,
            inactivity_min_displacement=inactivity_min_displacement,
            size_limits=size_limits,
            rendering_flags=rendering_flags,
        )
    else:
        viewer = InteractiveViewer(
            composed_xml=composed_xml,
            red_policy=red_policy,
            blue_policy=blue_policy,
            max_steps=max_steps,
            camera_mode=camera_mode,
            size_limits=size_limits,
        )
        viewer.run()


def resolve_inactivity_rule(
    args: argparse.Namespace, tournament_match: Mapping[str, object]
) -> Tuple[Optional[float], float]:
    """Resolve (inactivity_timeout, inactivity_min_displacement): CLI flag > config > disabled.

    Once a tournament config is actually loaded, its tournament.match section
    always carries these keys (base.yaml provides them) — a missing key there
    is a broken config, not a legitimate "no rule" state, so it raises instead
    of silently disabling the rule. With no --config at all there is no
    section to read the rule from, so "disabled" is the documented default —
    unless --inactivity-timeout was passed without --config, in which case
    there is no config to fall back to for the displacement half either, and
    a hardcoded number would silently play a different rule from the one the
    tournament plays if base.yaml ever changed it, so that also raises.
    """
    if args.skip_inactivity_check:
        inactivity_timeout = None
    elif args.inactivity_timeout is not None:
        inactivity_timeout = args.inactivity_timeout
    elif args.config is None:
        inactivity_timeout = None
    elif "inactivity_timeout" in tournament_match:
        inactivity_timeout = tournament_match["inactivity_timeout"]
    else:
        raise KeyError(
            f"missing 'inactivity_timeout' in tournament.match of {args.config} "
            "(no fallback — pass a config that inherits from base.yaml, or pass "
            "--inactivity-timeout / --skip-inactivity-check explicitly)"
        )
    # The displacement half of the same rule, read the same way: CLI flag >
    # config > raise (raise also when --inactivity-timeout enabled the rule
    # without --config, since there is then no config to fall back to either).
    # A hardcoded 0.5 here would silently play a different rule from the one
    # the tournament plays if base.yaml ever changed the number.
    if inactivity_timeout is None:
        inactivity_min_displacement = 0.0   # rule disabled; the value is never read
    elif args.inactivity_min_displacement is not None:
        inactivity_min_displacement = args.inactivity_min_displacement
    elif args.config is None:
        raise ValueError(
            "--inactivity-timeout was given without --config, so there is no "
            "tournament.match section to read 'inactivity_min_displacement' from "
            "(no fallback — pass --inactivity-min-displacement explicitly, or "
            "pass --config)"
        )
    elif "inactivity_min_displacement" in tournament_match:
        inactivity_min_displacement = tournament_match["inactivity_min_displacement"]
    else:
        raise KeyError(
            f"missing 'inactivity_min_displacement' in tournament.match of {args.config} "
            "(no fallback — pass a config that inherits from base.yaml, or pass "
            "--inactivity-min-displacement / --skip-inactivity-check explicitly)"
        )

    return inactivity_timeout, inactivity_min_displacement


def main():
    parser = argparse.ArgumentParser(
        description="Interactive MuJoCo Episode Viewer with Camera Control",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Controls:
  Mouse drag    - Rotate camera
  Scroll        - Zoom in/out
  Right-drag    - Pan camera
  R             - Reset episode
  Space / P     - Pause/Resume
  Q             - Quit

Examples:
  # Load from app match data:
  python run_episode_viewer.py --match-id match-001

  # Load from files:
  python run_episode_viewer.py --arena mjarena/assets/sumo_ring_env.xml \\
      --red-morphology car.xml --red-policy controller.py
        """,
    )

    # Mode selection
    parser.add_argument(
        "--run-episode-directly-nightly",
        action="store_true",
        help="Enable nightly/experimental mode",
    )

    # Match loading
    parser.add_argument(
        "--match-id",
        type=str,
        help="Match ID to load from app/match-logs",
    )
    parser.add_argument(
        "--app-dir",
        type=Path,
        default=Path(__file__).parent / "app",
        help="Path to app directory containing match-logs",
    )

    # File loading
    parser.add_argument(
        "--arena",
        type=Path,
        help="Arena environment XML",
    )
    parser.add_argument(
        "--red-morphology",
        type=Path,
        help="Red robot XML or builder",
    )
    parser.add_argument(
        "--blue-morphology",
        type=Path,
        help="Blue robot XML or builder (default: same as red)",
    )
    parser.add_argument(
        "--red-policy",
        type=Path,
        help="Red controller Python file",
    )
    parser.add_argument(
        "--blue-policy",
        type=Path,
        help="Blue controller Python file (default: zero policy)",
    )

    # Config
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Tournament YAML for defaults (arena, camera, steps, etc.)",
    )

    # Viewer options
    parser.add_argument(
        "--camera",
        type=str,
        choices=["free", "topdown", "side", "tracking", "orbit", "top"],
        default=None,
        help="Camera mode (default: free for interactive, tracking for headless)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )

    # Headless / video options
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run headless, save MP4, and exit",
    )
    parser.add_argument(
        "--video-path",
        type=Path,
        default=None,
        help="Output video path (headless only, default: output.mp4)",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=None,
        help="Video width (headless only, default: 1280)",
    )
    parser.add_argument(
        "--height",
        type=int,
        default=None,
        help="Video height (headless only, default: 720)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=0,
        help="Random seed base for spawn positions",
    )
    parser.add_argument(
        "--n-rollouts",
        type=int,
        default=None,
        help="Number of seeds to run (headless only, default: 1)",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=None,
        help="Max simulation steps per match (default: 1000)",
    )
    parser.add_argument(
        "--score-function",
        type=str,
        choices=["any", "thres-50"],
        default=None,
        help="Score function (default: any)",
    )

    # Match time / inactivity
    parser.add_argument(
        "--match-time",
        type=float,
        default=None,
        help="Match duration in seconds of sim time (overrides --max-steps)",
    )
    parser.add_argument(
        "--inactivity-timeout",
        type=float,
        default=None,
        help="Seconds of inactivity before bot loses (default: from config or disabled)",
    )
    parser.add_argument(
        "--inactivity-min-displacement",
        type=float,
        default=None,
        help="Metres of COM travel that clear the inactivity window (default: from config)",
    )
    parser.add_argument(
        "--skip-inactivity-check",
        action="store_true",
        help="Force-disable inactivity timeout even if config enables it",
    )

    # Material processing
    parser.add_argument(
        "--constraints",
        type=Path,
        default=None,
        help="Constraints YAML for material pipeline",
    )
    parser.add_argument(
        "--no-process",
        action="store_true",
        help="Skip material processing (for pre-processed XMLs)",
    )
    parser.add_argument(
        "--save-match-logs",
        type=Path,
        default=None,
        help="Save match logs in app-compatible format to this directory (enables telemetry viewing in the web app)",
    )
    parser.add_argument(
        "--render-blender",
        action="store_true",
        help="After running the match, re-render with Blender Cycles for cinematic quality (requires blender on PATH)",
    )
    parser.add_argument(
        "--blender-samples",
        type=int,
        default=16,
        help="Blender render samples (default: 16)",
    )
    parser.add_argument(
        "--blender-engine",
        choices=["eevee", "cycles"],
        default="eevee",
        help="Blender engine (default: eevee; cycles for ray-traced)",
    )

    args = parser.parse_args()

    # Auto-enable save-match-logs if render-blender is on
    if args.render_blender and not args.save_match_logs:
        args.save_match_logs = Path("logs/blender_render_temp")

    # Setup logging
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.run_episode_directly_nightly:
        logger.info("Running in nightly mode (experimental features enabled)")

    # ── Load config if provided ──────────────────────────────────────
    config: dict = {}
    if args.config:
        from run_baseline_agent import load_tournament_config
        config = load_tournament_config(args.config)

    # Read from new config structure (rules/models_as_engineers/tournament)
    rules_cfg = config.get("rules", {})
    tournament_cfg = config.get("tournament", {})
    tournament_match = tournament_cfg.get("match", {})
    build_cfg = config.get("models_as_engineers", config.get("build", {}))
    rendering_flags = config.get("rendering", {
        "show_joint": False,
        "show_com": False,
        "show_contact_point": False,
        "show_contact_force": False,
        "show_autoconnect": False,
    })

    # ── Resolve: CLI flag > config > hardcoded default ───────────────
    arena       = args.arena or Path(rules_cfg.get("arena", config.get("arena", "mjarena/assets/sumo_ring_env_cinematic_3d.xml")))
    constraints = args.constraints or Path(rules_cfg.get("constraints", config.get("constraints", str(_DEFAULT_CONSTRAINTS))))
    camera      = args.camera or tournament_match.get("camera", "tracking" if args.headless else "free")
    max_steps   = args.max_steps or tournament_match.get("max_steps", 1000)
    n_rollouts  = args.n_rollouts or tournament_match.get("n_rollouts", 1)
    score_fn    = args.score_function or rules_cfg.get("off_the_ring_criteria", "any")
    width       = args.width or tournament_match.get("video_width", 1280)
    height      = args.height or tournament_match.get("video_height", 720)
    video_path  = args.video_path or Path("logs/viewer_temp/output.mp4")

    # Match time (overrides max_steps)
    match_time  = args.match_time or tournament_match.get("match_time", 120)
    max_steps = int(match_time / 0.01)

    # Inactivity timeout / min displacement: resolved together (see
    # resolve_inactivity_rule's docstring for the CLI > config > disabled/raise
    # policy behind this).
    inactivity_timeout, inactivity_min_displacement = resolve_inactivity_rule(
        args, tournament_match
    )

    # Runtime size limit: the viewer plays the same box the validator (and the
    # tournament/qualification/two-stage paths) enforce. This file composes
    # and validates robots as 3D only, same as _process_robot_xml() above.
    validation_config = ModelValidationConfig(constraints, physics_mode="3d")
    size_limits = (
        validation_config.max_robot_x_span,
        validation_config.max_robot_y_span,
        validation_config.max_robot_z_span,
    )

    # Seed generation: [seed_base, seed_base+1, ..., seed_base+n_rollouts-1]
    seeds = [args.seed + i for i in range(n_rollouts)]

    # ── Determine which mode to run ──────────────────────────────────
    if args.match_id:
        run_from_match_id(
            match_id=args.match_id,
            app_dir=args.app_dir,
            arena_xml=arena,
            camera_mode=camera,
            constraints_path=constraints,
            process_xml=not args.no_process,
            headless=args.headless,
            video_path=video_path,
            width=width,
            height=height,
            seeds=seeds,
            max_steps=max_steps,
            score_function=score_fn,
            match_time=match_time,
            inactivity_timeout=inactivity_timeout,
            inactivity_min_displacement=inactivity_min_displacement,
            size_limits=size_limits,
            rendering_flags=rendering_flags,
        )
    elif args.red_morphology and args.red_policy:
        blue_morph = args.blue_morphology or args.red_morphology
        run_from_files(
            arena_xml=arena,
            red_morphology=args.red_morphology,
            blue_morphology=blue_morph,
            red_policy_file=args.red_policy,
            blue_policy_file=args.blue_policy,
            camera_mode=camera,
            constraints_path=constraints,
            process_xml=not args.no_process,
            headless=args.headless,
            video_path=video_path,
            width=width,
            height=height,
            seeds=seeds,
            max_steps=max_steps,
            score_function=score_fn,
            save_match_logs=args.save_match_logs,
            match_time=match_time,
            inactivity_timeout=inactivity_timeout,
            inactivity_min_displacement=inactivity_min_displacement,
            size_limits=size_limits,
            rendering_flags=rendering_flags,
        )
    else:
        parser.error(
            "Either --match-id OR (--red-morphology, --red-policy) required"
        )

    # Optional Blender Cycles re-render
    if args.render_blender and args.save_match_logs:
        import glob
        match_dirs = glob.glob(str(args.save_match_logs / "**/match_data.json"), recursive=True)
        if not match_dirs:
            logger.error("No match_data.json found — cannot run Blender render")
        else:
            match_dir = Path(match_dirs[0]).parent
            logger.info(f"Running Blender Cycles render from {match_dir}")
            from mjarena.rendering.render_cinematic import run_export, run_blender, stitch_frames
            import tempfile, shutil

            blender_output = video_path.parent / f"{video_path.stem}_cinematic.mp4"
            with tempfile.TemporaryDirectory(prefix="cinematic_") as tmpdir:
                tmpdir = Path(tmpdir)
                trajectory_npz = tmpdir / "trajectory.npz"
                run_export(match_dir / "composed.xml", match_dir / "match_data.json", seeds[0], trajectory_npz)
                frames_dir = tmpdir / "frames"
                frames_dir.mkdir()
                run_blender("blender", trajectory_npz, frames_dir, width, height, args.blender_samples, args.blender_engine)
                import numpy as np
                traj = np.load(trajectory_npz)
                render_fps = int(float(traj["fps"]) / 3)  # default frame_step=3
                stitch_frames(frames_dir, blender_output, render_fps)
                logger.info(f"Cinematic video: {blender_output}")


if __name__ == "__main__":
    main()
