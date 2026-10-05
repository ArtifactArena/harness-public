"""Surface proximity without convexifying concave mesh/SDF geometry.

MuJoCo's SDF collider only reports nearby penetrations, so separated SDFs
are queried against their original triangles using convex distance queries.
"""
from itertools import combinations
import numpy as np
cdef extern from "numpy/arrayobject.h":
    void* PyArray_DATA(object array)
    Py_ssize_t* PyArray_STRIDES(object array)
    int _import_array() except -1
_import_array()
import mujoco
from ._helpers import norm as vector_norm, cross, simplex_lstsq, simplex_weights, witnesses, simplex_lstsq_batch

include "_native_blas.pxi"


def _closest_simplex_legacy(points, cache=None):
    """Reuse unchanged simplex subsets within one distance query, exactly."""
    best = None
    point_ids = [id(point) for point in points]
    for count in range(1, min(4, len(points)) + 1):
        subsets = [(ids, tuple(point_ids[i] for i in ids))
                   for ids in combinations(range(len(points)), count)]
        pending = [(ids,key) for ids,key in subsets if cache is None or key not in cache]
        batched = {}
        if count > 1 and len(pending) > 1:
            vertices_batch = np.array([[points[i][0] for i in ids] for ids,key in pending])
            tails = simplex_lstsq_batch(vertices_batch)
            batched = {key:(vertices_batch[j], tails[j]) for j,(ids,key) in enumerate(pending)}
        for ids, key in subsets:
            hit = cache.get(key) if cache is not None else None
            if hit is not None:
                # Keep point references in the entry so Python cannot reuse IDs.
                norm, weights, p, keepalive = hit
                if weights is None:
                    continue
            else:
                if key in batched:
                    vertices, tail = batched[key]
                    weights = simplex_weights(tail)
                else:
                    vertices = np.array([points[i][0] for i in ids])
                    if count == 1:
                        weights = np.ones(1)
                    else:
                        edges = (vertices[1:] - vertices[0]).T
                        tail = simplex_lstsq(edges, -vertices[0])
                        weights = simplex_weights(tail)
                if weights is None:
                    if cache is not None:
                        cache[key] = (None, None, None, tuple(points[i] for i in ids))
                    continue
                p = _weighted_point(weights,vertices)
                norm = _squared3(p)
                if cache is not None:
                    cache[key] = (norm, weights, p, tuple(points[i] for i in ids))
            if best is None or norm < best[0]:
                best = norm, ids, weights, p
    _, ids, weights, p = best
    active = [(points[i], w) for i, w in zip(ids, weights) if w > 1e-12]
    a, b = witnesses(active)
    return [point for point, _ in active], p, a, b


def _convex_distance_legacy(support_a, support_b, direction):
    direction = np.asarray(direction, dtype=float)
    if _norm_vector(direction) < 1e-12:
        direction = np.array([1., 0., 0.])
    direction = direction / _norm_vector(direction)
    def vertex(v):
        a, b = support_a(v), support_b(-v)
        return a-b, a, b
    simplex = [vertex(direction)]
    subset_cache = {}
    for _ in range(256):
        simplex, p, a, b = _closest_simplex(simplex, subset_cache)
        distance = float(_norm_vector(p))
        if distance < 1e-10:
            return 0., a, b
        new = vertex(-p / distance)
        # The support plane gives a lower bound; the simplex witnesses give
        # an upper bound. Bound error in meters, including near touching.
        lower = max(0., float(p @ new[0]) / distance)
        if distance-lower <= 1e-9 * max(1., distance):
            return distance, a, b
        if any(_norm_vector(new[0]-v[0]) < 1e-12 for v in simplex):
            return float(_norm_vector(p)), a, b
        simplex.append(new)
    simplex, p, a, b = _closest_simplex(simplex, subset_cache)
    return float(_norm_vector(p)), a, b


# All entries retain the same per-query simplex enumeration and LAPACK kernel.
# Only independent queries share the gufunc dispatch and input allocation.
_UNIT_WEIGHT = np.ones(1)
_UNIT_WEIGHT.setflags(write=False)


include "_native_simplex.pxi"

