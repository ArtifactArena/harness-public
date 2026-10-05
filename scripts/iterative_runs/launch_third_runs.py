"""Launch the five explicitly requested third iterative runs from repeat 2.

Copies source/configuration only, validates the identical first prompt without
an API call, then registers and launches persistent CPU-only tmux runners.
"""
import argparse
import datetime
import fcntl
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess

MODELS = ('deepseek4', 'glm52', 'glm53', 'kimi3', 'qwen38')
SOURCES = ('run.py', 'provider_adapter.py', 'provider_slots.py',
           'evaluation_slots.py', 'parallel_cube.py', 'monitor_rewards.py',
           'report.py', 'truncation_guard.py', 'sampling_prompt.md',
           'iterative_prompt_template.md')


def read(path):
    return json.loads(path.read_text())


def save(path, data):
    temporary = path.with_suffix(path.suffix + '.third-run.tmp')
    temporary.write_text(json.dumps(data, indent=2) + '\n')
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    with (root / 'third-run-launch.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        registry = read(root / 'registry.json')
        by_id = {r['id']: r for r in registry}
        for model in MODELS:
            ident = 'r3_' + model
            if ident in by_id or (root / 'runs' / ident).exists():
                raise RuntimeError(f'{ident} already exists; inspect before launching')
        prepared = []
        stamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        for model in MODELS:
            source_record = by_id['r2_' + model]
            source = Path(source_record['path'])
            ident = 'r3_' + model
            target = root / 'runs' / ident
            config = read(source / 'config.json')
            assert config['provider'] == 'together'
            assert config['starting_bot'] is None
            assert config['revision_attempts'] == 10
            assert not config['champion_matches_enabled']
            assert read(source / 'status.json')['status'] == 'completed'
            target.mkdir()
            for name in SOURCES:
                shutil.copy2(source / name, target / name)
                if name.endswith('.py'):
                    compile((target / name).read_text(), str(target / name), 'exec')
            for name, key in [('sampling_prompt.md', 'sampling_prompt_sha256'),
                              ('iterative_prompt_template.md', 'template_sha256')]:
                assert hashlib.sha256((target / name).read_bytes()).hexdigest() == config[key]
            title = source_record['title'].replace('repeat 2', 'repeat 3')
            config.update(repeat=3, run_id=root.name + '-' + ident,
                          experiment_title=title)
            save(target / 'config.json', config)
            launch = (source / 'launch.sh').read_text().replace(str(source), str(target))
            assert "CUDA_VISIBLE_DEVICES=''" in launch
            assert str(source) not in launch
            (target / 'launch.sh').write_text(launch)
            subprocess.run(['bash', '-n', str(target / 'launch.sh')], check=True)
            python = str(Path(config['python_environment']) / 'bin/python')
            subprocess.run([python, str(target / 'run.py'), '--prepare'], cwd=target, check=True)
            assert (target / 'first_prompt_preview.txt').read_bytes() == (source / 'first_prompt_preview.txt').read_bytes()
            assert not list(target.glob('revision_*'))
            save(target / 'status.json', dict(status='queued', stage='third run prepared', completed_revisions=0))
            record = dict(source_record, id=ident, path=str(target), repeat=3,
                          title=title, continued=False, session='user-23x2-' + ident)
            save(target / 'preflight.json', dict(prepared_at=stamp, source=str(source),
                 first_prompt_unchanged=True, source_sha256={name:hashlib.sha256((target/name).read_bytes()).hexdigest() for name in SOURCES}))
            prepared.append(record)
        shutil.copy2(root / 'registry.json', root / 'registry.before-third-runs.json')
        save(root / 'registry.json', registry + prepared)
        manifest = dict(prepared_at=stamp, runs=[])
        save(root / 'third-runs-launch.json', manifest)
        for record in prepared:
            target = Path(record['path'])
            session = record['session']
            if subprocess.run(['tmux', 'has-session', '-t', '=' + session], capture_output=True).returncode == 0:
                raise RuntimeError(f'Session already exists: {session}')
            subprocess.run(['tmux', 'new-session', '-d', '-s', session, '-c', str(target),
                            'bash ' + shlex.quote(str(target / 'launch.sh'))], check=True)
            pid = int(subprocess.check_output(['tmux', 'list-panes', '-t', '=' + session,
                                              '-F', '#{pane_pid}'], text=True).strip())
            entry = dict(record, pid=pid, launched_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                         start_ticks=Path(f'/proc/{pid}/stat').read_text().split()[21])
            save(target / 'launch_manifest.json', entry)
            manifest['runs'].append(entry)
            save(root / 'third-runs-launch.json', manifest)
            print(record['id'], 'launched', flush=True)


if __name__ == '__main__':
    main()
