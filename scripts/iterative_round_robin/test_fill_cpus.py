"""Core reservations must survive until the exact retired worker exits."""
import json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import fill_cpus
class DrainTest(unittest.TestCase):
 def test_only_acknowledged_exited_slots_release(self):
  with tempfile.TemporaryDirectory() as directory:
   base=Path(directory);deployment=base/'deployment';deployment.mkdir();locks=base/'locks';locks.mkdir();root=base/'run';(root/'tournament/retired-slots').mkdir(parents=True)
   parent=base/'proc/42';parent.mkdir(parents=True);(parent/'cwd').symlink_to(root,target_is_directory=True);(parent/'cmdline').write_text('python progress_worker.py');fields=['S']+['0']*18+['999'];(parent/'stat').write_text('42 (python) '+' '.join(fields))
   (root/'tournament/retired-slots/0').write_text(json.dumps({'pid':777}))
   d=dict(budget=4,host=os.uname().nodename,pid=42,root=str(root),job_id='j',step_id='s',workers=2,cpus=list(range(8)));(deployment/'run.json').write_text(json.dumps(d))
   reservation=locks/'straggler-reservation-progress-j-s-4.json';reservation.write_text(json.dumps(dict(pid=42,start_ticks='999',cpus=list(range(8)),cores=[[0,i] for i in range(8)])))
   def mapped(value):return base/str(value).lstrip('/') if str(value)=='/proc' else Path(value)
   with patch.object(fill_cpus,'Path',side_effect=mapped):fill_cpus.retire_finished_heavy(deployment,locks)
   self.assertEqual(json.loads(reservation.read_text())['cpus'],[4,5,6,7]);self.assertEqual(json.loads((root/'tournament/retire-slots.json').read_text()),[0,1])
   # An acknowledged PID that still exists must retain its reservation.
   child=base/'proc/888';child.mkdir();(child/'stat').write_text('888 (python) '+' '.join(fields));(root/'tournament/retired-slots/1').write_text(json.dumps({'pid':888}))
   with patch.object(fill_cpus,'Path',side_effect=mapped):fill_cpus.retire_finished_heavy(deployment,locks)
   self.assertEqual(json.loads(reservation.read_text())['cpus'],[4,5,6,7])
if __name__=='__main__':unittest.main()