def convex_distance_many(supports, directions):
    if all(isinstance(sa,_SupportBase) and isinstance(sb,_SupportBase) for sa,sb in supports):
        return [_convex_primitives_array(sa,sb,direction) for (sa,sb),direction in zip(supports,directions)]
    states = []
    results = [None] * len(supports)
    for index, ((sa,sb),direction) in enumerate(zip(supports,directions)):
        direction = np.asarray(direction,dtype=float)
        if _norm_vector(direction) < 1e-12:
            direction = np.array([1.,0.,0.])
        direction = direction / _norm_vector(direction)
        a,b = sa(direction),sb(-direction)
        states.append((index,sa,sb,[(a-b,a,b)],{}))
    for iteration in range(256):
        if not states:
            break
        closest = _closest_simplex_many([s[3] for s in states],[s[4] for s in states])
        pending = []
        for state,(simplex,p,a,b) in zip(states,closest):
            index,sa,sb,_,cache = state
            distance = float(_norm_vector(p))
            if distance < 1e-10:
                results[index] = (0.,a,b)
                continue
            direction = -p / distance
            va,vb = sa(direction),sb(-direction)
            new = (va-vb,va,vb)
            lower = max(0.,float(p @ new[0]) / distance)
            if distance-lower <= 1e-9 * max(1.,distance):
                results[index] = (distance,a,b)
                continue
            if any(_norm_vector(new[0]-v[0]) < 1e-12 for v in simplex):
                results[index] = (float(_norm_vector(p)),a,b)
                continue
            simplex.append(new)
            pending.append((index,sa,sb,simplex,cache))
        states = pending
    if states:
        closest = _closest_simplex_many([s[3] for s in states],[s[4] for s in states])
        for state,(_,p,a,b) in zip(states,closest):
            results[state[0]] = (float(_norm_vector(p)),a,b)
    return results


def _triangle_support(vertices):
    if (type(vertices) is np.ndarray and vertices.dtype==np.float64
            and vertices.ndim==2 and vertices.shape[1]==3 and vertices.shape[0]>0
            and vertices.flags.c_contiguous):
        return _TriangleSupport(vertices)
    return lambda direction: vertices[int(np.argmax(vertices @ direction))]


def _prepare_mesh_surface(triangles):
    """Reuse only point-independent arithmetic within one geometry update."""
    a, b, c = np.moveaxis(triangles, 1, 0)
    normal = cross(b-a, c-a)
    area_squared = np.einsum('ij,ij->i', normal, normal)
    return a, b, c, normal, area_squared, 1e-9 * np.sqrt(area_squared)


def _on_prepared_mesh_surface_legacy(point, prepared):
    a, b, c, normal, area_squared, plane_tolerance = prepared
    valid = area_squared > 0
    plane = np.abs(np.einsum('ij,ij->i', point-a, normal))
    valid &= plane <= plane_tolerance
    if not np.any(valid):
        return False
    a, b, c, normal, area_squared = a[valid], b[valid], c[valid], normal[valid], area_squared[valid]
    alpha = np.einsum('ij,ij->i', cross(b-point, c-point), normal) / area_squared
    beta = np.einsum('ij,ij->i', cross(c-point, a-point), normal) / area_squared
    gamma = 1-alpha-beta
    return bool(np.any((alpha >= -1e-12) & (beta >= -1e-12) & (gamma >= -1e-12)))


def _on_mesh_surface(point, triangles):
    """Certify that a hull witness also lies on an original mesh triangle."""
    return _on_prepared_mesh_surface(point, _prepare_mesh_surface(triangles))


_DEFAULT_MESH_CERTIFICATE = _on_mesh_surface


def _inside_mesh(point, triangles):
    # Sum oriented solid angles of the closed, consistently wound surface.
    # Ray-hit parity misclassifies rays that only graze an edge/vertex; merely
    # deduplicating their hits still counts a tangency as a boundary crossing.
    vectors = triangles - point
    lengths = vector_norm(vectors, axis=2)
    if np.any(lengths == 0):
        return True  # On the surface: separation is zero either way.
    a, b, c = np.moveaxis(vectors / lengths[:, :, None], 1, 0)
    numerator = np.einsum('ij,ij->i', a, cross(b, c))
    denominator = (1 + np.einsum('ij,ij->i', a, b)
                   + np.einsum('ij,ij->i', b, c)
                   + np.einsum('ij,ij->i', c, a))
    winding = np.sum(2 * np.arctan2(numerator, denominator)) / (4 * np.pi)
    # Preserve odd/even shell containment, including empty nested cavities.
    return bool(int(np.rint(abs(winding))) % 2)


