import importlib.util,json,tempfile,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('protocol',Path(__file__).with_name('progress_protocol.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class ProtocolTest(unittest.TestCase):
 def test_cpu_budget_counts_both_bots(self):
  def bot(n):return {'xml':'<mujoco><worldbody>'+('<geom type="sdf"/>'*n)+'</worldbody></mujoco>'}
  self.assertEqual(m.cpu_budget(dict(red=bot(1),blue=bot(2))),1)
  self.assertEqual(m.cpu_budget(dict(red=bot(2),blue=bot(2))),4)
 def test_rejects_cross_worker_progress(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);d=dict(worker='lab-host-42-0',job='selection__a__b__7101_red',progress=dict(job='selection__a__b__7101_red',host='lab-host',pid=43,sim_seconds=11))
   m.record_progress(root,d);self.assertFalse((root/'progress').exists())
   d['progress']['pid']=42;m.record_progress(root,d);saved=json.loads((root/'progress/lab-host-42-0.json').read_text());self.assertEqual(saved['sim_seconds'],11)
if __name__=='__main__':unittest.main()
