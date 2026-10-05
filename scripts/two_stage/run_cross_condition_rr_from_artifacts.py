"""Cross-condition RR built directly from exported bot artifacts.

The original per-condition source pools (two_stage_per_iter_*) are no longer
available on this machine; only the exported top-1 / top-5 bot artifacts under
`final-graphs/{top1,top5}/<condition>/<model>/<artifact_id>/{robot.xml,
controller.py}` remain.

This script scans that artifact tree, synthesizes one inter_model/<model>__<cond>
top_5_bots.json per (model, condition) bot, then runs the existing Stage 3
round-robin over the whole set + baselines. With a fresh combined dir there is
NO match cache, so EVERY bot plays EVERY bot (true cross-condition RR) — real
simulated matches, no interpolation.

Usage (top-1):
    MUJOCO_GL=egl python scripts/two_stage/run_cross_condition_rr_from_artifacts.py \
        --artifacts-root final-graphs/top1 \
        --combined-dir final-graphs/_cross_condition_top1_pool \
        --baselines-dir mjarena/core/assets/baseline_bots \
        --baselines baseline-static baseline-pusher \
        --tournament-config configs/tournaments/final-frontier-build50-buildonly.yaml \
        --n-parallel-matches 8 --no-save-video
"""
from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from mjarena.two_stage.artifact_loader import TopKBotRecord, write_top_k_bots  # noqa: E402
from mjarena.two_stage.cross_model import DEFAULT_BASELINES, run_stage3  # noqa: E402
from mjarena.two_stage.match_config import resolve_match_config  # noqa: E402

logger = logging.getLogger(__name__)

ARTIFACT_RE = re.compile(r"^(?P<model>.+)__t(?P<t>\d{2})_c(?P<c>\d{3})$")


def _build_inter_model(artifacts_root: Path, dst_inter: Path) -> int:
    """Scan <artifacts_root>/<condition>/<model>/<artifact_id>/ and write one
    inter_model/<model>__<cond>/top_5_bots.json per (model, condition),
    accumulating ALL that pair's artifacts as ranked bots in a single file.

    Critical for top-5: a model/condition has up to 5 artifact dirs, and they
    must ALL land in the one top_5_bots.json (ranked) — writing per-artifact
    would overwrite the file and collapse the pair to a single bot. Returns the
    total bot count (sum over all pairs)."""
    # Group every artifact by its (model, condition) label first.
    grouped: Dict[str, List[Tuple[Path, int, int]]] = {}
    for cond_dir in sorted(p for p in artifacts_root.iterdir() if p.is_dir()):
        cond = cond_dir.name
        for model_dir in sorted(p for p in cond_dir.iterdir() if p.is_dir()):
            for artifact_dir in sorted(p for p in model_dir.iterdir() if p.is_dir()):
                robot_xml = artifact_dir / "robot.xml"
                controller_py = artifact_dir / "controller.py"
                if not (robot_xml.exists() and controller_py.exists()):
                    logger.warning("skip (missing files): %s", artifact_dir)
                    continue
                m = ARTIFACT_RE.match(artifact_dir.name)
                if not m:
                    logger.warning("skip (unparseable id): %s", artifact_dir.name)
                    continue
                t, c = int(m.group("t")), int(m.group("c"))
                model_label = f"{m.group('model')}__{cond}"
                grouped.setdefault(model_label, []).append((artifact_dir, t, c))

    n = 0
    for model_label, arts in grouped.items():
        # Stable rank order: by (tournament_idx, commit_idx). The exported
        # artifacts are already the top-K picks per pair; absolute rank within
        # the pair doesn't affect the RR (every bot plays every bot regardless).
        arts.sort(key=lambda a: (a[1], a[2]))
        records = []
        for rank, (artifact_dir, t, c) in enumerate(arts, 1):
            # artifact_id reconstructed by load_commit_artifact as
            # make_artifact_id(model_label, t, c) -> unique per (model,cond,t,c)
            artifact_id = f"{model_label}__t{t:02d}_c{c:03d}"
            records.append(TopKBotRecord(
                rank=rank,
                artifact_id=artifact_id,
                model=model_label,
                kind="refinement_commit",
                tournament_idx=t,
                commit_idx=c,
                # absolute paths: pool may live outside REPO_ROOT (self-contained dataset,
                # no symlinks). Downstream resolves as `repo_root / robot_xml`; pathlib makes
                # that the absolute path unchanged, so this works at read time too.
                robot_xml=str((artifact_dir / "robot.xml").resolve()),
                controller_py=str((artifact_dir / "controller.py").resolve()),
                qualification_score=None,
                intra_model_elo=None,
                intra_model_wld=None,
                cross_model_elo={"k1": None, "k3": None, "k5": None},
                cross_model_wld={"k1": None, "k3": None, "k5": None},
            ).to_dict())
        out_dir = dst_inter / model_label
        write_top_k_bots(
            out_dir / "top_5_bots.json",
            k=5,
            scope="cross_condition_top_k",
            model=model_label,
            source={"condition_model_dir": model_label},
            bots=records,
        )
        n += len(records)
    return n


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--artifacts-root", type=Path, required=True,
                    help="e.g. final-graphs/top1 (contains <cond>/<model>/<artifact_id>/)")
    ap.add_argument("--combined-dir", type=Path, required=True,
                    help="Output pool dir; cross_model/top_5_matches lands here.")
    ap.add_argument("--baselines-dir", type=Path, required=True)
    ap.add_argument("--tournament-config", type=Path, required=True)
    ap.add_argument("--baselines", nargs="*", default=DEFAULT_BASELINES)
    ap.add_argument("--n-rollouts", type=int, default=None)
    ap.add_argument("--n-parallel-matches", type=int, default=8)
    ap.add_argument("--n-parallel-seeds", type=int, default=1)
    ap.add_argument("--no-save-video", action="store_true")
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    def _abs(p: Path) -> Path:
        return p if p.is_absolute() else REPO_ROOT / p

    artifacts_root = _abs(args.artifacts_root)
    combined_dir = _abs(args.combined_dir)
    baselines_dir = _abs(args.baselines_dir)
    tournament_config = _abs(args.tournament_config)

    match_cfg = resolve_match_config(combined_dir, tournament_config)
    if args.no_save_video:
        match_cfg.save_video = False
        match_cfg.save_all_videos = False

    inter_model_dir = combined_dir / "inter_model"
    inter_model_dir.mkdir(parents=True, exist_ok=True)
    n = _build_inter_model(artifacts_root, inter_model_dir)
    logger.info("wrote %d (model, condition) inter_model dirs under %s", n, inter_model_dir)

    cross_model_out = combined_dir / "cross_model"
    clean_cache = combined_dir / "_clean_artifacts"
    run_stage3(
        inter_model_dir=inter_model_dir,
        output_root=cross_model_out,
        baselines_dir=baselines_dir,
        repo_root=REPO_ROOT,
        match_cfg=match_cfg,
        k_max=5,
        n_rollouts=args.n_rollouts,
        n_parallel_matches=args.n_parallel_matches,
        n_parallel_seeds=args.n_parallel_seeds,
        baselines=args.baselines,
        clean_cache_root=clean_cache,
    )
    logger.info("cross-condition RR done. matches in %s/top_5_matches/matches/", cross_model_out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
