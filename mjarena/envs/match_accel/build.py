"""Build the exact CPU SDF backend against MuJoCo 3.10.0."""
import argparse,re,subprocess,hashlib,json,platform,sys
from pathlib import Path
import mujoco
p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('output',type=Path);p.add_argument('--ispc',type=Path,help='optional ISPC 1.31.0 compiler for single-core AVX-512 batching');p.add_argument('--verify-simd',action='store_true',help='debug build: compare every SIMD query with scalar arithmetic');p.add_argument('--verify-rejection',action='store_true',help='debug build: run the stock collider for every rejected pair');p.add_argument('--parallel',action='store_true',help='enable opt-in four-core SDF pair execution');args=p.parse_args()
if mujoco.__version__!='3.10.0':raise RuntimeError('Requires MuJoCo 3.10.0')
expected={
 'src/engine/engine_util_misc.c':'f24198840a9fecea750d061763e5d0df103f9d01edf1e013bc15cea94fbb99fc',
 'src/engine/engine_collision_sdf.c':'3235b94665934d40257b5e397a99296d5e321fda15d4f0f4260d5cfd17bb1c4f',
 'src/engine/engine_util_blas.c':'92856302640bd62299a5e1c70bc21cfe1a42fdccacebffdaf2c5fc14b3658cf8',
 'include/mujoco/mjdata.h':'e2c7ac8a6011372eb1df4e9a53d63f8ddbc3fb940fd68d906480fe85ad0931d7',
 'include/mujoco/mjmodel.h':'bcd51b20cb29b6aac7c8b9e1cf348f569b7fc2239f9226b844737c73511d90c8',
 'include/mujoco/mjtype.h':'ec580ce2a4ef0c1f6a3e68b3c5b5eeaf61d03413827453e2d0a87c3bd92d16e4',
}
for name,digest in expected.items():
 if hashlib.sha256((args.source/name).read_bytes()).hexdigest()!=digest:
  raise RuntimeError('Source differs from pinned MuJoCo 3.10.0: '+name)
here=Path(__file__).parent
s=(args.source/'src/engine/engine_collision_sdf.c').read_text()
original=s
start=original.index('static int findOct(');end=original.index('// sdf\nmjtNum oct_distance',start)
oracle=original[start:end].replace('findOct(', 'arena_reference_findOct(',1)

s=s.replace('#include <math.h>','#include <math.h>\n#include <stdlib.h>\n#include <string.h>')
s=s.replace('mjp_getPluginAtSlotUnsafe(slot, nslot)','mjp_getPluginAtSlot(slot)')
pos=s.index('//---------------------------- interpolated sdf')
s=s[:pos]+(here/'octree_table.c').read_text()+'\n'+s[pos:]
s=s.replace('  int stack = 0;\n  mjtNum eps','  int initial=arena_lookup_leaf(oct_aabb,oct_child,p);\n  int stack=initial<0?0:initial;\n  mjtNum eps',1)
s+=(here/'collision_bounds.c').read_text()+'\n'+(here/('parallel_step.c' if args.parallel else 'serial_step.c')).read_text()
halton='static mjtNum arena_halton_values[3][64];\nstatic int arena_halton_ready;\nstatic void arena_init_halton(void) {\n  if(arena_halton_ready)return;\n  for(int i=0;i<64;i++){arena_halton_values[0][i]=mju_Halton(i,2);arena_halton_values[1][i]=mju_Halton(i,3);arena_halton_values[2][i]=mju_Halton(i,5);}\n  arena_halton_ready=1;\n}\nstatic inline mjtNum arena_halton(int i,int base) {\n  if(arena_halton_ready && i>=0 && i<64){if(base==2)return arena_halton_values[0][i];if(base==3)return arena_halton_values[1][i];if(base==5)return arena_halton_values[2][i];}\n  return mju_Halton(i,base);\n}\n'
s=s.replace('mju_Halton(', 'arena_halton(')
pos=s.index('//---------------------------- interpolated sdf');s=s[:pos]+halton+s[pos:]
s=s.replace('  arena_register_tables(m);','  arena_init_halton();\n  arena_register_tables(m);')
pos=s.index('// get sdf from geom id')
s=s[:pos]+(here/'fused_query.c').read_text()+'\n'+s[pos:]
a=s.index('static mjtNum stepGradient(');b=s.index('//---------------------------- bounding box vs sdf',a)
part=s[a:b].replace('    mjc_gradient(m, d, s, grad, x);',
 '    mjtNum dist0;\n    if(s->type==mjSDFTYPE_COLLISION)dist0=arena_collision_value_gradient(m,d,s,grad,x);\n    else mjc_gradient(m,d,s,grad,x);',1)
