/* Independent SDF pairs run concurrently; contacts retain original order. */
#include <mujoco/mujoco.h>
#include "engine/engine_util_sparse.h"
#include <omp.h>
typedef struct { int g1,g2,count; double margin; mjPreContact con[mjMAXCONPAIR]; } ArenaPair;
typedef struct {
 const mjModel* m; mjData* d; ArenaReject* reject;
 mjData* probe; ArenaPair* pairs; int* lookup;
 int threads,mode,count,capacity;
} ArenaContext;
static _Thread_local ArenaContext* arena_context;
static mjfCollision arena_original[mjNGEOMTYPES][mjNGEOMTYPES];
static int arena_installed;
static void arena_prepare(ArenaContext* ctx);
static int arena_supported(const mjModel* m,const mjData* d) {
 return !m->nplugin && !m->nflex && !(m->opt.enableflags & mjENBL_SLEEP) &&
        !d->threadpool && !mjcb_control && !mjcb_passive && !mjcb_sensor && !mjcb_contactfilter;
}
static int arena_eval(ArenaContext* ctx,mjData* d,mjPreContact* con,int g1,int g2,double margin) {
 const mjModel* m=ctx->m;
 if(arena_reject_pair(m,d,ctx->reject,g1,g2)) {
#ifdef ARENA_VERIFY_REJECTION
  mjPreContact original[mjMAXCONPAIR];
  if(arena_original[m->geom_type[g1]][m->geom_type[g2]](m,d,original,g1,g2,margin))
    mju_error("Rejected reference contact");
#endif
  return 0;
 }
 return mjc_SDF(m,d,con,g1,g2,margin);
}
static int arena_collider(const mjModel* m,mjData* d,mjPreContact* con,int g1,int g2,double margin) {
 ArenaContext* ctx=arena_context;int t1=m->geom_type[g1],t2=m->geom_type[g2];
 if(!ctx || ctx->m!=m || (d!=ctx->d && d!=ctx->probe))return arena_original[t1][t2](m,d,con,g1,g2,margin);
 int sdf=t2==mjGEOM_SDF && t1>=mjGEOM_SPHERE && t1!=mjGEOM_MESH;
 if(ctx->threads>1) {
  if(ctx->mode==0)arena_prepare(ctx);
  if(ctx->mode==1) {
   if(sdf && ctx->count<ctx->capacity) {
    int i=ctx->count++;ArenaPair* p=ctx->pairs+i;
    p->g1=g1;p->g2=g2;p->margin=margin;ctx->lookup[g1*m->ngeom+g2]=i;
   }
   return 0;
  }
  if(sdf) {
   int i=ctx->lookup[g1*m->ngeom+g2];
   if(i>=0) {
    ArenaPair* p=ctx->pairs+i;
    if(!memcmp(&p->margin,&margin,sizeof(double)) &&
       !memcmp(d->geom_xpos+3*g1,ctx->probe->geom_xpos+3*g1,3*sizeof(double)) &&
       !memcmp(d->geom_xpos+3*g2,ctx->probe->geom_xpos+3*g2,3*sizeof(double)) &&
       !memcmp(d->geom_xmat+9*g1,ctx->probe->geom_xmat+9*g1,9*sizeof(double)) &&
       !memcmp(d->geom_xmat+9*g2,ctx->probe->geom_xmat+9*g2,9*sizeof(double))) {
     memcpy(con,p->con,p->count*sizeof(mjPreContact));return p->count;
    }
   }
  }
 }
 if(sdf)return arena_eval(ctx,d,con,g1,g2,margin);
 if(t2==mjGEOM_SDF && t1==mjGEOM_MESH) {
  if(arena_reject_pair(m,d,ctx->reject,g1,g2))return 0;
  return mjc_MeshSDF(m,d,con,g1,g2,margin);
 }
 return arena_original[t1][t2](m,d,con,g1,g2,margin);
}
void arena_enable(int enabled) {
 if(enabled && !arena_installed) {
  for(int a=0;a<mjNGEOMTYPES;a++)for(int b=a;b<mjNGEOMTYPES;b++) {
   arena_original[a][b]=mjCOLLISIONFUNC[a][b];if(mjCOLLISIONFUNC[a][b])mjCOLLISIONFUNC[a][b]=arena_collider;
  }
  arena_installed=1;
 } else if(!enabled && arena_installed) {
  for(int a=0;a<mjNGEOMTYPES;a++)for(int b=a;b<mjNGEOMTYPES;b++)mjCOLLISIONFUNC[a][b]=arena_original[a][b];
  arena_installed=0;
 }
}
ArenaContext* arena_create(const mjModel* m,mjData* d,int threads) {
 if((threads!=1 && threads!=4) || m->ngeom>256 || !arena_supported(m,d))return NULL;
 ArenaContext* ctx=calloc(1,sizeof(*ctx));if(!ctx)return NULL;
 arena_register_tables(m);
 ctx->m=m;ctx->d=d;ctx->reject=arena_reject_create(m);ctx->threads=threads;
 if(threads==1)return ctx;
 ctx->capacity=m->ngeom*m->ngeom;ctx->probe=mj_makeData(m);
 ctx->pairs=calloc(ctx->capacity,sizeof(ArenaPair));ctx->lookup=malloc(ctx->capacity*sizeof(int));
 if(!ctx->pairs || !ctx->lookup || !ctx->probe) {
  if(ctx->probe)mj_deleteData(ctx->probe);
  free(ctx->pairs);free(ctx->lookup);ctx->pairs=NULL;ctx->lookup=NULL;ctx->probe=NULL;
  ctx->threads=1;
 }
 omp_set_dynamic(0);return ctx;
}
void arena_destroy(ArenaContext* ctx) {
 if(!ctx)return;arena_unregister_tables(ctx->m);arena_reject_destroy(ctx->reject);
 if(ctx->probe)mj_deleteData(ctx->probe);free(ctx->pairs);free(ctx->lookup);free(ctx);
}
static void arena_prepare(ArenaContext* ctx) {
 const mjModel* m=ctx->m;ctx->count=0;
 for(int i=0;i<ctx->capacity;i++)ctx->lookup[i]=-1;
 memcpy(ctx->probe->geom_xpos,ctx->d->geom_xpos,3*m->ngeom*sizeof(double));
 memcpy(ctx->probe->geom_xmat,ctx->d->geom_xmat,9*m->ngeom*sizeof(double));
 memcpy(ctx->probe->xipos,ctx->d->xipos,3*m->nbody*sizeof(double));
 memcpy(ctx->probe->ximat,ctx->d->ximat,9*m->nbody*sizeof(double));
 memcpy(ctx->probe->body_awake,ctx->d->body_awake,m->nbody*sizeof(*ctx->d->body_awake));
 ctx->probe->nbody_awake=ctx->d->nbody_awake;ctx->mode=1;
 mj_collision(m,ctx->probe);
 #pragma omp parallel for num_threads(ctx->threads) schedule(dynamic,1) if(ctx->count>=4)
 for(int i=0;i<ctx->count;i++) {
  ArenaPair* p=ctx->pairs+i;p->count=arena_eval(ctx,ctx->probe,p->con,p->g1,p->g2,p->margin);
 }
 ctx->mode=2;
}
void arena_step(ArenaContext* ctx) {
 ArenaContext* previous=arena_context;
 arena_context=arena_supported(ctx->m,ctx->d)?ctx:NULL;ctx->mode=0;
 mj_step(ctx->m,ctx->d);arena_context=previous;
}
void arena_forward(ArenaContext* ctx) {
 ArenaContext* previous=arena_context;
 arena_context=arena_supported(ctx->m,ctx->d)?ctx:NULL;ctx->mode=0;
 mj_forward(ctx->m,ctx->d);arena_context=previous;
}

