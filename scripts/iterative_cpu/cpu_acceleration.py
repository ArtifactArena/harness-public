"""Enable the validated CPU backend in each new worker, before its first match."""
from pathlib import Path
import hashlib,json,os,sys

def enable(index):
    budget=int(os.environ.get("MATCH_CPU_BUDGET", "1"))
    if budget not in (1,4):raise ValueError("MATCH_CPU_BUDGET must be 1 or 4")
    root=Path(__file__).resolve().parents[1]
    manifest=json.loads((root/'cpu-acceleration-manifest.json').read_text())
    for name,expected in manifest['files'].items():
        if hashlib.sha256((root/name).read_bytes()).hexdigest()!=expected:
            raise RuntimeError('CPU accelerator source/library checksum mismatch: '+name)
    allowed=sorted(os.sched_getaffinity(0))
    # Parent requires workers <= available CPUs; each process receives a distinct index.
    cpus=allowed[index*budget:(index+1)*budget]
    if len(cpus)!=budget:raise RuntimeError('Insufficient allocated CPUs for worker count')
    os.sched_setaffinity(0,set(cpus))
    os.environ['OMP_PLACES']=','.join('{'+str(c)+'}' for c in cpus)
    os.environ['OMP_PROC_BIND']='close'
    os.environ['GOMP_SPINCOUNT']='3000'
    os.environ['CUDA_VISIBLE_DEVICES']=''
    for name in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:
        os.environ[name]='1'
    sys.path.insert(0,str(root/'harness'))
    from mjarena.envs.observation_accel import install as observations
    observations()  # Checks runtime, source hashes, NumPy and BLAS ABI; fails closed.
    flags=set(next(x.split(':',1)[1].split() for x in Path('/proc/cpuinfo').read_text().splitlines() if x.startswith('flags')))
    mode='cython-observations'
    if {'avx512f','avx512dq','avx512cd','avx512bw','avx512vl'}<=flags:
        from mjarena.envs.match_accel import install
        install(root/'native/arena_onecore_v3.so',threads=budget,interval=True)
        mode='cython-observations+native-simd'
    print(json.dumps({'event':'cpu_acceleration','mode':mode,'pid':os.getpid(),'cpus':cpus,'cpu_budget':budget,'gpus_used':0}),flush=True)
