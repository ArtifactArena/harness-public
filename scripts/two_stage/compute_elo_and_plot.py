"""Two-stage Elo: derive top-1/3/K_max model Elos and render the leaderboard.

Reads the cross-model pool file + saved match results from Stage 3. Never simulates
a match — re-runnable in seconds with different K values or aggregations.

Usage:
    python scripts/two_stage/compute_elo_and_plot.py \
        --cross-model-dir two_stage_tournaments/cross_model/top_5_matches \
        --k-values 1 3 5 \
        --output-plot two_stage_tournaments/cross_model/top_5_matches/leaderboard.png
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

from mjarena.two_stage.aggregate import run_stage4  # noqa: E402

logger = logging.getLogger(__name__)


def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument(
        "--cross-model-dir",
        type=Path,
        required=True,
        help="e.g. two_stage_tournaments/cross_model/top_5_matches",
    )
    p.add_argument(
        "--k-values",
        type=int,
        nargs="+",
        default=None,
        help=(
            "Top-K scheme: which K' values to evaluate as separate bars per "
            "model. Default: 1 3 5 (clipped to whatever the pool supports). "
            "Pass any list, e.g. '--k-values 1 5 10' for a different scheme."
        ),
    )
    p.add_argument(
        "--output-plot",
        type=Path,
        default=None,
        help="Path for the leaderboard PNG. Default: <cross-model-dir>/leaderboard.png",
    )
    p.add_argument(
        "--aggregations",
        nargs="+",
        choices=["mean", "max", "pooled"],
        default=["mean"],
        help=(
            "Which model-Elo aggregations to write (default: mean only). "
            "First listed becomes the primary aggregation used for "
            "elo_results.json (no suffix)."
        ),
    )
    p.add_argument(
        "--render-per-k",
        action="store_true",
        help=(
            "Also render per-K family-shaded leaderboards "
            "(leaderboard_top{1,3,5}_<agg>.png). Off by default — only the "
            "two grouped 3-bar plots (leaderboard_mean.png, leaderboard_max.png) "
            "are written."
        ),
    )
    p.add_argument(
        "--anchor",
        default="none",
        help=(
            "Baseline to pin to --anchor-elo (substring match against "
            "artifact ids; case-insensitive). Default: none (skip pinning, "
            "use BT default normalization / mean-centered). Pass e.g. 'Box' "
            "to pin a baseline to --anchor-elo instead."
        ),
    )
    p.add_argument(
        "--anchor-elo",
        type=float,
        default=1000.0,
        help="Elo to pin the anchor to (default: 1000).",
    )
    p.add_argument(
        "--per-k-bt-pass",
        action="store_true",
        help=(
            "Legacy mode: re-run BT MLE per K (different normalization per "
            "pass; top@1/top@3/top@5 numbers not directly comparable). Default "
            "is a single BT pass over the full T_max field then filter per K."
        ),
    )
    p.add_argument(
        "--sort-descending",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Order models on the leaderboard by Elo descending (best on the "
            "left; default). Pass --no-sort-descending to flip to ascending "
            "(worst on the left)."
        ),
    )
    p.add_argument(
        "--box-baseline-right",
        action="store_true",
        help=(
            "Place the 'Box Baseline (Elo = 1000)' label on the RIGHT side "
            "of the leaderboard (default: left)."
        ),
    )
    p.add_argument(
        "--title",
        type=str,
        default=None,
        help=(
            "Override the leaderboard chart title. Default uses the auto-built "
            "string (e.g. 'Two-Stage Model Elo · top-1 / top-3 / top-5 artifacts "
            "per model (BT · mean)'). Example: "
            "--title 'Artifact Arena ELO Score · top-1 artifact per model'"
        ),
    )
    p.add_argument(
        "--y-label",
        type=str,
        default="Artifact Arena ELO Score",
        help="Y-axis label on the leaderboard. Default: 'Artifact Arena ELO Score'.",
    )
    p.add_argument(
        "--ignore",
        nargs="*",
        default=["hexahedron"],
        help=(
            "Substrings to suppress from the leaderboard outputs (matched "
            "case-insensitively against artifact_id and model name). Their "
            "matches still feed BT calibration and the anchor; they're just "
            "hidden from the JSONs and plots. Default: 'hexahedron' "
            "(duplicate of Box). Pass an empty list to keep everything."
        ),
    )
    p.add_argument("--elo-k-factor", type=float, default=32.0)
    p.add_argument("--elo-initial-rating", type=float, default=1000.0)
    p.add_argument("--log-level", default="INFO")
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    cross_model_dir = (
        args.cross_model_dir
        if args.cross_model_dir.is_absolute()
        else REPO_ROOT / args.cross_model_dir
    )
    output_plot = args.output_plot
    if output_plot is None:
        output_plot = cross_model_dir / "leaderboard.png"
    elif not output_plot.is_absolute():
        output_plot = REPO_ROOT / output_plot

    run_stage4(
        cross_model_dir=cross_model_dir,
        k_values=args.k_values,
        output_plot=output_plot,
        elo_k_factor=args.elo_k_factor,
        elo_initial_rating=args.elo_initial_rating,
        aggregations=tuple(args.aggregations),
        render_per_k=args.render_per_k,
        single_bt_pass=not args.per_k_bt_pass,
        anchor=args.anchor,
        anchor_elo=args.anchor_elo,
        ignore=args.ignore,
        sort_descending=args.sort_descending,
        box_baseline_right=args.box_baseline_right,
        title=args.title,
        y_label=args.y_label,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
