"""Integrate an interval with exact, ordered contact accumulation."""
import numpy as np
import mujoco._functions as _mujoco_functions
from mjarena.envs.observation_accel._helpers import norm as vector_norm
cdef extern from "numpy/arrayobject.h":
    void* PyArray_DATA(object array)
    int _import_array() except -1
_import_array()
include "../observation_accel/_native_blas.pxi"

cdef extern from "mujoco/mujoco.h":
    ctypedef struct mjModel:
        int ngeom
    ctypedef struct mjContact:
        double pos[3]
        double frame[9]
        int geom1
        int geom2
        int efc_address
    ctypedef struct mjData:
        int ncon
        mjContact* contact
ctypedef void (*Step)(void*) noexcept
ctypedef void (*Force)(const mjModel*,const mjData*,int,double*) noexcept
_force_library=ctypes.CDLL(_mujoco_functions.__file__)
cdef Force contact_force=<Force><uintptr_t>ctypes.cast(_force_library.mj_contactForce,ctypes.c_void_p).value

def advance(observer,int count,uintptr_t function,uintptr_t context):
    cdef mjModel* m=<mjModel*><uintptr_t>observer.model._address
    cdef mjData* d=<mjData*><uintptr_t>observer.env.data._address
    cdef Step step=<Step>function
    cdef int n=m.ngeom, sub, i, j, a, b, key, used=0
    cdef double dt=float(observer.model.opt.timestep), duration=observer.interval_seconds
    cdef double buf[6], force[3], torque[3], weight, product
    cdef mjContact* contact
    cdef object accumulator=np.zeros((n*n,11),dtype=np.float64)
    cdef double* accum=<double*>PyArray_DATA(accumulator)
    cdef object flags=np.zeros(n*n,dtype=np.int32),order=np.empty(n*n,dtype=np.int32),owners=np.zeros(n,dtype=np.int32)
    cdef int* seen=<int*>PyArray_DATA(flags)
    cdef int* sequence=<int*>PyArray_DATA(order)
    cdef int* owned=<int*>PyArray_DATA(owners)
    cdef double* row
    cdef object item
    if observer.impulses or observer.interval_seconds!=0:
        raise ValueError('begin_interval must precede advance')
    for i in observer.owners:owned[i]=1
    for sub in range(count):
        step(<void*>context)
        for j in range(6):buf[j]=0.0
        for i in range(d.ncon):
            contact=d.contact+i;a=contact.geom1;b=contact.geom2
            if (not owned[a] and not owned[b]) or contact.efc_address<0:continue
            contact_force(m,d,i,buf)
            _gemv(101,112,3,3,1.0,contact.frame,3,buf,1,0.0,force,1)
            _gemv(101,112,3,3,1.0,contact.frame,3,buf+3,1,0.0,torque,1)
            key=a*n+b
            if not seen[key]:seen[key]=1;sequence[used]=key;used+=1
            row=accum+key*11
            for j in range(3):
                product=force[j]*dt;row[j]=row[j]+product
                product=torque[j]*dt;row[3+j]=row[3+j]+product
            weight=_norm_raw(force,3)*dt
            for j in range(3):
                product=contact.pos[j]*weight;row[6+j]=row[6+j]+product
            row[9]=row[9]+weight;row[10]=row[10]+dt
        duration=duration+dt
    for i in range(used):
        key=sequence[i];row=accum+key*11
        item={'impulse':accumulator[key,:3].copy(),'torque_impulse':accumulator[key,3:6].copy(),
              'position_sum':accumulator[key,6:9].copy(),'weight':row[9],'duration':row[10]}
        observer.impulses[(key//n,key%n)]=item
    observer.interval_seconds=duration
    observer.capture_contacts(integrate=False)
