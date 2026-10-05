"""Resume the two billing-rejected Fable 5.1 tool-use runs and prepare repeat 3."""
import argparse,datetime,fcntl,hashlib,importlib.util,json,os,re,shutil,subprocess,sys,time
from pathlib import Path

def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,d):
 tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(d,indent=2)+'\n');tmp.replace(p)
def launch(record):
 root=Path(record['path'])
 assert subprocess.run(['tmux','has-session','-t','='+record['session']],capture_output=True).returncode!=0
 subprocess.run(['tmux','new-session','-d','-s',record['session'],'-c',str(root),'bash launch.sh'],check=True)
 return dict(id=record['id'],session=record['session'],at=time.time(),host=os.uname().nodename)
def resume(base,record,stamp):
 root=Path(record['path']);status=read(root/'status.json');assert status['status']=='failed' and status['completed_turns']==1 and status['turn']==2
 folder=root/'turns/turn_02';error=read(folder/'request_error.json');assert error['status']==400 and 'credit balance is too low' in error['body']
 assert not (folder/'response.json').exists() and not (folder/'checkpoint.json').exists() and not list(folder.glob('tool_*')) and not (folder/'stream.jsonl').exists()
 assert not (root/'EXCLUDED.json').exists()
 assert subprocess.run(['tmux','has-session','-t','='+record['session']],capture_output=True).returncode!=0
 with (root/'run.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  preserved=[root/'config.json',folder/'prompt.txt',root/'turns/turn_01/checkpoint.json',root/'journal.json']+[root/'workspace'/name for name in ['robot.xml','controller.py','notes.md']]
  before={str(p.relative_to(root)):sha(p) for p in preserved}
  archive=folder/'attempts'/('credit-retry-'+stamp);archive.mkdir(parents=True)
  shutil.copy2(root/'status.json',archive/'status.json')
  for name in ['request_settings.json','response_pending.json','request_error.json']:
   p=folder/name
   if p.exists():p.rename(archive/name)
  audit=dict(id=record['id'],at=stamp,resume_turn=2,reason='User requested continuation after confirmed credit rejection',preserved_sha256=before,previous_error=error)
  save(archive/'audit.json',audit)
  assert all(sha(root/p)==v for p,v in before.items())
  save(root/'status.json',{**status,'status':'queued','stage':'credit retry requested','error':None,'error_detail':None,'updated_at':datetime.datetime.now(datetime.timezone.utc).isoformat()})
 receipt=launch(record);save(root/('resume-'+stamp+'.json'),receipt);return receipt

def prepare_third(base,template,stamp):
 ident='oe_r3_fable51';root=base/ident;assert not root.exists(), 'Repeat 3 already exists; inspect it instead of duplicating'
 source=base/'source';root.mkdir();config=read(Path(template['path'])/'config.json');config.update(repeat=3,experiment_title='Claude Fable 5.1 · High · repeat 3 · tool use',run_id=base.name+'-'+ident)
 save(root/'config.json',config);save(root/'status.json',dict(model=config['model'],status='prepared',stage='preflight',total_turns=10,completed_turns=0,cost_usd=0,bots_produced=0))
 for name in ['run.py','provider_adapter.py','slots.py','monitoring.py']:shutil.copy2(Path(template['path'])/name,root/name)
 (root/'launch.sh').write_text((Path(template['path'])/'launch.sh').read_text().replace(template['path'],str(root)))
 sys.path.insert(0,str(source));sys.path.insert(0,str(root));os.environ['ARENA_REPO_ROOT']=str(source)
 import agent,linux_sandbox,mujoco
 workspace=root/'workspace';shutil.copytree(source/'arena_kit',workspace);(workspace/'notes.md').write_text('')
 runtime=linux_sandbox.prepare(workspace)
 result=linux_sandbox.execute(runtime,workspace,{'tool':'run_python','args':{'code':"import os,pathlib,socket\nassert not pathlib.Path('/storage').exists()\nassert not pathlib.Path('/.old_root').exists()\nassert not any(k.endswith('API_KEY') or k=='PROVIDER_API_KEY_FILE' for k in os.environ)\ntry: socket.create_connection(('1.1.1.1',443),timeout=1)\nexcept OSError: pass\nelse: raise AssertionError('network accessible')\nprint('ISOLATION_OK')"}},timeout=60)
 assert 'ISOLATION_OK' in result,result
 assert not (workspace/'robot.xml').read_text() and not (workspace/'controller.py').read_text() and not agent.harness_lib.list_bots(workspace)
 spec=importlib.util.spec_from_file_location('fable51_third_driver',root/'run.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 prompt=module.build_prompt(1,[],'No previous actions, bot, or feedback.',None,None)
 assert 'Current model turn: 1 of 10.' in prompt and '{{sampling_prompt}}' not in prompt
 assert prompt.startswith((source/'configs/rules/sampling_prompt.md').read_text().replace('{mujoco_version}',mujoco.__version__))
 (root/'first_prompt_preview.txt').write_text(prompt)
 save(root/'prepared.json',dict(isolation_verified=True,blank_workspace=True,source_commit=read(base/'source_manifest.json')['commit'],host=os.uname().nodename,prepared_at=time.time(),prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),python=sys.executable))
 record=dict(id=ident,path=str(root),session='user-oe_r3_fable51-20260925',title=config['experiment_title'],model=config['model'],provider='anthropic',repeat=3)
 for p in [base/'registry.json',base.parent/'iterative-high-20260924/dashboard/tool_use_registry.json']:
  with p.with_suffix('.lock').open('a') as lock:
   fcntl.flock(lock,fcntl.LOCK_EX);records=read(p);assert not any(r['id']==ident for r in records);shutil.copy2(p,p.with_name(p.name+'.before-fable51-'+stamp));save(p,[*records,record])
 dashboard=base.parent/'iterative-high-20260924/dashboard';index=dashboard/'index.html'
 shutil.copy2(index,index.with_name('index.html.before-fable51-'+stamp))
 total=len(read(dashboard/'tool_use_registry.json'));text=re.sub(r'Open-ended runs · \d+',f'Open-ended runs · {total}',index.read_text());tmp=index.with_suffix('.tmp');tmp.write_text(text);tmp.replace(index)
 return record

def main():
 p=argparse.ArgumentParser();p.add_argument('base',type=Path);a=p.parse_args();base=a.base;stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ');records={r['id']:r for r in read(base/'registry.json')}
 assert all(records[k]['model']=='claude-fable-5-1' for k in ['oe_r1_fable51','oe_r2_fable51'])
 assert 'oe_r3_fable51' not in records
 report=[]
 for key in ['oe_r1_fable51','oe_r2_fable51']:
  report.append(resume(base,records[key],stamp));save(base/('fable51-resume-'+stamp+'.json'),report);print('Resumed',key,'at turn 2',flush=True)
 third=prepare_third(base,records['oe_r1_fable51'],stamp);report.append(launch(third));save(Path(third['path'])/'launch_manifest.json',report[-1]);save(base/('fable51-resume-'+stamp+'.json'),report);print('Launched',third['id'],'from scratch',flush=True)
if __name__=='__main__':main()
