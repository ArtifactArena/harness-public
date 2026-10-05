"""Coordinator-side capability gate and read-only simulation telemetry."""
from functools import lru_cache
from pathlib import Path
import json,re,time,xml.etree.ElementTree as ET
PROTOCOL='simulation-v1'
@lru_cache(maxsize=2048)
def sdf_count(xml):
 if not xml:return 0
 return sum(n.get('type')=='sdf' for n in ET.fromstring(xml).iter('geom'))
def cpu_budget(job):
 return 4 if sum(sdf_count(job[s].get('xml','')) for s in ['red','blue'])>=4 else 1
def record_progress(root,data):
 progress=data.get('progress');worker=data.get('worker','')
 if not isinstance(progress,dict) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,200}',worker):return
 parts=worker.rsplit('-',2)
 if len(parts)!=3 or not parts[1].isdigit():return
 if progress.get('job')!=data.get('job') or progress.get('pid')!=int(parts[1]) or progress.get('host','').split('.')[0]!=parts[0].split('.')[0]:return
 path=root/'progress'/f'{worker}.json';path.parent.mkdir(exist_ok=True)
 progress={**progress,'updated_at':time.time(),'worker':worker}
 raw=json.dumps(progress,allow_nan=False);tmp=path.with_suffix('.tmp');tmp.write_text(raw);tmp.replace(path)
