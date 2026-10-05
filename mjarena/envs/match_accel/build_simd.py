"""Translate the pinned independent SDF searches into strict double SIMD lanes."""
import argparse,re,subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('compiler');p.add_argument('out',type=Path);args=p.parse_args()
src=(args.source/'src/engine/engine_collision_sdf.c').read_text();blas=(args.source/'src/engine/engine_util_blas.c').read_text()
def function(text,name):
 match=re.search(r'^(?:static )?(?:void|int|mjtNum) '+name+r'\(',text,re.M);start=match.start();brace=text.index('{',start);end=brace+1;depth=1
 while depth:depth+=(text[end]=='{')-(text[end]=='}');end+=1
 return text[start:end]
header='''
#define mjMINVAL 1e-15d
#define mjMAXVAL 1e10d
#define mjGEOM_PLANE 0
#define mjGEOM_SPHERE 2
#define mjGEOM_CAPSULE 3
#define mjGEOM_ELLIPSOID 4
#define mjGEOM_CYLINDER 5
#define mjGEOM_BOX 6
#define mjGEOM_MESH 7
#define mjGEOM_SDF 8
#define mjSDFTYPE_SINGLE 0
#define mjSDFTYPE_INTERSECTION 1
#define mjSDFTYPE_MIDSURFACE 2
#define mjSDFTYPE_COLLISION 3
#define mjERROR(...)\x20
#define mju_error(...)\x20
#define mju_sqrt sqrt
struct OctTable {
 uniform int n[3];
 uniform double * uniform cut[3];
 uniform double lo[3],hi[3],scale[3];
 uniform int * uniform leaf;
};
struct Model {
 uniform double * uniform geom_size;
 uniform int * uniform mesh_octadr;
 uniform int * uniform oct_child;
 uniform double * uniform oct_aabb;
 uniform double * uniform oct_coeff;
 uniform int iterations;
 uniform OctTable * uniform tables;
};
struct SDF {
 uniform int id[2];
 uniform int geomtype[2];
 uniform double relpos[3];
 uniform double relmat[9];
 uniform int type;
};
inline double mju_abs(double x) {return abs(x);}
inline double mju_min(double a,double b) {return a<b?a:b;}
inline double mju_max(double a,double b) {return a>b?a:b;}
inline double mju_clip(double x,double lo,double hi) {return x<lo?lo:(x>hi?hi:x);}
inline double mju_norm(const double x[], uniform int n) {return sqrt(0.d+(x[0]*x[0]+x[1]*x[1]));}
'''
helpers=['mju_zero3','mju_copy3','mju_scl3','mju_add3','mju_sub3','mju_addTo3','mju_subFrom3','mju_addToScl3','mju_addScl3','mju_normalize3','mju_norm3','mju_dot3','mju_dist3','mju_mulMatVec3','mju_mulMatTVec3']
parts=[]
for name in helpers:
 s=function(blas,name)
 s=s.replace('const mjtNum mat[9]','const uniform mjtNum mat[9]')
 parts.append(s)
# Uniform triangle corners require uniform-input overloads.
for name in ['mju_copy3','mju_dot3','mju_addTo3']:
 s=function(blas,name)
 s=s.replace('const mjtNum vec[3]','const uniform mjtNum vec[3]').replace('const mjtNum vec1[3]','const uniform mjtNum vec1[3]')
 parts.append(s)
