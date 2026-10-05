# Resolve the BLAS already loaded by NumPy; never load a different numerical backend.
# Mirrors NumPy 2.1.3 arraytypes.c.src DOUBLE_dot and matmul.c.src DOUBLE_gemv.
from libc.stdint cimport int64_t, uintptr_t
from libc.math cimport sqrt
import ctypes
import numpy._core._multiarray_umath as _numpy_core

ctypedef double (*_ddot_type)(int64_t, const double*, int64_t, const double*, int64_t) noexcept
ctypedef void (*_gemv_type)(int, int, int64_t, int64_t, double, const double*, int64_t, const double*, int64_t, double, double*, int64_t) noexcept
_blas_library = ctypes.CDLL(_numpy_core.__file__)
cdef _ddot_type _ddot = <_ddot_type><uintptr_t>ctypes.cast(_blas_library.scipy_cblas_ddot64_,ctypes.c_void_p).value
cdef _gemv_type _gemv = <_gemv_type><uintptr_t>ctypes.cast(_blas_library.scipy_cblas_dgemv64_,ctypes.c_void_p).value

cdef inline double _norm_raw(double* vector, int count):
    cdef double squared = 0.0
    squared += _ddot(count,vector,1,vector,1)
    return sqrt(squared)

cdef double _norm_vector(object vector):
    if type(vector) is np.ndarray and vector.dtype == np.float64 and vector.shape == (3,) and vector.strides == (8,):
        return _norm_raw(<double*>PyArray_DATA(vector),3)
    return vector_norm(vector)

cdef double _squared3(object p):
    cdef double result = 0.0
    cdef double* values = <double*>PyArray_DATA(p)
    result += _ddot(3,values,1,values,1)
    return result

cdef object _weighted_point(object weights,object vertices):
    cdef object output = np.empty(3,dtype=np.float64)
    cdef double* out = <double*>PyArray_DATA(output)
    cdef double* w = <double*>PyArray_DATA(weights)
    cdef double* v = <double*>PyArray_DATA(vertices)
    cdef int count = len(weights)
    cdef int i
    if count == 1:
        for i in range(3):
            out[i] = 0.0 + w[0]*v[i]
    else:
        _gemv(101,112,count,3,1.0,v,3,w,1,0.0,out,1)
    return output
