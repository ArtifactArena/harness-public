from pathlib import Path
import argparse

def patch(s):
 if 'from progress_protocol import' in s:return s
 needle='def now():';assert needle in s
 s=s.replace(needle,"sys.path.insert(0,str(HERE))\nfrom progress_protocol import cpu_budget,record_progress,PROTOCOL\n\n"+needle,1)
 needle='  body=self.rfile.read(length)';assert needle in s
 s=s.replace(needle,needle+"\n  if self.path=='/claim' and (HERE/'require_progress').exists() and self.headers.get('X-Match-Progress')!=PROTOCOL:return self.send({'job':None,'finished':True,'reason':'worker must report simulation progress'})\n  if self.path=='/heartbeat':record_progress(HERE,json.loads(body))",1)
 s=s.replace("pending=[j for j in JOBS.values() if j['status']=='pending']", "pending=[j for j in JOBS.values() if j['status']=='pending' and cpu_budget(j)==int(self.headers.get('X-Match-CPU-Budget','1'))]")
 s=s.replace('not INITIAL_SCAN_DONE or time.time()-START<180','time.time()-START<180')
 compile(s,'coordinator.py','exec');return s
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('output',type=Path);a=p.parse_args();a.output.write_text(patch(a.source.read_text()))
