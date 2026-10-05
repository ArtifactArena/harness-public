import json,tempfile,time,unittest
from pathlib import Path
from coordinator import Tournament
class QueueTest(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
  roster=[dict(id=i,title=i,model=i,repeat=1,revision=1,experiment=i) for i in ['a','b']]
  (self.root/'manifest.json').write_text(json.dumps(dict(roster=roster,seeds=[7101,7102,7103],seconds=300,total_matches=6,reused_matches=[],elo_method='test')))
  for i in ['a','b']:
   p=self.root/'selected'/i;p.mkdir(parents=True);(p/'recipe.json').write_text(json.dumps(dict(xml='<mujoco/>',code='',actuators=[])))
  self.t=Tournament(self.root);self.worker=dict(worker='host-123-0',host='host')
 def tearDown(self):self.tmp.cleanup()
 def test_durability_validation_and_duplicate(self):
  self.assertIsNone(self.t.claim(self.worker,4)['job'])
  j=self.t.claim(self.worker,1)['job'];self.assertEqual(j['id'],self.t.claim(self.worker,1)['job']['id'])
  resumed=Tournament(self.root);self.assertEqual(resumed.jobs[j['id']]['status'],'running')
  r={k:j[k] for k in ['id','kind','candidate_id','opponent_id','seed']};r.update(candidate_side=j['side'],outcome='win')
  with self.assertRaises(ValueError):self.t.result({'result':dict(r,seed=0)})
  self.t.result({'result':r});self.assertTrue(self.t.result({'result':r})['duplicate'])
  report=Tournament(self.root).status;self.assertEqual(report['completed_matches'],1);self.assertGreater(report['round_robin'][0]['elo'],1000)
  self.assertEqual(sum(x['completed'] for x in report['round_robin']),2)
 def test_omit_model_preserves_other_results(self):
  from omit_model import omit
  manifest=json.loads((self.root/'manifest.json').read_text());manifest['roster'].append(dict(id='c',title='c',model='c',repeat=1,revision=1,experiment='c'));manifest['total_matches']=18
  (self.root/'manifest.json').write_text(json.dumps(manifest));p=self.root/'selected/c';p.mkdir();(p/'recipe.json').write_text(json.dumps(dict(xml='<mujoco/>',code='',actuators=[])))
  t=Tournament(self.root)
  def result(a,b):
   j=next(j for j in t.jobs.values() if j['candidate_id']==a and j['opponent_id']==b)
   return {k:j[k] for k in ['id','kind','candidate_id','opponent_id','seed']}|dict(candidate_side=j['side'],outcome='win')
  removed=result('a','b');retained=result('b','c');t.result({'result':removed});t.result({'result':retained});t.report()
  receipt=omit(self.root,'a');self.assertEqual(receipt['retained_runs'],2)
  resumed=Tournament(self.root);self.assertEqual(resumed.status['total_matches'],6);self.assertEqual(resumed.status['completed_matches'],1)
  self.assertTrue(resumed.result({'result':removed})['excluded']);self.assertEqual(resumed.report()['completed_matches'],1)
  self.assertEqual(resumed.status['excluded_bot_ids'],['a']);self.assertTrue((self.root/'matches'/removed['id']/'result.json').exists())
 def test_lease_expiration_and_stale_error(self):
  j=self.t.claim(self.worker,1)['job'];j['heartbeat']=time.time()-301;self.t.report();self.assertEqual(j['status'],'pending')
  self.t.claim(dict(worker='host-456-0',host='host'),1)
  self.t.error(dict(self.worker,job=j['id'],error='late'));self.assertEqual(j['status'],'running')
  j.update(attempts=3,heartbeat=time.time()-301);self.t.report();self.assertEqual(j['status'],'failed')
if __name__=='__main__':unittest.main()
