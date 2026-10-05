"""Contact bookkeeping using the original MuJoCo force and NumPy BLAS kernels."""
import numpy as np
import mujoco
import mujoco._functions as _mujoco_functions
from ._helpers import norm as vector_norm
cdef extern from "numpy/arrayobject.h":
    void* PyArray_DATA(object array)
    Py_ssize_t* PyArray_STRIDES(object array)
    int _import_array() except -1
_import_array()
include "_native_blas.pxi"

cdef extern from "mujoco/mujoco.h":
    ctypedef struct mjModel:
        pass
    ctypedef struct mjContact:
        double dist
        double pos[3]
        double frame[9]
        int geom1
        int geom2
        int efc_address
    ctypedef struct mjData:
        int ncon
        mjContact* contact

ctypedef void (*_force_type)(const mjModel*,const mjData*,int,double*) noexcept
_force_library=ctypes.CDLL(_mujoco_functions.__file__)
cdef _force_type _contact_force=<_force_type><uintptr_t>ctypes.cast(_force_library.mj_contactForce,ctypes.c_void_p).value


def capture(observer, bint integrate=False):
    cdef mjModel* model=<mjModel*><uintptr_t>observer.model._address
    cdef mjData* data=<mjData*><uintptr_t>observer.env.data._address
    cdef mjContact* contact
    cdef double dt=float(observer.model.opt.timestep)
    cdef double buf[6]
    cdef double *fv,*tv,*pv,*nv,*accum
    cdef double weight,product
    cdef int i,j,a,b
    cdef object force,torque,pos,normal,item,records,owners,impulses,key
    records=[];owners=observer.owners;impulses=observer.impulses
    for j in range(6):buf[j]=0.0
    for i in range(data.ncon):
        contact=data.contact+i;a=contact.geom1;b=contact.geom2
        if a not in owners and b not in owners:continue
        if contact.efc_address<0:continue
        _contact_force(model,data,i,buf)
        force=np.empty(3,dtype=np.float64);torque=np.empty(3,dtype=np.float64)
        pos=np.empty(3,dtype=np.float64);normal=np.empty(3,dtype=np.float64)
        fv=<double*>PyArray_DATA(force);tv=<double*>PyArray_DATA(torque)
        pv=<double*>PyArray_DATA(pos);nv=<double*>PyArray_DATA(normal)
        # frame.T @ buf slices: the same RowMajor/Trans gemv chosen by NumPy.
        _gemv(101,112,3,3,1.0,contact.frame,3,buf,1,0.0,fv,1)
        _gemv(101,112,3,3,1.0,contact.frame,3,buf+3,1,0.0,tv,1)
        for j in range(3):pv[j]=contact.pos[j];nv[j]=contact.frame[j]
        records.append((a,b,pos,normal,force,torque,float(contact.dist)))
        if integrate:
            key=(a,b);item=impulses.get(key)
            if item is None:
                item={'impulse':np.zeros(3),'torque_impulse':np.zeros(3),'position_sum':np.zeros(3),'weight':0.,'duration':0.}
                impulses[key]=item
            accum=<double*>PyArray_DATA(item['impulse'])
            for j in range(3):
                product=fv[j]*dt
                accum[j]=accum[j]+product
            accum=<double*>PyArray_DATA(item['torque_impulse'])
            for j in range(3):
                product=tv[j]*dt
                accum[j]=accum[j]+product
            weight=_norm_raw(fv,3)*dt
            accum=<double*>PyArray_DATA(item['position_sum'])
            for j in range(3):
                product=pv[j]*weight
                accum[j]=accum[j]+product
            item['weight']+=weight;item['duration']+=dt
    observer.latest_contacts=records
    if integrate:observer.interval_seconds+=dt
