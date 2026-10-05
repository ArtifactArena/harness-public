import importlib.util,json,tempfile,time,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('live_matches',Path(__file__).with_name('live_matches.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class LiveMatchesTest(unittest.TestCase):
 def test_telemetry_replaces_only_its_own_attempt_and_stale_eta_is_hidden(self):
  with tempfile.TemporaryDirectory() as tmp:
   m.HERE=Path(tmp)/'iterative-high-20260924/dashboard';m.HERE.mkdir(parents=True)
   m.DATA=m.HERE/'live-data';m.DATA.mkdir();now=time.time()
   row=dict(id='selection__a__b__7101_red',host='gpu-node-8',pool='iterative-cpu-parallel4-20260924',started_at=now-100,tracking='legacy-inferred',sim_seconds=None)
   (m.DATA/'host.json').write_text(json.dumps(dict(host='gpu-node-8',updated_at=now,rows=[row,{**row,'pool':'old-pool'}])))
   progress=m.HERE.parents[1]/'sdf-multicpu-20260924/rescue/progress';progress.mkdir(parents=True)
   d=dict(job=row['id'],host='gpu-node-8',pid=123,updated_at=now,started_at=now-100,sim_seconds=50,sampled_at=now,limit_seconds=300)
   path=progress/(row['id']+'.json');path.write_text(json.dumps(d));s=m.state();self.assertEqual(len(s['matches']),2);self.assertEqual(s['measured'],1)
   live=next(r for r in s['matches'] if r['tracking']=='measured');self.assertEqual(live['eta_seconds'],500);self.assertAlmostEqual(live['progress'],1/6)
   d['sampled_at']=now-130;path.write_text(json.dumps(d));live=next(r for r in m.state()['matches'] if r['tracking']=='measured');self.assertIsNone(live['eta_seconds'])
   self.assertIsNone(next(r for r in s['matches'] if r['tracking']=='legacy-inferred')['progress'])
 def test_lease_requires_fresh_inventory_and_correct_pool_pid(self):
  with tempfile.TemporaryDirectory() as tmp:
   m.HERE=Path(tmp)/'iterative-high-20260924/dashboard';m.HERE.mkdir(parents=True)
   m.DATA=m.HERE/'live-data';m.DATA.mkdir();now=time.time();job='top1__a__b__7101_red'
   row=dict(id=job,host='gpu-node-8',pool='old-pool',started_at=now-200,tracking='legacy-inferred')
   inventory=dict(host='gpu-node-8',updated_at=now,rows=[row,{**row,'pool':'new-pool'}],pools=[dict(root='/old-pool',pids=[10]),dict(root='/new-pool',pids=[20])])
   target=m.DATA/'host.json';target.write_text(json.dumps(inventory))
   leases=m.HERE.parent/'tournament/live_leases';leases.mkdir(parents=True)
   # Two leases for one host/job must not overwrite each other; only PID 20 is live.
   for pid in [20,99]:
    (leases/f'{pid}.json').write_text(json.dumps(dict(worker=f'gpu-node-8-{pid}-0',job=job,updated_at=now)))
   result=m.HERE.parent/'tournament/matches'/job/'result.json';result.parent.mkdir(parents=True);result.write_text('{}')
   state=m.state();self.assertEqual(state['confirmed'],1);self.assertEqual(state['unverified'],1)
   live=next(r for r in state['matches'] if r['confirmed']);self.assertEqual(live['pool'],'new-pool');self.assertEqual(live['pid'],20);self.assertTrue(live['accepted_result'])
   inventory['updated_at']=now-121;target.write_text(json.dumps(inventory));self.assertEqual(m.state()['confirmed'],0)
 def test_new_source_telemetry_and_completed_job_removal(self):
  with tempfile.TemporaryDirectory() as tmp:
   m.HERE=Path(tmp)/'iterative-high-20260924/dashboard';m.HERE.mkdir(parents=True)
   m.DATA=m.HERE/'live-data';m.DATA.mkdir();now=time.time();job='selection__r1_a_01__r1_a_02__7101_red'
   root=m.HERE.parents[1]/'iterative-23x2-20260924/tournament';(root/'progress').mkdir(parents=True)
   d=dict(job=job,host='gpu-node-5',pid=42,updated_at=now,started_at=now-100,sim_seconds=60,sampled_at=now,limit_seconds=300)
   (root/'progress/worker.json').write_text(json.dumps(d));state=m.state();self.assertEqual(state['measured'],1);self.assertEqual(state['matches'][0]['source'],'iterative-23x2-20260924');self.assertAlmostEqual(state['matches'][0]['progress'],.2)
   result=root/'matches'/job/'result.json';result.parent.mkdir(parents=True);result.write_text('{}');self.assertEqual(m.state()['measured'],0)
if __name__=='__main__':unittest.main()
