from libc.math cimport fabs

# NumPy 2.1.3's x86-64 SSE2 einsum reduction for contiguous triples uses two
# lanes: (0 + x0*y0 + x2*y2) + (0 + x1*y1), then adds the zero output.
# Keep every operation separate: build.py disables contraction/reassociation.
cdef inline double _einsum3(double x0,double x1,double x2,
                             double y0,double y1,double y2) noexcept:
    cdef double even=0., odd=0., product
    product=x0*y0;even=even+product
    product=x1*y1;odd=odd+product
    product=x2*y2;even=even+product
    return 0.+(even+odd)

@cython.boundscheck(False)
@cython.wraparound(False)
@cython.cdivision(True)
def _mesh_certificate_terms(point, prepared):
    """Diagnostic terms for exact tests of the native certificate arithmetic."""
    cdef const double[:, :] a=prepared[0], b=prepared[1], c=prepared[2], normal=prepared[3]
    cdef const double[:] area=prepared[4]
    cdef const double[:] p=point
    cdef object result=np.empty((a.shape[0],3))
    cdef double[:, :] output=result
    cdef double u[3]
    cdef double v[3]
    cdef double w[3]
    cdef double alpha,beta
    cdef Py_ssize_t i,j
    for i in range(a.shape[0]):
        output[i,0]=fabs(_einsum3(p[0]-a[i,0],p[1]-a[i,1],p[2]-a[i,2],normal[i,0],normal[i,1],normal[i,2]))
        for j in range(3):u[j]=b[i,j]-p[j];v[j]=c[i,j]-p[j];w[j]=a[i,j]-p[j]
        alpha=_einsum3(u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0],normal[i,0],normal[i,1],normal[i,2])/area[i]
        beta=_einsum3(v[1]*w[2]-v[2]*w[1],v[2]*w[0]-v[0]*w[2],v[0]*w[1]-v[1]*w[0],normal[i,0],normal[i,1],normal[i,2])/area[i]
        output[i,1]=alpha;output[i,2]=beta
    return result

@cython.boundscheck(False)
@cython.wraparound(False)
@cython.cdivision(True)
def _on_prepared_mesh_surface(point, prepared):
    cdef const double[:, :] a,b,c,normal
    cdef const double[:] area,tolerance,p
    cdef double u[3]
    cdef double v[3]
    cdef double w[3]
    cdef double plane,alpha,beta,gamma
    cdef Py_ssize_t i,j
    if (not _MESH_REDUCTION_COMPATIBLE or type(point) is not np.ndarray or point.dtype!=np.float64 or point.shape!=(3,)
            or any(x.dtype!=np.float64 or x.strides[x.ndim-1]!=8 for x in prepared)):
        return _on_prepared_mesh_surface_legacy(point,prepared)
    a,b,c,normal,area,tolerance=prepared
    p=point
    for i in range(a.shape[0]):
        if not area[i]>0.:continue
        plane=fabs(_einsum3(p[0]-a[i,0],p[1]-a[i,1],p[2]-a[i,2],normal[i,0],normal[i,1],normal[i,2]))
        if not plane<=tolerance[i]:continue
        for j in range(3):u[j]=b[i,j]-p[j];v[j]=c[i,j]-p[j];w[j]=a[i,j]-p[j]
        alpha=_einsum3(u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0],normal[i,0],normal[i,1],normal[i,2])/area[i]
        beta=_einsum3(v[1]*w[2]-v[2]*w[1],v[2]*w[0]-v[0]*w[2],v[0]*w[1]-v[1]*w[0],normal[i,0],normal[i,1],normal[i,2])/area[i]
        gamma=1.-alpha-beta
        if alpha>=-1e-12 and beta>=-1e-12 and gamma>=-1e-12:return True
    return False


def _check_mesh_reduction():
    # Guard the SIMD-sensitive reduction before enabling this fast path.
    left=np.array([[1e16,1.,-1e16],[1.,-1e16,1e16],[-0.,-0.,-0.],
                   [1.,2.,3.],[1e-200,1e-200,-1e-200]],dtype=np.float64)
    right=np.ones_like(left)
    expected=np.einsum('ij,ij->i',left,right)
    actual=np.array([_einsum3(row[0],row[1],row[2],1.,1.,1.) for row in left])
    return actual.tobytes()==expected.tobytes()

_MESH_REDUCTION_COMPATIBLE = _check_mesh_reduction()
