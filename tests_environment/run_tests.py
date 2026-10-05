"""Run the original harness tests and native environment regressions together."""
from pathlib import Path
import subprocess
import sys


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests", "tests_environment",
         "--continue-on-collection-errors", "-ra", "--tb=short", *sys.argv[1:]],
        cwd=root,
    )
    raise SystemExit(result.returncode)
