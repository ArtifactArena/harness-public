import os,sys,time,json,statistics,types,importlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
exec(compile(Path(__file__).with_name('benchmark_state.py').read_text().split('timings = ')[0],'captured-setup','exec'))
name='mjarena.envs.observation_accel_baseline'
package=types.ModuleType(name);package.__path__=[str(Path(os.environ['OBS_BASELINE'])/'mjarena/envs/observation_accel')];package.__package__=name;sys.modules[name]=package
baseline_module=importlib.import_module(name+'._details');baseline=baseline_module.DetailedObservations(env)
print('baseline package',baseline_module.__file__,flush=True)
baseline.impulses=frozen['impulses'];baseline.interval_seconds=frozen['interval_seconds'];baseline.capture_contacts()
observers=[reference,baseline,candidate];times=[[],[],[]];cpu_times=[[],[],[]]
for repeat in range(16):
 values=[None]*3
 for idx in ([0,1,2] if repeat%2==0 else [2,1,0]):
  detail=observers[idx];detail.cached=None
  if idx==1:baseline_module._QUATERNIONS.clear()
  if idx==2:_details._QUATERNIONS.clear()
  cpu=time.process_time();t=time.perf_counter()
  values[idx]=[detail.for_robot(p) for p in frozen['prefixes']]
  times[idx].append(time.perf_counter()-t);cpu_times[idx].append(time.process_time()-cpu)
 exact(values[0],values[1]);exact(values[0],values[2])
med=[statistics.median(t[2:]) for t in times];cpu=[statistics.median(t[2:]) for t in cpu_times]
report={'wall_seconds':dict(zip(['original','deployed','candidate'],med)),'cpu_seconds':dict(zip(['original','deployed','candidate'],cpu)),'incremental_speedup':med[1]/med[2],'incremental_cpu_speedup':cpu[1]/cpu[2],'overall_speedup':med[0]/med[2],'bitwise_equal':True,'overlay':os.environ['OBS_OVERLAY']}
print(json.dumps(report),flush=True)
