/* Same per-point iteration order, compact active SIMD lanes between searches. */
#ifdef ARENA_VERIFY_SIMD
static unsigned long long arena_simd_checks[2];
void arena_simd_check_counts(unsigned long long* out) {
  memcpy(out,arena_simd_checks,sizeof(arena_simd_checks));
}
#endif
static void arena_wavefront(struct Model* m,struct SDF* s,double* points,
                            double* depths,int count,int iterations,
                            const mjModel* reference_model,const mjData* reference_data,const mjSDF* reference_sdf) {
  int active[mjMAXCONPAIR],pending[mjMAXCONPAIR],next[mjMAXCONPAIR];
  double packed[3*mjMAXCONPAIR],gradpacked[3*mjMAXCONPAIR],values[mjMAXCONPAIR];
  double grad[3*mjMAXCONPAIR],initial[3*mjMAXCONPAIR];
  double alpha[mjMAXCONPAIR],wolfe[mjMAXCONPAIR],dist0[mjMAXCONPAIR];
  int na=count;
  for(int i=0;i<count;i++){active[i]=i;depths[i]=mjMAXVAL;}
  for(int iteration=0;iteration<iterations && na;iteration++) {
    for(int j=0;j<na;j++)for(int k=0;k<3;k++)packed[k*na+j]=points[3*active[j]+k];
    arena_batch_grad(m,s,packed,gradpacked,values,na);
    int np=0,nn=0;
    for(int j=0;j<na;j++) {
      int i=active[j];double* g=grad+3*i;
      for(int k=0;k<3;k++)g[k]=gradpacked[k*na+j];
      if(!isfinite(g[0]) || !isfinite(g[1]) || !isfinite(g[2]) || !isfinite(values[j])) {
        arena_mjc_gradient(reference_model,reference_data,reference_sdf,g,points+3*i);
        values[j]=arena_mjc_distance(reference_model,reference_data,reference_sdf,points+3*i);
      }
#ifdef ARENA_VERIFY_SIMD
      double reference_gradient[3],reference_value;
      arena_mjc_gradient(reference_model,reference_data,reference_sdf,reference_gradient,points+3*i);
      reference_value=arena_mjc_distance(reference_model,reference_data,reference_sdf,points+3*i);
      if(memcmp(g,reference_gradient,sizeof(reference_gradient)) ||
         memcmp(values+j,&reference_value,sizeof(double)))mju_error("SIMD gradient/value differs from scalar reference");
      arena_simd_checks[0]++;
#endif
      if(isnan(g[0]) || g[0]>mjMAXVAL || g[0]<-mjMAXVAL ||
         isnan(g[1]) || g[1]>mjMAXVAL || g[1]<-mjMAXVAL ||
         isnan(g[2]) || g[2]>mjMAXVAL || g[2]<-mjMAXVAL) {depths[i]=mjMAXVAL;continue;}
      memcpy(initial+3*i,points+3*i,3*sizeof(double));
      dist0[i]=values[j];alpha[i]=2.;
      wolfe[i]=-0.1*alpha[i]*arena_mju_dot3(g,g);
      pending[np++]=i;
    }
    while(np) {
      for(int j=0;j<np;j++) {
        int i=pending[j];alpha[i]*=.5;wolfe[i]*=.5;
        arena_mju_addScl3(points+3*i,initial+3*i,grad+3*i,-alpha[i]);
        for(int k=0;k<3;k++)packed[k*np+j]=points[3*i+k];
      }
      arena_batch_distance(m,s,packed,values,np);
      int again=0;
      for(int j=0;j<np;j++) {
        int i=pending[j];double distance=values[j];
        if(!isfinite(distance))distance=arena_mjc_distance(reference_model,reference_data,reference_sdf,points+3*i);
#ifdef ARENA_VERIFY_SIMD
        double reference_value=arena_mjc_distance(reference_model,reference_data,reference_sdf,points+3*i);
        if(memcmp(&distance,&reference_value,sizeof(double)))mju_error("SIMD line-search distance differs from scalar reference");
        arena_simd_checks[1]++;
#endif
        depths[i]=distance;
        if(alpha[i]>1e-4 && distance-dist0[i]>wolfe[i])pending[again++]=i;
        else if(!(dist0[i]<distance))next[nn++]=i;
      }
      np=again;
    }
    memcpy(active,next,nn*sizeof(int));na=nn;
  }
}
static void arena_wavefront_model(const mjModel* m,struct Model* out,struct OctTable* tables) {
  memset(tables,0,m->nmesh*sizeof(struct OctTable));
  for(int mid=0;mid<m->nmesh;mid++) {
    int adr=m->mesh_octadr[mid];if(adr<0)continue;
    for(int j=0;j<arena_ntables;j++)if(arena_tables[j].model==m && arena_tables[j].aabb==m->oct_aabb+6*adr) {
      ArenaOctTable* a=arena_tables+j;struct OctTable* b=tables+mid;
      memcpy(b->n,a->n,sizeof(b->n));memcpy(b->cut,a->cut,sizeof(b->cut));
      memcpy(b->lo,a->lo,sizeof(b->lo));memcpy(b->hi,a->hi,sizeof(b->hi));
      memcpy(b->scale,a->scale,sizeof(b->scale));b->leaf=a->leaf;
    }
  }
  *out=(struct Model){m->geom_size,m->mesh_octadr,m->oct_child,m->oct_aabb,m->oct_coeff,m->opt.sdf_iterations,tables};
}
