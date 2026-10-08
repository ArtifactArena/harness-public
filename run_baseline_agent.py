#!/usr/bin/env python3
"""
Run N iterations of Build-only, then Tournament-only for LLM Arena competition.

The two phases are completely separated:

Phase 1 (BUILD): Run N iterations where each LLM generates a bot per iteration.
    No tournament feedback is used between iterations — each build is independent.

Phase 2 (TOURNAMENT): Go back through each iteration's bots directory and run
    round-robin matches.

Usage:
    # Using config file (recommended):
    python run_baseline_agent.py --config configs/tournaments/tournament.yaml

    # Override iterations:
    python run_baseline_agent.py --config configs/tournaments/tournament.yaml --iterations 5

    # Skip tournament phase (build only):
    python run_baseline_agent.py --config configs/tournaments/tournament.yaml --build-only

    # Skip build phase (tournament only, requires existing bot dirs):
    python run_baseline_agent.py --config configs/tournaments/tournament.yaml --tournament-only

    # Continue builds from where you left off:
    python run_baseline_agent.py --continue logs/20260317/my_season/

    # Continue and re-run from first incomplete build:
    python run_baseline_agent.py --continue logs/20260317/my_season/ --rerun-incomplete
"""
from __future__ import annotations

import argparse
import datetime
import io
import json
import logging
import random
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


class _TeeWriter(io.TextIOBase):
    """Write to both a terminal stream and a log file."""

    def __init__(self, path: Path, *, stream=None, file=None):
        self._stream = stream or sys.__stdout__
        self._file = file or open(path, "a", encoding="utf-8")

    def write(self, s):
        self._stream.write(s)
        self._file.write(s)
        self._file.flush()
        return len(s)

    def flush(self):
        self._stream.flush()
        self._file.flush()

    def isatty(self):
        return bool(getattr(self._stream, "isatty", lambda: False)())

    def write_ephemeral(self, s: str) -> int:
        """Write terminal-only content, skipping the log file."""
        self._stream.write(s)
        self._stream.flush()
        return len(s)