#ifdef ARENA_VERIFY_REJECTION
/* Debug-only entry points: exercise the field enclosure and original collider
   independently, including pairs not admitted by MuJoCo's broad phase. */
int arena_check_rejection_field(ArenaContext* ctx,int mid,int n,const double* points) {
  if(!ctx->reject || mid<0 || mid>=ctx->m->nmesh || !ctx->reject->valid[mid])return -2;
  const double extent[3]={0,0,0};int adr=ctx->m->mesh_octadr[mid];
  for(int i=0;i<n;i++) {
    const double* p=points+3*i;
    if(oct_distance(ctx->m,p,mid)<=0 &&
       !arena_reject_overlap(ctx->m,ctx->reject,adr,0,p,extent,0))return i;
  }
  return -1;
}
int arena_check_rejection_pair(ArenaContext* ctx,int g1,int g2) {
  if(!arena_reject_pair(ctx->m,ctx->d,ctx->reject,g1,g2))return 0;
  mjPreContact contacts[mjMAXCONPAIR];
  int t1=ctx->m->geom_type[g1],t2=ctx->m->geom_type[g2];
  return arena_original[t1][t2](ctx->m,ctx->d,contacts,g1,g2,0)?-1:1;
}
#endif

/* The observer reads kinematics and transmission rates, not a second solver. */
int arena_observe(const mjModel* m,mjData* d) {
  if(m->nplugin || m->nflex || (m->opt.enableflags & mjENBL_SLEEP) ||
     mjcb_control || mjcb_passive || mjcb_sensor || mjcb_contactfilter) return 0;
  mj_fwdKinematics(m,d);
  mj_transmission(m,d);
  d->flg_subtreevel=0;d->flg_energyvel=0;
  mju_mulMatVecSparse(d->ten_velocity,d->ten_J,d->qvel,m->ntendon,
                      m->ten_J_rownnz,m->ten_J_rowadr,m->ten_J_colind,NULL);
  if(!(m->opt.disableflags & mjDSBL_ACTUATION)) {
    mju_mulMatVecSparse(d->actuator_velocity,d->actuator_moment,d->qvel,m->nu,
                        d->moment_rownnz,d->moment_rowadr,d->moment_colind,NULL);
  } else mju_zero(d->actuator_velocity,m->nu);
  mj_comVel(m,d);
  return 1;
}
