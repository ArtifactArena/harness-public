"""The two-stage tournament code stays in the repo: the sampling pool round robin
(intra-model RR over every zero-shot sample -> top-5 / top-1) is built on it."""
import importlib
import py_compile
from pathlib import Path

import pytest

import mjarena.core.unified_builder  # noqa: F401  (import order)

ROOT = Path(__file__).resolve().parents[1]

MODULES = [
    "mjarena.two_stage.qualification",
    "mjarena.two_stage.intra_model",
    "mjarena.two_stage.cross_model",
    "mjarena.two_stage.match_config",
    "mjarena.two_stage.artifact_loader",
    "mjarena.two_stage.aggregate",
]
SCRIPTS = [
    "scripts/two_stage/run_tournaments.py",
    "scripts/two_stage/compute_elo_and_plot.py",
    "scripts/two_stage/run_cross_condition_rr_from_artifacts.py",
]


@pytest.mark.parametrize("name", MODULES)
def test_two_stage_module_imports(name):
    mod = importlib.import_module(name)
    assert mod is not None


@pytest.mark.parametrize("rel", SCRIPTS)
def test_two_stage_script_compiles(rel):
    path = ROOT / rel
    assert path.exists(), f"{rel} was removed; the sampling pool round robin needs it"
    py_compile.compile(str(path), doraise=True)


def test_intra_model_rr_entry_points_exist():
    from mjarena.two_stage.intra_model import run_stage2
    from mjarena.two_stage.match_config import resolve_match_config
    assert callable(run_stage2) and callable(resolve_match_config)
