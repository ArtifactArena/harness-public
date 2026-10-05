# Primitive GJK uses at most five support points and subsets of at most four.
# Keep current-simplex subsets in a 32-entry cache, remapping bit masks when
# inactive points are removed. Enumeration and all floating-point operations
# remain in precisely the reference order.
from libc.string cimport memset, memcpy

cdef struct _RawPoint:
    double position[3]
    double left[3]
    double right[3]

cdef struct _RawSubset:
    int state  # 0 uncomputed, 1 valid, 2 infeasible
    double squared
    double weights[4]
    double point[3]

cdef int _subset_length[6]
cdef int _subset_mask[6][30]
cdef int _subset_count[6][30]
cdef int _subset_ids[6][30][4]

def _initialize_subsets():
    cdef int n,count,row,i
    for n in range(1,6):
        row=0
        for count in range(1,min(4,n)+1):
            for ids in combinations(range(n),count):
                _subset_count[n][row]=count
                _subset_mask[n][row]=sum(1<<i for i in ids)
                for i in range(count):_subset_ids[n][row][i]=ids[i]
                row+=1
        _subset_length[n]=row
_initialize_subsets()

@cython.cdivision(True)
cdef int _solve_raw_subset(_RawPoint* points,int* ids,int count,_RawSubset* entry) except -1:
    cdef double vertices[12]
    cdef double total,value
    cdef int i,j,n=count-1
    cdef bint negative=False,nan=False
    cdef _GelsdWorkspace workspace
    for j in range(count):
        for i in range(3):vertices[3*j+i]=points[ids[j]].position[i]
    if count==1:
        entry.weights[0]=1.
    else:
        workspace=_GELSD_WORKSPACES[n-1]
        for i in range(3):
            workspace.b[i]=-vertices[i]
            if not isfinite(workspace.b[i]):return 0
            for j in range(n):
                workspace.a[3*j+i]=vertices[3*(j+1)+i]-vertices[i]
                if not isfinite(workspace.a[3*j+i]):return 0
        workspace.solve()
        total=-0.0
        for i in range(n):total=total+workspace.b[i]
        total=0.0+total
        entry.weights[0]=1.-total
        for i in range(n):entry.weights[i+1]=workspace.b[i]
        for i in range(count):
            value=entry.weights[i]
            if value!=value:nan=True
            if value < -1e-9:negative=True
        if negative and not nan:
            entry.state=2
            return 1
        for i in range(count):
            if entry.weights[i]<=0.:entry.weights[i]=0.
        total=-0.0
        for i in range(count):total=total+entry.weights[i]
        total=0.0+total
        for i in range(count):entry.weights[i]=entry.weights[i]/total
    if count==1:
        for i in range(3):entry.point[i]=0.0+entry.weights[0]*vertices[i]
    else:_gemv(101,112,count,3,1.0,vertices,3,entry.weights,1,0.0,entry.point,1)
    entry.squared=0.0
    entry.squared+=_ddot(3,entry.point,1,entry.point,1)
    entry.state=1
    return 1

cdef int _closest_raw(int count,_RawPoint* points,_RawSubset* cache) except -1:
    cdef int row,mask,best=0
    for row in range(_subset_length[count]):
        mask=_subset_mask[count][row]
        if cache[mask].state==0:
            if not _solve_raw_subset(points,_subset_ids[count][row],_subset_count[count][row],cache+mask):return 0
        if cache[mask].state==2:continue
        if best==0 or cache[mask].squared<cache[best].squared:best=mask
    return best

cdef void _vertex_raw(_SupportBase sa,_SupportBase sb,double* direction,_RawPoint* point) except *:
    cdef double negated[3]
    cdef int i
    for i in range(3):negated[i]=-direction[i]
    sa.support_raw(direction,point.left)
    sb.support_raw(negated,point.right)
    for i in range(3):point.position[i]=point.left[i]-point.right[i]

cdef object _witnesses_raw(int count,_RawPoint* points,int mask,_RawSubset* best,double distance):
    cdef object a=np.zeros(3),b=np.zeros(3)
    cdef double *av=<double*>PyArray_DATA(a),*bv=<double*>PyArray_DATA(b)
    cdef double weight,product
    cdef int i,j,k=0
    for j in range(count):
        if mask & (1<<j):
            weight=best.weights[k];k+=1
            if weight>1e-12:
                for i in range(3):
                    product=weight*points[j].left[i];av[i]=av[i]+product
                    product=weight*points[j].right[i];bv[i]=bv[i]+product
    return distance,a,b

@cython.cdivision(True)
cdef object _convex_primitives_array(_SupportBase sa,_SupportBase sb,object direction):
    cdef _RawPoint points[5]
    cdef _RawPoint next_points[5]
    cdef _RawPoint new
    cdef _RawSubset cache[32]
    cdef _RawSubset next_cache[32]
    cdef double v[3]
    cdef double gap[3]
    cdef double* initial
    cdef double length,distance,lower,product,threshold
    cdef int i,j,k,count=1,iteration,best,active_count,mask,old_mask
    cdef int active_ids[4]
    cdef bint duplicate
    array=np.asarray(direction,dtype=float)
    if array.shape!=(3,) or array.strides!=(8,):return _convex_distance_legacy(sa,sb,direction)
    initial=<double*>PyArray_DATA(array)
    for i in range(3):v[i]=initial[i]
    if _norm_raw(v,3)<1e-12:v[0],v[1],v[2]=1.,0.,0.
    length=_norm_raw(v,3)
    for i in range(3):v[i]=v[i]/length
    _vertex_raw(sa,sb,v,points)
    memset(cache,0,sizeof(cache))
    for iteration in range(256):
        best=_closest_raw(count,points,cache)
        if best==0:return _convex_distance_legacy(sa,sb,direction)
        distance=_norm_raw(cache[best].point,3)
        if distance<1e-10:return _witnesses_raw(count,points,best,cache+best,0.)
        for i in range(3):v[i]=-cache[best].point[i]/distance
        _vertex_raw(sa,sb,v,&new)
        product=0.0;product+=_ddot(3,cache[best].point,1,new.position,1)
        lower=product/distance
        if not lower>0.:lower=0.
        threshold=distance if distance>1. else 1.
        if distance-lower<=1e-9*threshold:return _witnesses_raw(count,points,best,cache+best,distance)
        active_count=0;k=0;duplicate=False
        for j in range(count):
            if best & (1<<j):
                if cache[best].weights[k]>1e-12:
                    active_ids[active_count]=j
                    next_points[active_count]=points[j]
                    active_count+=1
                    for i in range(3):gap[i]=new.position[i]-points[j].position[i]
                    if _norm_raw(gap,3)<1e-12:duplicate=True
                k+=1
        if duplicate:return _witnesses_raw(count,points,best,cache+best,_norm_raw(cache[best].point,3))
        memset(next_cache,0,sizeof(next_cache))
        for mask in range(1,1<<active_count):
            old_mask=0
            for j in range(active_count):
                if mask & (1<<j):old_mask |= 1<<active_ids[j]
            next_cache[mask]=cache[old_mask]
        next_points[active_count]=new;count=active_count+1
        memcpy(points,next_points,count*sizeof(_RawPoint))
        memcpy(cache,next_cache,sizeof(cache))
    best=_closest_raw(count,points,cache)
    if best==0:return _convex_distance_legacy(sa,sb,direction)
    return _witnesses_raw(count,points,best,cache+best,_norm_raw(cache[best].point,3))