cdef class _SupportBase:
    cdef void support_raw(self,double* direction,double* output) except *:
        raise NotImplementedError()

cdef class _TriangleSupport(_SupportBase):
    cdef object vertices,scratch
    cdef double *values,*products
    cdef int count
    def __init__(self,vertices):
        self.vertices=vertices;self.count=len(vertices)
        self.scratch=np.empty(self.count,dtype=np.float64)
        self.values=<double*>PyArray_DATA(vertices)
        self.products=<double*>PyArray_DATA(self.scratch)
    cdef void support_raw(self,double* direction,double* output) except *:
        cdef int i,selected=0
        cdef double best,value
        if self.count==1:
            self.products[0]=0.0
            self.products[0]+=_ddot(3,self.values,1,direction,1)
        else:
            _gemv(101,111,self.count,3,1.0,self.values,3,direction,1,0.0,self.products,1)
        best=self.products[0]
        if best==best:
            for i in range(1,self.count):
                value=self.products[i]
                if value!=value:
                    selected=i
                    break
                if value>best:best=value;selected=i
        for i in range(3):output[i]=self.values[3*selected+i]
    def __call__(self,direction):
        return self.vertices[int(np.argmax(self.vertices @ direction))]

cdef class _PrimitiveSupport(_SupportBase):
    cdef object size, position, rotation, transposed, corners
    cdef int kind
    cdef double* sizes
    cdef double* rotation_data
    cdef double* position_data
    cdef Py_ssize_t size_stride
    cdef double raw_corners[8][3]
    cdef bint raw_corner_valid[8]

    def __init__(self, kind, size, position, rotation):
        self.kind = kind
        self.size, self.position, self.rotation = size, position, rotation
        self.transposed = rotation.T
        self.corners = {}
        self.rotation = np.ascontiguousarray(rotation,dtype=np.float64)
        self.position = np.ascontiguousarray(position,dtype=np.float64)
        self.rotation_data = <double*>PyArray_DATA(self.rotation)
        self.position_data = <double*>PyArray_DATA(self.position)
        self.sizes = <double*>PyArray_DATA(size)
        self.size_stride = PyArray_STRIDES(size)[0] // <Py_ssize_t>sizeof(double)

    @cython.cdivision(True)
    cdef void support_raw(self,double* direction,double* output) except *:
        cdef double v[3]
        cdef double local[3]
        cdef double unit[3]
        cdef double sz[3]
        cdef double product[3]
        cdef double length,xy,denominator
        cdef int i,mask=0
        _gemv(101,112,3,3,1.0,self.rotation_data,3,direction,1,0.0,v,1)
        for i in range(3):sz[i]=self.sizes[i*self.size_stride]
        if self.kind==6:
            mask=(1 if v[0]>=0 else 0)|(2 if v[1]>=0 else 0)|(4 if v[2]>=0 else 0)
            if self.raw_corner_valid[mask]:
                for i in range(3):output[i]=self.raw_corners[mask][i]
                return
            for i in range(3):local[i]=sz[i]*(1. if v[i]>=0 else -1.)
        else:
            length=_norm_raw(v,3)
            if length>1e-15:
                for i in range(3):unit[i]=v[i]/length
            else:unit[0],unit[1],unit[2]=1.,0.,0.
            if self.kind==2 or self.kind==3:
                for i in range(3):local[i]=sz[0]*unit[i]
                if self.kind==3:local[2]+=sz[1]*(1 if v[2]>=0 else -1)
            elif self.kind==5:
                xy=_norm_raw(v,2)
                if xy>1e-15:
                    local[0]=(sz[0]*v[0])/xy;local[1]=(sz[0]*v[1])/xy
                else:local[0],local[1]=sz[0],0.
                local[2]=sz[1]*(1 if v[2]>=0 else -1)
            elif self.kind==4:
                for i in range(3):product[i]=sz[i]*v[i]
                denominator=_norm_raw(product,3)
                if denominator>1e-15:
                    for i in range(3):local[i]=((sz[i]*sz[i])*v[i])/denominator
                else:local[0],local[1],local[2]=sz[0],0.,0.
            else:raise ValueError(f'Unsupported proximity geom type {self.kind}')
        _gemv(102,112,3,3,1.0,self.rotation_data,3,local,1,0.0,output,1)
        for i in range(3):output[i]=self.position_data[i]+output[i]
        if self.kind==6:
            for i in range(3):self.raw_corners[mask][i]=output[i]
            self.raw_corner_valid[mask]=True

    def __call__(self, direction):
        cdef double *pp, *direction_data
        cdef double vv[3]
        cdef double local_result[3]
        cdef double product[3]
        cdef double sz[3]
        cdef object v, result
        cdef double unit[3]
        cdef double length, xy, denominator
        cdef int i, mask
        if not (type(direction) is np.ndarray and direction.dtype == np.float64
                and direction.shape == (3,) and direction.strides == (8,)):
            from mjarena.envs.surface_distance import primitive_support as reference_support
            return reference_support(self.kind,self.size,self.position,self.rotation)(direction)
        v = direction
        direction_data = <double*>PyArray_DATA(v)
        _gemv(101,112,3,3,1.0,self.rotation_data,3,direction_data,1,0.0,vv,1)
        for i in range(3):
            sz[i] = self.sizes[i * self.size_stride]
        if self.kind == 6:
            mask = (1 if vv[0] >= 0 else 0) | (2 if vv[1] >= 0 else 0) | (4 if vv[2] >= 0 else 0)
            cached = self.corners.get(mask)
            if cached is not None:
                return cached.copy()
            result = np.empty(3, dtype=np.float64)
            pp = <double*>PyArray_DATA(result)
            for i in range(3):
                pp[i] = sz[i] * (1. if vv[i] >= 0 else -1.)
            for i in range(3):local_result[i] = pp[i]
            _gemv(102,112,3,3,1.0,self.rotation_data,3,local_result,1,0.0,pp,1)
            for i in range(3):pp[i] = self.position_data[i] + pp[i]
            self.corners[mask] = result.copy()
            return result
        length = _norm_raw(vv,3)
        if length > 1e-15:
            for i in range(3):
                unit[i] = vv[i] / length
        else:
            unit[0], unit[1], unit[2] = 1., 0., 0.
        result = np.empty(3, dtype=np.float64)
        pp = <double*>PyArray_DATA(result)
        if self.kind == 2 or self.kind == 3:
            for i in range(3):
                pp[i] = sz[0] * unit[i]
            if self.kind == 3:
                pp[2] += sz[1] * (1 if vv[2] >= 0 else -1)
        elif self.kind == 5:
            xy = _norm_raw(vv,2)
            if xy > 1e-15:
                pp[0] = (sz[0] * vv[0]) / xy
                pp[1] = (sz[0] * vv[1]) / xy
            else:
                pp[0], pp[1] = sz[0], 0.
            pp[2] = sz[1] * (1 if vv[2] >= 0 else -1)
        elif self.kind == 4:
            for i in range(3):product[i] = sz[i]*vv[i]
            denominator = _norm_raw(product,3)
            if denominator > 1e-15:
                for i in range(3):
                    pp[i] = ((sz[i] * sz[i]) * vv[i]) / denominator
            else:
                pp[0], pp[1], pp[2] = sz[0], 0., 0.
        elif self.kind == 6:
            for i in range(3):
                pp[i] = sz[i] * (1. if vv[i] >= 0 else -1.)
        else:
            raise ValueError(f'Unsupported proximity geom type {self.kind}')
        # The same BLAS call and ordering as NumPy's DOUBLE_gemv, without dispatch.
        for i in range(3):local_result[i] = pp[i]
        _gemv(102,112,3,3,1.0,self.rotation_data,3,local_result,1,0.0,pp,1)
        for i in range(3):pp[i] = self.position_data[i] + pp[i]
        return result


