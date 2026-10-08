#!/usr/bin/env python3
"""Build the default exact CPU backend in the active harness environment."""
import argparse
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mujoco-source", type=Path,
                        help="MuJoCo 3.10.0 source tree (downloaded if omitted)")
    parser.add_argument("--ispc", type=Path,
                        help="ISPC 1.31.0 executable for optional AVX-512 acceleration")
    args = parser.parse_args()
    if (platform.system(), platform.machine(), sys.version_info[:2]) != (
        "Linux", "x86_64", (3, 10)
    ):
        parser.error("requires Linux x86-64 and Python 3.10")
    import Cython
    import mujoco
    import numpy
    import threadpoolctl  # noqa: F401 -- required by the automatic runner

    if (Cython.__version__, mujoco.__version__, numpy.__version__) != (
        "3.1.4", "3.10.0", "2.1.3"
    ):
        parser.error("requires Cython 3.1.4, MuJoCo 3.10.0, NumPy 2.1.3")
    if shutil.which("gcc") is None:
        parser.error("gcc is required")
    root = Path(__file__).resolve().parents[1]
    source = args.mujoco_source
    if source is None:
        cache = root / "build/acceleration"
        cache.mkdir(parents=True, exist_ok=True)
        source = cache / "mujoco-3.10.0"
        if not source.is_dir():
            archive = cache / "mujoco-3.10.0.tar.gz"
            url = "https://github.com/google-deepmind/mujoco/archive/refs/tags/3.10.0.tar.gz"
            print(f"Downloading {url}", flush=True)
            with urllib.request.urlopen(url, timeout=120) as response, archive.open("wb") as out:
                shutil.copyfileobj(response, out)
            with tarfile.open(archive) as tar:
                tar.extractall(cache, filter="data")
    source = source.resolve()
    for script in ("observation_accel/build.py", "match_accel/build_interval.py"):
        subprocess.run([sys.executable, str(root / "mjarena/envs" / script),
                        "build_ext", "--inplace"], cwd=root, check=True)
    library = root / "mjarena/envs/match_accel/arena_serial.so"
    command = [sys.executable, str(root / "mjarena/envs/match_accel/build.py"),
               str(source), str(library)]
    if args.ispc:
        command.extend(["--ispc", str(args.ispc.resolve())])
    subprocess.run(command, cwd=root, check=True)
    # Test the same initialization used by serial and spawned matches.
    subprocess.run([
        sys.executable, "-c",
        "import os; os.environ['ARENA_MATCH_ACCEL']='1'; "
        "import mjarena.core.unified_builder; "
        "from mjarena.runner.acceleration import match_acceleration; "
        "\nwith match_acceleration(): print('CPU acceleration ready', flush=True)",
    ], cwd=root, check=True)


if __name__ == "__main__":
    main()
