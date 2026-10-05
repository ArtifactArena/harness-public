"""Drain selected one-core slots and release only acknowledged, exited children."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import shutil
import time


def acknowledged_exit(ack):
    try:
        pid=json.loads(ack.read_text())['pid'];proc=Path('/proc')/str(pid)/'stat'
        return not proc.exists() or proc.read_text().rsplit(')',1)[1].split()[0]=='Z'
    except (OSError,ValueError,KeyError):return False


def drain(manifest, source, count, timeout):
    data=json.loads(manifest.read_text());root=Path(data['root'])
    assert data['budget']==1 and data['host']==os.uname().nodename
    parent=Path('/proc')/str(data['pid'])
    assert parent.stat().st_uid==os.getuid()
    assert 'progress_worker.py' in (parent/'cmdline').read_text()
    lockroot=Path('<local>/locks')
    reservation=lockroot/f"straggler-reservation-progress-{data['job_id']}-{data['step_id']}-1.json"
    original=json.loads(reservation.read_text())
    assert original['pid']==data['pid'] and set(original['cpus'])<=set(data['cpus'])
    released_before={i for i,cpu in enumerate(data['cpus']) if cpu not in original['cpus']}
    original['cpus']=data['cpus']
    original['cores']=[]
    for cpu in data['cpus']:
        topology=Path(f'/sys/devices/system/cpu/cpu{cpu}/topology')
        original['cores'].append([int((topology/'physical_package_id').read_text()),int((topology/'core_id').read_text())])
    ticks=(parent/'stat').read_text().rsplit(')',1)[1].split()[19]
    if original.get('start_ticks'):assert original['start_ticks']==ticks
    else:
        boot=int(next(l.split()[1] for l in Path('/proc/stat').read_text().splitlines() if l.startswith('btime ')))
        started=boot+int(ticks)/os.sysconf('SC_CLK_TCK')
        assert 0<=data['started_at']-started<120
    assert (parent/'cwd').resolve()==root.resolve()
    assert 0<count<=data['workers'] and count%4==0
    target=root/'tournament/progress_worker.py';request=target.with_name('retire-slots.json')
    prior=set(json.loads(request.read_text())) if request.exists() else set()
    starts={}
    for pid in (parent/'task'/str(data['pid'])/'children').read_text().split():
        try:
            p=Path('/proc')/pid;args=(p/'cmdline').read_text().split('\0')
            index=int(args[args.index('--slot-index')+1])
            if index not in prior:starts[index]=int((p/'stat').read_text().rsplit(')',1)[1].split()[19])
        except (OSError,ValueError):continue
    # Recent children are likely to finish sooner; current matches are never killed.
    by_socket={}
    for index in sorted(starts,key=starts.get,reverse=True):
        by_socket.setdefault(original['cores'][index][0],[]).append(index)
    selected=[]
    while len(selected)<count:
        before=len(selected)
        for indices in by_socket.values():
            if len(indices)>=4 and len(selected)<count:
                selected.extend(indices[:4]);del indices[:4]
        if len(selected)==before:break
    assert len(selected)==count
    selected=sorted(set(selected)|prior)
    shutil.copy2(source,target.with_suffix('.new'));target.with_suffix('.new').replace(target)
    tmp=request.with_suffix('.tmp');tmp.write_text(json.dumps(selected));tmp.replace(request)
    released=set(released_before);deadline=time.monotonic()+timeout
    report=manifest.with_name(manifest.stem+'-drain.json')
    while time.monotonic()<deadline:
        for index in selected:
            ack=target.with_name('retired-slots')/str(index)
            if acknowledged_exit(ack):released.add(index)
        with (lockroot/'straggler-races-20260924.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            current=json.loads(reservation.read_text())
            assert current['pid']==original['pid'] and current.get('start_ticks')==original.get('start_ticks')
            current['cpus']=[cpu for i,cpu in enumerate(original['cpus']) if i not in released]
            current['cores']=[core for i,core in enumerate(original['cores']) if i not in released]
            tmp=reservation.with_suffix('.tmp');tmp.write_text(json.dumps(current));tmp.replace(reservation)
        state=dict(selected=selected,released=sorted(released),updated_at=time.time(),parent_pid=data['pid'])
        tmp=report.with_suffix('.tmp');tmp.write_text(json.dumps(state));tmp.replace(report)
        if len(released)==len(selected):print(json.dumps(state),flush=True);return
        time.sleep(5)
    raise TimeoutError(f'Drain remains partial; see {report}. No running match was stopped.')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('manifest',type=Path);p.add_argument('source',type=Path)
    p.add_argument('--count',type=int,default=48);p.add_argument('--timeout',type=int,default=1800)
    a=p.parse_args()
    with a.manifest.with_suffix('.drain.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        drain(a.manifest,a.source,a.count,a.timeout)
