"""Deterministic observation stress tests, runnable on native MuJoCo.

Checks use analytic distances, separating planes, finite differences, and
momentum balance rather than comparing the observations with themselves.
"""
from contextlib import contextmanager
from itertools import product
import math
import numpy as np
import mujoco
from mjarena.envs.surface_distance import SurfaceQueries
from mjarena.envs.detailed_observations import _quaternion
from mjarena.envs.sumo import SumoEnv
from mjarena.agents.runtime import BotRuntime
from mjarena.runner.episode import Match


def release(*objects):
    for obj in objects:
        if hasattr(obj, 'close'):
            obj.close()


def rotation(q):
    w,x,y,z = np.asarray(q)/np.linalg.norm(q)
    return np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],
                     [2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],
                     [2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])


def support(kind, size, direction):
    """Analytic support points used to construct shapes with a known gap."""
    v=np.asarray(direction); unit=v/np.linalg.norm(v)
    if kind=='sphere': return size[0]*unit
    if kind=='box': return np.copysign(size,v)
    if kind=='ellipsoid': return size*size*v/np.linalg.norm(size*v)
    if kind=='capsule': return size[0]*unit + np.array([0,0,np.copysign(size[1],v[2])])
    radius=size[0]*v[:2]/np.linalg.norm(v[:2])
    return np.r_[radius,np.copysign(size[1],v[2])]


