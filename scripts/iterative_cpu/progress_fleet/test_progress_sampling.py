import importlib.util,os,sys,types,unittest
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('match_progress',Path(__file__).parents[1]/'match_progress.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class ProgressTest(unittest.TestCase):
 def test_observation_does_not_change_steps_and_restores_wrapper(self):
  class Geoms:
   def __eq__(self,x):return types.SimpleNamespace(sum=lambda:4)
  class Env:
   def __init__(self):self.data=types.SimpleNamespace(time=0.);self.model=types.SimpleNamespace(geom_type=Geoms(),opt=types.SimpleNamespace(sdf_initpoints=32))
   def step(self,actions):self.data.time+=.005;return self.data.time,actions
  original=Env.step;action=object();baseline=Env();expected=[baseline.step(action) for _ in range(10)];env=Env()
  modules={'mjarena.envs.sumo':types.SimpleNamespace(SumoEnv=Env),'mujoco':types.SimpleNamespace(mjtGeom=types.SimpleNamespace(mjGEOM_SDF=1))}
  with patch.dict(sys.modules,modules),patch.object(os,'sched_getaffinity',return_value={0,2,4,6},create=True),patch.dict(os.environ,{'MATCH_CPU_BUDGET':'4'}):
   progress=m.MatchProgress({'id':'test'})
   with progress:actual=[env.step(action) for _ in range(10)]
   self.assertEqual(actual,expected);self.assertEqual(progress.sample['threads'],4);self.assertGreater(progress.sample['sim_seconds'],0);self.assertIs(Env.step,original)
   with self.assertRaises(RuntimeError):
    with progress:raise RuntimeError('cleanup')
   self.assertIs(Env.step,original)
if __name__=='__main__':unittest.main()
