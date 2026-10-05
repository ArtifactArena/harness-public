import importlib.util
from pathlib import Path
import sys
import types
import tempfile
import json
import unittest
from unittest.mock import patch

with patch.dict(sys.modules, {'worker': types.ModuleType('worker'), 'httpx': types.ModuleType('httpx')}):
    spec=importlib.util.spec_from_file_location('progress_worker',Path(__file__).with_name('progress_worker.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class Child:
    def __init__(self,codes):self.codes=iter(codes);self.terminated=False
    def poll(self):return next(self.codes,75)
    def terminate(self):self.terminated=True

class SupervisionTest(unittest.TestCase):
    @unittest.skipUnless(Path('/proc/self/stat').exists(),'Linux process-state check')
    def test_drain_requires_acknowledgement_and_child_exit(self):
        spec=importlib.util.spec_from_file_location('drain_slots',Path(__file__).with_name('drain_slots.py'))
        drain=importlib.util.module_from_spec(spec);spec.loader.exec_module(drain)
        with tempfile.TemporaryDirectory() as folder:
            ack=Path(folder)/'ack'
            self.assertFalse(drain.acknowledged_exit(ack))
            child=module.subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'])
            try:
                ack.write_text(json.dumps({'pid':child.pid}))
                self.assertFalse(drain.acknowledged_exit(ack))
            finally:child.terminate();child.wait()
            self.assertTrue(drain.acknowledged_exit(ack))

    def test_retirement_acknowledges_only_requested_slot(self):
        with tempfile.TemporaryDirectory() as folder:
            script=Path(folder)/'progress_worker.py'
            with patch.object(module,'__file__',str(script)):
                self.assertFalse(module.retiring(2))
                (script.parent/'retire-slots.json').write_text('[2]')
                self.assertFalse(module.retiring(1))
                self.assertTrue(module.retiring(2))
                ack=json.loads((script.parent/'retired-slots/2').read_text())
                self.assertEqual(ack['pid'],module.os.getpid())
                self.assertEqual([p.name for p in (script.parent/'retired-slots').iterdir()],['2'])

    def test_crashed_match_does_not_terminate_running_sibling(self):
        children=[Child([-9]),Child([None,75]),Child([0]),Child([75])]
        with patch.object(module.subprocess,'Popen',side_effect=children) as spawn,patch.object(module.time,'sleep'):
            self.assertEqual(module.supervise(2,'token-path'),0)
        self.assertEqual(spawn.call_count,4)
        self.assertFalse(any(p.terminated for p in children))
        self.assertEqual([c.args[0][-3] for c in spawn.call_args_list],['0','1','0','0'])

    def test_repeated_crashes_are_bounded(self):
        with patch.object(module.subprocess,'Popen',side_effect=[Child([-9]) for _ in range(3)]) as spawn,patch.object(module.time,'sleep'):
            self.assertEqual(module.supervise(1,'token-path'),1)
        self.assertEqual(spawn.call_count,3)

if __name__=='__main__':unittest.main()
