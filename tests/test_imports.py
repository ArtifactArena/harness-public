"""Every public entry point imports cleanly in a fresh interpreter, in any order."""
import subprocess
import sys

import pytest

ORDERS = [
    "import mjarena.core.unified_builder",
    "import mjarena.eval.match_runner",
    "import mjarena.design_shop",
    "import mjarena.envs.sumo",
    "import mjarena.design_shop.tools.match_tools",
    "import run_baseline_agent",
    "import run_episode_viewer",
    "import mjarena.envs.sumo, mjarena.eval.match_runner, mjarena.design_shop, mjarena.core.unified_builder",
]


@pytest.mark.parametrize("stmt", ORDERS)
def test_fresh_process_import(stmt):
    proc = subprocess.run([sys.executable, "-c", stmt], capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr[-1500:]
