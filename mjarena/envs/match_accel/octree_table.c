/* Exact leaf lookup: numeric guesses are corrected against exact split cuts. */
#include <stdint.h>
#include <string.h>
#include <math.h>
typedef struct {
  const mjModel* model; const mjtNum* aabb; const int* child;
  int users; int n[3]; mjtNum* cut[3]; mjtNum lo[3],hi[3],scale[3]; int* leaf;
} ArenaOctTable;
static ArenaOctTable arena_tables[64];
static int arena_ntables;
static uint64_t arena_order(double d) {uint64_t u;memcpy(&u,&d,8);return u>>63?~u:u^(UINT64_C(1)<<63);}
static double arena_number(uint64_t u) {u=u>>63?u^(UINT64_C(1)<<63):~u;double d;memcpy(&d,&u,8);return d;}
static double arena_split(double lo,double hi) {
  uint64_t a=arena_order(lo),b=arena_order(hi);
  double width=hi-lo;
  while(b-a>1) {uint64_t c=a+(b-a)/2;double v=arena_number(c);if((v-lo)/width<.5)a=c;else b=c;}
  return arena_number(b);
}
static int arena_compare_cut(const void* a,const void* b) {double x=*(const double*)a,y=*(const double*)b;return (x>y)-(x<y);}
static void arena_register_tables(const mjModel* m) {
  for(int old=0;old<arena_ntables;old++) if(arena_tables[old].model==m) {
    for(int k=old;k<arena_ntables;k++)if(arena_tables[k].model==m)arena_tables[k].users++;
    return;
  }
  for(int mid=0;mid<m->nmesh && arena_ntables<64;mid++) {
    int adr=m->mesh_octadr[mid],count=m->mesh_octnum[mid];if(adr<0 || count<=0)continue;
    ArenaOctTable t={0};t.users=1;t.model=m;t.aabb=m->oct_aabb+6*adr;t.child=m->oct_child+8*adr;
    for(int k=0;k<3;k++) {t.cut[k]=malloc(count*sizeof(double));t.lo[k]=t.aabb[k]-t.aabb[k+3];t.hi[k]=t.aabb[k]+t.aabb[k+3];}
    if(!t.cut[0]||!t.cut[1]||!t.cut[2])mju_error("Octree table allocation failed");
    for(int i=0;i<count;i++) {
      int internal=0;for(int k=0;k<8;k++)internal|=t.child[8*i+k]!=-1;
      if(!internal)continue;
      for(int k=0;k<3;k++) {
        double lo=t.aabb[6*i+k]-t.aabb[6*i+k+3],hi=t.aabb[6*i+k]+t.aabb[6*i+k+3];
        if(!isfinite(lo)||!isfinite(hi)||!(lo<hi))mju_error("Invalid octree interval");
        t.cut[k][t.n[k]++]=arena_split(lo,hi);
      }
    }
    size_t total=1;
    for(int k=0;k<3;k++) {
      qsort(t.cut[k],t.n[k],sizeof(double),arena_compare_cut);
      int n=0;for(int i=0;i<t.n[k];i++)if(!n||t.cut[k][i]!=t.cut[k][n-1])t.cut[k][n++]=t.cut[k][i];
      /* n cuts delimit n+1 cells. This is only a guess; exact cuts correct it. */
      t.n[k]=n;total*=n+1;t.scale[k]=(n+1)/(t.hi[k]-t.lo[k]);
    }
    if(total>4000000) {for(int k=0;k<3;k++)free(t.cut[k]);continue;}
    t.leaf=malloc(total*sizeof(int));if(!t.leaf)mju_error("Octree table allocation failed");
    for(int x=0;x<=t.n[0];x++)for(int y=0;y<=t.n[1];y++)for(int z=0;z<=t.n[2];z++) {
      double p[3]={x?t.cut[0][x-1]:t.lo[0],y?t.cut[1][y-1]:t.lo[1],z?t.cut[2][z-1]:t.lo[2]};
      int node=0;
      while(t.child[8*node]!=-1) {
        int index=0;
        for(int k=0;k<3;k++) {double lo=t.aabb[6*node+k]-t.aabb[6*node+k+3],hi=t.aabb[6*node+k]+t.aabb[6*node+k+3];if(!((p[k]-lo)/(hi-lo)<.5))index|=1<<k;}
        node=t.child[8*node+index];
      }
      t.leaf[(x*(t.n[1]+1)+y)*(t.n[2]+1)+z]=node;
    }
    arena_tables[arena_ntables++]=t;
  }
}
static int arena_lookup_leaf(const double* aabb,const int* child,const double p[3]) {
  const ArenaOctTable* t=NULL;
  for(int i=arena_ntables-1;i>=0;i--)if(arena_tables[i].aabb==aabb && arena_tables[i].child==child){t=arena_tables+i;break;}
  if(!t)return -1;
  int index[3];
  for(int k=0;k<3;k++) {
    if(!isfinite(p[k]) || p[k]+1e-8<t->lo[k] || p[k]-1e-8>t->hi[k])return -1;
    double guess=(p[k]-t->lo[k])*t->scale[k];
    int i=guess<=0?0:guess>=t->n[k]?t->n[k]:(int)guess;
    while(i>0 && p[k]<t->cut[k][i-1])i--;
    while(i<t->n[k] && !(p[k]<t->cut[k][i]))i++;
    index[k]=i;
  }
  return t->leaf[(index[0]*(t->n[1]+1)+index[1])*(t->n[2]+1)+index[2]];
}

static void arena_unregister_tables(const mjModel* m) {
  for(int i=arena_ntables-1;i>=0;i--)if(arena_tables[i].model==m) {
    if(--arena_tables[i].users>0)continue;
    for(int k=0;k<3;k++)free(arena_tables[i].cut[k]);
    free(arena_tables[i].leaf);
    memmove(arena_tables+i,arena_tables+i+1,(arena_ntables-i-1)*sizeof(ArenaOctTable));
    arena_ntables--;
  }
}