for name in ['boxProjection','findOct','oct_distance','oct_gradient','radialField3d','geomDistance','geomGradient','mjc_distance','mjc_gradient']:
 s=function(src,name)
 s=s.replace('const mjModel* m','const uniform Model* uniform m').replace('const mjData* d,','').replace(', const mjData* d','')
 s=s.replace('const mjpPlugin* p,','').replace('const mjSDF* s,','const uniform SDF* uniform s,').replace('const mjSDF* sdf,','const uniform SDF* uniform sdf,')
 s=s.replace('int meshid','uniform int meshid').replace('int i, const mjtNum x[3], mjtGeom type','uniform int i, const mjtNum x[3], uniform int type').replace('int i, const mjtNum x[3],\n                         mjtGeom type','uniform int i, const mjtNum x[3],\n                         uniform int type')
 s=s.replace('const mjtNum box[6]','const uniform mjtNum box[6]').replace('const mjtNum size[3]','const uniform mjtNum size[3]')
 s=s.replace('const mjtNum* oct_aabb','const uniform mjtNum* uniform oct_aabb').replace('const int* oct_child','const uniform int* uniform oct_child')
 s=s.replace('mjtNum* oct_aabb','uniform mjtNum* uniform oct_aabb').replace('int* oct_child','uniform int* uniform oct_child').replace('mjtNum* oct_coeff','uniform mjtNum* uniform oct_coeff')
 s=s.replace('int octadr','uniform int octadr').replace('const mjtNum* size','const uniform mjtNum* uniform size')
 s=s.replace('const mjtNum* corners, int ncorners','const uniform mjtNum* uniform corners, uniform int ncorners').replace('int niter)','uniform int niter)')
 if name=='findOct':
  s=s.replace('findOct(mjtNum w[8]', 'findOct(const uniform OctTable* uniform table,mjtNum w[8]')
  s=s.replace('  int stack = 0;', '  int leaf=arena_leaf(table,p);\n  int stack = leaf<0?0:leaf;',1)
  # The table already resolves to a leaf. Avoid eight dependent child gathers;
  # retain the original bounds checks and traversal when no table entry exists.
  s=s.replace('if (oct_child[8*node+0] == -1 &&', 'if (leaf>=0 || (oct_child[8*node+0] == -1 &&').replace('oct_child[8*node+7] == -1) {','oct_child[8*node+7] == -1)) {')
 s=s.replace('findOct(w, NULL,', 'findOct(&m->tables[meshid],w, NULL,').replace('findOct(NULL, dw,','findOct(&m->tables[meshid],NULL, dw,')
 s=s.replace('m->opt.sdf_iterations','m->iterations')
 s=s.replace('m, d, s->plugin[0],','m,').replace('m, d, s->plugin[1],','m,').replace('m, d, s->plugin[i],','m,')
 s=s.replace('m, d, s,','m, s,').replace('m, d, sdf,','m, sdf,').replace('m, sdf, d,','m, sdf,').replace('m, s, d,','m, s,')
 s=re.sub(r'if \(p\) \{\s*(?:return p->sdf_distance\(x, d, i\);|p->sdf_gradient\(gradient, x, d, i\);)\s*\} else \{(.*?)\n    \}',r'\1',s,flags=re.S)
 # Direction-dependent SDF index in INTERSECTION is varying: implement both branches explicitly below.
 s=s.replace('geomGradient(gradient, m, s->id[i], point[i], s->geomtype[i]);', 'if(i==0) geomGradient(gradient,m,s->id[0],x,s->geomtype[0]); else geomGradient(gradient,m,s->id[1],y,s->geomtype[1]);')
 parts.append(s)
lookup="""
inline int arena_leaf(const uniform OctTable* uniform t,const double p[3]) {
 if(t->leaf==NULL)return -1;
 int index[3];
 for(uniform int k=0;k<3;k++) {
  double guess=(p[k]-t->lo[k])*t->scale[k];
  int i=guess<=0.d?0:guess>=t->n[k]?t->n[k]:(int)guess;
  while(i>0 && p[k]<t->cut[k][i-1])i--;
  while(i<t->n[k] && !(p[k]<t->cut[k][i]))i++;
  index[k]=i;
 }
 return t->leaf[(index[0]*(t->n[1]+1)+index[1])*(t->n[2]+1)+index[2]];
}
"""
s=header+lookup+'\n'+'\n'.join(parts)
s=s.replace('const mjSDF* sdf','const uniform SDF* uniform sdf')
s=s.replace('const mjtNum* point[2] = {x, y};','')
s=s.replace('s->id[0], point[0],','s->id[0], x,')
s=s.replace('mju_addToScl3(gradient, A > B ? grad1 : grad2, mju_max(A, B) > 0 ? 1 : -1);','for(uniform int k=0;k<3;k++) gradient[k]+=(A>B?grad1[k]:grad2[k])*(mju_max(A,B)>0?1:-1);')
s=s.replace('for (int ', 'for (uniform int ')
s=s.replace('mjtNum','double').replace('static ','').replace('mjtGeom','uniform int')
# Ensure decimal literals retain C double semantics (ISPC defaults literals to float).
s=re.sub(r'(?<![\w.])(\d+\.\d*(?:[eE][+-]?\d+)?|\.\d+(?:[eE][+-]?\d+)?|\d+[eE][+-]?\d+)(?![\w.])',r'\1d',s)

