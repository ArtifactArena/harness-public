"""Exact certificate terms and decisions near mesh planes, edges and vertices."""
import os,sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
import mjarena.envs
mjarena.envs.__path__.insert(0,str(Path(os.environ['OBS_OVERLAY'])/'mjarena/envs'))
import numpy as np
from mjarena.envs import surface_distance as ref
from mjarena.envs.observation_accel import _surface as fast
from validate import exact
assert fast._MESH_REDUCTION_COMPATIBLE
rng=np.random.default_rng(835644)
queries=0
with np.errstate(all='ignore'):
    for i in range(2000):
        n=[1,2,3,17,64,129][i%6]
        triangles=rng.normal(size=(n,3,3))*10.**rng.uniform(-5,5)
        if i%11==0:triangles[:,:,2]=0.
        if i%13==0:triangles[:,2]=triangles[:,1]
        if i%17==0:triangles[:]=-0.
        if i%19==0:triangles=triangles[::-1]
        if i%23==0:triangles=np.asfortranarray(triangles)
        if i%29==0:triangles.setflags(write=False)
        prepared=fast._prepare_mesh_surface(triangles)
        a,b,c,normal,area,tol=prepared
        points=[rng.normal(size=3),triangles[0,0].copy(),triangles[0].mean(axis=0)]
        if area[0]>0:
            for scale in [np.nextafter(1e-9,0.),1e-9,np.nextafter(1e-9,np.inf),-1e-9]:
                points.append(points[2]+normal[0]/np.sqrt(area[0])*scale)
        for point in points:
            if i%31==0:point.setflags(write=False)
            terms=fast._mesh_certificate_terms(point,prepared)
            plane=np.abs(np.einsum('ij,ij->i',point-a,normal))
            alpha=np.einsum('ij,ij->i',np.cross(b-point,c-point),normal)/area
            beta=np.einsum('ij,ij->i',np.cross(c-point,a-point),normal)/area
            expected=np.column_stack((plane,alpha,beta))
            # NaN payloads are not observable: only finite terms are compared.
            mask=np.isfinite(expected)
            if all(x.strides[-1]==8 for x in prepared):
                exact(expected[mask],terms[mask],f'terms-{i}')
            exact(ref._on_mesh_surface(point,triangles),fast._on_mesh_surface(point,triangles),f'certificate-{i}')
            queries+=1
        if i%400==0:print('mesh cases',i,flush=True)
print('PASS:',queries,'exact mesh certificates and finite intermediate terms',flush=True)
