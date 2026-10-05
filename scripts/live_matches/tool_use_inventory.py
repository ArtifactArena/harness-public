"""Read-only inventory of live sandbox tool calls, identified by workspace inode."""
from pathlib import Path
import json
import os
import socket
import time

BASE = Path('<work-root>')
SIMULATION_TOOLS = {'run_match', 'does_bot_qualify', 'save_bot'}


def read(path, default=None):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def tool_rows(spec, marker, pid, host, seeds, namespace_pids, now):
    """Describe only a currently live simulator tool; ordinary tools stay out."""
    tool = marker.get('tool')
    if tool not in SIMULATION_TOOLS:
        return []
    args = marker.get('args') or {}
    red = args.get('red', args.get('ref', args.get('source', 'draft')))
    blue = args.get('blue', 'qualification block')
    base = dict(host=host, pool='Tool use · ' + spec.get('title', spec['id']),
                category='tool_use', source='tool_use', run_id=spec['id'],
                candidate_id=spec['id'] + ' / ' + str(red),
                opponent_id=spec['id'] + ' / ' + str(blue), side='red',
                acceleration='Unaccelerated', threads=1, stale=False)
    rows = []
    for filename, seed in seeds:
        host_pid = namespace_pids.get(seed.get('pid'))
        if seed.get('complete') or not host_pid or now - seed.get('updated_at', 0) > 120:
            continue
        ident = 'tool__' + spec['id'] + '__' + filename
        rows.append(dict(base, **{k: seed[k] for k in
                         ('started_at', 'updated_at', 'sampled_at', 'sim_seconds', 'limit_seconds', 'seed')},
                         id=ident, attempt=f'{host}:{host_pid}:{ident}', pid=host_pid,
                         kind='tool use · ' + tool, tracking='measured'))
    # Old processes cannot gain a callback mid-match. Show their live invocation
    # explicitly as a batch, without inventing seed count, progress, or an ETA.
    if not rows and not seeds:
        ident = 'tool__' + spec['id'] + '__' + Path(marker.get('path', 'unknown')).name
        rows.append(dict(base, id=ident, attempt=f'{host}:{pid}:{ident}', pid=pid,
                         kind='tool use · ' + tool + ' batch', seed='batch',
                         started_at=marker.get('started_at', now), updated_at=now,
                         sim_seconds=None, limit_seconds=300, threads=None, tracking='process-confirmed'))
    return rows


def collect_tools():
    registry = read(BASE/'iterative-high-20260924/dashboard/tool_use_registry.json', [])
    workspaces = {}
    for spec in registry:
        workspace = Path(spec['path'])/'workspace'
        try:
            stat = workspace.stat()
            workspaces[(stat.st_dev, stat.st_ino)] = (spec, workspace)
        except OSError:
            pass
    if not workspaces:
        return []
    tools = []
    processes = {}
    boot = time.time() - float(Path('/proc/uptime').read_text().split()[0])
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            if proc.stat().st_uid != os.getuid():
                continue
            fields = (proc/'stat').read_text().rsplit(')', 1)[1].split()
            if fields[0] == 'Z':
                continue
            namespace = str((proc/'ns/pid').readlink())
            ns_pid = int(next(line for line in (proc/'status').read_text().splitlines()
                              if line.startswith('NSpid:')).split()[-1])
            processes.setdefault(namespace, {})[ns_pid] = int(proc.name)
            if b'/code/tool_worker.py' not in (proc/'cmdline').read_bytes().split(b'\0'):
                continue
            stat = (proc/'cwd').stat()
            item = workspaces.get((stat.st_dev, stat.st_ino))
            if item:
                born = boot + int(fields[19]) / os.sysconf('SC_CLK_TCK')
                tools.append((*item, int(proc.name), namespace, born))
        except (OSError, ValueError, StopIteration):
            continue
    rows = []
    for spec, workspace, pid, namespace, born in tools:
        marker = read(workspace/'_tool_progress_current.json', {})
        if marker.get('started_at', 0) < born - 2:
            continue  # A new worker must not inherit the previous tool's marker.
        directory = workspace/marker.get('path', '_missing')
        if not directory.resolve().is_relative_to(workspace.resolve()):
            continue
        seeds = [(p.stem, read(p, {})) for p in directory.glob('live-*.json')]
        rows.extend(tool_rows(spec, marker, pid, socket.gethostname(), seeds,
                              processes.get(namespace, {}), time.time()))
    return rows
