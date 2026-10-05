# Keep NumPy's DGELSD, barycentric normalization and BLAS operation order, while
# storing each cached subset in C fields instead of allocating four tiny arrays.
import cython
_RCOND3 = np.finfo(np.float64).eps * 3
include "_native_lstsq.pxi"

cdef class _NativeSubset:
    cdef double squared
    cdef double weights[4]
    cdef double point[3]
    cdef int valid
    cdef object keepalive

@cython.cdivision(True)
cdef _NativeSubset _solve_subset(object points, object ids):
    cdef _NativeSubset entry = _NativeSubset()
    cdef int count=len(ids), i,j,n=count-1
    cdef double vertices[12]
    cdef double* p
    cdef double total,value
    cdef bint negative=False, nan=False
    cdef _GelsdWorkspace workspace
    # Allocate all Python objects before touching shared LAPACK workspace.
    entry.keepalive=tuple(points[i] for i in ids)
    for j in range(count):
        p=<double*>PyArray_DATA(points[ids[j]][0])
        for i in range(3):vertices[3*j+i]=p[i]
    if count==1:
        entry.weights[0]=1.
    else:
        workspace=_GELSD_WORKSPACES[n-1]
        for i in range(3):
            workspace.b[i]=-vertices[i]
            if not isfinite(workspace.b[i]):entry.valid=-1;return entry
            for j in range(n):
                workspace.a[3*j+i]=vertices[3*(j+1)+i]-vertices[i]
                if not isfinite(workspace.a[3*j+i]):entry.valid=-1;return entry
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
            entry.valid=0
            return entry
        for i in range(count):
            if entry.weights[i]<=0.:entry.weights[i]=0.
        total=-0.0
        for i in range(count):total=total+entry.weights[i]
        total=0.0+total
        for i in range(count):entry.weights[i]=entry.weights[i]/total
    if count==1:
        for i in range(3):entry.point[i]=0.0+entry.weights[0]*vertices[i]
    else:
        _gemv(101,112,count,3,1.0,vertices,3,entry.weights,1,0.0,entry.point,1)
    entry.squared=0.0
    entry.squared+=_ddot(3,entry.point,1,entry.point,1)
    entry.valid=1
    return entry

cdef object _select_simplex_native(object points,object cache):
    cdef _NativeSubset entry,best=None
    cdef int count,i,j
    cdef double weight,product
    cdef double* av
    cdef double* bv
    cdef double* pv
    cdef double* source
    point_ids=[id(point) for point in points]
    best_ids=None
    for count in range(1,min(4,len(points))+1):
        for ids in combinations(range(len(points)),count):
            key=tuple(point_ids[i] for i in ids)
            entry=cache.get(key)
            if entry is None:
                entry=_solve_subset(points,ids)
                if entry.valid<0:return None
                cache[key]=entry
            if not entry.valid:continue
            if best is None or entry.squared<best.squared:
                best=entry;best_ids=ids
    return best,best_ids

cdef object _closest_simplex_native(object points,object cache):
    cdef _NativeSubset best
    cdef int i,j
    cdef double weight,product
    cdef double *av,*bv,*pv,*source
    chosen=_select_simplex_native(points,cache)
    if chosen is None:return _closest_simplex_legacy(points)
    best,best_ids=chosen
    p=np.empty(3,dtype=np.float64);a=np.zeros(3);b=np.zeros(3)
    pv=<double*>PyArray_DATA(p);av=<double*>PyArray_DATA(a);bv=<double*>PyArray_DATA(b)
    for i in range(3):pv[i]=best.point[i]
    active=[]
    for j in range(len(best_ids)):
        weight=best.weights[j]
        if weight>1e-12:
            point=points[best_ids[j]];active.append(point)
            source=<double*>PyArray_DATA(point[1])
            for i in range(3):
                product=weight*source[i];av[i]=av[i]+product
            source=<double*>PyArray_DATA(point[2])
            for i in range(3):
                product=weight*source[i];bv[i]=bv[i]+product
    return active,p,a,b


def _closest_simplex(points,cache=None):
    # Preserve the general reference path for nonstandard external layouts.
    for point in points:
        for vector in point:
            if not (type(vector) is np.ndarray and vector.dtype==np.float64
                    and vector.shape==(3,) and vector.strides==(8,)):
                return _closest_simplex_legacy(points)
    return _closest_simplex_native(points,{} if cache is None else cache)


def _closest_simplex_many(point_lists,caches):
    return [_closest_simplex(points,cache) for points,cache in zip(point_lists,caches)]
