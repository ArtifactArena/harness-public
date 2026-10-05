/* Bounds enclose the nonpositive *interpolated* SDF, including its exterior
   extension. They do not assume the mesh surface equals the SDF zero set. */
#include <float.h>
typedef struct { double* box; unsigned char* valid; } ArenaReject;

static int arena_reject_node(const mjModel* m, int adr, int node,
                             const double* root, double* boxes) {
  const double* a=m->oct_aabb+6*(adr+node);
  const int* child=m->oct_child+8*(adr+node);
  double* out=boxes+6*(adr+node);
  for(int k=0;k<3;k++){out[k]=INFINITY;out[k+3]=-INFINITY;}
  int leaf=1;for(int j=0;j<8;j++)if(child[j]>=0)leaf=0;
  if(!leaf) {
    for(int j=0;j<8;j++)if(child[j]>=0) {
      if(!arena_reject_node(m,adr,child[j],root,boxes))return 0;
      const double* b=boxes+6*(adr+child[j]);
      for(int k=0;k<3;k++){out[k]=fmin(out[k],b[k]);out[k+3]=fmax(out[k+3],b[k+3]);}
    }
    return 1;
  }
  long double lo[3],hi[3],eta[3];
  for(int k=0;k<3;k++) {
    // Match the rounded leaf endpoints used by findOct, then enlarge its
    // 1e-8 membership tolerance. Unsupported scales use the ordinary kernel.
    lo[k]=a[k]-a[k+3];hi[k]=a[k]+a[k+3];
    if(!isfinite((double)lo[k]) || !isfinite((double)hi[k]) ||
       fabsl(lo[k])>1000 || fabsl(hi[k])>1000 || hi[k]-lo[k]<2e-6L)return 0;
    eta[k]=2e-8L/(hi[k]-lo[k]);
  }
  const double* c=m->oct_coeff+8*(adr+node);
  long double magnitude=0,minimum=LDBL_MAX,maximum=-LDBL_MAX;
  for(int j=0;j<8;j++) {
    if(!isfinite(c[j]) || fabs(c[j])>1e6)return 0;
    magnitude=fmaxl(magnitude,fabsl(c[j]));
    minimum=fminl(minimum,c[j]);maximum=fmaxl(maximum,c[j]);
  }
  // The weights sum to one. Outside [0,1]^3 their total absolute weight
  // is at most product(1+2*eta), giving this conservative extrapolation bound.
  long double weight=(1+2*eta[0])*(1+2*eta[1])*(1+2*eta[2]);
  long double lower=minimum-.5L*(weight-1)*(maximum-minimum);
  lower-=1e-10L*(1+magnitude)*weight;
  if(lower>0)return 1;
  long double exterior=-lower+2e-6L;
  for(int k=0;k<3;k++) {
    long double low=lo[k]-2e-8L,high=hi[k]+2e-8L;
    // boxProjection moves exterior queries 1e-6 inside the root. Only leaves
    // in that boundary strip can contribute to a negative exterior value.
    if(lo[k]<=root[k]-root[k+3]+1.1e-6L)low-=exterior;
    if(hi[k]>=root[k]+root[k+3]-1.1e-6L)high+=exterior;
    out[k]=nextafter((double)low,-INFINITY);
    out[k+3]=nextafter((double)high,INFINITY);
  }
  return 1;
}

static ArenaReject* arena_reject_create(const mjModel* m) {
  if(m->noct<=0 || m->noct>2000000 || m->nplugin)return NULL;
  ArenaReject* r=calloc(1,sizeof(*r));if(!r)return NULL;
  r->box=malloc((size_t)m->noct*6*sizeof(double));
  r->valid=calloc(m->nmesh,1);
  if(!r->box || !r->valid){free(r->box);free(r->valid);free(r);return NULL;}
  for(int i=0;i<m->nmesh;i++) {
    int adr=m->mesh_octadr[i];
    if(adr>=0)r->valid[i]=arena_reject_node(m,adr,0,m->oct_aabb+6*adr,r->box);
  }
  return r;
}
static void arena_reject_destroy(ArenaReject* r) {
  if(r){free(r->box);free(r->valid);free(r);}
}

