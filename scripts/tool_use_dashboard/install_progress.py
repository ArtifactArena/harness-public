"""Add tool-use per-run progress without changing experiment execution."""
import argparse,datetime,shutil
from pathlib import Path

def install(root):
 source=Path(__file__).resolve().parent
 app=(root/'app.js').read_text();html=(root/'index.html').read_text();css=(root/'paper.css').read_text()
 marker='function toolExperimentProgress(runs){'
 if marker not in app:
  old='${toolOverall(runs)}<p class="muted">';assert app.count(old)==1
  app=app.replace(old,'${toolOverall(runs)}${toolExperimentProgress(runs)}<p class="muted">')
  old="runs.map(r=>[r.id,r.title,r.status,r.completed_turns,r.error,r.error_detail])";assert app.count(old)==1
  app=app.replace(old,"runs.map(r=>[r.id,r.title,r.status,r.stage,r.turn,r.completed_turns,r.total_turns,r.error,r.error_detail,r.eta_seconds,r.current_api_seconds,r.cost_usd,r.tool_calls,r.bots_produced])")
  old=" $('#tool-use-model').onchange=event=>";assert app.count(old)==1
  app=app.replace(old," section.querySelectorAll('[data-tool-progress-run]').forEach(button=>button.onclick=()=>{selectedToolRun=button.dataset.toolProgressRun;toolUseSignature=null;toolUseSection();toolUseCards()});\n"+old)
  app+='\n'+(source/'progress.js').read_text()
 if '/* Per-run progress for the tool-use experiment. */' not in css:css+='\n'+(source/'progress.css').read_text()
 import re
 html=re.sub(r'(/app\.js\?v=)[^"\s]+',r'\g<1>tool-experiment-progress-20260925',html)
 html=re.sub(r'(/paper\.css\?v=)[^"\s]+',r'\g<1>tool-experiment-progress-20260925',html)
 stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ');backup=root/'backups'/('tool-progress-'+stamp);backup.mkdir(parents=True)
 for name,text in [('app.js',app),('index.html',html),('paper.css',css)]:
  shutil.copy2(root/name,backup/name);tmp=root/(name+'.tmp');tmp.write_text(text);tmp.replace(root/name)
 print('Updated dashboard; backup:',backup)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('dashboard',type=Path);a=p.parse_args();install(a.dashboard)
