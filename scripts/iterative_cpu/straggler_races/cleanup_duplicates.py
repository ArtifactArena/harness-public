"""Stop accepted-result duplicates whose pool supervisor is already isolated.

The manifest is produced from fresh source leases and confirmed host inventory,
then workers are retired on both source coordinators before this script runs.
Never resumes or terminates a pool supervisor. Leaves ambiguous targets alone.
"""
from pathlib import Path
import argparse,json,os,signal,socket,time,urllib.request

def info(pid):
 p=Path(f'/proc/{pid}')
 if not p.exists():return None
 if p.stat().st_uid!=os.getuid():raise RuntimeError('owner mismatch')
 fields=(p/'stat').read_text().rsplit(')',1)[1].split();cmd=(p/'cmdline').read_bytes()
 return dict(pid=pid,ppid=int(fields[1]),start=int(fields[19]),state=fields[0],cwd=str((p/'cwd').resolve()),worker=any(x in cmd for x in [b'tournament/worker.py',b'tournament/fleet_worker.py']) and b'--workers' in cmd)

def main():
 p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--token-file',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 plan=json.loads(a.plan.read_text());host=socket.gethostname().split('.')[0];token=a.token_file.read_text().strip();rows=[r for r in plan['targets'] if r['host']==host];leases={}
 for source,port in [('iterative-high-20260924',8001),('iterative-roster-20260924',8002)]:
  req=urllib.request.Request(f'http://host_a.example.org:{port}/leases',headers={'Authorization':'Bearer '+token})
  with urllib.request.urlopen(req,timeout=30) as response:leases[source]={d['worker']:d for d in json.load(response)}
 receipts=[]
 for r in rows:
  receipt=dict(host=host,pid=r['pid'],job=r['id'],at=time.time(),status='unverified')
  try:
   current=info(r['pid']);lease=leases[r['source']].get(r['worker'],{});folder=Path(r['root'])/'tournament/worker_matches'/r['id']
   if not current or current['state']=='Z':receipt['status']='exited'
   elif not current['worker'] or current['cwd']!=str(Path(r['root'])/'harness'):receipt['reason']='worker identity mismatch'
   elif (folder/'result_payload.json.gz').exists() or (folder/'result.json').exists():receipt['status']='finished locally'
   elif lease.get('job')!=r['id'] or lease.get('updated_at',0)<=plan['retired_at'] or time.time()-lease.get('updated_at',0)>120:receipt['reason']='no matching heartbeat after retirement'
   else:
    boot=time.time()-float(Path('/proc/uptime').read_text().split()[0]);born=boot+current['start']/os.sysconf('SC_CLK_TCK')
    parent=info(current['ppid'])
    if born>(folder/'red.xml').stat().st_mtime+1:receipt['reason']='process younger than match'
    elif not parent or not parent['worker'] or parent['state'] not in ('T','t'):receipt['reason']='supervisor not already isolated'
    else:
     again=info(r['pid']);parent_again=info(parent['pid'])
     if again==current and parent_again==parent:
      os.kill(r['pid'],signal.SIGTERM);receipt.update(status='stopped',start_ticks=current['start'],parent_pid=parent['pid'])
     else:receipt['reason']='identity changed'
  except OSError as exc:receipt['reason']=str(exc)
  receipts.append(receipt)
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(receipts,indent=2));print(json.dumps(receipts))
if __name__=='__main__':main()