static int arena_reject_overlap(const mjModel* m,const ArenaReject* r,int adr,int node,
                                const double center[3],const double extent[3],double radius2) {
  const double* b=r->box+6*(adr+node);
  if(b[0]>b[3])return 0;
  double distance2=0;
  for(int k=0;k<3;k++) {
    if(center[k]+extent[k]<b[k] || center[k]-extent[k]>b[k+3])return 0;
    double delta=center[k]<b[k]?b[k]-center[k]:center[k]>b[k+3]?center[k]-b[k+3]:0;
    distance2+=delta*delta;
  }
  if(distance2>radius2)return 0;
  const int* child=m->oct_child+8*(adr+node);
  int leaf=1;
  for(int j=0;j<8;j++)if(child[j]>=0) {
    leaf=0;
    if(arena_reject_overlap(m,r,adr,child[j],center,extent,radius2))return 1;
  }
  return leaf;
}

static int arena_reject_pair(const mjModel* m,const mjData* d,const ArenaReject* r,int g1,int g2) {
  int type=m->geom_type[g1];
  if(!r || m->geom_type[g2]!=mjGEOM_SDF ||
     (type!=mjGEOM_SPHERE && type!=mjGEOM_CAPSULE && type!=mjGEOM_CYLINDER && type!=mjGEOM_BOX))return 0;
  int mid=m->geom_dataid[g2];if(mid<0 || !r->valid[mid])return 0;
  double q1[4],q2[4],offset[3],rotation[9];
  mju_mat2Quat(q1,d->geom_xmat+9*g1);mju_mat2Quat(q2,d->geom_xmat+9*g2);
  mapPose(d->geom_xpos+3*g2,q2,d->geom_xpos+3*g1,q1,offset,rotation);
  long double a[9],inv[9];
  for(int i=0;i<9;i++){a[i]=rotation[i];if(!isfinite(rotation[i]) || fabs(rotation[i])>2)return 0;}
  for(int i=0;i<3;i++)if(!isfinite(offset[i]) || fabs(offset[i])>1000)return 0;
  inv[0]=a[4]*a[8]-a[5]*a[7];inv[1]=a[2]*a[7]-a[1]*a[8];inv[2]=a[1]*a[5]-a[2]*a[4];
  inv[3]=a[5]*a[6]-a[3]*a[8];inv[4]=a[0]*a[8]-a[2]*a[6];inv[5]=a[2]*a[3]-a[0]*a[5];
  inv[6]=a[3]*a[7]-a[4]*a[6];inv[7]=a[1]*a[6]-a[0]*a[7];inv[8]=a[0]*a[4]-a[1]*a[3];
  long double det=a[0]*inv[0]+a[1]*inv[3]+a[2]*inv[6];
  if(fabsl(det)<.9L || fabsl(det)>1.1L)return 0;
  for(int i=0;i<9;i++)inv[i]/=det;
  double center[3];long double norm2=0;
  for(int i=0;i<3;i++) {
    center[i]=(double)(-inv[3*i]*offset[0]-inv[3*i+1]*offset[1]-inv[3*i+2]*offset[2]);
    long double row=0;
    for(int j=0;j<3;j++) {
      long double dot=0;for(int k=0;k<3;k++)dot+=inv[3*i+k]*inv[3*j+k];
      row+=fabsl(dot);
    }
    norm2=fmaxl(norm2,row);
  }
  const double* size=m->geom_size+3*g1;
  long double half[3]={size[0],size[0],size[0]},bound=size[0];
  if(type==mjGEOM_CYLINDER){half[2]=size[1];bound=sqrtl(half[0]*half[0]+half[2]*half[2]);}
  if(type==mjGEOM_CAPSULE){half[2]=size[0]+size[1];bound=half[2];}
  if(type==mjGEOM_BOX){half[1]=size[1];half[2]=size[2];bound=sqrtl(half[0]*half[0]+half[1]*half[1]+half[2]*half[2]);}
  for(int k=0;k<3;k++)if(!isfinite((double)half[k]) || half[k]<0 || half[k]>1000)return 0;
  // Includes inverse/center error, primitive-distance rounding, and rounded
  // matrix-vector evaluation at any point in the supported coordinate range.
  double radius=(double)((bound+1e-7L)*sqrtl(norm2))+1e-7;
  double extent[3];
  for(int k=0;k<3;k++)extent[k]=type==mjGEOM_SPHERE?radius:
    (double)(fabsl(inv[3*k])*half[0]+fabsl(inv[3*k+1])*half[1]+fabsl(inv[3*k+2])*half[2])+1e-6;
  return !arena_reject_overlap(m,r,m->mesh_octadr[mid],0,center,extent,radius*radius);
}
