"""Explicit, one-time retry of terminal Together truncations, preserving evidence.

Dry-run by default. Use --apply only after authorization; --report compares the
saved original with the new response without issuing requests.
"""
import argparse
import datetime
import fcntl
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import uuid

MARKER = 'authorized_truncation_retry.json'


def read(path):
    return json.loads(path.read_text())


def candidate(run):
    config = read(run / 'config.json')
    if config['model'] == 'claude-opus-5' or config['provider'] != 'together':
        return None
    if (run / MARKER).exists() or read(run / 'status.json').get('status') != 'failed':
        return None
    failures = [p for p in run.glob('revision_*/response.json')
                if read(p).get('status') == 'incomplete'
                and read(p).get('stop_reason') == 'length']
    if not failures:
        return None
    if len(failures) != 1:
        raise RuntimeError(f'Multiple terminal truncations: {run}')
    directory = failures[0].parent
    if (directory / 'evaluation_summary.json').exists():
        raise RuntimeError(f'Truncated revision still has evaluation: {directory}')
    if not (directory / 'prompt.txt').exists():
        raise RuntimeError(f'Missing original prompt: {directory}')
    return directory


def resume(record):
    run = Path(record['path'])
    session = record['session']
    if subprocess.run(['tmux', 'has-session', '-t', '=' + session],
                      capture_output=True).returncode == 0:
        raise RuntimeError(f'Existing session: {session}')
    with (run / 'run.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        directory = candidate(run)
        if directory is None:
            return
        ident = uuid.uuid4().hex
        archive = directory / 'failed_attempts' / ('truncation-' + ident)
        archive.mkdir(parents=True)
        audit = dict(run=record['id'], revision=directory.name, archive=str(archive),
                     session=session, retry_id=ident,
                     reason='User authorized one retry, excluding Claude Opus 5',
                     at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                     prompt_sha256=hashlib.sha256((directory / 'prompt.txt').read_bytes()).hexdigest(),
                     config_sha256=hashlib.sha256((run / 'config.json').read_bytes()).hexdigest(),
                     prior_status=read(run / 'status.json'))
        # Persist a run-wide one-shot marker before moving any artifacts. A failed
        # launch requires inspection rather than silently issuing another request.
        with (run / MARKER).open('x') as f:
            json.dump(audit, f, indent=2)
        (archive / 'retry-audit.json').write_text(json.dumps(audit, indent=2))
        for name in ('response.json', 'response_pending.json', 'response.txt',
                     'usage.json', 'request_settings.json', 'stream.jsonl',
                     'request_retry.json'):
            source = directory / name
            if source.exists():
                source.rename(archive / name)
        guard = run / 'STOPPED_TRUNCATED.json'
        if guard.exists():
            guard.rename(archive / guard.name)
    subprocess.run(['tmux', 'new-session', '-d', '-s', session, '-c', str(run),
                    'bash ' + shlex.quote(str(run / 'launch.sh'))], check=True)
    print(record['id'], 'resumed', directory.name, flush=True)


def report(run):
    audit = read(run / MARKER)
    directory = run / audit['revision']
    old = read(Path(audit['archive']) / 'response.json')
    new = read(directory / 'response.json') if (directory / 'response.json').exists() else {}
    return dict(run=audit['run'], revision=audit['revision'],
                original_usage=old.get('usage'), retry_status=new.get('status', 'pending'),
                retry_stop_reason=new.get('stop_reason'), retry_usage=new.get('usage'),
                run_status=read(run / 'status.json'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--apply', action='store_true')
    mode.add_argument('--report', action='store_true')
    args = parser.parse_args()
    for record in read(args.root / 'registry.json'):
        run = Path(record['path'])
        if args.report:
            if (run / MARKER).exists():
                print(json.dumps(report(run)))
        elif candidate(run) is not None:
            if args.apply:
                resume(record)
            else:
                print(record['id'], candidate(run).name)


if __name__ == '__main__':
    main()
