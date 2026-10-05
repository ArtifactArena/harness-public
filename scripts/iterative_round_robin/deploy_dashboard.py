"""Add the frozen all-run tournament to the existing live dashboard idempotently."""
import argparse,shutil,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('dashboard',type=Path);a=p.parse_args();root=a.dashboard
backup=root/'backups'/('length10-'+time.strftime('%Y%m%dT%H%M%SZ',time.gmtime()));backup.mkdir(parents=True)
for name in ['index.html','app.js','server.py','live_matches.py']:shutil.copy2(root/name,backup/name)
def change(name,fn):
 p=root/name;old=p.read_text();new=fn(old);tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(new);tmp.replace(p)
change('index.html',lambda s:s if 'id="length10-leaderboard"' in s else s.replace('<section id="iterative-leaderboard"','<section id="length10-leaderboard" class="iterative-leaderboard" aria-labelledby="length10-title"></section><section id="iterative-leaderboard"').replace('<a class="small" href="#iterative-leaderboard">','<a class="small" href="#length10-leaderboard">All-run tournament ↓</a> · <a class="small" href="#iterative-leaderboard">').replace('/app.js?v=tool-repeat3-20260925','/app.js?v=length10-round-robin-20260925'))
change('server.py',lambda s:s if 'iterative_length10=' in s else s.replace('iterative_leaderboard=read(',"iterative_length10=read(BASE.parent/'iterative-length10-round-robin-20260925/tournament/status.json',{}),\n                iterative_leaderboard=read("))
change('app.js',lambda s:s if 'function length10Leaderboard()' in s else s.replace('iterativeLeaderboard();', 'iterativeLeaderboard();length10Leaderboard();')+'\n'+Path(__file__).with_name('dashboard.js').read_text())
change('live_matches.py',lambda s:s if "'iterative-length10-round-robin-20260925'" in s else s.replace("SOURCES=[","SOURCES=['iterative-length10-round-robin-20260925',"))
print('Backup:',backup)
