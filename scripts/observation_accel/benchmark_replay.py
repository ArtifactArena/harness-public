"""Time a real 350-tick replay without correctness-hashing overhead.

Use validate.py separately for equivalence. This raises only after a complete
match step; it never writes tournament results and never changes match settings.
"""
import argparse
import dataclasses
import json
import os
from pathlib import Path
import pickle
import sys
import time

sys.path.insert(0, str(Path.cwd()))
import mjarena.core.unified_builder
import mjarena.envs
mjarena.envs.__path__.insert(0, str(Path(os.environ['OBS_OVERLAY'])/'mjarena/envs'))
from mjarena.envs.observation_accel import install
install()
from mjarena.runner.episode import Match

p=argparse.ArgumentParser();p.add_argument('task');p.add_argument('output',type=Path)
p.add_argument('--steps',type=int,default=350);args=p.parse_args()
task=pickle.loads(Path(args.task).read_bytes())
runner=dataclasses.replace(task[0],out_dir=args.output.parent/(args.output.stem+'-artifacts'),
                           trace_label=None,save_video_seeds=0)
class Finished(BaseException):pass
steps=0
original=Match.single_match_step
def step(self,*a,**kw):
    global steps
    result=original(self,*a,**kw);steps+=1
    if steps>=args.steps:raise Finished()
    return result
Match.single_match_step=step
start=time.perf_counter();cpu=time.process_time();finished=False
try:
    runner.run_with_policy_spec(task[1],seed=task[2],seed_index=task[3]);finished=True
except Finished:pass
report=dict(label=task[5],seed=task[2],steps=steps,finished=finished,
            wall_seconds=time.perf_counter()-start,cpu_seconds=time.process_time()-cpu,
            overlay=os.environ['OBS_OVERLAY'])
args.output.write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