def check_primitive_distances():
    rng=np.random.default_rng(61209)
    kinds=('sphere','box','capsule','cylinder','ellipsoid')
    count=0
    for ka,kb in product(kinds,repeat=2):
        xml=f'<mujoco><worldbody><geom type="{ka}" size=".3 .4 .5" pos=".1 .2 .3" quat=".5 .5 .5 .5"/><geom type="{kb}" size=".3 .4 .5" pos="3 0 0" quat=".5 .5 .5 .5"/></worldbody></mujoco>'
        m=mujoco.MjModel.from_xml_string(xml);d=mujoco.MjData(m)
        try:
            for trial in range(36):
                scale=(.0001,.001,.01,.1,1.,10.)[trial%6]
                sizes=rng.uniform(.15,.7,(2,3))*scale
                qa,qb=rng.normal(size=(2,4));qa/=np.linalg.norm(qa);qb/=np.linalg.norm(qb)
                ra,rb=rotation(qa),rotation(qb)
                axis=rng.normal(size=3);axis/=np.linalg.norm(axis)
                gap=(0.,1e-7,.003,.1,2.,20.)[trial//6]*scale
                origin=rng.uniform(-50,50,3)
                # Both support points lie on parallel separating planes and
                # differ only along their shared outward normal: exact distance.
                pa=origin+ra@support(ka,sizes[0],ra.T@axis)
                other=pa-rb@support(kb,sizes[1],-rb.T@axis)+gap*axis
                m.geom_size[:]=sizes;m.geom_pos[:]=[origin,other];m.geom_quat[:]=[qa,qb]
                mujoco.mj_forward(m,d);queries=SurfaceQueries(m);queries.update(d)
                for a,b in ((0,1),(1,0)):
                    distance,wa,wb=queries.distance(d,a,b)
                    tolerance=2e-6*scale+2e-8
                    np.testing.assert_allclose(distance,gap,atol=tolerance,rtol=2e-6,
                        err_msg=f'{ka}/{kb} trial={trial}, scale={scale}')
                    np.testing.assert_allclose(np.linalg.norm(wa-wb),distance,atol=2e-8)
                    assert np.isfinite(np.r_[distance,wa,wb]).all()
                    if gap>1e-4*scale:
                        # The witnesses are on the expected separating planes.
                        np.testing.assert_allclose((wa-pa)@axis,0 if a==0 else gap,atol=tolerance*2)
                    count+=1
        finally: release(d,m)
    print(f'PASS {count} primitive distance queries: all 25 pairs, rotations, scales, touching, tiny/large gaps',flush=True)


def check_false_zero_regression():
    xml='''<mujoco><worldbody>
    <geom type="box" size=".475 .55 .025" pos=".8358674407638023 .3144916944341652 2.0398025613012347" quat=".2706519233995241 -.012719333003742114 .0035744169114665537 .9625866082965324"/>
    <geom type="box" size=".6 .6 .25" pos=".3078019951927214 3.1121241889427487 2.2519943548787014" quat=".998554156708661 -3.126136213060066e-7 7.84389855904887e-8 .05375496367547504"/>
    </worldbody></mujoco>'''
    m=mujoco.MjModel.from_xml_string(xml);d=mujoco.MjData(m)
    try:
        mujoco.mj_forward(m,d);q=SurfaceQueries(m);q.update(d)
        distance,a,b=q.distance(d,0,1)
        np.testing.assert_allclose(distance,1.5122948022271805,atol=1e-8)
        np.testing.assert_allclose(np.linalg.norm(a-b),distance,atol=1e-9)
    finally: release(d,m)
    print('PASS Wedgehammer false-zero regression',flush=True)


def check_sphere_oracles():
    rng=np.random.default_rng(61210)
    count=0
    for kind in ('sphere','box','capsule','cylinder','ellipsoid'):
        xml=f'<mujoco><worldbody><geom type="{kind}" size=".4 .6 .8" pos=".1 .2 .3" quat=".5 .5 .5 .5"/><geom type="sphere" size=".1" pos="2 0 0"/></worldbody></mujoco>'
        m=mujoco.MjModel.from_xml_string(xml);d=mujoco.MjData(m)
        try:
            for _ in range(80):
                point=rng.uniform(-1.5,1.5,3);radius=rng.uniform(.01,.3)
                size=np.array(m.geom_size[0]);quat=rng.normal(size=4);quat/=np.linalg.norm(quat)
                offset=rng.uniform(-10,10,3)
                m.geom_quat[0]=quat;m.geom_pos[0]=offset
                m.geom_pos[1]=offset+rotation(quat)@point;m.geom_size[1,0]=radius
                if kind=='sphere': expected=max(0.,np.linalg.norm(point)-size[0]-radius)
                elif kind=='box': expected=max(0.,np.linalg.norm(np.maximum(np.abs(point)-size,0))-radius)
                elif kind=='capsule':
                    nearest=np.array([0.,0.,np.clip(point[2],-size[1],size[1])])
                    expected=max(0.,np.linalg.norm(point-nearest)-size[0]-radius)
                elif kind=='cylinder':
                    expected=max(0.,np.linalg.norm(np.maximum([np.linalg.norm(point[:2])-size[0],abs(point[2])-size[1]],0))-radius)
                elif np.sum((point/size)**2)<=1: expected=0.
                else:
                    lo,hi=0.,100.
                    for _ in range(90):
                        mid=(lo+hi)/2
                        if np.sum((size*point/(mid+size**2))**2)>1:lo=mid
                        else:hi=mid
                    nearest=size**2*point/(hi+size**2)
                    expected=max(0.,np.linalg.norm(point-nearest)-radius)
                mujoco.mj_forward(m,d);q=SurfaceQueries(m);q.update(d)
                distance,a,b=q.distance(d,0,1)
                np.testing.assert_allclose(distance,expected,atol=3e-6,rtol=2e-6,err_msg=f'{kind} point={point}')
                np.testing.assert_allclose(np.linalg.norm(a-b),distance,atol=2e-8)
                count+=1
        finally:release(d,m)
    print(f'PASS {count} independent sphere/solid oracles, including overlap and containment',flush=True)


ARENA='<geom name="outside_floor" type="plane" size="20 20 .1"/><geom name="sumo_ring" type="cylinder" size="7.5 1" pos="0 0 1"/>'
BLUE='<body name="blue_root" pos="4 0 3"><freejoint/><geom name="blue_base" type="sphere" size=".2" mass="7"/></body>'


@contextmanager
def arena(xml,max_steps=200,**env_kwargs):
    m=mujoco.MjModel.from_xml_string(xml);d=mujoco.MjData(m)
    red=BotRuntime(m,d,lambda obs:{},'red_');blue=BotRuntime(m,d,lambda obs:{},'blue_')
    env=SumoEnv(m,d,'',red,blue,max_steps=max_steps,**env_kwargs)
    match=Match(env,red,blue,max_steps=max_steps,headless=True)
    env.reset(seed=0)
    try:yield m,d,env,match
    finally:env.detailed_observations.close();release(d,m)


def named(m,kind,name):
    return int(mujoco.mj_name2id(m,getattr(mujoco.mjtObj,'mjOBJ_'+kind),name))


STATE_XML='<mujoco><compiler angle="radian"/><option timestep=".00025" gravity="0 0 0"/><worldbody>'+ARENA+'''
<body name="red_root" pos="-2 0 4" quat=".5 .5 .5 .5"><freejoint/>
<geom name="red_base" type="box" pos=".1 -.2 .05" size=".2 .3 .1" mass="11"/>
<site name="red_anchor" pos=".2 .1 .3" quat=".5 -.5 .5 -.5"/>
<body name="red_hinge_body" pos=".2 .3 .4" quat=".5 .5 -.5 .5">
<joint name="red_hinge" axis="1 2 3" pos=".1 .02 -.03" ref=".3" limited="true" range="-2 2" damping="1.2" frictionloss=".3" stiffness="4" springref=".3"/>
<geom name="red_hinge_geom" type="ellipsoid" pos=".12 .03 .05" size=".1 .2 .12" mass="3"/>
<body name="red_slider" pos=".3 0 .2"><joint name="red_slide" type="slide" axis="2 -1 1" ref=".2" limited="true" range="-.5 1"/>
<geom name="red_slider_geom" type="capsule" size=".05 .1" mass="2"/>
<site name="red_tip_site" pos=".2 .3 -.1"/>
</body></body>
<body name="red_ball_body" pos="-.4 .1 .2" quat=".5 -.5 .5 .5"><joint name="red_ball" type="ball" damping=".7" frictionloss=".2" limited="true" range="0 2"/>
<geom name="red_ball_geom" type="box" pos=".1 .02 -.03" size=".1 .06 .03" mass="1"/>
<site name="red_ball_site" pos=".1 .2 .3"/></body>
<body name="red_welded" pos="-.2 -.3 -.4"><geom name="red_welded_geom" type="cylinder" size=".07 .13" mass="4"/></body>
</body>'''+BLUE+'''</worldbody>
<tendon><fixed name="red_fixed" damping="2" frictionloss=".5"><joint joint="red_hinge" coef="-3"/><joint joint="red_slide" coef="2"/></fixed>
<spatial name="red_cable"><site site="red_anchor"/><site site="red_tip_site"/></spatial></tendon>
<actuator><motor name="red_hinge_motor" joint="red_hinge" gear="-4" ctrllimited="true" ctrlrange="-.4 .6"/>
<motor name="red_ball_motor" joint="red_ball" gear="1 2 -3"/><motor name="red_ball_parent_motor" jointinparent="red_ball" gear="-2 1 3"/>
<motor name="red_tendon_motor" tendon="red_fixed" gear="5"/><motor name="red_relative_motor" site="red_tip_site" refsite="red_anchor" gear="1 2 3 4 5 6"/></actuator></mujoco>'''


def integrate_positions(m,qpos,qvel,dt):
    """Independent native qpos integration."""
    result=np.array(qpos,copy=True)
    for j in range(m.njnt):
        qa,da=int(m.jnt_qposadr[j]),int(m.jnt_dofadr[j]);kind=int(m.jnt_type[j])
        if kind in (2,3):result[qa]+=qvel[da]*dt;continue
        if kind==0:result[qa:qa+3]+=qvel[da:da+3]*dt;qa+=3;da+=3
        w=qvel[da:da+3];theta=np.linalg.norm(w)*dt
        dq=np.r_[math.cos(theta/2),w*(math.sin(theta/2)/np.linalg.norm(w) if np.linalg.norm(w) else 0)]
        a=result[qa:qa+4];result[qa:qa+4]=np.r_[a[0]*dq[0]-a[1:]@dq[1:],a[0]*dq[1:]+dq[0]*a[1:]+np.cross(a[1:],dq[1:])]
    return result


def check_state_frames_and_rates():
    rng=np.random.default_rng(61211)
    with arena(STATE_XML) as (m,d,env,match):
        detail=env.detailed_observations
        for trial in range(24):
            d.qpos[:]=np.asarray(m.qpos0)
            for name in ('red_root','blue_root'):
                bid=named(m,'BODY',name);j=int(m.body_jntadr[bid]);a=int(m.jnt_qposadr[j])
                quat=rng.normal(size=4);quat/=np.linalg.norm(quat);d.qpos[a+3:a+7]=quat
            ball=named(m,'JOINT','red_ball');qa=int(m.jnt_qposadr[ball])
            quat=rng.normal(size=4);quat/=np.linalg.norm(quat);d.qpos[qa:qa+4]=quat
            for name in ('red_hinge','red_slide'):
                d.qpos[int(m.jnt_qposadr[named(m,'JOINT',name)])]=rng.uniform(-.3,.6)
            d.qvel[:]=rng.uniform(-2,2,m.nv);mujoco.mj_forward(m,d)
            detail.begin_interval();qpos=np.array(d.qpos);qvel=np.array(d.qvel)
            before={name:np.array(getattr(d,name)) for name in ('qpos','qvel','qacc','qacc_warmstart','ctrl','qfrc_constraint')}
            info=match.build_bot_observation(True,0).details;state=info['my_robot']
            assert set(state['joints'])=={'hinge','slide','ball'}
            assert set(state['motors'])=={'hinge_motor','ball_motor','ball_parent_motor','tendon_motor','relative_motor'}
            assert info['my_mass']==21 and info['opponent_mass']==7
            for key,value in before.items():np.testing.assert_array_equal(getattr(d,key),value)
            eps=1e-6;frames=[]
            for sign in (-1,1):
                d.qpos[:]=integrate_positions(m,qpos,qvel,sign*eps);mujoco.mj_forward(m,d)
                frames.append({key:np.array(getattr(d,key)) for key in ('xpos','xipos','xmat','geom_xpos','geom_xmat','site_xpos','site_xmat','ten_length')})
            d.qpos[:]=qpos;mujoco.mj_forward(m,d)
            for category,kind,posfield,matfield in (('bodies','BODY','xpos','xmat'),('geoms','GEOM','geom_xpos','geom_xmat'),('sites','SITE','site_xpos','site_xmat')):
                for name,record in state[category].items():
                    index=named(m,kind,'red_'+name)
                    expected=(frames[1][posfield][index]-frames[0][posfield][index])/(2*eps)
                    np.testing.assert_allclose(record['linear_velocity'],expected,atol=2e-7)
                    mat=np.asarray(getattr(d,matfield)[index]).reshape(3,3)
                    np.testing.assert_allclose(rotation(record['quaternion']),mat,atol=1e-10)
                    derivative=(frames[1][matfield][index]-frames[0][matfield][index]).reshape(3,3)/(2*eps)
                    skew=derivative@mat.T
                    np.testing.assert_allclose(record['angular_velocity'],[skew[2,1],skew[0,2],skew[1,0]],atol=2e-7)
                    if category=='bodies':
                        np.testing.assert_allclose(record['com_velocity'],(frames[1]['xipos'][index]-frames[0]['xipos'][index])/(2*eps),atol=2e-7)
                        np.testing.assert_allclose(record['com_position'],d.xpos[index]+mat@record['local_com'],atol=1e-10)
                    else:
                        body=state['bodies'][record['body']];br=rotation(body['quaternion'])
                        np.testing.assert_allclose(record['position'],body['position']+br@record['local_position'],atol=1e-10)
                        np.testing.assert_allclose(mat,br@rotation(record['local_quaternion']),atol=1e-10)
            for name,record in state['tendons'].items():
                index=named(m,'TENDON','red_'+name)
                np.testing.assert_allclose(record['velocity'],(frames[1]['ten_length'][index]-frames[0]['ten_length'][index])/(2*eps),atol=2e-7)
            for name,record in state['joints'].items():
                j=named(m,'JOINT','red_'+name);qa=int(m.jnt_qposadr[j]);da=int(m.jnt_dofadr[j])
                width=4 if record['type']=='ball' else 1;ratewidth=3 if width==4 else 1
                np.testing.assert_allclose(np.atleast_1d(record['position']),qpos[qa:qa+width])
                np.testing.assert_allclose(np.atleast_1d(record['velocity']),qvel[da:da+ratewidth])
            hinge=state['joints']['hinge']
            np.testing.assert_allclose(hinge['reference'],[.3]);np.testing.assert_allclose(hinge['damping'],[1.2])
            np.testing.assert_allclose(hinge['axis'],np.array([1,2,3])/math.sqrt(14))
            np.testing.assert_allclose(hinge['anchor'],[.1,.02,-.03])
            assert hinge['limited'] and hinge['stiffness']==4
            # Principal moments and their quaternion must reconstruct the
            # analytic inertia about the body's own COM, in body coordinates.
            for name,mass,half in (('root',11.,np.array([.2,.3,.1])),('ball_body',1.,np.array([.1,.06,.03]))):
                body=state['bodies'][name];axes=rotation(body['inertia_quaternion'])
                actual=axes@np.diag(body['inertia_diagonal'])@axes.T
                expected=np.diag(mass/3*(np.sum(half**2)-half**2))
                np.testing.assert_allclose(actual,expected,atol=1e-12)
            np.testing.assert_allclose(state['geoms']['base']['size'],[.2,.3,.1])
            np.testing.assert_allclose(state['motors']['hinge_motor']['ctrl_range'],[-.4,.6])
            assert state['motors']['relative_motor']['refsite']=='anchor'
            # Whole-robot COM is independently differentiated from mass-weighted poses.
            bids=detail.ids['red_'][0];mass=np.asarray(m.body_mass)[bids]
            expected=((frames[1]['xipos'][bids]-frames[0]['xipos'][bids])*mass[:,None]).sum(0)/(2*eps*mass.sum())
            np.testing.assert_allclose(info['my_com_velocity'],expected,atol=2e-7)
            # Every public array/list/dictionary is isolated from the cached state.
            def poison(value):
                if isinstance(value,np.ndarray):value[:]=0
                elif isinstance(value,dict):
                    for child in value.values():poison(child)
                elif isinstance(value,list):
                    for child in value:poison(child)
            original=state['bodies']['root']['position'].copy();poison(info)
            again=detail.for_robot('red_')
            np.testing.assert_array_equal(again['my_robot']['bodies']['root']['position'],original)
        # Stable quaternions through 180-degree rotations.
        for axis in np.eye(3):
            for angle in (0.,1e-12,math.pi-1e-12,math.pi,math.pi+1e-12):
                q=np.r_[math.cos(angle/2),axis*math.sin(angle/2)]
                np.testing.assert_allclose(rotation(_quaternion(rotation(q))),rotation(q),atol=1e-12)
    print('PASS randomized articulated state: frames, finite-difference velocities, joints, tendons, motors, COM, snapshot isolation',flush=True)


def check_unnamed_parts():
    xml='<mujoco><option gravity="0 0 0"/><worldbody>'+ARENA+'''
    <body name="red_root" pos="-2 0 4"><freejoint/><geom name="red_base" size=".1" mass="2"/>
    <site name="red_anchor"/><body pos="1 0 0"><joint type="slide" name="red_slide"/>
    <geom size=".2" mass="3"/><site name="red_end"/><body pos="0 1 0"><geom size=".1" mass="5"/><site/></body></body></body>
    <body name="red_beacon" mocap="true"><geom size=".1" contype="0" conaffinity="0"/></body>'''+BLUE+'''
    </worldbody><tendon><spatial><site site="red_anchor"/><site site="red_end"/></spatial></tendon></mujoco>'''
    with arena(xml) as (m,d,env,match):
        d.qpos[:]=np.asarray(m.qpos0);d.qvel[:]=0;mujoco.mj_forward(m,d)
        env.detailed_observations.begin_interval()
        info=match.build_bot_observation(True,0).details;state=info['my_robot']
        assert len(state['bodies'])==3 and len(state['geoms'])==3 and len(state['sites'])==3
        assert len(state['tendons'])==1 and info['my_mass']==10
        assert env.red_contender.total_mass==10
        np.testing.assert_allclose(state['com_position'],[-1.2,.5,4])
        np.testing.assert_allclose(env.red_contender.com_position,state['com_position'],atol=1e-6)
        assert all(name is not None for name in state['bodies'])
        for geom in state['geoms'].values():assert geom['body'] in state['bodies']
        for body in state['bodies'].values():assert body['parent'] is None or body['parent'] in state['bodies']
        names=set(state['bodies'])
        env.reset(seed=1)
        assert names==set(match.build_bot_observation(True,0).details['my_robot']['bodies'])
    print('PASS unnamed descendants, generated names, tendon ownership, mass/COM and marker exclusion',flush=True)


def check_contact_impulses():
    # Free spheres collide off-center in zero gravity, away from the platform.
    # Momentum change independently determines total external contact impulse.
    xml='<mujoco><option timestep=".00025" gravity="0 0 0" integrator="Euler"/><worldbody>'+ARENA+'''
    <body name="red_root" pos="-.19 0 5"><freejoint/><geom name="red_ball" type="sphere" size=".2" mass="3" friction=".8 .005 .0001"/></body>
    <body name="blue_root" pos=".19 .03 5"><freejoint/><geom name="blue_ball" type="sphere" size=".2" mass="5" friction=".8 .005 .0001"/></body>
    </worldbody></mujoco>'''
    with arena(xml) as (m,d,env,match):
        d.qpos[:]=np.asarray(m.qpos0);d.qvel[:]=[1,.3,0,0,0,2,-1,-.1,0,0,0,-1]
        mujoco.mj_forward(m,d);detail=env.detailed_observations
        detail.begin_interval();detail.capture_contacts()
        initial=detail.for_robot('red_')
        assert initial['contact_interval']==0 and initial['contact_impulses']==[]
        before=np.array(d.qvel)
        body=named(m,'BODY','red_root');inertia=float(m.body_inertia[body,0])
        angular_before=inertia*(rotation(np.asarray(d.qpos)[3:7])@before[3:6])
        angular_impulse=np.zeros(3)
        weighted_position=np.zeros(3);weight_sum=0.;wrench=np.zeros(6)
        for _ in range(40):
            mujoco.mj_step(m,d);detail.capture_contacts(integrate=True)
            for index in range(int(d.ncon)):
                contact=d.contact[index]
                if int(contact.efc_address)<0:continue
                mujoco.mj_contactForce(m,d,index,wrench)
                weight=np.linalg.norm(wrench[:3])*float(m.opt.timestep)
                weighted_position+=weight*np.asarray(contact.pos);weight_sum+=weight
            for contact in detail.contacts_for('red_'):
                angular_impulse+=(np.cross(contact['position']-np.asarray(d.xipos[body]),contact['force_on_me'])+contact['torque_on_me'])*float(m.opt.timestep)
        env.t=1;detail.cached=None
        red=detail.for_robot('red_');blue=detail.for_robot('blue_')
        np.testing.assert_allclose(red['contact_interval'],.01,atol=1e-14)
        ri=sum((c['impulse_on_me'] for c in red['contact_impulses']),np.zeros(3))
        bi=sum((c['impulse_on_me'] for c in blue['contact_impulses']),np.zeros(3))
        np.testing.assert_allclose(ri,3*(np.asarray(d.qvel)[:3]-before[:3]),atol=1e-9)
        np.testing.assert_allclose(bi,5*(np.asarray(d.qvel)[6:9]-before[6:9]),atol=1e-9)
        np.testing.assert_allclose(ri,-bi,atol=1e-10)
        angular_after=inertia*(rotation(np.asarray(d.qpos)[3:7])@np.asarray(d.qvel)[3:6])
        np.testing.assert_allclose(angular_after-angular_before,angular_impulse,atol=2e-6)
        assert np.linalg.norm(ri)>0 and all(c['other_kind']=='opponent' for c in red['contact_impulses'])
        assert len(red['contact_impulses'])==1 and weight_sum>0
        np.testing.assert_allclose(red['contact_impulses'][0]['position'],weighted_position/weight_sum,atol=1e-10)
        for rc,bc in zip(red['contacts'],blue['contacts']):
            np.testing.assert_allclose(rc['force_on_me'],-bc['force_on_me'],atol=1e-10)
            np.testing.assert_allclose(rc['torque_on_me'],-bc['torque_on_me'],atol=1e-10)
            np.testing.assert_allclose(rc['normal_toward_me'],-bc['normal_toward_me'],atol=1e-10)
            np.testing.assert_allclose(rc['position'],bc['position'],atol=1e-10)
        # Contacts that end during the interval must leave their accumulated impulse.
        d.qpos[0]=-3;d.qpos[7]=3;mujoco.mj_forward(m,d);detail.capture_contacts();detail.cached=None
        info=detail.for_robot('red_');assert info['contacts']==[] and info['contact_impulses']
        detail.begin_interval();assert detail.for_robot('red_')['contact_impulses']==[]
        env.reset(seed=2);info=match.build_bot_observation(True,0).details
        assert info['contact_interval']==0 and info['contact_impulses']==[]
        # An overlapping pair separating rapidly can have active constraints
        # but zero contact force. Its impulse location must be None, not NaN.
        d.qpos[:]=np.asarray(m.qpos0);d.qvel[:]=0;d.qvel[0]=-100;d.qvel[6]=100
        mujoco.mj_forward(m,d);detail.begin_interval();detail.capture_contacts(integrate=True)
        zero=detail.impulses_for('red_')
        assert zero and all(np.linalg.norm(c['impulse_on_me'])==0 for c in zero)
        assert all(c['position'] is None for c in zero)
    # Static support under gravity: total measured normal force is the weight.
    xml='<mujoco><option timestep=".00025"/><worldbody>'+ARENA+'''
    <body name="red_root" pos="0 0 2.2"><freejoint/><geom name="red_ball" type="sphere" size=".2" mass="3"/></body>'''+BLUE+'</worldbody></mujoco>'
    with arena(xml) as (m,d,env,match):
        for _ in range(1000):mujoco.mj_step(m,d)
        env.detailed_observations.begin_interval();env.detailed_observations.capture_contacts()
        info=match.build_bot_observation(True,0).details
        force=sum((c['force_on_me'] for c in info['contacts']),np.zeros(3))
        np.testing.assert_allclose(force,[0,0,3*9.81],atol=.02)
        assert all(c['other_kind']=='platform' for c in info['contacts'])
        # Move the same robot onto the outside floor.
        d.qpos[:3]=[10,0,.199];d.qvel[:]=0;mujoco.mj_forward(m,d)
        env.detailed_observations.begin_interval();env.detailed_observations.capture_contacts()
        info=match.build_bot_observation(True,0).details
        assert info['contacts'] and all(c['other_kind']=='floor' for c in info['contacts'])
    print('PASS contacts and impulses: momentum balance, signs, frames, separation, reset, platform weight and floor',flush=True)


def cube_mesh(name,boxes):
    vertices=[];faces=[]
    triangles=[(0,2,1),(0,3,2),(4,5,6),(4,6,7),(0,1,5),(0,5,4),(1,2,6),(1,6,5),(2,3,7),(2,7,6),(3,0,4),(3,4,7)]
    corners=np.array([[-1,-1,-1],[1,-1,-1],[1,1,-1],[-1,1,-1],[-1,-1,1],[1,-1,1],[1,1,1],[-1,1,1]])
    for center,half in boxes:
        offset=len(vertices);vertices.extend(corners*np.array(half)+center)
        faces.extend(tuple(offset+i for i in f) for f in triangles)
    return '<mesh name="'+name+'" vertex="'+' '.join(map(str,np.array(vertices).ravel()))+'" face="'+' '.join(map(str,np.array(faces).ravel()))+'"/>'


def check_mesh_containment_and_frames():
    asset=cube_mesh('pieces',[([0,0,0],[.2,.2,.2]),([4,0,0],[.2,.2,.2])])+cube_mesh('container',[([4,0,0],[.8,.8,.8])])
    for order in (('pieces','container'),('container','pieces')):
        xml='<mujoco><asset>'+asset+'</asset><worldbody>'+''.join('<geom type="sdf" mesh="'+name+'"/>' for name in order)+'</worldbody></mujoco>'
        m=mujoco.MjModel.from_xml_string(xml);d=mujoco.MjData(m)
        try:
            mujoco.mj_forward(m,d);q=SurfaceQueries(m);q.update(d)
            np.testing.assert_allclose(q.distance(d,0,1)[0],0,atol=1e-8)
        finally:release(d,m)
    # Compiled vertices already include mesh scale and inertia-frame recentering.
    asset=cube_mesh('offset',[([1,2,3],[.1,.2,.3])]).replace('/>',' scale="2 3 4"/>')
    xml='<mujoco><asset>'+asset+'</asset><worldbody>'+ARENA+'''<body name="red_root" pos="-3 0 4" quat=".5 .5 .5 .5"><freejoint/>
    <geom name="red_mesh" type="sdf" mesh="offset" mass="2" pos=".2 -.1 .3" quat=".5 -.5 .5 .5"/></body>'''+BLUE+'</worldbody></mujoco>'
    with arena(xml) as (m,d,env,match):
        d.qpos[:]=np.asarray(m.qpos0);d.qvel[:]=0;mujoco.mj_forward(m,d);env.detailed_observations.begin_interval()
        info=match.build_bot_observation(True,0).details;g=info['my_robot']['geoms']['mesh']
        world=g['vertices']@rotation(g['quaternion']).T+g['position']
        corners=np.array(list(product((-1,1),repeat=3)))*[.2,.6,1.2]+[2,6,12]
        expected=(corners@rotation([.5,-.5,.5,.5]).T+[.2,-.1,.3])@rotation([.5,.5,.5,.5]).T+[-3,0,4]
        for point in expected:assert min(np.linalg.norm(world-point,axis=1))<2e-6
        gid=named(m,'GEOM','red_mesh')
        assert env.detailed_observations.radii[gid]+1e-6>=np.max(np.linalg.norm(g['vertices'],axis=1))
        assert g['faces'].shape==(12,3)
    print('PASS disconnected SDF containment, scaled/recentered mesh frames, conservative proximity bounds',flush=True)


def check_proximity_limits_and_rates():
    # Exercise both sides of the limit and the intermediate pruning threshold.
    for count in (1,32,33,64,65,80):
        red='<body name="red_root" pos="0 0 4"><freejoint/><geom name="red_ball" size=".1" mass="1"/></body>'
        blue='<body name="blue_root" pos="1 0 4"><freejoint/>'+''.join(f'<geom name="blue_g{i}" size=".1" mass="1"/>' for i in range(count))+'</body>'
        xml='<mujoco><option gravity="0 0 0"/><worldbody>'+ARENA+red+blue+'</worldbody></mujoco>'
        with arena(xml) as (m,d,env,match):
            d.qpos[:]=np.asarray(m.qpos0);d.qvel[:]=0;mujoco.mj_forward(m,d)
            for x in (1.,2.2,2.2001,20.):
                d.qpos[7]=x;mujoco.mj_forward(m,d);env.detailed_observations.begin_interval()
                a=match.build_bot_observation(True,0).details;b=match.build_bot_observation(False,0).details
                expected_count=min(count,32) if x<=2.2 else 0
                assert len(a['opponent_proximity'])==expected_count,(count,x,len(a['opponent_proximity']))
                assert a['proximity_truncated']==(count>32 and x<=2.2)
                np.testing.assert_allclose(a['opponent_surface_distance'],x-.2,atol=1e-8)
                assert a['opponent_surface_distance']==b['opponent_surface_distance']
                for i,(ra,rb) in enumerate(zip(a['opponent_proximity'],b['opponent_proximity'])):
                    assert ra['opponent_geom']==f'g{i}' and rb['my_geom']==f'g{i}'
                    np.testing.assert_array_equal(ra['my_point'],rb['opponent_point'])
                    np.testing.assert_array_equal(ra['opponent_point'],rb['my_point'])
                    assert ra['closing_speed']==rb['closing_speed']==0
    rng=np.random.default_rng(61212)
    xml='<mujoco><option gravity="0 0 0"/><worldbody>'+ARENA+'''
    <body name="red_root" pos="-.6 0 4"><freejoint/><geom name="red_shape" type="ellipsoid" size=".1 .3 .2" pos=".1 .1 0" mass="2"/></body>
    <body name="blue_root" pos=".6 0 4"><freejoint/><geom name="blue_shape" type="capsule" size=".1 .2" pos="-.1 0 .1" mass="2"/></body></worldbody></mujoco>'''
    with arena(xml) as (m,d,env,match):
        for trial in range(30):
            d.qpos[:]=np.asarray(m.qpos0)
            for a in (3,10):
                q=rng.normal(size=4);q/=np.linalg.norm(q);d.qpos[a:a+4]=q
            d.qvel[:]=rng.uniform(-2,2,m.nv);mujoco.mj_forward(m,d)
            env.detailed_observations.begin_interval()
            info=match.build_bot_observation(True,0).details
            rate=info['opponent_proximity'][0]['closing_speed']
            qp=np.array(d.qpos);qv=np.array(d.qvel);eps=1e-5;distances=[]
            for sign in (-1,1):
                d.qpos[:]=integrate_positions(m,qp,qv,sign*eps);mujoco.mj_forward(m,d)
                env.detailed_observations.begin_interval()
                distances.append(match.build_bot_observation(True,0).details['opponent_surface_distance'])
            np.testing.assert_allclose(rate,-(distances[1]-distances[0])/(2*eps),atol=3e-4)
    print('PASS proximity cutoff boundaries, 32/64-pair limits, ties, far minimum, perspective symmetry and finite-difference closing speeds',flush=True)


def check_time_and_solver_isolation():
    with arena(STATE_XML,max_steps=100) as (m,d,env,match):
        d.qpos[:]=np.asarray(m.qpos0);d.qvel[:]=0;mujoco.mj_forward(m,d)
        reference=mujoco.MjData(m)
        try:
            reference.qpos[:]=np.asarray(d.qpos);reference.qvel[:]=np.asarray(d.qvel)
            reference.qacc_warmstart[:]=np.asarray(d.qacc_warmstart)
            mujoco.mj_forward(m,reference)
            for step in range(4):
                info=match.build_bot_observation(True,step).details
                assert info['control_dt']==.01
                np.testing.assert_allclose(info['elapsed_time'],step*.01,atol=1e-14)
                np.testing.assert_allclose(info['time_remaining'],(100-step)*.01,atol=1e-14)
                np.testing.assert_allclose(info['contact_interval'],0 if step==0 else .01,atol=1e-14)
                actions=np.linspace(-.2,.2,m.nu,dtype=np.float32);reference.ctrl[:]=actions
                for _ in range(40):mujoco.mj_step(m,reference)
                env.step({'red':actions,'blue':np.zeros(0)})
                np.testing.assert_array_equal(d.qpos,reference.qpos)
                np.testing.assert_array_equal(d.qvel,reference.qvel)
            info=match.build_bot_observation(True,101).details
            assert info['time_remaining']==0 and info['elapsed_time']==1.01
            env.reset(seed=1)
            info=match.build_bot_observation(True,0).details
            assert info['elapsed_time']==0 and info['time_remaining']==1 and info['contact_interval']==0
        finally:release(reference)
    print('PASS time fields, reset, control intervals, and bit-identical physics with/without observation queries',flush=True)


def check_self_contacts_and_environment():
    xml='<mujoco><option gravity="0 0 0"/><worldbody>'+ARENA+'''
    <geom name="obstacle" size=".15" pos="-.3 0 4"/>
    <body name="red_root" pos="0 0 4"><freejoint/><geom name="red_root_geom" size=".05" mass="1" pos="0 0 1"/>
    <body name="red_a"><joint type="slide"/><geom name="red_a_geom" size=".2" mass="1"/></body>
    <body name="red_b" pos=".3 0 0"><joint type="slide"/><geom name="red_b_geom" size=".2" mass="1"/></body></body>'''+BLUE+'</worldbody></mujoco>'
    with arena(xml) as (m,d,env,match):
        d.qpos[:]=np.asarray(m.qpos0);d.qvel[:]=0;mujoco.mj_forward(m,d)
        detail=env.detailed_observations;detail.begin_interval();detail.capture_contacts()
        info=match.build_bot_observation(True,0).details
        own=[c for c in info['contacts'] if c['other_kind']=='self']
        assert len(own)==2
        np.testing.assert_allclose(own[0]['force_on_me'],-own[1]['force_on_me'],atol=1e-12)
        assert own[0]['my_geom']==own[1]['other_geom']
        assert any(c['other_kind']=='environment' and c['other_geom']=='obstacle' for c in info['contacts'])
    print('PASS self-contact duplication and non-platform environment contacts',flush=True)


def check_rotated_box_intersections():
    rng=np.random.default_rng(61213)
    xml='<mujoco><worldbody><geom type="box" size=".2 .3 .4" pos=".1 .1 .1" quat=".5 .5 .5 .5"/><geom type="box" size=".2 .3 .4" pos="2 1 1" quat=".5 .5 .5 .5"/></worldbody></mujoco>'
    m=mujoco.MjModel.from_xml_string(xml);d=mujoco.MjData(m)
    separated=intersecting=0
    try:
        for i in range(400):
            sizes=rng.uniform(.02,.8,(2,3))
            if i%4==0:sizes[:,2]=1e-4 # thin plates and edge/edge cases
            quats=rng.normal(size=(2,4));quats/=np.linalg.norm(quats,axis=1)[:,None]
            matrices=[rotation(q) for q in quats]
            centers=rng.uniform(-.8,.8,(2,3)) if i%3 else np.zeros((2,3))
            axes=[*matrices[0].T,*matrices[1].T]+[np.cross(a,b) for a in matrices[0].T for b in matrices[1].T]
            gaps=[]
            for axis in axes:
                if np.linalg.norm(axis)<1e-12:continue
                axis=axis/np.linalg.norm(axis)
                gaps.append(abs((centers[1]-centers[0])@axis)-np.abs(matrices[0].T@axis)@sizes[0]-np.abs(matrices[1].T@axis)@sizes[1])
            lower=max(gaps)
            m.geom_size[:]=sizes;m.geom_pos[:]=centers;m.geom_quat[:]=quats
            mujoco.mj_forward(m,d);queries=SurfaceQueries(m);queries.update(d)
            forward=queries.distance(d,0,1)[0];reverse=queries.distance(d,1,0)[0]
            np.testing.assert_allclose(forward,reverse,atol=1e-7)
            if lower<=0:
                intersecting+=1;np.testing.assert_allclose(forward,0,atol=1e-8)
            else:
                separated+=1;assert forward>=lower-1e-8
    finally:release(d,m)
    print(f'PASS independent oriented-box separating-axis oracle: {separated} separated, {intersecting} intersecting, including thin plates',flush=True)


def check_hollow_mesh():
    import xml.etree.ElementTree as ET
    outer=ET.fromstring(cube_mesh('hollow',[([0,0,0],[1,1,1])]))
    inner=ET.fromstring(cube_mesh('inner',[([0,0,0],[.6,.6,.6])]))
    faces=np.array(list(map(int,inner.get('face').split()))).reshape(-1,3)[:,::-1]+8
    outer.set('vertex',outer.get('vertex')+' '+inner.get('vertex'))
    outer.set('face',outer.get('face')+' '+' '.join(map(str,faces.ravel())))
    asset=ET.tostring(outer,encoding='unicode')
    for position,expected in (([0,0,0],.5),([.5,0,0],0),([.8,0,0],0),([1.4,0,0],.3)):
        xml='<mujoco><asset>'+asset+'</asset><worldbody><geom type="sdf" mesh="hollow"/><geom type="sphere" size=".1" pos="'+' '.join(map(str,position))+'"/></worldbody></mujoco>'
        m=mujoco.MjModel.from_xml_string(xml);d=mujoco.MjData(m)
        try:
            mujoco.mj_forward(m,d);queries=SurfaceQueries(m);queries.update(d)
            for a,b in ((0,1),(1,0)):
                np.testing.assert_allclose(queries.distance(d,a,b)[0],expected,atol=2e-7)
        finally:release(d,m)
    print('PASS hollow SDF: cavity clearance, internal/external contact, containment and reversed query order',flush=True)


def check_wrapped_tendons_and_defaults():
    for kind in ('sphere','cylinder'):
        xml='''<mujoco><compiler angle="radian"/><option gravity="0 0 0"/>
        <default><joint damping="3" frictionloss=".2" limited="true" range="0 .8"/>
        <motor ctrllimited="true" ctrlrange="-.3 .7"/></default><worldbody>'''+ARENA+f'''
        <body name="red_root" pos="-2 0 4"><freejoint/>
        <geom name="red_wrap" type="{kind}" size=".1 .2" mass="2"/>
        <site name="red_a" pos="-.4 0 0"/><site name="red_branch_a" pos="-.4 0 .4"/>
        <site name="red_side" pos="0 .2 0"/>
        <body name="red_slider" pos=".4 0 0"><joint name="red_slide" type="slide" axis="1 0 0"/>
        <geom name="red_end_geom" size=".03" mass="1"/><site name="red_b"/><site name="red_branch_b" pos="0 0 .4"/></body>
        </body>'''+BLUE+'''</worldbody><tendon><spatial name="red_cable" stiffness="12" damping="4" frictionloss=".3" limited="true" range=".7 2" springlength=".7 1.2">
        <site site="red_a"/><geom geom="red_wrap" sidesite="red_side"/><site site="red_b"/>
        <pulley divisor="2"/><site site="red_branch_a"/><site site="red_branch_b"/>
        </spatial></tendon><actuator><motor name="red_pull" tendon="red_cable" gear="-3"/></actuator></mujoco>'''
        with arena(xml) as (m,d,env,match):
            d.qpos[:]=np.asarray(m.qpos0);d.qpos[7]=.1;d.qvel[:]=0;d.qvel[6]=.7
            mujoco.mj_forward(m,d);env.detailed_observations.begin_interval()
            info=match.build_bot_observation(True,0).details;robot=info['my_robot'];t=robot['tendons']['cable']
            def expected(q):
                a,b,r=.4,.4+q,.1
                return math.sqrt(a*a-r*r)+math.sqrt(b*b-r*r)+r*(math.pi-math.acos(r/a)-math.acos(r/b))+(a+b)/2
            np.testing.assert_allclose(t['length'],expected(.1),atol=1e-10)
            np.testing.assert_allclose(t['velocity'],.7*(expected(.100001)-expected(.099999))/2e-6,atol=1e-8)
            assert [p['type'] for p in t['path']]==['site',kind,'site','pulley','site','site']
            assert t['path'][1]['geom']=='wrap' and t['path'][1]['sidesite']=='side'
            assert t['path'][3]['divisor']==2
            assert t['limited'] and t['stiffness']==12 and t['damping']==4 and t['frictionloss']==.3
            np.testing.assert_allclose(t['springlength'],[.7,1.2]);np.testing.assert_allclose(t['range'],[.7,2])
            j=robot['joints']['slide'];assert j['limited'];np.testing.assert_allclose(j['damping'],[3]);np.testing.assert_allclose(j['frictionloss'],[.2])
            motor=robot['motors']['pull'];assert motor['ctrl_limited']
            np.testing.assert_allclose(motor['ctrl_range'],[-.3,.7]);np.testing.assert_allclose(motor['gear'],[-3,0,0,0,0,0])
            np.testing.assert_allclose(env.red_contender.actuator_joint_velocity(env.detailed_observations.data)['pull'],t['velocity'])
    print('PASS sphere/cylinder tendon wraps, side sites, pulley branches, analytic lengths/rates and inherited limits',flush=True)


def run_all():
    check_false_zero_regression()
    check_primitive_distances()
    check_sphere_oracles()
    check_state_frames_and_rates()
    check_unnamed_parts()
    check_contact_impulses()
    check_mesh_containment_and_frames()
    check_proximity_limits_and_rates()
    check_time_and_solver_isolation()
    check_self_contacts_and_environment()
    check_rotated_box_intersections()
    check_hollow_mesh()
    check_wrapped_tendons_and_defaults()


if __name__=='__main__':run_all()
