"""Add durable visibility to the tool-use selection queue, without restarting matches."""
from pathlib import Path
import argparse


def patch_coordinator(s):
    if '# Durable leases make tool-use selection visible' in s:
        return s
    old="  d=json.loads(raw);worker=d.get('worker','unknown');reply={};code=200"
    assert old in s
    s=s.replace(old,old+"\n  if not re.fullmatch(r'[A-Za-z0-9_.-]{1,200}',worker):return self.send({'error':'invalid worker'},400)")
    old='  self.send(reply,code)';assert s.count(old)==1
    s=s.replace(old,"""  # Durable leases make tool-use selection visible without touching workers.
  lease=HERE/'live_leases'/f'{worker}.json'
  if self.path=='/heartbeat':save(lease,{'worker':worker,'job':d['job'],'updated_at':time.time()})
  elif self.path=='/claim':
   if reply.get('job'):save(lease,{'worker':worker,'job':reply['job']['id'],'updated_at':time.time()})
   else:lease.unlink(missing_ok=True)
  elif self.path=='/error':lease.unlink(missing_ok=True)
  self.send(reply,code)""")
    old="  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);threading.Thread(target=scheduler,daemon=True).start();Server(('0.0.0.0',args.port),Handler).serve_forever()";assert old in s
    s=s.replace(old,"""  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  for p in (HERE/'live_leases').glob('*.json'):
   lease=read(p,{})
   if lease.get('job') and time.time()-lease.get('updated_at',0)<120:LEASES[lease['job']]={'worker':lease['worker'],'time':lease['updated_at']}
  threading.Thread(target=scheduler,daemon=True).start();Server(('0.0.0.0',args.port),Handler).serve_forever()""")
    return s


def patch_worker(s):
    if "os.environ['MH_LIVE_MATCH_DIR']" in s:
        return s
    old=" h=BASE/'source';os.chdir(h);started=time.monotonic()";assert old in s
    s=s.replace(old,old+"\n os.environ['MH_LIVE_MATCH_DIR']=str(root/'live-progress')")
    return s

def patch_engine(s):
    if 'from mjarena.live_seed_progress import live_seed_callback' in s:
        return s
    anchor = '        trace_enabled = bool(self.trace_label)'
    assert s.count(anchor) == 1
    s = s.replace(anchor, """        if os.environ.get('MH_TOOL_PROGRESS_DIR') or os.environ.get('MH_LIVE_MATCH_DIR'):
            from mjarena.live_seed_progress import live_seed_callback
            progress_callback = live_seed_callback(progress_callback, seed=seed,
                match_time=self.match_time, max_steps=self.max_steps, match_dir=self.out_dir)
""" + anchor)
    if '\nimport os\n' not in s:
        s = s.replace('\nimport json\n', '\nimport json\nimport os\n', 1)
    return s


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('kind', choices=['coordinator', 'worker', 'engine'])
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    result = {'coordinator': patch_coordinator, 'worker': patch_worker,
              'engine': patch_engine}[args.kind](args.source.read_text())
    compile(result, str(args.output), 'exec')
    args.output.write_text(result)
