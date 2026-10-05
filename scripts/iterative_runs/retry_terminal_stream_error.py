"""Retry one Together stream failure, preserving evidence.

Run directories must be registered iterative or tool-use runs. A per-step marker prevents
repeating this action after an ambiguous launch or another failed attempt.
Interrupted streams require --allow-interrupted-stream and explicit user
authorization, since their final provider status and billing are unknown.
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


def read(path):
    return json.loads(path.read_text())


def validate(directory, allow_interrupted=False):
    if any((directory / name).exists() for name in
           ('response.json', 'evaluation_summary.json', 'checkpoint.json', 'terminal_stream_retry.json')):
        raise RuntimeError('Response/evaluation or prior retry exists; inspect first')
    events = [json.loads(line) for line in (directory / 'stream.jsonl').read_text().splitlines() if line.strip()]
    error = events[-1].get('error', {}) if events else {}
    if any(choice.get('finish_reason') is not None
           for event in events for choice in event.get('choices', [])):
        raise RuntimeError('Stream contains a completion; inspect first')
    if allow_interrupted and events and not any(e.get('error') or e.get('usage') for e in events):
        return dict(type='interrupted_stream', message='Stream ended without completion marker; user explicitly authorized retry')
    if error.get('type') != 'internal_error' or 'h2 protocol error' not in error.get('message', ''):
        raise RuntimeError('Not a verified terminal Together HTTP/2 error')
    return error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    step = parser.add_mutually_exclusive_group(required=True)
    step.add_argument('--revision', type=int)
    step.add_argument('--turn', type=int)
    parser.add_argument('--allow-interrupted-stream', action='store_true',
                        help='Only after explicit user authorization to retry an interrupted stream')
    args = parser.parse_args()
    run = args.run.resolve()
    registry_root = run.parent if args.turn is not None else run.parents[1]
    record = next(r for r in read(registry_root / 'registry.json') if Path(r['path']).resolve() == run)
    session = record['session']
    if subprocess.run(['tmux', 'has-session', '-t', '=' + session], capture_output=True).returncode == 0:
        raise RuntimeError('Run session already exists')
    with (run / 'run.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        config = read(run / 'config.json')
        if config['provider'] != 'together' or read(run / 'status.json')['status'] != 'failed':
            raise RuntimeError('Expected a failed Together run')
        if (run / 'STOPPED_TRUNCATED.json').exists():
            raise RuntimeError('Truncation requires separate handling')
        if args.allow_interrupted_stream and read(run / 'status.json').get('error') != 'Provider stream ended without completion marker; partial events saved':
            raise RuntimeError('Expected the explicitly authorized interrupted-stream failure')
        number = args.turn if args.turn is not None else args.revision
        if not 1 <= number <= 10:
            raise RuntimeError('Expected a step between 1 and 10')
        directory = run / 'turns' / f'turn_{number:02d}' if args.turn is not None else run / f'revision_{number:02d}'
        error = validate(directory, args.allow_interrupted_stream)
        preserved = [run / 'config.json', directory / 'prompt.txt']
        if args.turn is not None:
            if list(directory.glob('tool_*.json')) or list(directory.glob('tool_*.pending')):
                raise RuntimeError('Failed API turn has tool activity; inspect first')
            checkpoints = [run / 'turns' / f'turn_{n:02d}' / 'checkpoint.json' for n in range(1, number)]
            if not all(p.exists() for p in checkpoints):
                raise RuntimeError('Missing earlier turn checkpoint')
            preserved += checkpoints + [run / 'journal.json']
            preserved += [run / 'workspace' / name for name in ('robot.xml', 'controller.py', 'notes.md')]
        ident = uuid.uuid4().hex
        archive = directory / 'failed_attempts' / ('terminal-stream-' + ident)
        archive.mkdir(parents=True)
        audit = dict(run=record['id'], revision=args.revision, turn=args.turn, error=error, retry_id=ident,
                     at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                     reason=('User explicitly authorized retry of interrupted stream' if args.allow_interrupted_stream
                             else 'Retry terminal provider connection failure') + '; prompt/settings unchanged',
                     prompt_sha256=hashlib.sha256((directory / 'prompt.txt').read_bytes()).hexdigest(),
                     config_sha256=hashlib.sha256((run / 'config.json').read_bytes()).hexdigest(),
                     preserved_sha256={str(p.relative_to(run)):hashlib.sha256(p.read_bytes()).hexdigest()
                                       for p in preserved if p.exists()},
                     failed_attempt_usage_unknown=True, prior_status=read(run / 'status.json'))
        (directory / 'terminal_stream_retry.json').write_text(json.dumps(audit, indent=2))
        (archive / 'retry-audit.json').write_text(json.dumps(audit, indent=2))
        for name in ('stream.jsonl', 'response_pending.json', 'request_settings.json'):
            source = directory / name
            if source.exists():
                source.rename(archive / name)
    subprocess.run(['tmux', 'new-session', '-d', '-s', session, '-c', str(run),
                    'bash ' + shlex.quote(str(run / 'launch.sh'))], check=True)
    print(record['id'], 'resumed at', 'turn' if args.turn is not None else 'revision', number)


if __name__ == '__main__':
    main()
