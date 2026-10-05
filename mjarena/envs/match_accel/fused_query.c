/* Evaluate a value and gradient together, retaining each original reduction. */
static mjtNum arena_oct_value_gradient(const mjModel* m,mjtNum grad[3],const mjtNum point[3],int meshid) {
  int adr=m->mesh_octadr[meshid];
  if(adr<0)mju_error("Octree not found");
  const mjtNum* aabb=m->oct_aabb+6*adr;
  const mjtNum* coeff=m->oct_coeff+8*adr;
  const int* child=m->oct_child+8*adr;
  mjtNum p[3]={point[0],point[1],point[2]},w[8],dw[8][3];
  mjtNum box=boxProjection(p,aabb),value=0;
  int node=findOct(w,box<=0?dw:NULL,aabb,child,p);
  for(int i=0;i<8;i++)value+=w[i]*coeff[8*node+i];
  value=box>0?value+box:value;
  mju_zero3(grad);
  if(box<=0) {
    for(int i=0;i<8;i++) {
      grad[0]+=dw[i][0]*coeff[8*node+i];
      grad[1]+=dw[i][1]*coeff[8*node+i];
      grad[2]+=dw[i][2]*coeff[8*node+i];
    }
  } else {
    mjtNum eps=1e-8;
    mjtNum px[3]={point[0]+eps,point[1],point[2]};
    mjtNum py[3]={point[0],point[1]+eps,point[2]};
    mjtNum pz[3]={point[0],point[1],point[2]+eps};
    mjtNum dx=oct_distance(m,px,meshid),dy=oct_distance(m,py,meshid),dz=oct_distance(m,pz,meshid);
    grad[0]=(dx-value)/eps;grad[1]=(dy-value)/eps;grad[2]=(dz-value)/eps;
  }
  return value;
}
static mjtNum arena_geom_value_gradient(mjtNum grad[3],const mjModel* m,const mjData* d,
                                       const mjpPlugin* plugin,int id,const mjtNum p[3],mjtGeom type) {
  if(!plugin && (type==mjGEOM_SDF || type==mjGEOM_MESH))return arena_oct_value_gradient(m,grad,p,id);
  mjtNum value=geomDistance(m,d,plugin,id,p,type);
  geomGradient(grad,m,d,plugin,id,p,type);
  return value;
}
static mjtNum arena_collision_value_gradient(const mjModel* m,const mjData* d,const mjSDF* s,
                                            mjtNum gradient[3],const mjtNum x[3]) {
  mjtNum y[3],grad1[3],grad2[3];
  mju_mulMatVec3(y,s->relmat,x);mju_addTo3(y,s->relpos);
  mjtNum A=arena_geom_value_gradient(grad1,m,d,s->plugin[0],s->id[0],x,s->geomtype[0]);
  mjtNum B=arena_geom_value_gradient(grad2,m,d,s->plugin[1],s->id[1],y,s->geomtype[1]);
  mju_mulMatTVec3(grad2,s->relmat,grad2);
  gradient[0]=grad1[0]+grad2[0];gradient[1]=grad1[1]+grad2[1];gradient[2]=grad1[2]+grad2[2];
  mju_addToScl3(gradient,A>B?grad1:grad2,mju_max(A,B)>0?1:-1);
  return A+B+mju_abs(mju_max(A,B));
}
