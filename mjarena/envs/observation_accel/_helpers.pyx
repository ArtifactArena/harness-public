"""Small-array fast paths with the reference operation order and NumPy LAPACK."""
import numpy as np
cdef extern from "numpy/arrayobject.h":
    void* PyArray_DATA(object array)
    Py_ssize_t* PyArray_STRIDES(object array)
    int _import_array() except -1
_import_array()
import cython
from copy import deepcopy
from numpy.linalg import _umath_linalg
from numpy.linalg._linalg import _raise_linalgerror_lstsq

_RCOND3 = np.finfo(np.float64).eps * 3

include "_native_lstsq.pxi"

@cython.cdivision(True)
def simplex_weights(tail):
    cdef double *tv, *wv
    cdef object tail_array, weights
    cdef Py_ssize_t ts
    cdef double total, value
    cdef int i, n
    cdef bint negative = False
    cdef bint nan = False
    n = len(tail) + 1
    weights = np.empty(n, dtype=np.float64)
    tail_array = tail
    tv = <double*>PyArray_DATA(tail_array)
    ts = PyArray_STRIDES(tail_array)[0] // <Py_ssize_t>sizeof(double)
    wv = <double*>PyArray_DATA(weights)
    if n <= 4:
        # NumPy DOUBLE_pairwise_sum uses a -0 initial accumulator for n < 8;
        # the reduction adds that block sum to its +0 identity.
        total = -0.0
        for i in range(n-1):total = total + tv[i*ts]
        total = 0.0 + total
    else:
        total = tail.sum()
    wv[0] = 1. - total
    for i in range(1, n):
        wv[i] = tv[(i-1) * ts]
    for i in range(n):
        value = wv[i]
        if value != value: nan = True
        if value < -1e-9: negative = True
    if negative and not nan:
        return None
    for i in range(n):
        if wv[i] <= 0.: wv[i] = 0.
    if n <= 4:
        total = -0.0
        for i in range(n):total = total + wv[i]
        total = 0.0 + total
    else:
        total = weights.sum()
    for i in range(n):
        wv[i] = wv[i] / total
    return weights

def witnesses(active):
    cdef double[:] av, bv, pa, pb
    cdef double weight, product
    cdef int i
    a, b = np.zeros(3), np.zeros(3)
    av, bv = a, b
    for point, w in active:
        weight = w
        pa, pb = point[1], point[2]
        for i in range(3):
            product = weight * pa[i]
            av[i] = av[i] + product
            product = weight * pb[i]
            bv[i] = bv[i] + product
    return a, b

def simplex_lstsq(a, b):
    # The exact NumPy 2.1.3 gufunc, signature, cutoff and error handling.
    # Only the unused residual/rank/singular-value wrapper work is omitted.
    if (type(a) is np.ndarray and type(b) is np.ndarray and
            a.dtype == np.float64 and b.dtype == np.float64 and
            a.ndim == 2 and a.shape[0] == 3 and 1 <= a.shape[1] <= 3 and b.shape == (3,)):
        native = _small_lstsq(a,b)
        if native is not None:return native
        with np.errstate(call=_raise_linalgerror_lstsq, invalid='call',
                         over='ignore', divide='ignore', under='ignore'):
            x, resids, rank, s = _umath_linalg.lstsq(a, b[:, None], _RCOND3,
                                                   signature='ddd->ddid')
        return x.squeeze(axis=-1).astype(np.float64, copy=True)
    return np.linalg.lstsq(a, b, rcond=None)[0]

def simplex_lstsq_batch(vertices):
    # Each batch item calls the same LAPACK kernel with the same 3-by-N input.
    if (type(vertices) is np.ndarray and vertices.dtype == np.float64
            and vertices.ndim == 3 and vertices.shape[2] == 3
            and 2 <= vertices.shape[1] <= 4 and vertices.flags.c_contiguous):
        native = _small_lstsq_batch(vertices)
        if native is not None:return native
    edges = (vertices[:, 1:] - vertices[:, :1]).transpose(0, 2, 1)
    rhs = -vertices[:, 0, :, None]
    with np.errstate(call=_raise_linalgerror_lstsq, invalid='call',
                     over='ignore', divide='ignore', under='ignore'):
        x, resids, rank, s = _umath_linalg.lstsq(edges, rhs, _RCOND3,
                                               signature='ddd->ddid')
    return x[..., 0].copy()

def norm(a, axis=None):
    # NumPy 2.1.3's axis=None real-vector path performs exactly this dot/sqrt.
    if axis is None and type(a) is np.ndarray and a.ndim == 1 and a.dtype == np.float64:
        v = a.ravel(order='K')
        return np.sqrt(v.dot(v))
    return np.linalg.norm(a, axis=axis)

def cross(a, b):
    cdef double *av, *bv, *cv
    cdef Py_ssize_t astride, bstride
    cdef object aa, bb, result
    cdef double tmp
    if (type(a) is np.ndarray and type(b) is np.ndarray and
            a.shape == (3,) and b.shape == (3,) and
            a.dtype == np.float64 and b.dtype == np.float64):
        result = np.empty(3, dtype=np.float64)
        aa, bb = a, b
        av, bv, cv = <double*>PyArray_DATA(aa), <double*>PyArray_DATA(bb), <double*>PyArray_DATA(result)
        astride, bstride = PyArray_STRIDES(aa)[0] // <Py_ssize_t>sizeof(double), PyArray_STRIDES(bb)[0] // <Py_ssize_t>sizeof(double)
        # Identical component product/subtraction order to numpy.cross.
        cv[0] = av[1 * astride] * bv[2 * bstride]
        tmp = av[2 * astride] * bv[1 * bstride]
        cv[0] -= tmp
        cv[1] = av[2 * astride] * bv[0 * bstride]
        tmp = av[0 * astride] * bv[2 * bstride]
        cv[1] -= tmp
        cv[2] = av[0 * astride] * bv[1 * bstride]
        tmp = av[1 * astride] * bv[0 * bstride]
        cv[2] -= tmp
        return result
    return np.cross(a, b)

def clone(value, memo=None):
    # Preserve ownership AND aliases; controllers can mutate their snapshots.
    if memo is None:
        memo = {}
    kind = type(value)
    if kind in (str, int, float, bool, type(None)):
        return value
    key = id(value)
    if key in memo:
        return memo[key]
    if kind is np.ndarray and not value.dtype.hasobject:
        result = value.copy(order='K')
        memo[key] = result
        return result
    if kind is dict:
        result = {}
        memo[key] = result
        for k, v in value.items():
            result[clone(k, memo)] = clone(v, memo)
        return result
    if kind is list:
        result = []
        memo[key] = result
        for v in value:
            result.append(clone(v, memo))
        return result
    return deepcopy(value, memo)
