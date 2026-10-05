import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import add_retry_warning as warning


class WarningTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.run = Path(self.temp.name)
        self.current = self.run / 'revision_02'
        self.current.mkdir()
        (self.current / 'prompt.txt').write_text('original prompt')
        warning.save(self.run / warning.MARKER, dict(revision='revision_02', session='test'))
        warning.save(self.run / 'config.json', dict(model='MiniMaxAI/MiniMax-M3', max_output_tokens=98304))
        warning.save(self.run / 'status.json', dict(status='running'))
        (self.run / 'run.py').write_text('def render_prompt(revision):\n    template = "base"\n    return template\n')
        (self.run / 'iterative_prompt_template.md').write_text('base template')

    def test_queued_retry_preserves_original_and_changes_only_target(self):
        with patch.object(warning, 'launch') as launch:
            warning.prepare(self.run)
        launch.assert_called_once()
        self.assertEqual((self.current / 'before_retry_warning/prompt.txt').read_text(), 'original prompt')
        self.assertEqual((self.current / 'prompt.txt').read_text().count('## Retry notice'), 1)
        self.assertFalse((self.run / 'revision_01/retry_notice.txt').exists())

    def test_accepted_request_is_not_overwritten(self):
        warning.save(self.current / 'response_pending.json', {})
        with self.assertRaisesRegex(RuntimeError, 'already started'):
            warning.prepare(self.run)
        self.assertEqual((self.current / 'prompt.txt').read_text(), 'original prompt')

    def test_active_success_warns_next_iteration_and_restores_template(self):
        def finish(_):
            warning.save(self.current / 'response.json', dict(status='completed'))
            next_prompt = self.run / 'revision_03/prompt.txt'
            next_prompt.write_text((self.run / 'iterative_prompt_template.md').read_text())
        with patch.object(warning.time, 'sleep', side_effect=finish), patch.object(warning, 'launch') as launch:
            warning.watch_active(self.run)
        launch.assert_not_called()
        self.assertEqual((self.run / 'iterative_prompt_template.md').read_text(), 'base template')
        self.assertIn('## Retry notice', (self.run / 'revision_03/prompt.txt').read_text())
        self.assertEqual((self.current / 'prompt.txt').read_text(), 'original prompt')

    def test_active_truncation_gets_one_warned_retry(self):
        def finish(_):
            warning.save(self.current / 'response.json', dict(status='incomplete', stop_reason='length'))
            warning.save(self.run / 'status.json', dict(status='failed'))
        with patch.object(warning.time, 'sleep', side_effect=finish), patch.object(warning, 'launch') as launch:
            warning.watch_active(self.run)
        launch.assert_called_once()
        self.assertTrue((self.current / 'failed_attempts/unwarned-retry/response.json').exists())
        self.assertFalse((self.run / 'revision_03/retry_notice.txt').exists())
        self.assertIn('## Retry notice', (self.current / 'prompt.txt').read_text())
        self.assertEqual((self.run / 'iterative_prompt_template.md').read_text(), 'base template')

    def test_opus5_excluded(self):
        warning.save(self.run / 'config.json', dict(model='claude-opus-5'))
        with self.assertRaisesRegex(RuntimeError, 'excluded'):
            warning.prepare(self.run)


if __name__ == '__main__':
    unittest.main()
