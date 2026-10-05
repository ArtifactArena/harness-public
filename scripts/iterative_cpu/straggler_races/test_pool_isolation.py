from pathlib import Path
import os,signal,subprocess,sys,time,tempfile,json
with tempfile.TemporaryDirectory() as tmp:
 r=Path(tmp);s=r/'supervisor.py';s.write_text('''import concurrent.futures,os,time,json
from pathlib import Path
r=Path(__file__).parent
def worker(n):
 (r/f"pid{n}").write_text(str(os.getpid()))
 while not (r/f"stop{n}").exists():
  (r/f"beat{n}").write_text(str(time.time()));time.sleep(.05)
if __name__=="__main__":
 with concurrent.futures.ProcessPoolExecutor(max_workers=2) as p:
  for f in [p.submit(worker,i) for i in range(2)]:f.result()
''')
 p=subprocess.Popen([sys.executable,str(s)],stderr=subprocess.DEVNULL)
 try:
  deadline=time.monotonic()+5
  while not (r/'pid1').exists():
   assert time.monotonic()<deadline;time.sleep(.05)
  children=[int((r/f'pid{i}').read_text()) for i in range(2)]
  os.kill(p.pid,signal.SIGSTOP);time.sleep(.1);os.kill(children[0],signal.SIGTERM)
  before=float((r/'beat1').read_text());time.sleep(.3);after=float((r/'beat1').read_text());assert after>before
  (r/'stop1').touch();time.sleep(.2);os.kill(p.pid,signal.SIGCONT);p.wait(timeout=5)
  print('PASS: cancelling one child with the supervisor stopped preserves the sibling until it finishes')
 finally:
  if p.poll() is None:os.kill(p.pid,signal.SIGCONT);p.terminate();p.wait(timeout=5)
