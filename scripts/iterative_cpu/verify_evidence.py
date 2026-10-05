"""Check saved bitwise parity evidence without rerunning expensive matches."""
from pathlib import Path
import json

root = Path(__file__).resolve().parent
for row in json.loads((root / 'comparison.json').read_text()):
    suffix = 'complete' if row['complete_match'] else '500'
    reports = [json.loads((root / 'evidence' /
               f"{row['pair']}-{mode}-{suffix}" / 'report.json').read_text())
               for mode in ('reference', 'native')]
    reference, native = reports
    assert reference['events'] == native['events'], row['pair']
    assert len(reference['events']) == row['events']
    assert reference['steps'] == native['steps'] == row['steps']
    assert reference['finished'] == native['finished'] == row['complete_match']
    assert reference['affinity'] == native['affinity']
    assert len(reference['affinity']) == 1
    assert reference['gpus_used'] == native['gpus_used'] == 0
    assert reference['wall'] == row['reference_seconds']
    assert native['wall'] == row['native_seconds']
    print(f"{row['pair']}: {row['events']} exact events, {row['speedup']:.2f}x")

for left, right in [
    ('grok46-candidate-final500', 'grok46-candidate-top32-final500'),
    ('fable51-opus-reference-complete', 'fable51-opus-top32-complete'),
]:
    a, b = [json.loads((root / 'evidence' / name / 'report.json').read_text())
            for name in (left, right)]
    assert a['events'] == b['events']
    assert a['steps'] == b['steps'] and a['finished'] == b['finished']
    print(f"{right}: {len(a['events'])} exact events")
