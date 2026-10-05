"""Two-stage Elo: drives Stages 1 → 2 → 3 (heavy compute, run once).

Usage:
    python scripts/two_stage/run_tournaments.py \
        --logs-root LOGS-LEVEL0-LEVEL1/combined-refine50 \
        --output two_stage_tournaments \
        --top-n-qualified 15 \
        --k-max 5 \
        --n-rollouts 3 \
        --n-parallel-matches 8

After this finishes, run scripts/two_stage/compute_elo_and_plot.py to derive
top-1/3/K_max model Elos and render the leaderboard.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import List, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from mjarena.two_stage.cross_model import DEFAULT_BASELINES, run_stage3  # noqa: E402
from mjarena.two_stage.intra_model import run_stage2  # noqa: E402
from mjarena.two_stage.match_config import resolve_match_config  # noqa: E402
from mjarena.two_stage.qualification import run_stage1  # noqa: E402

logger = logging.getLogger(__name__)


def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument(
        "--logs-root",
        type=Path,
        required=True,
        help="Root containing tournament_*/round_robin_match/bots/<model>/refinement/commit_*/",
    )
    p.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output directory (created if missing). Defaults to <logs-root>/two_stage_tournaments.",
    )
    p.add_argument(
        "--tournament-config",
        type=Path,
        default=None,
        help=(
            "Tournament YAML used to produce the LOGS being analyzed (e.g. "
            "configs/tournaments/final-frontier-build50-buildonly.yaml). Resolves "
            "`base:` inheritance. If omitted, falls back to <logs-root>/config.yaml."
        ),
    )
    p.add_argument("--top-n-qualified", type=int, default=15)
    p.add_argument("--k-max", type=int, default=5)
    p.add_argument(
        "--n-rollouts",
        type=int,
        default=None,
        help="Override n_rollouts (default: from tournament config; usually 5).",
    )
    p.add_argument("--n-parallel-matches", type=int, default=8)
    p.add_argument(
        "--baselines-dir",
        type=Path,
        default=Path("LOGS-LEVEL0-LEVEL1/combined-refine50/tournament_06/round_robin_match/bots"),
        help="Directory containing baseline-* subdirectories.",
    )
    p.add_argument(
        "--baselines",
        nargs="*",
        default=DEFAULT_BASELINES,
        help="Baseline directory names to include in the cross-model pool.",
    )
    p.add_argument(
        "--models",
        nargs="*",
        default=None,
        help="Restrict Stage 2 to these model names (default: all).",
    )
    p.add_argument(
        "--no-save-video",
        action="store_true",
        help="Override the tournament config's save_video=true.",
    )
    p.add_argument(
        "--skip-stage1",
        action="store_true",
        help="Reuse existing qualification_ranking.json (must already exist).",
    )
    p.add_argument(
        "--skip-stage2",
        action="store_true",
        help="Reuse existing inter_model/<model>/top_{K_max}_bots.json files.",
    )
    p.add_argument(
        "--skip-stage3",
        action="store_true",
        help="Stop after Stage 2 (no cross-model RR).",
    )
    p.add_argument("--log-level", default="INFO")
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    repo_root = REPO_ROOT
    logs_root = args.logs_root if args.logs_root.is_absolute() else repo_root / args.logs_root
    if args.output is None:
        output_root = logs_root / "two_stage_tournaments"
    else:
        output_root = args.output if args.output.is_absolute() else repo_root / args.output
    inter_model_dir = output_root / "inter_model"
    cross_model_dir = output_root / "cross_model"
    qualification_path = output_root / "qualification_ranking.json"
    baselines_dir = (
        args.baselines_dir if args.baselines_dir.is_absolute() else repo_root / args.baselines_dir
    )

    output_root.mkdir(parents=True, exist_ok=True)

    # Resolve tournament config (single source of truth for match settings)
    explicit_cfg = (
        args.tournament_config
        if args.tournament_config is None or args.tournament_config.is_absolute()
        else repo_root / args.tournament_config
    )
    match_cfg = resolve_match_config(logs_root, explicit_cfg)
    if args.no_save_video:
        match_cfg.save_video = False
        match_cfg.save_all_videos = False
    logger.info(
        "Match settings: arena=%s, n_rollouts=%d, match_time=%s, save_video=%s, "
        "save_all_videos=%s, highres=%s, score_function=%s",
        match_cfg.arena_xml,
        match_cfg.n_rollouts,
        match_cfg.match_time,
        match_cfg.save_video,
        match_cfg.save_all_videos,
        match_cfg.highres,
        match_cfg.score_function,
    )

    clean_cache_root = output_root / "_clean_artifacts"

    # Stage 1
    if args.skip_stage1:
        if not qualification_path.exists():
            logger.error(
                "--skip-stage1 set but %s does not exist", qualification_path
            )
            return 2
        logger.info("Stage 1: skipping (using %s)", qualification_path)
    else:
        run_stage1(logs_root=logs_root, output_path=qualification_path, repo_root=repo_root)

    # Stage 2
    if args.skip_stage2:
        logger.info("Stage 2: skipping (reusing %s)", inter_model_dir)
    else:
        run_stage2(
            qualification_path=qualification_path,
            output_root=inter_model_dir,
            repo_root=repo_root,
            match_cfg=match_cfg,
            top_n_qualified=args.top_n_qualified,
            k_max=args.k_max,
            n_rollouts=args.n_rollouts,
            n_parallel_matches=args.n_parallel_matches,
            models=args.models,
            clean_cache_root=clean_cache_root,
        )

    # Stage 3
    if args.skip_stage3:
        logger.info("Stage 3: skipping per --skip-stage3")
        return 0

    run_stage3(
        inter_model_dir=inter_model_dir,
        output_root=cross_model_dir,
        baselines_dir=baselines_dir,
        repo_root=repo_root,
        match_cfg=match_cfg,
        k_max=args.k_max,
        n_rollouts=args.n_rollouts,
        n_parallel_matches=args.n_parallel_matches,
        baselines=args.baselines,
        clean_cache_root=clean_cache_root,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