part=part.replace('    mjtNum dist0 = mjc_distance(m, d, s, x0);','    if(s->type!=mjSDFTYPE_COLLISION)dist0=mjc_distance(m,d,s,x0);',1)
s=s[:a]+part+s[b:]
# Inline the same small vector bodies without changing reduction order.
blas=(args.source/'src/engine/engine_util_blas.c').read_text()
misc=(args.source/'src/engine/engine_util_misc.c').read_text()
names=['mju_min','mju_max','mju_clip','mju_zero3','mju_copy3','mju_scl3','mju_add3','mju_sub3','mju_addTo3','mju_subFrom3','mju_addToScl3','mju_addScl3','mju_normalize3','mju_norm3','mju_dot3','mju_dist3','mju_mulMatVec3','mju_mulMatTVec3']
bodies=[]
for name in names:
 source=misc if name in ['mju_min','mju_max','mju_clip'] else blas
 match=re.search(r'^(?:void|mjtNum) '+name+r'\(',source,re.M);start=match.start();end=source.index('{',start)+1;depth=1
 while depth:depth+=(source[end]=='{')-(source[end]=='}');end+=1
 bodies.append(source[start:end])
helpers='\n'.join(bodies)
for name in names:
 s=re.sub(r'\b'+name+r'\b','arena_'+name,s);helpers=re.sub(r'\b'+name+r'\b','arena_'+name,helpers)
helpers=re.sub(r'^(void|mjtNum) ',r'static __attribute__((always_inline)) inline \1 ',helpers,flags=re.M)
pos=s.index('//---------------------------- interpolated sdf');s=s[:pos]+helpers+'\n'+s[pos:]
for name in ['oct_gradient','mjc_distance','mjc_gradient']:
 s=re.sub(r'\b'+name+r'\b','arena_'+name,s);s=re.sub(r'^(void|mjtNum) arena_'+name+r'\(',r'static __attribute__((always_inline)) inline \1 arena_'+name+'(',s,flags=re.M)
for name in ['findOct','oct_distance','geomDistance','geomGradient']:
 s=re.sub(r'^static (void|int|mjtNum) '+name+r'\(',r'static __attribute__((always_inline)) inline \1 '+name+'(',s,flags=re.M)
