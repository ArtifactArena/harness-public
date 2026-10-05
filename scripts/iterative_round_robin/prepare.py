"""Freeze every completed length-10 iterative winner; audit selections and reuse exact matches."""
import argparse, hashlib, itertools, json, shutil, sys
from pathlib import Path

def read(p): return json.loads(p.read_text())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,d):
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(d,indent=2)+'\n')
def prepare(base,root):
 sys.path.insert(0,str(base/'iterative-leaderboard-20260924/tournament'))
 import source_coordinator as source
 registry={k:{'id':k,'path':str(base/'iterative-high-20260924/runs'/k)} for k in ['grok','gemini','astra','opus']}
 for batch in ['iterative-roster-20260924','iterative-23x2-20260924']:
  for r in read(base/batch/'registry.json'):registry[r['id']]={**r,'path':r.get('path',str(base/batch/'runs'/r['id']))}
 roster=[];recipes={}
 for key,r in registry.items():
  run=Path(r['path']);config=read(run/'config.json');status=read(run/'status.json')
  if config['model'] in ['MiniMaxAI/MiniMax-M3','claude-opus-5','grok-4.7']:continue
  assert config['revision_attempts']==10 and status['completed_revisions']==10 and status['status']=='completed',(key,status)
  selection=read(run/'selected_bot/selection.json');assert selection['matches']==270
  standings=selection['standings'];assert len(standings)==10
  counts={x['id']:{'wins':0,'losses':0,'draws':0} for x in standings}
  matches=list((run.parents[1]/'tournament/matches').glob('selection__'+key+'_*'+'/result.json'))
  assert len(matches)==270,(key,len(matches))
  seen=set()
  for p in matches:
   result=read(p);a=result['candidate_id'];b=result['opponent_id'];assert a in counts and b in counts and a!=b
   scheduled_seed=int(p.parent.name.rsplit('__',1)[1].split('_')[0]);identity=(a,b,scheduled_seed,result['candidate_side']);assert identity not in seen;seen.add(identity)
   assert scheduled_seed in [7101,7102,7103] and result['candidate_side'] in ['red','blue']
   if result['seed']!=scheduled_seed:assert result.get('replacement') or result.get('race') or result.get('replacement_seed'),result
   outcome=result['outcome'];counts[a][{'win':'wins','loss':'losses','draw':'draws'}[outcome]]+=1
   counts[b][{'win':'losses','loss':'wins','draw':'draws'}[outcome]]+=1
  for s in standings:
   assert all(s[k]==v for k,v in counts[s['id']].items()),(key,s,counts[s['id']])
   assert s['points']==s['wins']+.5*s['draws'] and sum(counts[s['id']].values())==54
  winner=sorted(standings,key=lambda s:(not s['eligible'],-s['points'],-s['wins'],s['revision']))[0]
  assert winner['eligible'] and winner['id']==selection['winner']
  ident=winner['id'];src=run/f"revision_{winner['revision']:02d}";dest=root/'tournament/selected'/ident
  item=dict(id=ident,experiment=key,title=config.get('experiment_title',r.get('title',key)),model=config['model'],repeat=config.get('repeat',r.get('repeat','historical')),revision=winner['revision'],source=str(src),source_robot_sha256=sha(src/'robot.xml'),source_controller_sha256=sha(src/'controller.py'),selection_matches=270,selection=selection)
  for name in ['robot.xml','controller.py']:assert sha(src/name)==sha(run/'selected_bot'/name)
  bench=read(run.parents[1]/'tournament/status.json');row=next((x for x in bench.get('rows',[]) if x['id']==ident),None)
  if row:assert all(item[k]==row[k] for k in ['source_robot_sha256','source_controller_sha256'])
  recipe,error=source.prepare(src,dest);assert not error,(ident,error)
  for name in ['robot.xml','controller.py']:shutil.copy2(src/name,dest/name)
  save(dest/'recipe.json',recipe);save(dest/'selection.json',item);roster.append(item);recipes[ident]=recipe
  print('Audited and prepared',ident,flush=True)
 old=base/'iterative-leaderboard-20260924/tournament';compatible=set()
 for item in roster:
  p=old/'selected'/item['id']
  if (p/'selection.json').exists() and all(read(p/'selection.json').get(k)==item[k] for k in ['source_robot_sha256','source_controller_sha256']) and read(p/'recipe.json')==recipes[item['id']]:compatible.add(item['id'])
 reused=[]
 for a,b in itertools.combinations(sorted(recipes),2):
  if a not in compatible or b not in compatible:continue
  for seed,side in itertools.product([7101,7102,7103],['red','blue']):
   ident=f'iterative_top1__{a}__{b}__{seed}_{side}';p=old/'matches'/ident/'result.json'
   if not p.exists():continue
   result=read(p)
   assert result['candidate_id']==a and result['opponent_id']==b and result['seed']==seed and result['candidate_side']==side and result['kind']=='iterative_top1'
   assert result['outcome'] in ['win','loss','draw']
   result['reused_from']=str(p);save(root/'tournament/matches'/ident/'result.json',result);reused.append(ident)
 manifest=dict(roster=roster,seeds=[7101,7102,7103],seconds=300,total_matches=len(roster)*(len(roster)-1)*3,reused_matches=reused,selection_audit='All 270 result identities and standings recomputed for every run; source hashes and selected copies verified',elo_method='Bradley-Terry MAP; independent N(1000,800²) priors; draws count 0.5')
 save(root/'tournament/manifest.json',manifest)
 print('FROZEN',len(roster),'bots',manifest['total_matches'],'matches',len(reused),'reused',flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--base',type=Path,required=True);p.add_argument('--root',type=Path,required=True);a=p.parse_args();prepare(a.base,a.root)
