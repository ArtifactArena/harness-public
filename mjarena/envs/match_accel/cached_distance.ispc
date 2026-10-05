// Reuse a leaf only inside the identical table cell selected by exact cuts.
inline int arena_cell(const uniform OctTable* uniform t, const double p[3],
                      double lower[3], double upper[3]) {
  if (t->leaf == NULL) {
    for(uniform int k=0;k<3;k++){lower[k]=0.d;upper[k]=0.d;}
    return -1;
  }
  int index[3];
  for (uniform int k=0; k<3; k++) {
    double guess=(p[k]-t->lo[k])*t->scale[k];
    int i=guess<=0.d?0:guess>=t->n[k]?t->n[k]:(int)guess;
    while(i>0 && p[k]<t->cut[k][i-1])i--;
    while(i<t->n[k] && !(p[k]<t->cut[k][i]))i++;
    lower[k]=i>0?t->cut[k][i-1]:t->lo[k];
    upper[k]=i<t->n[k]?t->cut[k][i]:t->hi[k];
    index[k]=i;
  }
  return t->leaf[(index[0]*(t->n[1]+1)+index[1])*(t->n[2]+1)+index[2]];
}

inline double arena_cached_distance(const uniform Model* uniform m,
    const double point[3], uniform int meshid, int node,
    const double lower[3], const double upper[3]) {
  uniform int adr=m->mesh_octadr[meshid];
  const uniform double* uniform aabb=m->oct_aabb+6*adr;
  const uniform double* uniform coeff=m->oct_coeff+8*adr;
  double p[3]={point[0],point[1],point[2]};
  double box=boxProjection(p,aabb);
  bool hit=node>=0;
  for(uniform int k=0;k<3;k++)hit &= p[k]>=lower[k] && p[k]<upper[k];
  if(!hit)return oct_distance(m,point,meshid);
  double coord[3];
  for(uniform int k=0;k<3;k++) {
    double lo=aabb[6*node+k]-aabb[6*node+3+k];
    double hi=aabb[6*node+k]+aabb[6*node+3+k];
    coord[k]=(p[k]-lo)/(hi-lo);
  }
  double value=0.d;
  for(uniform int i=0;i<8;i++) {
    double w=(i&1?coord[0]:1-coord[0])*
             (i&2?coord[1]:1-coord[1])*
             (i&4?coord[2]:1-coord[2]);
    value+=w*coeff[8*node+i];
  }
  return box>0?value+box:value;
}
