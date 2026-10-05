"""Run a harness match on exactly one CPU core, without worker processes."""
import argparse
import os
from pathlib import Path
import runpy
import sys


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library',required=True,type=Path)
    parser.add_argument('--cpu',type=int,help='logical CPU within scheduler affinity; defaults to the first allowed CPU')
    parser.add_argument('--threads',type=int,choices=[1],default=1)
    parser.add_argument('--surface-workers',type=int,choices=[0],default=0)
    parser.add_argument('command',nargs=argparse.REMAINDER,
                        help='-- script.py [args], or -- -m package.module [args]')
    args=parser.parse_args()
    command=args.command[1:] if args.command[:1]==['--'] else args.command
    if not command:parser.error('provide a Python script or -m module after --')
    if not sys.platform.startswith('linux'):parser.error('the validated accelerator requires Linux x86-64')
    allowed=os.sched_getaffinity(0)
    cpu=min(allowed) if args.cpu is None else args.cpu
    if cpu not in allowed:parser.error(f'CPU {cpu} is outside scheduler affinity')
    os.sched_setaffinity(0,{cpu})
    for name in ['OMP_PLACES','OMP_PROC_BIND','OMP_WAIT_POLICY','GOMP_SPINCOUNT','ARENA_SURFACE_CPUS']:
        os.environ.pop(name,None)
    os.environ.update(OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',OMP_NUM_THREADS='1',
                      OMP_THREAD_LIMIT='1',BLIS_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1',
                      VECLIB_MAXIMUM_THREADS='1',ARENA_OBS_ACCEL='1')
    # Initialize the harness in its existing dependency order.
    import mjarena.core.unified_builder
    from . import install
    print(f'Single-core match acceleration: CPU {cpu}, no worker processes; {args.library}',flush=True)
    with install(args.library,1,interval=True):
        if command[0]=='-m':
            if len(command)<2:parser.error('-m needs a module name')
            sys.argv=command[1:]
            runpy.run_module(command[1],run_name='__main__',alter_sys=True)
        else:
            sys.argv=command
            runpy.run_path(command[0],run_name='__main__')


if __name__=='__main__':main()
