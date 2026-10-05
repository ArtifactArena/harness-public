"""Exact runtime bounds using the same NumPy BLAS kernels and operation order."""
import numpy as np,ctypes
import numpy._core._multiarray_umath as _numpy_core
from libc.stdint cimport int64_t,uintptr_t
from libc.math cimport isnan
cdef extern from "numpy/arrayobject.h":
    void* PyArray_DATA(object array)
    int _import_array() except -1
_import_array()
cdef extern from "mujoco/mujoco.h":
    ctypedef struct mjData:
        double* xpos
        double* xmat
        double* geom_xpos
        double* geom_xmat
ctypedef void (*Gemm)(int,int,int,int64_t,int64_t,int64_t,double,const double*,int64_t,const double*,int64_t,double,double*,int64_t) noexcept
_library=ctypes.CDLL(_numpy_core.__file__)
cdef Gemm gemm=<Gemm><uintptr_t>ctypes.cast(_library.scipy_cblas_dgemm64_,ctypes.c_void_p).value

cdef class Bounds:
    cdef object model,points,world,local
    def __init__(self,model):
        from mjarena.design_shop.utils import _geom_local_points
        self.model=model
        self.points=[np.ascontiguousarray(_geom_local_points(model,g),dtype=np.float64) for g in range(model.ngeom)]
        n=max(len(p) for p in self.points)
        self.world=np.empty((n,3),dtype=np.float64);self.local=np.empty((n,3),dtype=np.float64)
    def extents(self,data,geom_ids,int root):
        cdef mjData* d=<mjData*><uintptr_t>data._address
        cdef double* world=<double*>PyArray_DATA(self.world)
        cdef double* local=<double*>PyArray_DATA(self.local)
        cdef double* points
        cdef double lo[3],hi[3],a,b,x
        cdef int g,n,i,j
        cdef object p,out
        if root<0 or not len(geom_ids):return np.zeros(3,dtype=float)
        for j in range(3):lo[j]=float('inf');hi[j]=-float('inf')
        for g in geom_ids:
            p=self.points[g];n=len(p);points=<double*>PyArray_DATA(p)
            if n==0:raise ValueError('zero-size array to reduction operation minimum which has no identity')
            gemm(101,111,112,n,3,3,1.0,points,3,d.geom_xmat+9*g,3,0.0,world,3)
            for i in range(n):
                for j in range(3):
                    world[3*i+j]=world[3*i+j]+d.geom_xpos[3*g+j]
                    world[3*i+j]=world[3*i+j]-d.xpos[3*root+j]
            gemm(101,111,111,n,3,3,1.0,world,3,d.xmat+9*root,3,0.0,local,3)
            for j in range(3):
                a=local[j];b=local[j]
                for i in range(1,n):
                    x=local[3*i+j]
                    if x<=a or isnan(x):a=x
                    if x>=b or isnan(x):b=x
                if a<=lo[j] or isnan(a):lo[j]=a
                if b>=hi[j] or isnan(b):hi[j]=b
        out=np.empty(3,dtype=np.float64)
        for j in range(3):(<double*>PyArray_DATA(out))[j]=hi[j]-lo[j]
        return out
