# NumPy 2.1.3 umath_linalg.cpp init_gelsd/call_gelsd, specialized to 3 x (1..3).
# Reuse the same workspace that NumPy already reuses within a gufunc batch.
from libc.stdint cimport int64_t, uintptr_t
from libc.stdlib cimport malloc, free
from libc.math cimport isfinite
import ctypes
import numpy._core._multiarray_umath as _numpy_linalg_core

ctypedef void (*_gelsd_type)(int64_t*,int64_t*,int64_t*,double*,int64_t*,double*,int64_t*,double*,double*,int64_t*,double*,int64_t*,int64_t*,int64_t*) noexcept
_lapack_library = ctypes.CDLL(_numpy_linalg_core.__file__)
cdef _gelsd_type _gelsd = <_gelsd_type><uintptr_t>ctypes.cast(_lapack_library.scipy_dgelsd_64_,ctypes.c_void_p).value

cdef class _GelsdWorkspace:
    cdef int64_t m,n,nrhs,lda,ldb,rank,lwork
    cdef double rcond
    cdef double *storage,*a,*b,*s,*work
    cdef int64_t *iwork
    cdef void* work_storage

    def __cinit__(self,int columns):
        cdef int64_t info,integer_count
        cdef double work_count
        self.m,self.n,self.nrhs,self.lda,self.ldb=3,columns,1,3,3
        self.rcond=_RCOND3
        self.storage=<double*>malloc((3*columns+3+columns)*sizeof(double))
        if self.storage==NULL:raise MemoryError()
        self.a=self.storage;self.b=self.a+3*columns;self.s=self.b+3
        self.lwork=-1
        _gelsd(&self.m,&self.n,&self.nrhs,self.a,&self.lda,self.b,&self.ldb,
               self.s,&self.rcond,&self.rank,&work_count,&self.lwork,&integer_count,&info)
        if info != 0:raise np.linalg.LinAlgError('DGELSD workspace query failed')
        self.lwork=<int64_t>work_count
        if self.lwork<=0 or integer_count<=0:raise RuntimeError('Invalid DGELSD workspace size')
        self.work_storage=malloc(self.lwork*sizeof(double)+integer_count*sizeof(int64_t))
        if self.work_storage==NULL:raise MemoryError()
        self.work=<double*>self.work_storage
        self.iwork=<int64_t*>(self.work+self.lwork)

    def __dealloc__(self):
        free(self.storage);free(self.work_storage)

    cdef solve(self):
        cdef int64_t info
        _gelsd(&self.m,&self.n,&self.nrhs,self.a,&self.lda,self.b,&self.ldb,
               self.s,&self.rcond,&self.rank,self.work,&self.lwork,self.iwork,&info)
        if info != 0:raise np.linalg.LinAlgError('SVD did not converge in Linear Least Squares')

_GELSD_WORKSPACES=tuple(_GelsdWorkspace(n) for n in (1,2,3))

cdef object _small_lstsq(object a,object b):
    cdef int n=a.shape[1]
    cdef _GelsdWorkspace workspace=_GELSD_WORKSPACES[n-1]
    cdef double* av=<double*>PyArray_DATA(a)
    cdef double* bv=<double*>PyArray_DATA(b)
    cdef Py_ssize_t rstride=PyArray_STRIDES(a)[0]//<Py_ssize_t>sizeof(double)
    cdef Py_ssize_t cstride=PyArray_STRIDES(a)[1]//<Py_ssize_t>sizeof(double)
    cdef Py_ssize_t bstride=PyArray_STRIDES(b)[0]//<Py_ssize_t>sizeof(double)
    cdef int i,j
    cdef object result
    cdef double* output
    # Allocate before touching shared scratch: an allocation could run a Python
    # finalizer that re-enters this helper. No Python callbacks occur below.
    result=np.empty(n,dtype=np.float64);output=<double*>PyArray_DATA(result)
    for i in range(3):
        workspace.b[i]=bv[i*bstride]
        if not isfinite(workspace.b[i]):return None
        for j in range(n):
            workspace.a[3*j+i]=av[i*rstride+j*cstride]
            if not isfinite(workspace.a[3*j+i]):return None
    workspace.solve()
    for i in range(n):output[i]=workspace.b[i]
    return result

cdef object _small_lstsq_batch(object vertices):
    cdef int n=vertices.shape[1]-1
    cdef int count=vertices.shape[0]
    cdef _GelsdWorkspace workspace=_GELSD_WORKSPACES[n-1]
    cdef double* values=<double*>PyArray_DATA(vertices)
    cdef object result=np.empty((count,n),dtype=np.float64)
    cdef double* output=<double*>PyArray_DATA(result)
    cdef double* v
    cdef int batch,i,j
    for batch in range(count):
        v=values+batch*(n+1)*3
        for i in range(3):
            workspace.b[i]=-v[i]
            if not isfinite(workspace.b[i]):return None
            for j in range(n):
                workspace.a[3*j+i]=v[3*(j+1)+i]-v[i]
                if not isfinite(workspace.a[3*j+i]):return None
        workspace.solve()
        for i in range(n):output[batch*n+i]=workspace.b[i]
    return result
