import gzip
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from omit_models import excluded, patch_coordinator


class OmissionTests(unittest.TestCase):
    def test_exact_model_identity_preserves_opus_48(self):
        self.assertTrue(excluded({'model':'MiniMaxAI/MiniMax-M3'}))
        self.assertTrue(excluded({'model':'claude-opus-5'}))
        self.assertFalse(excluded({'model':'claude-opus-4-8'}))
        self.assertFalse(excluded({'model':'claude-sonnet-5'}))

    def test_late_upload_is_ignored_and_other_results_are_retained(self):
        source=Path(__file__).parents[1]/'live_matches/23x2-coordinator.py'
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'registry.json').write_text('[]')
            (root/'excluded_runs.json').write_text('[{"id":"r1_minimax3"},{"id":"r1_opus5"}]')
            tournament=root/'tournament';tournament.mkdir()
            path=tournament/'coordinator.py';path.write_text(patch_coordinator(source.read_text(),'iterative'))
            spec=importlib.util.spec_from_file_location('omission_coordinator',path)
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);module.TOKEN='test'
            server=ThreadingHTTPServer(('127.0.0.1',0),module.Handler)
            thread=threading.Thread(target=server.serve_forever);thread.start()
            try:
                for run,omitted in [('r1_minimax3',True),('r1_opus5',True),('r1_opus',False)]:
                    ident=f'selection__{run}_01__{run}_02__7101_red'
                    result=dict(id=ident,kind='selection',candidate_id=run+'_01',opponent_id=run+'_02',outcome='win')
                    request=urllib.request.Request(f'http://127.0.0.1:{server.server_port}/result',data=gzip.compress(json.dumps({'result':result}).encode()),headers={'Authorization':'Bearer test'})
                    with urllib.request.urlopen(request) as response:reply=json.load(response)
                    self.assertEqual(reply.get('excluded',False),omitted)
                    self.assertEqual(ident in module.RESULTS,not omitted)
                    self.assertEqual((tournament/'matches'/ident/'result.json').exists(),not omitted)
            finally:server.shutdown();server.server_close();thread.join()


if __name__=='__main__':unittest.main()
