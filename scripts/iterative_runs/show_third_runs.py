"""Expose the five third runs in the existing iterative dashboard filters."""
import argparse
from pathlib import Path
import shutil


def replace(path, changes):
    source = path.read_text()
    updated = source
    for before, after in changes:
        if after in updated:
            continue
        if updated.count(before) != 1:
            raise RuntimeError(f'Unexpected dashboard source: {path}: {before}')
        updated = updated.replace(before, after)
    backup = path.with_name(path.name + '.before-third-runs')
    if not backup.exists():
        shutil.copy2(path, backup)
    path.write_text(updated)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('dashboard', type=Path)
    d = p.parse_args().dashboard
    replace(d / 'app.js', [
        ("modelColors['r1_'+id]=color;modelColors['r2_'+id]=color",
         "for(const repeat of [1,2,3])modelColors['r'+repeat+'_'+id]=color"),
        ("e.repeat===1||e.repeat===2?' · '+e.repeat",
         "Number.isInteger(e.repeat)?' · '+e.repeat"),
    ])
    replace(d / 'index.html', [
        ('Current batch · all 48 runs', 'Current batch · all 53 runs'),
        ('<option value="2">Repeat 2 · 23 fresh runs</option>',
         '<option value="2">Repeat 2 · 23 fresh runs</option><option value="3">Repeat 3 · 5 fresh runs</option>'),
        ('23 models × 2 fresh runs · 10 iterations each · 2 prior runs registered to continue.',
         '23 models × 2 fresh runs, plus 5 third runs · 10 iterations each · 2 prior runs registered to continue.'),
        ('/app.js?v=stopped-details', '/app.js?v=third-runs'),
    ])


if __name__ == '__main__':
    main()
