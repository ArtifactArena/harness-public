import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch


def module(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + '.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


inventory = module('tool_use_inventory')
telemetry = module('tool_seed_progress')
live = module('live_matches')


class ToolUseTests(unittest.TestCase):
    def test_seed_callback_preserves_existing_listener_and_emits_no_scores(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'MH_TOOL_PROGRESS_DIR': tmp}):
            events = []
            callback = telemetry.live_seed_callback(events.append, seed=7, match_time=30,
                                                     max_steps=2000, match_dir='/workspace/match')
            event = {'type': 'progress', 'step': 1000, 'max_steps': 2000, 'winner': 'red'}
            callback(event)
            row = json.loads(next(Path(tmp).glob('live-*.json')).read_text())
            self.assertEqual(row['sim_seconds'], 15)
            self.assertNotIn('winner', row)
            self.assertEqual(events, [event])
            callback({'type': 'done', 'step': 1100, 'max_steps': 2000})
            self.assertTrue(json.loads(next(Path(tmp).glob('live-*.json')).read_text())['complete'])

    def test_legacy_batch_and_live_namespace_identity(self):
        now = time.time()
        spec = {'id': 'oe_r1_model'}
        marker = {'tool': 'run_match', 'path': '_tool_progress/abc', 'started_at': now-60,
                  'args': {'red': 'draft', 'blue': 'saved', 'n_seeds': 3}}
        args = (spec, marker, 100, 'host_a')
        row = inventory.tool_rows(*args, [], {}, now)[0]
        self.assertEqual(row['tracking'], 'process-confirmed')
        self.assertIsNone(row['sim_seconds'])
        seed = dict(pid=8, seed=1, started_at=now-10, updated_at=now,
                    sampled_at=now, sim_seconds=15, limit_seconds=30, complete=False)
        rows = inventory.tool_rows(*args, [('live-a', seed)], {8: 999}, now)
        self.assertEqual(rows[0]['pid'], 999)
        self.assertEqual(rows[0]['tracking'], 'measured')
        self.assertEqual(inventory.tool_rows(*args, [('live-a', seed)], {}, now), [])
        self.assertEqual(inventory.tool_rows(*args, [('live-a', dict(seed, complete=True))], {8: 999}, now), [])
        self.assertEqual(inventory.tool_rows(*args, [('live-a', dict(seed, updated_at=now-121))], {8: 999}, now), [])
        self.assertEqual(inventory.tool_rows(spec, dict(marker, tool='read_file'), 100, 'host_a', [], {}, now), [])

    def test_selection_and_tool_calls_visible_but_stale_inventory_unconfirmed(self):
        with tempfile.TemporaryDirectory() as tmp:
            live.HERE = Path(tmp)/'iterative-high-20260924/dashboard'
            live.DATA = live.HERE/'live-data'
            live.DATA.mkdir(parents=True)
            now = time.time()
            job = 'selection__oe_r1_a_001__oe_r1_a_002__0_red'
            rows = [dict(id=job, pool='design-lab-23x2-20260924', started_at=now-100, tracking='legacy-inferred'),
                    dict(id='tool__a', pool='Tool use', started_at=now-100, tracking='process-confirmed')]
            data = dict(host='host_a', updated_at=now, rows=rows,
                        pools=[dict(root='/design-lab-23x2-20260924', pids=[123])])
            path = live.DATA/'host_a.json'
            path.write_text(json.dumps(data))
            leases = live.HERE.parents[1]/'design-lab-23x2-20260924/tournament/live_leases'
            leases.mkdir(parents=True)
            (leases/'worker.json').write_text(json.dumps(dict(worker='host_a-123-0', job=job, updated_at=now)))
            state = live.state()
            self.assertEqual(state['confirmed'], 2)
            self.assertEqual(state['matches'][0]['category'], 'tool_use')
            data['updated_at'] = now-121
            path.write_text(json.dumps(data))
            self.assertEqual(live.state()['confirmed'], 0)


if __name__ == '__main__':
    unittest.main()