def fused_source():
    s=(Path(__file__).parent/'fused_query.c').read_text()
    s=s.replace('const mjModel* m','const uniform Model* uniform m').replace('const mjData* d,','').replace(',const mjData* d','')
    s=s.replace('const mjSDF* s','const uniform SDF* uniform s')
    s=s.replace('const mjpPlugin* plugin,','').replace('int meshid','uniform int meshid').replace('int id,','uniform int id,').replace('mjtGeom type','uniform int type')
    s=s.replace('!plugin && ', '').replace('m,d,plugin,','m,').replace('m,d,s->plugin[0],','m,').replace('m,d,s->plugin[1],','m,')
    s=s.replace('int adr=', 'uniform int adr=').replace('const mjtNum* aabb','const uniform mjtNum* uniform aabb').replace('const mjtNum* coeff','const uniform mjtNum* uniform coeff').replace('const int* child','const uniform int* uniform child')
    s=s.replace('int node=findOct(w,box<=0?dw:NULL,aabb,child,p);', 'int node;\n  if(box<=0)node=findOct(&m->tables[meshid],w,dw,aabb,child,p);\n  else node=findOct(&m->tables[meshid],w,NULL,aabb,child,p);')
    s=s.replace('mju_addToScl3(gradient,A>B?grad1:grad2,mju_max(A,B)>0?1:-1);','for(uniform int k=0;k<3;k++)gradient[k]+=(A>B?grad1[k]:grad2[k])*(mju_max(A,B)>0?1:-1);')
    s=s.replace('  for(int i=0;i<8;i++)value+=', '  if(node<0){grad[0]=grad[1]=grad[2]=0.0/0.0;return 0.0/0.0;}\n  for(int i=0;i<8;i++)value+=')
    s=s.replace('for(int ', 'for(uniform int ').replace('mjtNum','double').replace('static ','')
    s=re.sub(r'(?<![\w.])(\d+\.\d*(?:[eE][+-]?\d+)?|\.\d+(?:[eE][+-]?\d+)?|\d+[eE][+-]?\d+)(?![\w.])',r'\1d',s)
    return s

s += (Path(__file__).parent/'cached_distance.ispc').read_text()
fused=fused_source()
fused=fused.replace('double dx=oct_distance(m,px,meshid),dy=oct_distance(m,py,meshid),dz=oct_distance(m,pz,meshid);', '''double lower[3],upper[3];
    int cached=arena_cell(&m->tables[meshid],p,lower,upper);
    double dx=arena_cached_distance(m,px,meshid,cached,lower,upper);
    double dy=arena_cached_distance(m,py,meshid,cached,lower,upper);
    double dz=arena_cached_distance(m,pz,meshid,cached,lower,upper);''')
s += fused
# Invalid interpolation inputs take the host's scalar reference path.
s=s.replace('  for (uniform int i = 0; i < 8; ++i) {\n    sdf +=',
            '  if(node<0)return 0.0d/0.0d;\n  for (uniform int i = 0; i < 8; ++i) {\n    sdf +=')
s=s.replace('    for (uniform int i = 0; i < 8; ++i) {\n      grad[0] +=',
            '    if(node<0){grad[0]=grad[1]=grad[2]=0.0d/0.0d;return;}\n    for (uniform int i = 0; i < 8; ++i) {\n      grad[0] +=')
s=s.replace(' if(t->leaf==NULL)return -1;',
            ' if(t->leaf==NULL)return -1;\n for(uniform int k=0;k<3;k++)if(isnan(p[k]) || abs(p[k])>1.7976931348623157e308d || p[k]+1e-8d<t->lo[k] || p[k]-1e-8d>t->hi[k])return -1;')
s += """
export void arena_batch_grad(uniform Model* uniform m,uniform SDF* uniform s,
 const uniform double points[],uniform double gradients[],uniform double values[],uniform int n) {
 foreach(i=0 ... n) {
  double x[3]={points[i],points[n+i],points[2*n+i]},g[3];
  if(s->type==mjSDFTYPE_COLLISION)values[i]=arena_collision_value_gradient(m,s,g,x);
  else {mjc_gradient(m,s,g,x);values[i]=mjc_distance(m,s,x);}
  gradients[i]=g[0];gradients[n+i]=g[1];gradients[2*n+i]=g[2];
 }
}
export void arena_batch_distance(uniform Model* uniform m,uniform SDF* uniform s,
 const uniform double points[],uniform double values[],uniform int n) {
 foreach(i=0 ... n) {
  double x[3]={points[i],points[n+i],points[2*n+i]};
  values[i]=mjc_distance(m,s,x);
 }
}
"""
# Inline only these small helpers so unused interpolation outputs disappear.
# Inlining the entire call tree increased code size without improving runtime.
s=re.sub(r'^(double boxProjection|int findOct)\(',r'inline \1(',s,flags=re.M)
args.out.parent.mkdir(parents=True,exist_ok=True)
source=args.out.with_suffix('.ispc');source.write_text(s)
version=subprocess.check_output([args.compiler,'--version'],text=True)
if '1.31.0' not in version:raise RuntimeError('Validated SIMD compiler is ISPC 1.31.0')
subprocess.run([args.compiler,str(source),'-O3','--opt=disable-fma','--target=avx512skx-i32x16','--pic','--math-lib=default','-o',str(args.out),'-h',str(args.out.with_suffix('.h'))],check=True)