def primitive_support(kind, size, position, rotation):
    # Native entry matches the float64 C-order arrays in SurfaceQueries.update.
    # Other layouts retain NumPy's own layout-dependent kernel selection.
    if not (type(size) is np.ndarray and type(position) is np.ndarray
            and type(rotation) is np.ndarray and size.dtype == np.float64
            and position.dtype == np.float64 and rotation.dtype == np.float64
            and size.shape == (3,) and position.shape == (3,) and rotation.shape == (3,3)
            and rotation.flags.c_contiguous):
        from mjarena.envs.surface_distance import primitive_support as reference_support
        return reference_support(kind,size,position,rotation)
    return _PrimitiveSupport(kind, size, position, rotation)


class SurfaceQueries:
    def __init__(self, model):
        self.model = model
        self.types = np.asarray(model.geom_type).copy()
        self.sizes = np.asarray(model.geom_size).copy()
        self.meshes = {}
        self.vertices = {}
        self.components = {}
        for gid in range(model.ngeom):
            if self.types[gid] not in (int(mujoco.mjtGeom.mjGEOM_SDF), int(mujoco.mjtGeom.mjGEOM_MESH)):
                continue
            mid = int(model.geom_dataid[gid]); va = int(model.mesh_vertadr[mid]); vn = int(model.mesh_vertnum[mid])
            fa = int(model.mesh_faceadr[mid]); fn = int(model.mesh_facenum[mid])
            vertices = np.asarray(model.mesh_vert)[va:va+vn].copy()
            faces = np.asarray(model.mesh_face)[fa:fa+fn].copy()
            self.meshes[gid] = vertices[faces]
            self.vertices[gid] = vertices
            # One sample per connected shell is enough for containment tests
            # once surface intersections are also checked. Disconnected solids
            # can overlap even when their first component is entirely outside.
            parent = list(range(vn))
            def find(i):
                while parent[i] != i:
                    parent[i] = parent[parent[i]]
                    i = parent[i]
                return i
            for face in faces:
                for index in face[1:]:
                    parent[find(int(index))] = find(int(face[0]))
            representatives = sorted({find(int(i)) for i in faces.flat})
            self.components[gid] = vertices[representatives]

    def update(self, data):
        self._supports = {}
        self._mesh_certificates = {}
        self._hull_supports = {}
        self.positions = np.asarray(data.geom_xpos).copy()
        self.rotations = np.asarray(data.geom_xmat).reshape(-1, 3, 3).copy()
        self.triangles = {g: t @ self.rotations[g].T + self.positions[g] for g, t in self.meshes.items()}
        self.world_vertices = {g: v @ self.rotations[g].T + self.positions[g] for g, v in self.vertices.items()}
        self.component_points = {g: p @ self.rotations[g].T + self.positions[g] for g, p in self.components.items()}

    def _support(self, g):
        support = self._supports.get(g)
        if support is None:
            support = primitive_support(int(self.types[g]), self.sizes[g], self.positions[g], self.rotations[g])
            self._supports[g] = support
        return support

    def _certify_mesh(self, point, gid):
        # Keep the public certificate hook usable by adversarial tests.
        if _on_mesh_surface is not _DEFAULT_MESH_CERTIFICATE:
            return _on_mesh_surface(point, self.triangles[gid])
        prepared = self._mesh_certificates.get(gid)
        if prepared is None:
            prepared = _prepare_mesh_surface(self.triangles[gid])
            self._mesh_certificates[gid] = prepared
        return _on_prepared_mesh_surface(point, prepared)

    def _hull_support(self, gid):
        support = self._hull_supports.get(gid)
        if support is None:
            support = _triangle_support(self.world_vertices[gid])
            self._hull_supports[gid] = support
        return support

    def distances(self, data, pairs):
        result = [None] * len(pairs)
        primitive = [(i,a,b) for i,(a,b) in enumerate(pairs)
                     if a not in self.meshes and b not in self.meshes]
        if primitive:
            batched = convex_distance_many(
                [(self._support(a),self._support(b)) for i,a,b in primitive],
                [self.positions[b]-self.positions[a] for i,a,b in primitive])
            for (i,a,b),value in zip(primitive,batched):
                result[i] = value
        for i,(a,b) in enumerate(pairs):
            if result[i] is None:
                result[i] = self.distance(data,a,b)
        return result

    def distance(self, data, a, b):
        if a not in self.meshes and b not in self.meshes:
            # MuJoCo 3.10's collision-distance query can return zero for
            # separated primitives (including box/box). Query their convex
            # surfaces directly so proximity does not inherit that failure.
            sa = self._support(a)
            sb = self._support(b)
            return convex_distance(sa, sb, self.positions[b]-self.positions[a])
        ta, tb = self.triangles.get(a), self.triangles.get(b)
        sa = self._support(a) if ta is None else None
        sb = self._support(b) if tb is None else None
        # A convex-hull distance is a lower bound on the true mesh distance.
        # It is exact when BOTH witnesses lie on the original surfaces. This
        # certificate avoids expensive triangle searches without filling in
        # concavities or cavities; uncertified results use the full query below.
        hull_a = sa if ta is None else self._hull_support(a)
        hull_b = sb if tb is None else self._hull_support(b)
        hull = convex_distance(hull_a, hull_b, self.positions[b]-self.positions[a])
        direction = (hull[2]-hull[1])/hull[0] if hull[0] > 1e-8 else np.zeros(3)
        lower = float(direction @ (hull_b(-direction)-hull_a(direction)))
        if (hull[0] > 1e-8
                and hull[0]-lower <= 1e-9 * max(1., hull[0])
                and (ta is None or self._certify_mesh(hull[1], a))
                and (tb is None or self._certify_mesh(hull[2], b))):
            return hull
        # Handle complete containment, which surface-triangle distances alone miss.
        pa = self.positions[a] if ta is None else ta[0, 0]
        pb = self.positions[b] if tb is None else tb[0, 0]
        for point in self.component_points.get(b, [pb]):
            if ta is not None and _inside_mesh(point, ta):
                return 0., point.copy(), point.copy()
        for point in self.component_points.get(a, [pa]):
            if tb is not None and _inside_mesh(point, tb):
                return 0., point.copy(), point.copy()
        best = (float('inf'), pa, pb)
        # Sort conservative AABB lower bounds before expensive support queries.
        # Bounds only prune candidates that cannot improve the current result.
        pieces_a = list(ta) if ta is not None else [None]
        pieces_b = list(tb) if tb is not None else [None]
        def bounds(triangles, support):
            if triangles is not None:
                return triangles.min(axis=1), triangles.max(axis=1)
            axes = np.eye(3)
            lo = np.array([support(-axis)[i] for i, axis in enumerate(axes)])
            hi = np.array([support(axis)[i] for i, axis in enumerate(axes)])
            return lo[None, :], hi[None, :]
        amin, amax = bounds(ta, sa)
        bmin, bmax = bounds(tb, sb)
        a_lower = vector_norm(np.maximum(np.maximum(amin-bmax.max(0), bmin.min(0)-amax), 0), axis=1)
        for i in np.argsort(a_lower, kind='stable'):
            if a_lower[i] >= best[0]:
                break
            tri_a = pieces_a[i]
            support_a = sa if tri_a is None else _triangle_support(tri_a)
            gaps = np.maximum(np.maximum(amin[i]-bmax, bmin-amax[i]), 0)
            lower = vector_norm(gaps, axis=1)
            for j in np.argsort(lower, kind='stable'):
                if lower[j] >= best[0]:
                    break
                tri_b = pieces_b[j]
                support_b = sb if tri_b is None else _triangle_support(tri_b)
                result = convex_distance(support_a, support_b, self.positions[b]-self.positions[a])
                if result[0] < best[0]:
                    best = result
                    if best[0] <= 1e-8:
                        return best
        return best

def convex_distance(support_a,support_b,direction):
    if isinstance(support_a,_SupportBase) and isinstance(support_b,_SupportBase):
        return _convex_primitives_array(support_a,support_b,direction)
    return _convex_distance_legacy(support_a,support_b,direction)


include "_native_gjk_array.pxi"

include "_native_mesh.pxi"
