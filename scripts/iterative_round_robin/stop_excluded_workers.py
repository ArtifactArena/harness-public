"""Stop only an omitted one-match child identified by host, PID, slot and birth time."""
import json,os,signal,socket,sys,time
from pathlib import Path

def stop(receipt):
 boot=int(next(l.split()[1] for l in Path('/proc/stat').read_text().splitlines() if l.startswith('btime ')));reports=[]
 for item in receipt['active']:
  d=item['progress']
  if d.get('host','').split('.')[0]!=socket.gethostname().split('.')[0]:continue
  assert d['job']==item['id'] and 'grok_10' in item['id'].split('__')
  pid=d['pid'];p=Path('/proc')/str(pid)
  try:
   fd=os.pidfd_open(pid)
  except ProcessLookupError:reports.append(dict(pid=pid,state='already exited'));continue
  try:
   assert p.stat().st_uid==os.getuid()
   stat=(p/'stat').read_text().rsplit(')',1)[1].split();birth=boot+int(stat[19])/os.sysconf('SC_CLK_TCK');args=(p/'cmdline').read_text().split('\0')
   assert 0<=d['started_at']-birth<120,(pid,birth,d['started_at'])
   assert any(x.endswith('progress_worker.py') for x in args) and '--slot-index' in args
   assert int(args[args.index('--slot-index')+1])==int(item['claim']['worker'].rsplit('-',1)[1])
   cwd=(p/'cwd').resolve();assert cwd.name=='harness'
   assert (cwd.parent/'tournament/worker_matches'/item['id']).is_dir()
   signal.pidfd_send_signal(fd,signal.SIGTERM);reports.append(dict(pid=pid,job=item['id'],state='SIGTERM sent',start_ticks=stat[19]))
  except (FileNotFoundError,ProcessLookupError):reports.append(dict(pid=pid,state='already exited'))
  finally:os.close(fd)
 print(json.dumps(dict(host=socket.gethostname(),results=reports)))
if __name__=='__main__':stop(json.load(sys.stdin))
