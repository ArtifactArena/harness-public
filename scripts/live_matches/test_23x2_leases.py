import gzip,importlib.util,json,tempfile,threading,time,unittest,urllib.request
from pathlib import Path
from http.server import ThreadingHTTPServer
class LeasesTest(unittest.TestCase):
 def test_restart_recovery_results_and_new_claim_visibility(self):
  with tempfile.TemporaryDirectory() as tmp:
   base=Path(tmp);(base/'registry.json').write_text('[]');root=base/'tournament';root.mkdir()
   fleet=Path(__file__).parents[1]/'iterative_cpu/progress_fleet'
   ps=importlib.util.spec_from_file_location('patcher',fleet/'patch_coordinator.py');patcher=importlib.util.module_from_spec(ps);ps.loader.exec_module(patcher)
   (root/'progress_protocol.py').write_text((fleet/'progress_protocol.py').read_text())
   path=root/'coordinator.py';path.write_text(patcher.patch(Path(__file__).with_name('23x2-coordinator.py').read_text()))
   spec=importlib.util.spec_from_file_location('test_coordinator',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);m.TOKEN='test';m.START=time.time()-181
   server=ThreadingHTTPServer(('127.0.0.1',0),m.Handler);thread=threading.Thread(target=server.serve_forever);thread.start()
   def post(route,data,compressed=False,capability=True):
    raw=json.dumps(data).encode();req=urllib.request.Request(f'http://127.0.0.1:{server.server_port}'+route,data=gzip.compress(raw) if compressed else raw,headers={'Authorization':'Bearer test',**({'X-Match-Progress':'simulation-v1','X-Match-CPU-Budget':'1'} if capability else {})})
    with urllib.request.urlopen(req) as r:return json.load(r)
   try:
    (root/'require_progress').touch()
    self.assertTrue(post('/claim',{'worker':'legacy-999-0'},capability=False)['finished'])
    worker='lab-123-0';ident='selection__r1_a_01__r1_a_02__7101_red'
    self.assertIsNone(post('/claim',{'worker':worker})['job'])
    post('/heartbeat',{'worker':worker,'job':ident,'progress':dict(job=ident,host='lab',pid=123,sim_seconds=12.5)})
    self.assertEqual(json.loads((root/'progress'/f'{worker}.json').read_text())['sim_seconds'],12.5)
    a=dict(id='r1_a_01',recipe={},eligible=True);b=dict(id='r1_a_02',recipe={},eligible=True)
    m.add_job(a,b,'selection',7101,'red');self.assertEqual(m.JOBS[ident]['status'],'running')
    self.assertEqual(m.JOBS[ident]['worker'],worker)
    # Uploads completing during the initial scan are durable, including retries.
    ident2='selection__r1_a_01__r1_a_02__7102_red';result=dict(id=ident2,kind='selection',outcome='win')
    self.assertTrue(post('/result',{'result':result},True)['ok'])
    self.assertTrue(post('/result',{'result':{**result,'outcome':'loss'}},True)['duplicate'])
    m.add_job(a,b,'selection',7102,'red');self.assertEqual(m.JOBS[ident2]['status'],'completed');self.assertEqual(m.RESULTS[ident2]['outcome'],'win')
    m.add_job(a,b,'selection',7103,'red');m.INITIAL_SCAN_DONE=False
    m.START=time.time();self.assertIsNone(post('/claim',{'worker':'lab-124-1'})['job'])
    m.START=time.time()-181
    reply=post('/claim',{'worker':'lab-124-1'});lease=json.loads((root/'live_leases/lab-124-1.json').read_text());self.assertEqual(lease['job'],reply['job']['id'])
    post('/result',{'result':dict(id=lease['job'],kind='selection',outcome='draw')},True)
    self.assertFalse((root/'live_leases/lab-124-1.json').exists())
   finally:server.shutdown();server.server_close();thread.join()
if __name__=='__main__':unittest.main()