s+='\n'+oracle+'\n'+(here/'check_octree.c').read_text()
s=s.replace('mju_norm(b, 2)', 'arena_norm2(b)')
pos=s.index('//---------------------------- interpolated sdf')
s=s[:pos]+'static inline mjtNum arena_norm2(const mjtNum* x){mjtNum res=0;res+=x[0]*x[0]+x[1]*x[1];return mju_sqrt(res); }\n'+s[pos:]
simd_objects=[]
if args.ispc:
 obj=args.output.with_suffix('.simd.o')
 subprocess.run([sys.executable,str(here/'build_simd.py'),str(args.source),str(args.ispc),str(obj)],check=True)
 simd_objects=[str(obj)]
 start=s.index('int mjc_SDF(');end=s.index('// Context for flex element processing',start)
 function=s[start:end]
 scalar=function.replace('int mjc_SDF(', 'static int arena_scalar_sdf(',1)
 function=function.replace('  mjtNum contacts[3*mjMAXCONPAIR];',"""  mjtNum contacts[3*mjMAXCONPAIR];
  double batch_points[3*mjMAXCONPAIR],batch_depths[mjMAXCONPAIR];
  struct OctTable tables[64];struct Model kernel;struct SDF ks;
  arena_wavefront_model(m,&kernel,tables);
  memcpy(ks.id,sdf.id,sizeof(ks.id));memcpy(ks.geomtype,sdf.geomtype,sizeof(ks.geomtype));
  memcpy(ks.relpos,sdf.relpos,sizeof(ks.relpos));memcpy(ks.relmat,sdf.relmat,sizeof(ks.relmat));
""")
 a=function.index('    // gradient descent -');z=function.index('    // contact point and normal',a)
 function=function[:a]+"""    memcpy(batch_points+3*(i-1),x,3*sizeof(double));
  }
  ks.type=sdf.type=mjSDFTYPE_COLLISION;
  arena_wavefront(&kernel,&ks,batch_points,batch_depths,i,m->opt.sdf_iterations,m,d,&sdf);
  ks.type=sdf.type=mjSDFTYPE_INTERSECTION;
  arena_wavefront(&kernel,&ks,batch_points,batch_depths,i,1,m,d,&sdf);
  for(int batch_i=0;batch_i<i;batch_i++) {
    memcpy(x,batch_points+3*batch_i,3*sizeof(double));dist2=batch_depths[batch_i];
"""+function[z:]
 a=function.index('{')+1
 function=function[:a]+"""
  if(m->nmesh>64 || m->nplugin || m->opt.sdf_initpoints>mjMAXCONPAIR)
    return arena_scalar_sdf(m,d,con,g1,g2,margin);
"""+function[a:]
 s=s[:start]+scalar+function+s[end:]
 pos=s.index('//---------------------------- bounding box vs sdf')
 s=s[:pos]+(here/'wavefront.c').read_text()+'\n'+s[pos:]
 s='#include "'+str(obj.with_suffix('.h').resolve())+'"\n'+s
args.output.parent.mkdir(parents=True,exist_ok=True);generated=args.output.with_suffix('.c');generated.write_text(s)
paths={line.split()[-1] for line in Path('/proc/self/maps').read_text().splitlines() if '/libmujoco.so.' in line};assert len(paths)==1
lib=Path(paths.pop())
subprocess.run(['gcc',*(['-fopenmp'] if args.parallel else []),'-shared','-D_GNU_SOURCE','-fPIC','-O3','-fno-fast-math','-ffp-contract=off','-march=native','-mprefer-vector-width=512','-fno-semantic-interposition','-Wl,-Bsymbolic-functions','-I'+str(args.source/'include'),'-I'+str(args.source/'src'),*(['-DARENA_VERIFY_SIMD'] if args.verify_simd else []),*(['-DARENA_VERIFY_REJECTION'] if args.verify_rejection else []),str(generated),*simd_objects,str(lib),'-Wl,-rpath,'+str(lib.parent),'-lm','-o',str(args.output)],check=True)
print('BUILT',args.output,flush=True)

metadata={'verify_simd':args.verify_simd,'verify_rejection':args.verify_rejection,'collision_bounds':'interpolated-sdf-negative-region','simd_query_cache':bool(args.ispc),'simd_target':'avx512skx-i32x16' if args.ispc else None,'backend':'cpu-pair-parallel' if args.parallel else 'cpu-serial','mujoco':mujoco.__version__,'machine':platform.machine(),
 'library_sha256':hashlib.sha256(args.output.read_bytes()).hexdigest(),
 'mujoco_library_sha256':hashlib.sha256(lib.read_bytes()).hexdigest(),
 'source_hashes':expected,'generated_sha256':hashlib.sha256(generated.read_bytes()).hexdigest(),
 'compiler':subprocess.check_output(['gcc','--version'],text=True).splitlines()[0],
 'flags':[*(['-fopenmp'] if args.parallel else []),'-O3','-fno-fast-math','-ffp-contract=off','-march=native','-mprefer-vector-width=512']}
if args.ispc:
 metadata['ispc_version']=subprocess.check_output([str(args.ispc),'--version'],text=True).splitlines()[0]
 metadata['simd_source_sha256']=hashlib.sha256(obj.with_suffix('.ispc').read_bytes()).hexdigest()
 metadata['simd_flags']=['-O3','--opt=disable-fma','--target=avx512skx-i32x16','--pic','--math-lib=default']
args.output.with_suffix('.json').write_text(json.dumps(metadata,indent=2)+'\n')
