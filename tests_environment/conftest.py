"""Run these regressions against this checkout's real simulator modules."""
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent / "support"))
sys.path.insert(0, str(ROOT))

# Match the application's import order; do not stub missing simulator APIs.
import mjarena.core.unified_builder  # noqa: E402,F401


def pytest_sessionfinish(session, exitstatus):
    foreign = {}
    for name, module in list(sys.modules.items()):
        if name != "mjarena" and not name.startswith("mjarena."):
            continue
        filename = getattr(module, "__file__", None)
        if filename and not Path(filename).resolve().is_relative_to(ROOT):
            foreign[name] = filename
    if foreign:
        reporter = session.config.pluginmanager.get_plugin("terminalreporter")
        if reporter:
            reporter.write_line(f"ERROR: simulator imports outside {ROOT}: {foreign}", red=True)
        session.exitstatus = pytest.ExitCode.USAGE_ERROR