import yaml

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from mjarena.agents.types import BotArtifact
from mjarena.core import BuildConfig, generate_bots
from mjarena.core.rules_config import RulesConfig
from mjarena.tournament import (
    run_round_robin, TournamentResult, elo_rank_players,
    MatchOutcome, compute_standings, MatchResult,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config loading & helpers (also imported by calculate_elo.py, episode_viewer)
# ---------------------------------------------------------------------------

def _deep_merge(base: dict, override: dict) -> dict:
    """Deep merge two dicts. Override wins. Lists are replaced, not appended."""
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_tournament_config(config_path: Path) -> Dict[str, Any]:
    """Load tournament configuration from YAML file.

    Supports single-level inheritance via a ``base:`` key that points to a
    parent YAML (resolved relative to the child's directory).  The parent is
    deep-merged with the child, and the child's values win on conflict.

    Args:
        config_path: Path to tournament config YAML

    Returns:
        Dictionary with all configuration settings
    """
    if not config_path.exists():
        raise FileNotFoundError(f"Tournament config not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    base_ref = config.pop("base", None)
    if base_ref:
        base_path = config_path.parent / base_ref
        if not base_path.exists():
            raise FileNotFoundError(
                f"Base config not found: {base_path} (referenced by {config_path})"
            )
        with base_path.open("r", encoding="utf-8") as f:
            base_config = yaml.safe_load(f) or {}
        config = _deep_merge(base_config, config)

    return config


def save_consolidated_prompt(cfg: BuildConfig, output_dir: Path) -> Path:
    """Snapshot the run's consolidated design document next to config.yaml.

    Every build in the run sends this exact text, so it is written once per run rather
    than once per bot. Returns the path written.
    """
    from mjarena.core.unified_builder import load_consolidated_prompt

    name, text = load_consolidated_prompt(cfg)
    path = output_dir / name
    path.write_text(text, encoding="utf-8")
    return path


def save_resolved_config(config: Dict[str, Any], output_dir: Path) -> None:
    """Write a self-sufficient config (no ``base:`` key) to *output_dir*/config.yaml."""
    config_to_save = dict(config)
    config_to_save.pop("base", None)
    path = output_dir / "config.yaml"
    with path.open("w", encoding="utf-8") as f:
        f.write("# Resolved tournament config (self-sufficient, no base reference)\n")
        yaml.dump(config_to_save, f, default_flow_style=False, sort_keys=False)


def config_to_args(config: Dict[str, Any]) -> Dict[str, Any]:
    """Convert tournament config to run_baseline_agent() arguments.

    Reads from new config structure (rules/models_as_engineers/tournament).
    Falls back to legacy keys (build/top-level arena) for backward compat.

    Args:
        config: Tournament configuration dictionary

    Returns:
        Dictionary of arguments for run_baseline_agent()
    """
    from mjarena.core.rules_config import MatchConfig
    from mjarena.core.build_config import ControllerValidationParams, ObservationConfig

    # Extract nested configs — new keys with legacy fallback
    season = config.get("season", {})
    build = config.get("models_as_engineers", config.get("build", {}))
    tournament = config.get("tournament", {})
    output = config.get("output", {})

    # Convert LLM paths to Path objects
    llm_paths = [Path(p) for p in config.get("llms", [])]

    # Extract IDs
    env = season.get("env", "DEBUG")
    season_id = season.get("season_id", "season_00")
    tournament_id = season.get("tournament_id", "tournament_00")

    # Handle output_dir with template substitution
    output_dir = season.get("output_dir", "logs/{date}/{tournament_id}")
    output_dir = output_dir.replace("{date}", datetime.datetime.now().strftime("%Y%m%d"))
    output_dir = output_dir.replace("{tournament_id}", tournament_id)
    output_dir = output_dir.replace("{season_id}", season_id)
    output_dir = output_dir.replace("{env}", env)

    # Parse rules config (handles both new "rules" section and legacy format)
    rules = RulesConfig.from_yaml(config)
    # Sync physics_mode into build dict so BuildConfig picks it up
    build["physics_mode"] = rules.physics_mode

    # Build all build-phase params into a single BuildConfig
    cfg = BuildConfig.from_yaml(build, output)

    # Bridge controller rules into BuildConfig
    cfg.controller_validation_params = ControllerValidationParams.from_controller_rules(rules.controller)

    # --- Tournament match config ---
    tournament_match = tournament.get("match", {})
    match_fields = {f.name for f in __import__("dataclasses").fields(MatchConfig)}
    match_kwargs = {k: v for k, v in tournament_match.items() if k in match_fields}
    tournament_match_config = MatchConfig(**match_kwargs)
    # One inactivity rule for the whole game: qualification uses the tournament's values.
    cfg.controller_validation_params.inactivity_timeout = tournament_match_config.inactivity_timeout
    cfg.controller_validation_params.inactivity_min_displacement = tournament_match_config.inactivity_min_displacement
    # The prompt states the MuJoCo version and commit budget this run actually uses.
    import mujoco
    cfg.game_spec_vars = {
        "mujoco_version": mujoco.__version__,
        "commit_budget": cfg.commit_budget,
    }

    # --- Observation config from tournament.agents.observation ---
    obs_cfg_dict = tournament.get("agents", {}).get("observation", {})
    if obs_cfg_dict:
        obs_fields = {f.name for f in __import__("dataclasses").fields(ObservationConfig)}
        obs_kwargs = {k: v for k, v in obs_cfg_dict.items() if k in obs_fields}
        observation_config = ObservationConfig(**obs_kwargs)
    else:
        observation_config = cfg.observation  # fallback to build config

    # Runtime size limit: the tournament plays the same box the validator enforces.
    from mjarena.design_shop.rules.mj_validators import ModelValidationConfig
    validation_config = ModelValidationConfig(
        constraints_yaml_path=rules.constraints,
        physics_mode=rules.physics_mode,
    )
    size_limits = (
        validation_config.max_robot_x_span,
        validation_config.max_robot_y_span,
        validation_config.max_robot_z_span,
    )

    # Derive legacy-compatible values from MatchConfig
    match_time = tournament_match_config.match_time
    inactivity_timeout = tournament_match_config.inactivity_timeout
    inactivity_min_displacement = tournament_match_config.inactivity_min_displacement

    # Legacy fallback for tournament params not yet in MatchConfig
    n_rollouts = tournament_match_config.n_rollouts
    camera = tournament_match_config.camera
    record_video = tournament_match_config.save_video

    return {
        "llm_config_paths": llm_paths,
        "arena_xml": rules.arena,
        "constraints_path": rules.constraints,
        "rules": rules,
        "output_dir": Path(output_dir),
        "env": env,
        "season_id": season_id,
        "tournament_id": tournament_id,
        "iterations": season.get("iterations", 10),
        "cfg": cfg,
        # Required keys (configs/tournaments/base.yaml). They govern the match
        # feedback the build loop shows the model, so a missing one is a
        # KeyError, not a silent default a published run would carry.
        "use_previous_match_data_for_build": build["use_previous_match_data_for_build"],
        "max_feedback_examples": build["max_feedback_examples"],
        # Tournament params
        "tournament_match": tournament_match_config,
        "observation_config": observation_config,
        "n_rollouts": n_rollouts,
        "max_steps": tournament_match_config.max_steps,
        "record_video": record_video,
        "save_all_videos": tournament.get("save_all_videos", False),
        "highres": tournament.get("highres", False),
        "camera": camera,
        "score_function": rules.off_the_ring_criteria,
        "n_parallel_matches": tournament.get("n_parallel_tournament", 1),
        "n_parallel_seeds": 1,
        "gear_clamp_ratio": validation_config.gear_clamp_ratio,
        "include_baselines": tournament.get("include_baselines", True),
        "match_time": match_time,
        "inactivity_timeout": inactivity_timeout,
        "inactivity_min_displacement": inactivity_min_displacement,
        "size_limits": size_limits,
        "verbose": output.get("verbose", True),
        "trace_progress": True,
        "elo_config": config.get("elo", {}),
        "rendering_flags": config.get("rendering"),
    }


def _cli_default_build_config() -> "BuildConfig":
    """The BuildConfig a CLI run with neither --config nor --continue uses.

    One big prompt per harness: the iterative brief, with the placeholder values the
    document needs, exactly as ``config_to_args`` fills them from a tournament YAML.
    """
    import mujoco

    cfg = BuildConfig(
        unified_generation=True,
        autoresearch_prompt_path="configs/rules/autoresearch_prompt.md",
    )
    cfg.game_spec_vars = {
        "mujoco_version": mujoco.__version__,
        "commit_budget": cfg.commit_budget,
    }
    return cfg


def _cli_default_run_args() -> Dict[str, Any]:
    """The run_args main() uses with neither --config nor --continue (CLI defaults).

    Every key a run reads must be present here with the same meaning
    ``config_to_args`` gives it, because both feed the same ``run_season`` call.
    In particular the match rules are armed exactly as in a config-driven run:
    inactivity 10 s / 0.5 m, and the runtime size box read from the same
    rules file.
    """
    from mjarena.design_shop.rules.mj_validators import ModelValidationConfig

    date_str = datetime.datetime.now().strftime("%Y%m%d")
    constraints_path = Path("configs/rules/rules.yaml")
    # Same source of truth as config_to_args: never a second copy of the numbers.
    validation_config = ModelValidationConfig(
        constraints_yaml_path=constraints_path,
        physics_mode="3d",
    )
    return {
        "llm_config_paths": [],
        "arena_xml": Path("mjarena/assets/sumo_ring_env_cinematic_3d.xml"),
        "constraints_path": constraints_path,
        "output_dir": Path(f"logs/{date_str}/tournament"),
        "env": "DEBUG",
        "season_id": "season_00",
        "tournament_id": "tournament_00",
        "iterations": 10,
        "cfg": _cli_default_build_config(),
        "use_previous_match_data_for_build": False,
        "max_feedback_examples": 3,
        "n_rollouts": 5,
        "max_steps": 1000,
        "record_video": True,
        "save_all_videos": True,
        "highres": False,
        "camera": "tracking",
        "score_function": "any",
        "n_parallel_matches": 1,
        "n_parallel_seeds": 1,
        "gear_clamp_ratio": validation_config.gear_clamp_ratio,
        "inactivity_timeout": 10.0,
        "inactivity_min_displacement": 0.5,
        "size_limits": (
            validation_config.max_robot_x_span,
            validation_config.max_robot_y_span,
            validation_config.max_robot_z_span,
        ),
        "verbose": True,
        "trace_progress": True,
        "elo_config": {},
        "raise_on_error": False,
    }


def _disable_tournament_render_outputs(run_args: Dict[str, Any]) -> None:
    """Disable tournament-side rendering and video output only."""
    run_args["record_video"] = False
    run_args["save_all_videos"] = False
    run_args["highres"] = False


def load_llm_configs(config_paths: List[Path]) -> Dict[str, Path]:
    """Load LLM configuration paths and extract names.

    Args:
        config_paths: List of paths to LLM config YAML files

    Returns:
        Dictionary mapping LLM name (from filename) to config path
    """
    configs = {}
    for path in config_paths:
        if not path.exists():
            raise FileNotFoundError(f"LLM config not found: {path}")
        # Use stem as name (e.g., "gpt4o" from "gpt4o.yaml")
        name = path.stem
        configs[name] = path
    return configs


# ---------------------------------------------------------------------------
# Baseline bot injection
# ---------------------------------------------------------------------------

_BASELINE_DIR = Path(__file__).resolve().parent / "mjarena" / "core" / "assets" / "baseline_bots"


def _inject_baseline_bots(
    bots: Dict[str, BotArtifact],
    bots_dir: Path,
) -> Dict[str, BotArtifact]:
    """Copy baseline bots into bots_dir and add them to the bots dict.

    Auto-discovers all subdirs in ``baseline_bots/`` that contain a
    ``bot_artifact.json``.  Each subdirectory name becomes the generator
    name (e.g. ``baseline-static``).

    Args:
        bots: Existing bots dict (mutated in-place AND returned).
        bots_dir: Directory where all bot folders live (e.g. ``round_robin_match/bots/``).

    Returns:
        The same *bots* dict with baseline entries added.
    """
    if not _BASELINE_DIR.is_dir():
        return bots

    for baseline_dir in sorted(_BASELINE_DIR.iterdir()):
        if not baseline_dir.is_dir() or not (baseline_dir / "bot_artifact.json").exists():
            continue

        dest = bots_dir / baseline_dir.name
        shutil.copytree(baseline_dir, dest, dirs_exist_ok=True)

        artifact = BotArtifact.load(dest)
        # Fix relative paths to absolute after copy
        artifact.morphology_xml = dest / "robot.xml"
        artifact.controller_code = dest / "controller.py"
        bots[artifact.name] = artifact

    return bots


# ---------------------------------------------------------------------------
# Tournament phase (single iteration)
# ---------------------------------------------------------------------------

def run_tournament_phase(
    bots: Dict[str, BotArtifact],
    arena_xml: Path,
    tournament_dir: Path,
    *,
    n_rollouts: int = 5,
    max_steps: int = 1000,
    record_video: bool = True,
    save_all_videos: bool = True,
    highres: bool = False,
    verbose: bool = True,
    trace_progress: bool = True,
    use_material_palette: bool = False,
    season_id: str = "",
    tournament_id: str = "",
    camera_mode: str = "tracking",
    score_function: str = "any",
    iteration: int = 0,
    season_root: Optional[Path] = None,
    init_seed: int = 42,
    physics_mode: str = "3d",
    n_parallel_matches: int = 1,
    n_parallel_seeds: int = 1,
    gear_clamp_ratio: float = 0.0,
    match_time: Optional[float] = None,
    inactivity_timeout_seconds: Optional[float] = 10.0,
    inactivity_min_displacement: float = 0.5,
    size_limits: Optional[Tuple[float, float, float]] = None,
    contact_fidelity: str = "high",
    raise_on_error: bool = False,
    rendering_flags: Optional[Dict[str, bool]] = None,
) -> TournamentResult:
    """Run tournament phase: round-robin matches between all bots.

    Forfeit bots (those that failed generation) automatically lose to all valid bots.
    Valid bots compete normally in round-robin matches.

    Args:
        bots: Dictionary mapping LLM name to BotArtifact
        arena_xml: Path to arena XML
        tournament_dir: Directory for tournament outputs
        n_rollouts: Matches per bot pair
        max_steps: Max simulation steps
        record_video: Save videos
        save_all_videos: Save video for every rollout (not just 1 per direction)
        highres: Use high resolution (1920x1080) for videos
        verbose: Print progress
        iteration: Current season iteration (for JSON enrichment + seed scheme).
        season_root: Root output directory of the season (for relative paths in JSON).

    Returns:
        TournamentResult with matches and standings (including forfeit matches)
    """
    if len(bots) < 2:
        logger.warning("Not enough bots for tournament (need at least 2)")
        return TournamentResult(
            matches=[],
            standings={name: {"wins": 0, "losses": 0, "draws": 0, "elo": 1000.0}
                      for name in bots.keys()},
            elo_history=[{name: 1000.0 for name in bots.keys()}],
            metadata={"error": "Not enough bots"},
        )

    # Separate forfeit bots from valid bots
    forfeit_bots = {name: bot for name, bot in bots.items() if bot.forfeit}
    valid_bots = {name: bot for name, bot in bots.items() if not bot.forfeit and bot.controller_verified}
    failed_verification_bots = {name: bot for name, bot in bots.items() if not bot.forfeit and not bot.controller_verified}

    # Combine failed verification bots into forfeit category (they also auto-lose)
    all_failed_bots = {**forfeit_bots, **failed_verification_bots}

    forfeit_matches: List[MatchResult] = []

    # Log forfeit/failed bots
    if all_failed_bots and verbose:
        print(f"\n{'='*60}")
        print(f"FORFEIT BOTS: {len(all_failed_bots)}")
        print(f"{'='*60}")
        for name, bot in all_failed_bots.items():
            if bot.forfeit:
                print(f"  - {name}: FORFEIT at {bot.forfeit_stage}")
                print(f"      Error: {bot.forfeit_error[:100]}...")
            else:
                print(f"  - {name}: FAILED VERIFICATION")
                for err in bot.controller_errors:
                    print(f"      {err}")

    # Build bot_name_to_id mapping for all bots (use list index as ID)
    bot_name_to_id = {name: idx for idx, name in enumerate(bots.keys())}

    # Create forfeit matches: one match per pair, forfeiter loses
    for failed_name, failed_bot in all_failed_bots.items():
        for valid_name, valid_bot in valid_bots.items():
            forfeit_matches.append(MatchResult(
                red_bot=failed_name,
                blue_bot=valid_name,
                winner="blue",
                red_score=-1.0,
                seed=0,
                steps=0,
                video_path=None,
                details={
                    "forfeit": True,
                    "forfeit_stage": failed_bot.forfeit_stage if failed_bot.forfeit else "controller",
                    "forfeit_error": failed_bot.forfeit_error if failed_bot.forfeit else "; ".join(failed_bot.controller_errors),
                    "forfeit_bot": failed_name,
                },
            ))

    # Both bots forfeit — tie (one match per pair)
    failed_bot_names = list(all_failed_bots.keys())
    for i, name_a in enumerate(failed_bot_names):
        for name_b in failed_bot_names[i+1:]:
            forfeit_matches.append(MatchResult(
                red_bot=name_a,
                blue_bot=name_b,
                winner="tie",
                red_score=0.0,
                seed=0,
                steps=0,
                video_path=None,
                details={
                    "forfeit": True,
                    "forfeit_stage": "both",
                    "forfeit_error": "Both bots forfeited",
                },
            ))

    if verbose and forfeit_matches:
        print(f"\n[FORFEIT] Created {len(forfeit_matches)} forfeit match records")

    # Save forfeit matches to matches/ directory (same location as round-robin results)
    if forfeit_matches:
        matches_dir = tournament_dir / "matches"
        matches_dir.mkdir(parents=True, exist_ok=True)
        for fm in forfeit_matches:
            id_a = bot_name_to_id.get(fm.red_bot, 0)
            id_b = bot_name_to_id.get(fm.blue_bot, 0)
            gen_a = bots[fm.red_bot].generator if fm.red_bot in bots else fm.red_bot
            gen_b = bots[fm.blue_bot].generator if fm.blue_bot in bots else fm.blue_bot
            if id_a > id_b:
                id_a, id_b = id_b, id_a
                gen_a, gen_b = gen_b, gen_a
            is_tie = fm.winner == "tie"
            forfeit_data = {
                "red_bot": fm.red_bot,
                "blue_bot": fm.blue_bot,
                "red_model": bots[fm.red_bot].generator if fm.red_bot in bots else "",
                "blue_model": bots[fm.blue_bot].generator if fm.blue_bot in bots else "",
                "red_id": bot_name_to_id.get(fm.red_bot, 0),
                "blue_id": bot_name_to_id.get(fm.blue_bot, 0),
                "iteration": iteration,
                "timestamp": datetime.datetime.now().isoformat(),
                "wins_a": 0,
                "wins_b": 0 if is_tie else 1,
                "ties": 1 if is_tie else 0,
                "n_seeds": 1,
                "matches": [{
                    "seed": 0,
                    "winner": fm.winner,
                    "red_score": fm.red_score,
                    "num_steps": 0,
                    "winner_step": 0,
                    "progress": 0.0,
                    "initial_distance": 0.0,
                    "forfeit": True,
                    "forfeit_stage": fm.details.get("forfeit_stage", ""),
                    "forfeit_error": fm.details.get("forfeit_error", ""),
                }],
            }
            matchup_dir = matches_dir / f"{gen_a}_vs_{gen_b}"
            matchup_dir.mkdir(parents=True, exist_ok=True)
            result_path = matchup_dir / "match_result.json"
            with result_path.open("w", encoding="utf-8") as f:
                json.dump(forfeit_data, f, indent=2)

    # Run actual tournament only with valid bots
    if len(valid_bots) >= 2:
        if verbose:
            print(f"\n{'='*60}")
            print(f"TOURNAMENT PHASE: {len(valid_bots)} valid bots")
            print(f"Tournament dir: {tournament_dir}")
            print(f"n_parallel_matches={n_parallel_matches} | n_parallel_seeds={n_parallel_seeds}")
            print(f"match_time={match_time} | max_steps={max_steps} | record_video={record_video}")
            print(f"{'='*60}")

        results = run_round_robin(
            bots=valid_bots,
            arena_xml=arena_xml,
            out_dir=tournament_dir,
            n_rollouts=n_rollouts,
            max_steps=max_steps,
            record_video=record_video,
            save_all_videos=save_all_videos,
            highres=highres,
            verbose=verbose,
            trace_progress=trace_progress,
            use_material_palette=use_material_palette,
            season_id=season_id,
            tournament_id=tournament_id,
            camera_mode=camera_mode,
            score_function=score_function,
            iteration=iteration,
            season_root=season_root,
            init_seed=init_seed,
            physics_mode=physics_mode,
            n_parallel_matches=n_parallel_matches,
            n_parallel_seeds=n_parallel_seeds,
            gear_clamp_ratio=gear_clamp_ratio,
            match_time=match_time,
            inactivity_timeout_seconds=inactivity_timeout_seconds,
            inactivity_min_displacement=inactivity_min_displacement,
            size_limits=size_limits,
            contact_fidelity=contact_fidelity,
            raise_on_error=raise_on_error,
            rendering_flags=rendering_flags,
        )

        # Combine forfeit matches with actual matches
        all_matches = forfeit_matches + results.matches

        # Recompute standings including forfeit bots
        combined_standings = dict(results.standings)
        for failed_name in all_failed_bots.keys():
            n_mutual = len(all_failed_bots) - 1  # ties against other failed bots
            combined_standings[failed_name] = {
                "wins": 0,
                "losses": len(valid_bots),  # one loss per valid bot
                "draws": n_mutual,
                "elo": 1000.0,  # Will be recomputed
            }

        return TournamentResult(
            matches=all_matches,
            standings=combined_standings,
            elo_history=results.elo_history,
            metadata={
                **results.metadata,
                "forfeit_bots": {name: {
                    "stage": bot.forfeit_stage if bot.forfeit else "controller",
                    "error": bot.forfeit_error if bot.forfeit else "; ".join(bot.controller_errors),
                } for name, bot in all_failed_bots.items()},
            },
        )

    elif len(valid_bots) == 1:
        # Only one valid bot - it wins by default
        valid_name = list(valid_bots.keys())[0]
        if verbose:
            print(f"\n[TOURNAMENT] Only one valid bot ({valid_name}), wins by default")

        standings = {valid_name: {"wins": len(all_failed_bots), "losses": 0, "draws": 0, "elo": 1000.0}}
        n_mutual = len(all_failed_bots) - 1
        for failed_name in all_failed_bots.keys():
            standings[failed_name] = {"wins": 0, "losses": 1, "draws": n_mutual, "elo": 1000.0}

        return TournamentResult(
            matches=forfeit_matches,
            standings=standings,
            elo_history=[{name: 1000.0 for name in bots.keys()}],
            metadata={
                "forfeit_bots": {name: {
                    "stage": bot.forfeit_stage if bot.forfeit else "controller",
                    "error": bot.forfeit_error if bot.forfeit else "; ".join(bot.controller_errors),
                } for name, bot in all_failed_bots.items()},
            },
        )

    else:
        # No valid bots - all forfeited
        if verbose:
            print(f"\n[TOURNAMENT] No valid bots - all forfeited")

        standings = {}
        for failed_name in all_failed_bots.keys():
            standings[failed_name] = {"wins": 0, "losses": 0, "draws": len(all_failed_bots) - 1, "elo": 1000.0}

        return TournamentResult(
            matches=forfeit_matches,
            standings=standings,
            elo_history=[{name: 1000.0 for name in bots.keys()}],
            metadata={
                "error": "All bots forfeited",
                "forfeit_bots": {name: {
                    "stage": bot.forfeit_stage if bot.forfeit else "controller",
                    "error": bot.forfeit_error if bot.forfeit else "; ".join(bot.controller_errors),
                } for name, bot in all_failed_bots.items()},
            },
        )


# ---------------------------------------------------------------------------
# Match examples & season stats
# ---------------------------------------------------------------------------

def save_season_stats(
    output_dir: Path,
    tournament_history: List[Dict[str, Any]],
    all_standings: List[Dict[str, Dict]],
    bots_by_tournament: List[Dict[str, BotArtifact]],
) -> None:
    """Save season_stats.json with leaderboard and tournament history.

    Args:
        output_dir: Season output directory
        tournament_history: List of tournament results (winners, elo)
        all_standings: All standings from each tournament
        bots_by_tournament: List of bot dicts per tournament
    """
    if not all_standings:
        return

    # Build leaderboard from latest standings
    latest_standings = all_standings[-1]
    latest_bots = bots_by_tournament[-1] if bots_by_tournament else {}

    leaderboard = []
    ranked = elo_rank_players({name: stats["elo"] for name, stats in latest_standings.items()})
    for rank, (name, elo) in enumerate(ranked, 1):
        stats = latest_standings[name]
        # Get bot path from artifact
        bot_path = ""
        if name in latest_bots:
            bot = latest_bots[name]
            bot_dir = bot.morphology_xml.parent
            # Get relative path from output_dir
            try:
                bot_path = str(bot_dir.relative_to(output_dir))
            except ValueError:
                bot_path = str(bot_dir)

        leaderboard.append({
            "rank": rank,
            "bot_name": name,
            "bot_path": bot_path,
            "elo": elo,
            "wins": stats["wins"],
            "losses": stats["losses"],
            "draws": stats["draws"],
        })

    # Build top performers list (paths to top bots)
    top_performers = [entry["bot_path"] for entry in leaderboard[:3] if entry["bot_path"]]

    season_stats = {
        "last_updated": datetime.datetime.now().isoformat(),
        "total_tournaments": len(tournament_history),
        "leaderboard": leaderboard,
        "top_performers": top_performers,
        "tournament_history": tournament_history,
    }

    stats_path = output_dir / "season_stats.json"
    with stats_path.open("w", encoding="utf-8") as f:
        json.dump(season_stats, f, indent=2)


# ---------------------------------------------------------------------------
# Build detection & state loading (for --continue)
# ---------------------------------------------------------------------------

def detect_completed_builds(output_dir: Path) -> tuple:
    """Determine how many build iterations completed in a previous run.

    A build iteration is considered complete if its bots/ directory exists
    with at least one bot_artifact.json.

    Returns:
        (num_completed, has_incomplete) where *num_completed* is the number
        of contiguous completed builds starting from index 0, and
        *has_incomplete* is True if the next build directory exists but
        has no bot artifacts (suggesting an interrupted run).
    """
    num_completed = 0
    while True:
        bots_dir = output_dir / f"tournament_{num_completed:02d}" / "round_robin_match" / "bots"
        if not bots_dir.exists():
            break
        artifacts = list(bots_dir.glob("*/bot_artifact.json"))
        if not artifacts:
            break
        num_completed += 1

    # Check whether the next build directory exists (incomplete run)
    next_bots_dir = output_dir / f"tournament_{num_completed:02d}" / "round_robin_match" / "bots"
    has_incomplete = next_bots_dir.exists()
    return num_completed, has_incomplete


def _load_bots_from_disk(output_dir: Path, iteration: int) -> Dict[str, BotArtifact]:
    """Load bot artifacts from a completed build iteration directory."""
    bots: Dict[str, BotArtifact] = {}
    bots_dir = output_dir / f"tournament_{iteration:02d}" / "round_robin_match" / "bots"
    if not bots_dir.exists():
        return bots

    for bot_dir in sorted(bots_dir.iterdir()):
        artifact_path = bot_dir / "bot_artifact.json"
        if artifact_path.exists():
            try:
                bot = BotArtifact.load(artifact_path)
                # Fix paths to absolute — JSON stores relative paths
                bot.morphology_xml = bot_dir / "robot.xml"
                bot.controller_code = bot_dir / "controller.py"
                bots[bot.name] = bot
            except Exception as exc:
                logger.warning("Failed to load bot artifact %s: %s", artifact_path, exc)
    return bots


# ---------------------------------------------------------------------------
# Phase 1: BUILD — N iterations, no tournament feedback
# ---------------------------------------------------------------------------

def run_build_phase(
    llm_config_paths: List[Path],
    arena_xml: Path,
    constraints_path: Path,
    output_dir: Path,
    cfg: BuildConfig,
    *,
    env: str = "DEBUG",
    season_id: str = "season_00",
    tournament_id: str = "tournament_00",
    iterations: int = 10,
    include_baselines: bool = True,
    verbose: bool = True,
    trace_progress: bool = True,
    start_iteration: int = 0,
) -> List[Dict[str, BotArtifact]]:
    """Run N iterations of bot generation with NO tournament feedback.

    Each iteration independently generates one bot per LLM.
    No match feedback is passed between iterations.

    Args:
        llm_config_paths: Paths to LLM config YAMLs.
        arena_xml: Path to arena XML (used for controller verification during build).
        constraints_path: Path to BOT_CONSTRAINTS.yaml.
        output_dir: Root output directory for the season.
        cfg: BuildConfig with build-phase parameters.
        iterations: Total number of build iterations.
        include_baselines: Inject baseline bots into each iteration's bot set.
        verbose: Print progress.
        start_iteration: Skip already-completed iterations (for --continue).

    Returns:
        List of bot dicts, one per iteration. Index = iteration number.
        Entries for iterations < start_iteration are loaded from disk.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    llm_configs = load_llm_configs(llm_config_paths)

    # Set global seed for reproducibility
    seed = cfg.init_seed
    random.seed(seed)
    np.random.seed(seed)

    if verbose:
        print(f"\n{'#'*60}")
        print(f"# BUILD PHASE (no tournament feedback)")
        print(f"# Iterations: {start_iteration}-{iterations - 1} ({iterations - start_iteration} to build)")
        print(f"# LLMs: {list(llm_configs.keys())}")
        print(f"# Output: {output_dir}")
        print(f"# Global seed: {seed}")
        print(f"{'#'*60}\n")

    bots_by_iteration: List[Dict[str, BotArtifact]] = []

    # Load already-completed iterations from disk
    for i in range(start_iteration):
        bots = _load_bots_from_disk(output_dir, i)
        bots_by_iteration.append(bots)
        if verbose:
            print(f"[Build] Loaded iteration {i}: {len(bots)} bots from disk")

    # Build new iterations
    for i in range(start_iteration, iterations):
        if verbose:
            print(f"\n{'='*60}")
            print(f"BUILD ITERATION {i+1}/{iterations}")
            print(f"{'='*60}")

        tournament_dir = output_dir / f"tournament_{i:02d}"
        round_robin_dir = tournament_dir / "round_robin_match"
        bots_dir = round_robin_dir / "bots"
        bots_dir.mkdir(parents=True, exist_ok=True)

        # No match feedback — empty string
        match_feedback = ""

        bots = generate_bots(
            llm_configs=llm_configs,
            constraints_path=constraints_path,
            arena_xml=arena_xml,
            iteration_dir=bots_dir,
            cfg=cfg,
            env=env,
            season_id=season_id,
            tournament_id=tournament_id,
            iteration=i,
            match_feedback=match_feedback,
            verbose=verbose,
            trace_progress=trace_progress,
        )

        # Inject baseline bots for Elo calibration
        if include_baselines:
            bots = _inject_baseline_bots(bots, bots_dir)

        bots_by_iteration.append(bots)

        if verbose:
            n_ok = sum(1 for b in bots.values() if not b.forfeit)
            n_forfeit = len(bots) - n_ok
            print(f"\n[Build] Iteration {i+1}: {n_ok} valid, {n_forfeit} forfeit")
            for name, bot in bots.items():
                if bot.forfeit:
                    print(f"  [FORFEIT] {name} ({bot.forfeit_stage})")
                else:
                    print(f"  [OK] {name} morph={bot.morphology_score:.2f} ctrl={bot.controller_score:.2f}")

    if verbose:
        print(f"\n{'#'*60}")
        print(f"# BUILD PHASE COMPLETE — {iterations} iterations")
        print(f"{'#'*60}\n")

    return bots_by_iteration


# ---------------------------------------------------------------------------
# Phase 2: TOURNAMENT — run matches on all pre-built bot sets
# ---------------------------------------------------------------------------

def run_tournament_phase_all(
    bots_by_iteration: List[Dict[str, BotArtifact]],
    arena_xml: Path,
    constraints_path: Path,
    output_dir: Path,
    cfg: BuildConfig,
    *,
    env: str = "DEBUG",
    season_id: str = "season_00",
    tournament_id: str = "tournament_00",
    n_rollouts: int = 5,
    max_steps: int = 1000,
    record_video: bool = True,
    save_all_videos: bool = True,
    highres: bool = False,
    camera: str = "tracking",
    score_function: str = "any",
    n_parallel_matches: int = 1,
    n_parallel_seeds: int = 1,
    gear_clamp_ratio: float = 0.0,
    match_time: Optional[float] = None,
    inactivity_timeout: Optional[float] = 10.0,
    inactivity_min_displacement: float = 0.5,
    size_limits: Optional[Tuple[float, float, float]] = None,
    verbose: bool = True,
    trace_progress: bool = True,
    elo_config: Optional[Dict[str, Any]] = None,
    raise_on_error: bool = False,
    rendering_flags: Optional[Dict[str, bool]] = None,
) -> Dict[str, Any]:
    """Run tournaments for each iteration's bots and compute cumulative Elo.

    Goes through each iteration's bot set in order, running round-robin
    matches and accumulating Elo across iterations.

    Args:
        bots_by_iteration: List of bot dicts, one per iteration.
        arena_xml: Path to arena XML.
        constraints_path: Path to constraints (for material palette check).
        output_dir: Root output directory.
        cfg: BuildConfig (for physics_mode, init_seed, etc.).
        Other args: tournament parameters.

    Returns:
        Season summary dict.
    """
    output_dir = Path(output_dir)


    if verbose:
        print(f"\n{'#'*60}")
        print(f"# TOURNAMENT PHASE")
        print(f"# Iterations to process: {len(bots_by_iteration)}")
        print(f"# Output: {output_dir}")
        print(f"{'#'*60}\n")

    # Cumulative state
    cumulative_match_outcomes: List[MatchOutcome] = []
    cumulative_forfeit_counts: Dict[str, int] = {}
    season_elo_history: List[Dict[str, float]] = []
    all_standings: List[Dict[str, Dict]] = []
    tournament_history: List[Dict[str, Any]] = []
    # Map bot names to model-level identity (generator) across iterations
    _name_to_model: Dict[str, str] = {}

    for i, bots in enumerate(bots_by_iteration):
        # Update name→model mapping with this iteration's bots
        for name, bot in bots.items():
            _name_to_model[name] = bot.generator
        if verbose:
            print(f"\n{'='*60}")
            print(f"TOURNAMENT {i+1}/{len(bots_by_iteration)}")
            print(f"Bots: {list(bots.keys())}")
            print(f"{'='*60}")

        if len(bots) < 2:
            logger.warning(f"Iteration {i}: Not enough bots ({len(bots)}), skipping tournament")
            continue

        tournament_dir = output_dir / f"tournament_{i:02d}"
        round_robin_dir = tournament_dir / "round_robin_match"

        # Run tournament
        tournament = run_tournament_phase(
            bots=bots,
            arena_xml=arena_xml,
            tournament_dir=round_robin_dir,
            n_rollouts=n_rollouts,
            max_steps=max_steps,
            record_video=record_video,
            save_all_videos=save_all_videos,
            highres=highres,
            verbose=verbose,
            use_material_palette=(constraints_path.parent / "materials_store.yaml").exists(),
            season_id=season_id,
            tournament_id=tournament_id,
            camera_mode=camera,
            score_function=score_function,
            iteration=i,
            season_root=output_dir,
            init_seed=cfg.init_seed,
            physics_mode=cfg.physics_mode,
            n_parallel_matches=n_parallel_matches,
            n_parallel_seeds=n_parallel_seeds,
            gear_clamp_ratio=gear_clamp_ratio,
            match_time=match_time,
            inactivity_timeout_seconds=inactivity_timeout,
            inactivity_min_displacement=inactivity_min_displacement,
            size_limits=size_limits,
            raise_on_error=raise_on_error,
            trace_progress=trace_progress,
            rendering_flags=rendering_flags,
        )

        # Accumulate match outcomes using model-level identity
        for match in tournament.matches:
            pa = _name_to_model.get(match.red_bot, match.red_bot)
            pb = _name_to_model.get(match.blue_bot, match.blue_bot)
            if match.winner == "red":
                winner = pa
            elif match.winner == "blue":
                winner = pb
            else:
                winner = "draw"

            cumulative_match_outcomes.append(MatchOutcome(
                player_a=pa,
                player_b=pb,
                winner=winner,
            ))

        # Track forfeit counts (using model-level identity)
        forfeit_bots_this_iter = tournament.metadata.get("forfeit_bots", {})
        for bot_name in forfeit_bots_this_iter:
            model_id = _name_to_model.get(bot_name, bot_name)
            cumulative_forfeit_counts[model_id] = cumulative_forfeit_counts.get(model_id, 0) + 1

        # Compute cumulative Elo
        cumulative_standings = compute_standings(cumulative_match_outcomes)

        # Apply forfeit penalty
        forfeit_penalty = 50
        for bot_name, count in cumulative_forfeit_counts.items():
            if bot_name in cumulative_standings:
                cumulative_standings[bot_name]["elo"] -= forfeit_penalty * count

        current_elo = {name: stats["elo"] for name, stats in cumulative_standings.items()}
        season_elo_history.append(current_elo)
        all_standings.append(cumulative_standings)

        # Track tournament history
        ranked = elo_rank_players(current_elo)
        winner_name = ranked[0][0] if ranked else ""
        tournament_history.append({
            "tournament": i,
            "winner": winner_name,
            "final_elo": current_elo,
            "cumulative_matches": len(cumulative_match_outcomes),
        })

        # Save season_stats.json after each tournament
        save_season_stats(
            output_dir=output_dir,
            tournament_history=tournament_history,
            all_standings=all_standings,
            bots_by_tournament=bots_by_iteration[:i + 1],
        )


        if verbose:
            print(f"\n[Tournament {i+1}] Complete!")
            ranked = elo_rank_players(current_elo)
            print("Current Standings:")
            for rank, (name, elo) in enumerate(ranked, 1):
                print(f"  {rank}. {name}: {elo:.0f}")

    if verbose:
        print(f"\n{'#'*60}")
        print(f"# TOURNAMENTS COMPLETE")
        print(f"# Results saved to: {output_dir}")
        print(f"{'#'*60}\n")

        if all_standings:
            print("Final Standings (cumulative simple Elo):")
            final_elo = {name: stats["elo"] for name, stats in all_standings[-1].items()}
            for rank, (name, elo) in enumerate(elo_rank_players(final_elo), 1):
                stats = all_standings[-1][name]
                print(f"  {rank}. {name}: Elo {elo:.0f} | W:{stats['wins']} L:{stats['losses']} D:{stats['draws']}")

    # Post-season Elo dashboard
    if all_standings:
        _generate_elo_dashboard(
            output_dir=output_dir,
            elo_config=elo_config or {},
            season_id=season_id,
            verbose=verbose,
        )

    # Print BT ratings from elo_results.json (the authoritative ratings)
    if verbose:
        elo_results_path = output_dir / "elo" / "elo_results.json"
        if elo_results_path.exists():
            try:
                with elo_results_path.open("r", encoding="utf-8") as f:
                    elo_results = json.load(f)
                bt_ratings = elo_results.get("ratings", {})
                if bt_ratings:
                    print(f"\n{'='*60}")
                    print("Bradley-Terry Ratings (from elo_results.json):")
                    print(f"{'='*60}")
                    sorted_ratings = sorted(bt_ratings.items(), key=lambda x: x[1], reverse=True)
                    for rank, (name, rating) in enumerate(sorted_ratings, 1):
                        wld = elo_results.get("wld", {}).get(name, {})
                        w = wld.get("wins", 0)
                        l = wld.get("losses", 0)
                        d = wld.get("draws", 0)
                        print(f"  {rank}. {name}: {rating:.0f} | W:{w} L:{l} D:{d}")
                    print(f"{'='*60}\n")
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Failed to read elo_results.json: %s", exc)

    return {
        "total_tournaments": len(tournament_history),
        "final_standings": all_standings[-1] if all_standings else {},
    }


def _generate_elo_dashboard(
    output_dir: Path,
    elo_config: Dict[str, Any],
    season_id: str,
    verbose: bool,
) -> None:
    """Generate post-season Elo dashboard."""
    try:
        from mjarena.elo.ratings import compute_ratings
        from mjarena.elo.display import plot_dashboard, save_results

        elo_method = elo_config.get("method", "bt")
        elo_level = elo_config.get("level", "model")
        elo_strategy = elo_config.get("strategy", "cumulative")
        elo_top_k = elo_config.get("top_k", 3)
        elo_bootstrap = elo_config.get("bootstrap", 0)
        elo_exclude_forfeits = elo_config.get("exclude_forfeits", False)
        elo_title = elo_config.get("title", "") or f"{season_id} Elo Ratings"
        elo_force = elo_config.get("force", True)
        elo_build_stats = elo_config.get("build_stats", False)

        result_data = compute_ratings(
            output_dir,
            level=elo_level,
            strategy=elo_strategy,
            top_k=elo_top_k,
            bootstrap=elo_bootstrap,
            exclude_forfeits=elo_exclude_forfeits,
            force=elo_force,
        )

        elo_dir = output_dir / "elo"
        elo_dir.mkdir(parents=True, exist_ok=True)

        save_results(
            elo_dir / "elo_results.json",
            result_data["ratings"],
            confidence=result_data["confidence"],
            wld=result_data["wld"],
            metadata=result_data["metadata"],
        )

        build_stats = None
        if elo_build_stats:
            from mjarena.elo.build_stats import load_build_stats, save_build_costs
            build_stats = load_build_stats(output_dir)
            if build_stats:
                costs_path = save_build_costs(output_dir, build_stats)
                if verbose:
                    print(f"[Elo] Build costs saved to {costs_path}")

        plot_dashboard(
            result_data["ratings"],
            result_data["matches"],
            output_dir,
            level=elo_level,
            method=elo_method,
            confidence=result_data["confidence"],
            wld=result_data["wld"],
            build_stats=build_stats,
            title=elo_title,
        )

        if verbose:
            print(f"\n[Elo] Results saved to {elo_dir}")

    except Exception as exc:
        logger.warning("Post-season Elo dashboard generation failed: %s", exc)
        if verbose:
            print(f"\n[Elo] Dashboard generation failed: {exc}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Run N iterations of LLM Arena competition (build-then-tournament)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  # Using config file (recommended):
  python run_baseline_agent.py --config configs/tournaments/tournament.yaml

  # Override iterations from config:
  python run_baseline_agent.py --config configs/tournaments/tournament.yaml --iterations 5

  # Quick test without config file:
  python run_baseline_agent.py \\
      --llms configs/models/openai/gpt-4o.yaml configs/models/google/gemini-1-5-pro.yaml \\
      --iterations 2 \\
      --output-dir logs/test_season

  # Child config with base.yaml inheritance:
  python run_baseline_agent.py --config configs/tournaments/gpt52_vs_gpt5.yaml

  # Dry run (0 iterations) to check merged config:
  python run_baseline_agent.py --config configs/tournaments/gpt52_vs_gpt5.yaml --iterations 0

  # Build only (skip tournaments):
  python run_baseline_agent.py --config configs/tournaments/tournament.yaml --build-only

  # Tournament only (requires existing bot dirs):
  python run_baseline_agent.py --config configs/tournaments/tournament.yaml --tournament-only

  # Debug hangs/errors: disable all parallelism and re-raise exceptions:
  python run_baseline_agent.py --config configs/tournaments/tournament.yaml --tournament-only --no-parallel

  # Continue from an existing output directory:
  python run_baseline_agent.py --continue logs/20260217/my_season/

  # Continue with updated config (e.g., more iterations):
  python run_baseline_agent.py --continue logs/20260217/my_season/ --config configs/tournaments/new.yaml

  # Continue and re-run the first incomplete build:
  python run_baseline_agent.py --continue logs/20260217/my_season/ --rerun-incomplete
        """
    )

    # Config file (recommended approach)
    parser.add_argument(
        "--config", type=Path, default=None,
        help="Path to tournament config YAML (e.g., configs/tournaments/tournament.yaml)"
    )

    # These can override config file or be used standalone
    parser.add_argument(
        "--llms", nargs="+", type=Path,
        help="Paths to LLM config YAML files (overrides config)"
    )
    parser.add_argument(
        "--arena", type=Path,
        help="Path to arena XML (overrides config)"
    )
    parser.add_argument(
        "--constraints", type=Path,
        help="Path to constraints YAML (overrides config)"
    )
    parser.add_argument(
        "--output-dir", type=Path,
        help="Output directory for season results (overrides config)"
    )
    parser.add_argument(
        "--name", type=str,
        help="Tournament name (overrides config)"
    )
    parser.add_argument(
        "--iterations", type=int,
        help="Number of iterations to run (overrides config)"
    )
    parser.add_argument(
        "--no-render", "--no-video", dest="no_render", action="store_true",
        help="Disable tournament rendering and video saving only; keep build-phase screenshots and validation videos"
    )
    parser.add_argument(
        "--quiet", action="store_true",
        help="Suppress verbose output (overrides config)"
    )
    parser.add_argument(
        "--no-trace", action="store_true",
        help="Disable extra debug trace prints while keeping normal progress output"
    )
    parser.add_argument(
        "--no-parallel", "--debug-serial", dest="debug_serial", action="store_true",
        help="Disable all build/tournament parallelism and re-raise exceptions instead of summarizing them"
    )
    parser.add_argument(
        "--debug-all", action="store_true",
        help="Dump full prompt, CoT reasoning, and outputs per bot per phase"
    )
    parser.add_argument(
        "--dump-prompt", action="store_true",
        help="Save full LLM prompts and responses as text files in debug/"
    )
    parser.add_argument(
        "--save-intermediate-candidates", action="store_true",
        help="Save all BestOfN candidates with scores to candidates/ directory"
    )
    parser.add_argument(
        "--camera", choices=["side", "tracking", "top"],
        help="Camera mode for match videos (overrides config)"
    )
    parser.add_argument(
        "--score-function", choices=["any", "thres-50"],
        help="Score function: 'any' (instant loss on floor contact) or 'thres-50' (>50%% mass = loss)"
    )
    parser.add_argument(
        "--continue", dest="continue_dir", type=Path, metavar="DIR",
        help="Continue season from existing output directory"
    )
    parser.add_argument(
        "--rerun-incomplete", action="store_true",
        help="With --continue: re-run from the first incomplete build instead of skipping it"
    )
    parser.add_argument(
        "--build-only", action="store_true",
        help="Only run build phase, skip tournaments"
    )
    parser.add_argument(
        "--tournament-only", action="store_true",
        help="Only run tournaments on existing bot dirs (skip build phase)"
    )

    args = parser.parse_args()

    if args.build_only and args.tournament_only:
        print("Error: --build-only and --tournament-only are mutually exclusive")
        sys.exit(1)

    # ── Branch 1: --continue mode ──────────────────────────────────────
    start_iteration = 0

    if args.continue_dir:
        continue_dir = args.continue_dir.resolve()
        if not continue_dir.is_dir():
            print(f"Error: Continue directory not found: {continue_dir}")
            sys.exit(1)

        # Load config: --config if provided, else <dir>/config.yaml
        if args.config and args.config.exists():
            try:
                config = load_tournament_config(args.config)
            except FileNotFoundError as exc:
                print(f"Error loading config: {exc}")
                sys.exit(1)
            print(f"Loaded config from: {args.config}")
        else:
            saved_config = continue_dir / "config.yaml"
            if not saved_config.exists():
                print(f"Error: No config.yaml found in {continue_dir}")
                print("  This may be an old run without a self-sufficient config.")
                print("  Pass --config <path> to supply a config file explicitly.")
                sys.exit(1)
            try:
                config = load_tournament_config(saved_config)
            except FileNotFoundError as exc:
                print(f"Error: Saved config references a missing base file: {exc}")
                print("  Pass --config <path> to supply a self-sufficient config.")
                sys.exit(1)
            print(f"Loaded config from: {saved_config}")

        run_args = config_to_args(config)
        # Force output_dir to the continue directory
        run_args["output_dir"] = continue_dir

        # Detect completed builds
        num_completed, has_incomplete = detect_completed_builds(continue_dir)
        print(f"[Continue] Found {num_completed} completed build iteration(s) in {continue_dir}")
        if has_incomplete:
            incomplete_idx = num_completed
            print(f"[Continue] tournament_{incomplete_idx:02d} build is incomplete")

        # Determine start_iteration
        if args.rerun_incomplete and has_incomplete:
            start_iteration = num_completed
            print(f"[Continue] --rerun-incomplete: will re-run from tournament_{start_iteration:02d}")
        else:
            start_iteration = num_completed + (1 if has_incomplete else 0)
            if has_incomplete:
                print(f"[Continue] Skipping incomplete tournament_{num_completed:02d}, "
                      f"starting from tournament_{start_iteration:02d}")

    # ── Branch 2: --config mode ────────────────────────────────────────
    elif args.config and args.config.exists():
        config = load_tournament_config(args.config)
        run_args = config_to_args(config)
        print(f"Loaded config from: {args.config}")

    # ── Branch 3: CLI defaults ─────────────────────────────────────────
    else:
        config = {}
        run_args = _cli_default_run_args()

    # ── Apply CLI overrides (all branches) ─────────────────────────────
    cfg: BuildConfig = run_args["cfg"]
    if args.llms:
        run_args["llm_config_paths"] = args.llms
    if args.arena:
        run_args["arena_xml"] = args.arena
    if args.constraints:
        run_args["constraints_path"] = args.constraints
    if args.output_dir and not args.continue_dir:
        run_args["output_dir"] = args.output_dir
    if args.name:
        run_args["tournament_id"] = args.name
        # Also update output_dir if it uses default pattern
        if not args.output_dir and not args.continue_dir:
            date_str = datetime.datetime.now().strftime("%Y%m%d")
            run_args["output_dir"] = Path(f"logs/{date_str}/{args.name}")
    if args.iterations is not None:
        run_args["iterations"] = args.iterations
    if args.no_render:
        _disable_tournament_render_outputs(run_args)
    if args.quiet:
        run_args["verbose"] = False
    if args.no_trace:
        run_args["trace_progress"] = False
    if args.debug_all:
        cfg.debug_all = True
    if args.dump_prompt:
        cfg.dump_prompt = True
    if args.save_intermediate_candidates:
        cfg.save_intermediate_candidates = True
    if args.camera:
        run_args["camera"] = args.camera
    if args.score_function:
        run_args["score_function"] = args.score_function
    run_args["raise_on_error"] = run_args.get("raise_on_error", cfg.raise_on_error)
    if args.debug_serial:
        cfg.n_parallel_builds = 1
        cfg.controller_validation_params.n_parallel_seeds = 1
        cfg.raise_on_error = True
        run_args["n_parallel_matches"] = 1
        run_args["n_parallel_seeds"] = 1
        run_args["raise_on_error"] = True

    # Check if all iterations are already done (continue mode)
    if args.continue_dir and start_iteration >= run_args["iterations"]:
        print(f"\n[Continue] All {run_args['iterations']} build iteration(s) already completed.")
        if not args.build_only:
            print("[Continue] Proceeding to tournament phase.")
        else:
            print(f"  Use --iterations N (with N > {run_args['iterations']}) to run more.")
            sys.exit(0)

    # Validate required inputs
    if not args.tournament_only and not run_args["llm_config_paths"]:
        print("Error: No LLM configs specified. Use --config or --llms")
        sys.exit(1)

    if not args.tournament_only:
        for llm_path in run_args["llm_config_paths"]:
            if not llm_path.exists():
                print(f"Error: LLM config not found: {llm_path}")
                sys.exit(1)

    if not run_args["arena_xml"].exists():
        print(f"Error: Arena XML not found: {run_args['arena_xml']}")
        sys.exit(1)

    if not run_args["constraints_path"].exists():
        print(f"Error: Constraints YAML not found: {run_args['constraints_path']}")
        sys.exit(1)

    iterations = run_args["iterations"]

    # Print configuration summary
    if run_args["verbose"]:
        mode = "build-only" if args.build_only else "tournament-only" if args.tournament_only else "build + tournament"
        print(f"\nConfiguration:")
        print(f"  Mode: {mode}")
        print(f"  Env: {run_args['env']}")
        print(f"  Season: {run_args['season_id']}")
        print(f"  Tournament: {run_args['tournament_id']}")
        if not args.tournament_only:
            print(f"  LLMs: {[p.stem for p in run_args['llm_config_paths']]}")
        print(f"  Iterations: {iterations} (starting from {start_iteration})")
        print(f"  Rollouts per matchup: {run_args['n_rollouts']}")
        print(
            "  Rendering: "
            f"tournament_videos={run_args['record_video']} "
            f"build_videos={cfg.controller_validation_params.save_video} "
        )
        print(
            f"  Parallelism: builds={cfg.n_parallel_builds} "
            f"build_seeds={cfg.controller_validation_params.n_parallel_seeds or cfg.controller_validation_params.n_rollouts} "
            f"matchups={run_args.get('n_parallel_matches', 1)} "
            f"tournament_seeds={run_args.get('n_parallel_seeds', 1)}"
        )
        print(f"  Trace Progress: {run_args.get('trace_progress', True)}")
        print(f"  Raise On Error: {run_args.get('raise_on_error', False)}")
        print(f"  Output: {run_args['output_dir']}")
        print()

    # Save resolved config to output directory (all branches)
    run_args["output_dir"].mkdir(parents=True, exist_ok=True)
    if config:
        save_resolved_config(config, run_args["output_dir"])
    # …and the consolidated design document, if this run uses one: exactly the text
    # every build sends, snapshotted once per run beside config.yaml.
    save_consolidated_prompt(run_args["cfg"], run_args["output_dir"])

    # Invalidate CSV cache when continuing so post-season Elo rescans all JSONs
    if args.continue_dir:
        csv_cache = run_args["output_dir"] / "match_log.csv"
        if csv_cache.exists():
            csv_cache.unlink()
            print(f"[Continue] Deleted stale {csv_cache.name}")

    # Tee stdout+stderr to log.txt in the output directory
    log_path = run_args["output_dir"] / "log.txt"
    _tee = _TeeWriter(log_path)
    sys.stdout = _tee
    sys.stderr = _TeeWriter(log_path, stream=sys.stderr, file=_tee._file)

    # Report the backend before expensive generation; required acceleration must
    # fail here rather than turn a worker setup failure into a bot forfeiture.
    from mjarena.runner.acceleration import match_acceleration
    with match_acceleration():
        pass

    # ── Phase 1: BUILD ───────────────────────────────────────────────────
    if not args.tournament_only:
        bots_by_iteration = run_build_phase(
            llm_config_paths=run_args["llm_config_paths"],
            arena_xml=run_args["arena_xml"],
            constraints_path=run_args["constraints_path"],
            output_dir=run_args["output_dir"],
            cfg=cfg,
            env=run_args["env"],
            season_id=run_args["season_id"],
            tournament_id=run_args["tournament_id"],
            iterations=iterations,
            include_baselines=run_args.get("include_baselines", True),
            verbose=run_args["verbose"],
            trace_progress=run_args.get("trace_progress", True),
            start_iteration=start_iteration,
        )
    else:
        # Load all bots from disk for tournament-only mode
        bots_by_iteration = []
        for i in range(iterations):
            bots = _load_bots_from_disk(run_args["output_dir"], i)
            if not bots:
                print(f"Warning: No bots found for iteration {i}")
            bots_by_iteration.append(bots)
        if run_args["verbose"]:
            total_bots = sum(len(b) for b in bots_by_iteration)
            print(f"[Tournament-only] Loaded {total_bots} bots across {iterations} iterations")

    if args.build_only:
        if run_args["verbose"]:
            print("\n[Build-only] Skipping tournament phase.")
        return

    # ── Phase 2: TOURNAMENT ──────────────────────────────────────────────
    # Invalidate CSV cache so Elo rescans all JSONs
    csv_cache = run_args["output_dir"] / "match_log.csv"
    if csv_cache.exists():
        csv_cache.unlink()

    run_tournament_phase_all(
        bots_by_iteration=bots_by_iteration,
        arena_xml=run_args["arena_xml"],
        constraints_path=run_args["constraints_path"],
        output_dir=run_args["output_dir"],
        cfg=cfg,
        env=run_args["env"],
        season_id=run_args["season_id"],
        tournament_id=run_args["tournament_id"],
        n_rollouts=run_args["n_rollouts"],
        max_steps=run_args["max_steps"],
        record_video=run_args["record_video"],
        save_all_videos=run_args["save_all_videos"],
        highres=run_args["highres"],
        camera=run_args["camera"],
        score_function=run_args["score_function"],
        n_parallel_matches=run_args.get("n_parallel_matches", 1),
        n_parallel_seeds=run_args.get("n_parallel_seeds", 1),
        gear_clamp_ratio=run_args["gear_clamp_ratio"],
        match_time=run_args.get("match_time"),
        inactivity_timeout=run_args["inactivity_timeout"],
        inactivity_min_displacement=run_args["inactivity_min_displacement"],
        size_limits=run_args["size_limits"],
        verbose=run_args["verbose"],
        trace_progress=run_args.get("trace_progress", True),
        elo_config=run_args.get("elo_config"),
        raise_on_error=run_args.get("raise_on_error", False),
        rendering_flags=run_args.get("rendering_flags"),
    )


if __name__ == "__main__":
    main()
