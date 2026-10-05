"""Package the validated accelerator without upgrading frozen tournament rules.

Build compiled extensions using the accelerator READMEs first. This tool only
assembles a release; it does not download dependencies or run matches.
"""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline', required=True, type=Path)
    p.add_argument('--compiled-harness', required=True, type=Path)
    p.add_argument('--library', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    args = p.parse_args()
    here = Path(__file__).resolve().parent
    validated = json.loads((here / 'validated-release.json').read_text())
    for name, expected in validated['baseline'].items():
        if sha(args.baseline / name) != expected:
            raise RuntimeError('Frozen baseline mismatch: ' + name)
    args.output.mkdir(parents=True, exist_ok=False)
    harness = args.output / 'harness'
    target = harness / 'mjarena/envs/sumo.py'
    target.parent.mkdir(parents=True)
    shutil.copy2(args.baseline / 'mjarena/envs/sumo.py', target)
    subprocess.run(['patch', '-p1', '-i', str(here / 'frozen-sumo.patch')],
                   cwd=harness, check=True)
    for package in ('observation_accel', 'match_accel'):
        source = args.compiled_harness / 'mjarena/envs' / package
        if not list(source.glob('*.so')):
            raise RuntimeError('Build extensions first: ' + str(source))
        shutil.copytree(source, harness / 'mjarena/envs' / package,
                        ignore=shutil.ignore_patterns('__pycache__', 'build', '*.o'))
    (args.output / 'native').mkdir()
    shutil.copy2(args.library, args.output / 'native/arena_onecore_v3.so')
    shutil.copy2(args.library.with_suffix('.json'),
                 args.output / 'native/arena_onecore_v3.json')
    (args.output / 'tournament').mkdir()
    for name in ('cpu_acceleration.py', 'fleet_worker.py', 'match_progress.py'):
        shutil.copy2(here / name, args.output / 'tournament' / name)
    # Record rebuilt binary hashes, not just the historical validated hashes.
    manifest = {'baseline': validated['baseline'], 'files': {
        str(path.relative_to(args.output)): sha(path)
        for path in sorted(args.output.rglob('*')) if path.is_file()
    }}
    (args.output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print('Packaged:', args.output)
    print('A rebuilt native library requires parity validation before production use.')


if __name__ == '__main__':
    main()
