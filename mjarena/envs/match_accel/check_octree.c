/* Exact oracle checks for leaf selection and interpolation at split boundaries. */
static int arena_check_point(const ArenaOctTable* t,const double p[3]) {
  mjtNum w1[8],w2[8],d1[8][3],d2[8][3];
  int a=arena_reference_findOct(w1,d1,t->aabb,t->child,p);
  int b=findOct(w2,d2,t->aabb,t->child,p);
  return a!=b || memcmp(w1,w2,sizeof(w1)) || memcmp(d1,d2,sizeof(d1));
}
int arena_check_octrees(const mjModel* m) {
  arena_register_tables(m);unsigned seed=42;int tested=0;
  for(int i=0;i<arena_ntables;i++) {
    ArenaOctTable* t=arena_tables+i;if(t->model!=m)continue;
    for(int axis=0;axis<3;axis++)for(int cut=-1;cut<=t->n[axis];cut++)for(int side=-1;side<=1;side++)for(int trial=0;trial<32;trial++) {
      double p[3];
      for(int k=0;k<3;k++) {seed=1664525*seed+1013904223;p[k]=t->lo[k]+(t->hi[k]-t->lo[k])*(seed/(double)UINT32_MAX);}
      double v=cut<0?t->lo[axis]:cut==t->n[axis]?t->hi[axis]:t->cut[axis][cut];
      p[axis]=side<0?nextafter(v,-INFINITY):side>0?nextafter(v,INFINITY):v;
      if(arena_check_point(t,p)){arena_unregister_tables(m);return -1;}
      tested++;
    }
  }
  arena_unregister_tables(m);
  return tested;
}
