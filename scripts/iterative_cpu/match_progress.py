"""Sample progress without changing actions or simulator arithmetic."""
import os,socket,time

class MatchProgress:
    def __init__(self,job):
        self.started=time.time();self.job=job;self.sample=None;self.last_write=0
        self.reserved_cpus=sorted(os.sched_getaffinity(0))

    def snapshot(self):
        from pathlib import Path
        cpus=set(self.reserved_cpus)
        for task in Path('/proc/self/task').iterdir():
            try:cpus.update(os.sched_getaffinity(int(task.name)))
            except ProcessLookupError:pass
        result=dict(job=self.job['id'],host=socket.gethostname(),pid=os.getpid(),
                    started_at=self.started,updated_at=time.time(),
                    candidate_id=self.job['candidate_id'],opponent_id=self.job['opponent_id'],
                    side=self.job['side'],kind=self.job['kind'],seed=self.job['seed'],
                    limit_seconds=self.job.get('seconds',300),reserved_cpus=sorted(cpus),
                    acceleration='SIMD + SDF rejection',threads=1)
        if self.sample:result.update(self.sample)
        return result

    def __enter__(self):
        from mjarena.envs.sumo import SumoEnv
        self.owner=SumoEnv;self.original=SumoEnv.step
        def step(env,actions):
            result=self.original(env,actions)
            now=time.time()
            if now-self.last_write>=5:
                import mujoco
                sdf=int((env.model.geom_type==mujoco.mjtGeom.mjGEOM_SDF).sum())
                threads=4 if int(os.environ.get('MATCH_CPU_BUDGET','1'))==4 and sdf>=4 and env.model.opt.sdf_initpoints>=16 else 1
                self.sample=dict(sim_seconds=float(env.data.time),sampled_at=now,sdf_geoms=sdf,threads=threads)
                self.last_write=now
            return result
        self.wrapper=step;SumoEnv.step=step;return self

    def __exit__(self,*args):
        if self.owner.step is self.wrapper:self.owner.step=self.original
