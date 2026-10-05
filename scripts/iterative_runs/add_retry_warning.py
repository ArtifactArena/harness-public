"""Add the authorized truncation warning to a queued retry or its next request.

For an already accepted request, --watch-active preserves the request in flight.
It adds the warning to the next iteration, or retries the current revision once
with the warning if the request in flight also ends with terminal truncation.
"""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import time

from resume_truncated_responses import MARKER, read

NOTICE = """

## Retry notice: previous response was truncated
This is a retry/continuation after a previous API call produced a truncated
response because the model did not leave enough tokens within its output budget
to provide a full response. Thinking and the final answer share that budget.
Limit your thinking and reserve enough tokens to return the complete required
robot XML and Python controller. Finish both code blocks; do not leave a partial
response. The total output token limit remains {limit} tokens.
"""


def save(path, data):
    path.write_text(json.dumps(data, indent=2))


def live_read(path):
    try:
        return read(path)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def patch_renderer(run):
    path = run / 'run.py'
    source = path.read_text()
    hook = '''    notice = HERE / f"revision_{revision:02d}" / "retry_notice.txt"
    if notice.exists():
        template += notice.read_text()
    return template
'''
    if hook in source:
        return
    anchor = '    return template\n'
    if source.count(anchor) != 1:
        raise RuntimeError('Unexpected prompt renderer')
    updated = source.replace(anchor, hook)
    compile(updated, str(path), 'exec')
    shutil.copy2(path, run / 'run.before-retry-warning.py')
    path.write_text(updated)


def install_notice(run, directory, notice):
    archive = directory / 'before_retry_warning'
    archive.mkdir(exist_ok=True)
    prompt = directory / 'prompt.txt'
    original = archive / 'prompt.txt'
    if prompt.exists() and not original.exists():
        shutil.copy2(prompt, original)
    (directory / 'retry_notice.txt').write_text(notice)
    if original.exists():
        prompt.write_text(original.read_text() + notice)
    save(archive / 'change.json', dict(reason='User requested a truncation warning',
         original_sha256=hashlib.sha256(original.read_bytes()).hexdigest() if original.exists() else None,
         updated_sha256=hashlib.sha256(prompt.read_bytes()).hexdigest() if prompt.exists() else None))


def launch(run, session):
    # The old launch shell can briefly outlive the runner holding run.lock.
    for _ in range(20):
        if subprocess.run(['tmux', 'has-session', '-t', '=' + session], capture_output=True).returncode:
            break
        time.sleep(.5)
    else:
        raise RuntimeError('Original run session still exists')
    subprocess.run(['tmux', 'new-session', '-d', '-s', session, '-c', str(run),
                    'bash ' + shlex.quote(str(run / 'launch.sh'))], check=True)


def prepare(run):
    audit = read(run / MARKER)
    config = read(run / 'config.json')
    if config['model'] == 'claude-opus-5':
        raise RuntimeError('Claude Opus 5 excluded')
    directory = run / audit['revision']
    with (run / 'run.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if any((directory / f).exists() for f in ('response_pending.json', 'response.json')):
            raise RuntimeError('Request already started')
        patch_renderer(run)
        install_notice(run, directory, NOTICE.format(limit=config['max_output_tokens']))
        save(run / 'retry_warning_status.json', dict(status='prepared', revision=directory.name))
    launch(run, audit['session'])
    print(run.name, 'resumed with warning at', directory.name, flush=True)


def watch_active(run):
    audit = read(run / MARKER)
    config = read(run / 'config.json')
    if config['model'] == 'claude-opus-5':
        raise RuntimeError('Claude Opus 5 excluded')
    current = run / audit['revision']
    following = run / f"revision_{int(audit['revision'][-2:])+1:02d}"
    template = run / 'iterative_prompt_template.md'
    backup = run / 'template.before-retry-warning.md'
    notice = NOTICE.format(limit=config['max_output_tokens'])
    if backup.exists():
        raise RuntimeError('Active watcher already prepared; inspect before resuming')
    if (current / 'response.json').exists() or (following / 'prompt.txt').exists():
        raise RuntimeError('Run advanced; inspect before changing template')
    patch_renderer(run)
    shutil.copy2(template, backup)
    # The running Python process already loaded the old renderer, which reads
    # this template fresh for every revision. The next prompt gets the warning;
    # restoring the template afterward confines the change to that request.
    following.mkdir(exist_ok=True)
    (following / 'retry_notice.txt').write_text(notice)
    template.write_text(backup.read_text() + notice)
    save(run / 'retry_warning_status.json', dict(status='armed for next request',
         active_revision=current.name, next_revision=following.name))
    print(run.name, 'warning armed; preserving active request', flush=True)
    deadline = time.monotonic() + 24 * 3600
    while time.monotonic() < deadline:
        response_path = current / 'response.json'
        response = live_read(response_path)
        if response and response.get('status') == 'incomplete' and response.get('stop_reason') == 'length':
            with (run / 'run.lock').open('a') as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    time.sleep(1)
                    continue
                template.write_bytes(backup.read_bytes())
                (following / 'retry_notice.txt').unlink(missing_ok=True)
                archive = current / 'failed_attempts' / 'unwarned-retry'
                archive.mkdir(parents=True)  # Never silently retry twice.
                for name in ('response.json', 'response_pending.json', 'response.txt',
                             'stream.jsonl', 'request_settings.json', 'usage.json'):
                    p = current / name
                    if p.exists():
                        p.rename(archive / name)
                guard = run / 'STOPPED_TRUNCATED.json'
                if guard.exists():
                    guard.rename(archive / guard.name)
                install_notice(run, current, notice)
                save(run / 'retry_warning_status.json', dict(status='warned retry prepared',
                     revision=current.name, previous_retry_status=response['status']))
            launch(run, audit['session'])
            print(run.name, 'unwarned request truncated; launched ONE warned retry', flush=True)
            return
        prompt = following / 'prompt.txt'
        if prompt.exists():
            if notice not in prompt.read_text():
                raise RuntimeError('Next prompt did not receive warning')
            template.write_bytes(backup.read_bytes())
            save(run / 'retry_warning_status.json', dict(status='warning delivered to next iteration',
                 revision=following.name, previous_retry_status=response.get('status') if response else None))
            print(run.name, 'warning delivered at', following.name, flush=True)
            return
        if live_read(run / 'status.json').get('status') == 'failed':
            # An incomplete response is handled above; other errors need review.
            template.write_bytes(backup.read_bytes())
            save(run / 'retry_warning_status.json', dict(status='stopped on unrelated error'))
            return
        time.sleep(1)
    template.write_bytes(backup.read_bytes())
    save(run / 'retry_warning_status.json', dict(status='watcher timed out; inspect run'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--watch-active', action='store_true')
    args = parser.parse_args()
    (watch_active if args.watch_active else prepare)(args.run)
