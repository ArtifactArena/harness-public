#!/usr/bin/env python3
"""
Standalone CLI for computing Elo ratings from season match data.

Reads match_result.json files from a season output directory, computes
ratings using configurable methods and strategies, and generates a
dashboard image + JSON results.

Usage:
    # Defaults: Bradley-Terry, model-level, cumulative strategy
    python scripts/calculate_elo.py path/to/season_output/

    # Use elo config from tournament YAML
    python scripts/calculate_elo.py path/to/season_output/ --config configs/tournaments/base.yaml

    # Bot-level
    python scripts/calculate_elo.py path/to/season_output/ --level bot

    # Model-level, top-3 strategy
    python scripts/calculate_elo.py path/to/season_output/ --level model \\
        --strategy topk --top-k 3

    # With bootstrap confidence intervals
    python scripts/calculate_elo.py path/to/season_output/ --bootstrap 1000

    # Filter iterations, exclude forfeits
    python scripts/calculate_elo.py path/to/season_output/ --iteration-range 5-20 --exclude-forfeits

    # Force re-scan JSONs (skip CSV cache)
    python scripts/calculate_elo.py path/to/season_output/ --force

    # Output formats (inferred from extension)
    python scripts/calculate_elo.py path/to/season_output/ --output results.json
    python scripts/calculate_elo.py path/to/season_output/ --output dashboard.pdf

    # With generation time/cost vs Elo plots
    python scripts/calculate_elo.py path/to/season_output/ --build-stats

"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from mjarena.elo.ratings import compute_ratings
from mjarena.elo.display import plot_dashboard, save_results


def main():
    parser = argparse.ArgumentParser(
        description="Compute Elo ratings from season match data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "season_dir", type=Path,
        help="Path to season output directory (contains tournament_XX/ dirs)"
    )
    parser.add_argument(
        "--config", type=Path, default=None,
        help="Load elo config section from tournament YAML (CLI flags override)"
    )
    parser.add_argument(
        "--level", choices=["bot", "model"], default=None,
        help="Aggregation level: 'bot' (individual bots) or 'model' (by LLM)"
    )
    parser.add_argument(
        "--strategy", choices=["cumulative", "topk"], default=None,
        help="Which matches to include: 'cumulative' (all) or 'topk' (top K per model)"
    )
    parser.add_argument("--top-k", type=int, default=None, help="K for topk strategy")
    parser.add_argument("--bootstrap", type=int, default=None, help="Bootstrap resamples (0=off)")
    parser.add_argument("--exclude-forfeits", action="store_true", help="Drop forfeit matches")
    parser.add_argument("--exclude-unstable", action="store_true", help="Drop matches with physics instability")
    parser.add_argument("--force", action="store_true", help="Re-scan JSONs (skip CSV cache)")
    parser.add_argument("--iteration-range", type=str, default=None, help="Iteration range (e.g. 5-20)")
    parser.add_argument("--title", type=str, default="", help="Plot title")
    parser.add_argument("--output", type=Path, default=None, help="Output path (.png, .pdf, or .json)")

    # Build stats (time/cost vs Elo)
    parser.add_argument(
        "--build-stats", action="store_true", default=False,
        help="Load generation timing/cost from bot artifacts and generate time/cost vs Elo plots"
    )


    args = parser.parse_args()

    if not args.season_dir.exists():
        print(f"Error: Season directory not found: {args.season_dir}")
        sys.exit(1)

    # Load defaults from config YAML if provided
    elo_cfg = {}
    if args.config:
        import yaml
        from run_baseline_agent import load_tournament_config
        config = load_tournament_config(args.config)
        elo_cfg = config.get("elo", {})

    # CLI flags override config. Ratings are always Bradley-Terry.
    method = "bt"
    level = args.level or elo_cfg.get("level", "model")
    strategy = args.strategy or elo_cfg.get("strategy", "cumulative")
    top_k = args.top_k if args.top_k is not None else elo_cfg.get("top_k", 3)
    bootstrap = args.bootstrap if args.bootstrap is not None else elo_cfg.get("bootstrap", 0)
    exclude_forfeits = args.exclude_forfeits or elo_cfg.get("exclude_forfeits", False)
    exclude_unstable = args.exclude_unstable or elo_cfg.get("exclude_unstable", False)
    force = args.force or elo_cfg.get("force", True)
    title = args.title or elo_cfg.get("title", "")

    # Parse iteration range
    iteration_range = None
    if args.iteration_range:
        parts = args.iteration_range.split("-")
        if len(parts) == 2:
            iteration_range = (int(parts[0]), int(parts[1]))

    # Compute ratings
    result = compute_ratings(
        args.season_dir,
        level=level,
        strategy=strategy,
        top_k=top_k,
        bootstrap=bootstrap,
        exclude_forfeits=exclude_forfeits,
        exclude_unstable=exclude_unstable,
        force=force,
        iteration_range=iteration_range,
    )

    ratings = result["ratings"]
    confidence = result["confidence"]
    wld = result["wld"]
    matches = result["matches"]
    metadata = result["metadata"]

    if not ratings:
        print("No matches found. Check that the season directory contains tournament data.")
        sys.exit(1)

    # Print summary
    print(f"\nMethod: {method} | Level: {level} | Strategy: {strategy}")
    print(f"Total matches: {metadata['total_matches']}")
    print(f"\n{'='*50}")
    print("Ratings:")
    print(f"{'='*50}")
    for name, elo in sorted(ratings.items(), key=lambda x: x[1], reverse=True):
        ci_str = ""
        if confidence and name in confidence:
            med, lo, hi = confidence[name]
            ci_str = f" [{lo:.0f}, {hi:.0f}]"
        w = wld.get(name, {})
        print(f"  {name}: {elo:.0f}{ci_str}  W:{w.get('wins',0)} L:{w.get('losses',0)} D:{w.get('draws',0)}")

    # Output: plots + JSON, all inside {season_dir}/elo/
    elo_dir = args.season_dir / "elo"
    elo_dir.mkdir(parents=True, exist_ok=True)

    # Save JSON results
    json_path = args.output if args.output and args.output.suffix == ".json" \
        else elo_dir / "elo_results.json"
    save_results(
        json_path,
        ratings,
        confidence=confidence,
        wld=wld,
        metadata=metadata,
    )

    # Load build stats if requested
    build_stats = None
    if args.build_stats:
        from mjarena.elo.build_stats import load_build_stats
        build_stats = load_build_stats(args.season_dir)
        if build_stats:
            print(f"\nBuild stats loaded for {len(build_stats)} models")
        else:
            print("\nNo build stats found (no bot_artifact.json files with timing data)")

    # Save plots
    if not args.output or args.output.suffix != ".json":
        plot_dashboard(
            ratings,
            matches,
            args.season_dir,
            level=level,
            method=method,
            confidence=confidence,
            wld=wld,
            build_stats=build_stats,
            title=title,
        )


if __name__ == "__main__":
    main()
