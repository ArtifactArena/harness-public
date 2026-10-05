"""Add job lookup and durable worker retirement to the selection coordinator.

These endpoints let the existing first-result-wins race service handle iterative
repeats. Retirement affects the next claim only; the active match keeps running.
"""
from pathlib import Path
import argparse


def patch(text):
    if '# Selection race endpoints' in text:
        return text
    old = "TOKEN='';INITIAL_SCAN_DONE=False;RESTORED_HEARTBEATS={}"
    assert old in text
    text = text.replace(old, old + ';RETIRED=set()', 1)
    old = "def scan():\n for key in RUNS:"
    assert old in text
    text = text.replace(old, "def scan():\n active_runs={ident.split('__')[1].rsplit('_',1)[0] for ident in RESTORED_HEARTBEATS if ident.startswith('selection__')}\n for key in sorted(RUNS,key=lambda run:run not in active_runs):", 1)
    old = "  if self.path=='/status':return self.send(read(HERE/'status.json',{}))"
    assert old in text
    text = text.replace(old, old + '''
  # Selection race endpoints: return existing recipes without creating a match.
  if self.path=='/job':
   with LOCK:
    job=JOBS.get(self.headers.get('X-Match-ID',''))
    return self.send({'job':dict(job) if job else None})
  if self.path=='/leases':
   return self.send([read(p,{}) for p in (HERE/'live_leases').glob('*.json')])''', 1)
    old = "  d=json.loads(body)\n  with LOCK:"
    assert old in text
    text = text.replace(old, '''  d=json.loads(body)
  if self.path=='/retire':
   workers=d.get('workers')
   if not isinstance(workers,list) or not all(isinstance(w,str) and re.fullmatch(r'[A-Za-z0-9_.-]{1,200}',w) for w in workers):return self.send({'error':'invalid workers'},400)
   with LOCK:
    RETIRED.update(workers);save(HERE/'retired_workers.json',sorted(RETIRED))
   return self.send({'ok':True})
  with LOCK:''', 1)
    old = "   if self.path=='/claim':\n    (HERE/'live_leases'/f'{worker}.json').unlink(missing_ok=True)"
    assert old in text
    text = text.replace(old, "   if self.path=='/claim':\n    if worker in RETIRED:return self.send({'job':None,'finished':True,'reason':'worker retired after current match'})\n    (HERE/'live_leases'/f'{worker}.json').unlink(missing_ok=True)", 1)
    old = '  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)'
    assert old in text
    return text.replace(old, old + "\n  RETIRED.update(read(HERE/'retired_workers.json',[]))", 1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    result = patch(args.source.read_text())
    compile(result, str(args.output), 'exec')
    args.output.write_text(result)
