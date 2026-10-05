"""Additional randomized and adversarial observation contract checks."""
from itertools import product
import math
import numpy as np
import mujoco
from observation_stress import arena, ARENA, BLUE, STATE_XML, rotation, release, support, cube_mesh
from mjarena.envs.surface_distance import SurfaceQueries, _inside_mesh


def check_mesh_grazing_containment():
    asset=cube_mesh('cube',[([0,0,0],[1,1,1])])
    ray=np.array([1.,.371390676354,.529137])
    xml='<mujoco><asset>'+asset+'</asset><worldbody><geom type="sdf" mesh="cube"/><geom type="sphere" size=".1" pos=".3 .1 .2"/></worldbody></mujoco>'
    m=mujoco.MjModel.from_xml_string(xml);d=mujoco.MjData(m)
    try:
        for edge in ([-1,1,0],[-1,0,1],[0,-1,1],[-1,1,1]):
            for offset in (-1e-9,0.,1e-9):
                center=np.array(edge)-ray+[0,offset,0]
                m.geom_pos[1]=center;mujoco.mj_forward(m,d)
                queries=SurfaceQueries(m);queries.update(d)
                expected=np.linalg.norm(np.maximum(abs(center)-1,0))-.1
                assert expected>.2
                for a,b in ((0,1),(1,0)):
                    distance,pa,pb=queries.distance(d,a,b)
                    np.testing.assert_allclose(distance,expected,atol=2e-7)
                    np.testing.assert_allclose(np.linalg.norm(pa-pb),distance,atol=1e-8)
    finally:release(d,m)
    print('PASS mesh edge/vertex grazing containment: separated sphere stays separated',flush=True)


def check_mesh_winding_oracle():
    import xml.etree.ElementTree as ET
    rng=np.random.default_rng(93101)
    asset=ET.fromstring(cube_mesh('cube',[([0,0,0],[1,1,1])]))
    vertices=np.fromstring(asset.get('vertex'),sep=' ').reshape(-1,3)
    faces=np.fromstring(asset.get('face'),sep=' ',dtype=int).reshape(-1,3)
    triangles=vertices[faces]
    count=0
    for scale in (1e-6,1e-3,1.,10.,100.):
        q=rng.normal(size=4);q/=np.linalg.norm(q);matrix=rotation(q)
        center=rng.uniform(-10,10,3)
        shell=triangles*scale@matrix.T+center
        hollow=np.concatenate([shell,triangles[:,::-1]*scale*.6@matrix.T+center])
        for point in rng.uniform(-1.5,1.5,(500,3)):
            world=point*scale@matrix.T+center
            inside=bool(np.max(abs(point))<1)
            assert _inside_mesh(world,shell)==inside,(scale,point)
            assert _inside_mesh(world,hollow)==(inside and np.max(abs(point))>.6),(scale,point)
            count+=2
    print(f'PASS {count} independent solid/hollow-box containment classifications across scales and rotations',flush=True)


def check_mesh_surface_certificate():
    import mjarena.envs.surface_distance as surface
    rng=np.random.default_rng(93102)
    asset=cube_mesh('pieces',[([-1.2,0,0],[.3,.4,.2]),([1.2,0,0],[.3,.4,.2])])+cube_mesh('box',[([0,0,0],[.2,.1,.3])])
    original=surface._on_mesh_surface
    accepted=rejected=0
    def certificate(point,triangles):
        nonlocal accepted,rejected
        result=original(point,triangles)
        accepted+=int(result);rejected+=int(not result)
        return result
    try:
        for kind in ('sphere','box','sdf'):
            other='mesh="box"' if kind=='sdf' else 'size=".1 .2 .3"'
            xml=f'<mujoco><asset>{asset}</asset><worldbody><geom type="sdf" mesh="pieces" quat=".5 .5 .5 .5"/><geom type="{kind}" {other} pos=".3 .2 .1" quat=".5 .5 .5 .5"/></worldbody></mujoco>'
            m=mujoco.MjModel.from_xml_string(xml);d=mujoco.MjData(m)
            try:
                for trial in range(30):
                    # Includes hull witnesses spanning the empty gap between parts.
                    qs=rng.normal(size=(2,4));qs/=np.linalg.norm(qs,axis=1)[:,None]
                    m.geom_quat[:]=qs;m.geom_pos[1]=rng.uniform(-2,2,3)
                    mujoco.mj_forward(m,d);query=SurfaceQueries(m);query.update(d)
                    surface._on_mesh_surface=certificate
                    result=query.distance(d,0,1)
                    surface._on_mesh_surface=lambda *_:False
                    reference=query.distance(d,0,1)
                    np.testing.assert_allclose(result[0],reference[0],atol=3e-7,rtol=1e-7,err_msg=f'{kind}, trial {trial}')
                    np.testing.assert_allclose(np.linalg.norm(result[1]-result[2]),result[0],atol=1e-8)
            finally:release(d,m)
    finally:surface._on_mesh_surface=original
    assert accepted>0 and rejected>0,(accepted,rejected)
    print(f'PASS 90 mesh queries against full triangle search; certificate accepted {accepted}, rejected {rejected}',flush=True)


def check_generated_name_collisions():
    bk=int(mujoco.mjtObj.mjOBJ_BODY);gk=int(mujoco.mjtObj.mjOBJ_GEOM);sk=int(mujoco.mjtObj.mjOBJ_SITE)
    xml='<mujoco><option gravity="0 0 0"/><worldbody>'+ARENA+f'''
    <body name="red_root" pos="-2 0 4"><freejoint/><geom name="red_base" size=".1" mass="2"/>
    <site/><site name="red_@{sk}:0" pos=".2 0 0"/>
    <body pos="1 0 0"><geom size=".1" mass="3"/></body>
    <body name="red_@{bk}:2" pos="0 1 0"><geom name="red_@{gk}:3" size=".1" mass="5"/></body>
    </body>'''+BLUE+'</worldbody></mujoco>'
    with arena(xml) as (m,d,env,match):
        d.qpos[:]=np.asarray(m.qpos0);mujoco.mj_forward(m,d);env.detailed_observations.begin_interval()
        state=match.build_bot_observation(True,0).details['my_robot']
        assert len(state['bodies'])==3, list(state['bodies'])
        assert len(state['geoms'])==3, list(state['geoms'])
        assert len(state['sites'])==2, list(state['sites'])
        assert f'@{bk}:2' in state['bodies'] and f'@{gk}:3' in state['geoms'] and f'@{sk}:0' in state['sites']
        assert state['mass']==10
        np.testing.assert_allclose(state['com_position'],[-1.7,.5,4],atol=1e-10)
        for record in state['geoms'].values():assert record['body'] in state['bodies']
        for record in state['sites'].values():assert record['body'] in state['bodies']
    print('PASS authored names colliding with generated body/geom/site names',flush=True)


def check_nondefault_control_timing():
    xml='<mujoco><option gravity="0 0 0"/><worldbody>'+ARENA+'''
    <body name="red_root" pos="-2 0 4"><freejoint/><geom size=".1" mass="2"/></body>'''+BLUE+'</worldbody></mujoco>'
    count=0
    for fidelity,requested,repeats in product(('high','low'),(None,.01013,.00001),(1,2,3)):
        with arena(xml,max_steps=4,contact_fidelity=fidelity,control_timestep=requested,
                   apply_n_repeated_actions=repeats) as (m,d,env,match):
            initial=match.build_bot_observation(True,0).details
            start=float(d.time)
            assert initial['elapsed_time']==initial['contact_interval']==0
            for step in range(1,5):
                before=float(d.time);env.step({'red':np.zeros(0),'blue':np.zeros(0)})
                interval=float(d.time)-before
                current=match.build_bot_observation(True,env.t).details
                context=f'fidelity={fidelity} requested={requested} repeats={repeats}'
                np.testing.assert_allclose(initial['control_dt'],interval,atol=1e-12,err_msg=context)
                np.testing.assert_allclose(current['control_dt'],interval,atol=1e-12,err_msg=context)
                np.testing.assert_allclose(current['contact_interval'],interval,atol=1e-12,err_msg=context)
                np.testing.assert_allclose(current['elapsed_time'],float(d.time)-start,atol=1e-12,err_msg=context)
                np.testing.assert_allclose(current['time_remaining'],(4-step)*interval,atol=1e-12,err_msg=context)
            env.reset(seed=1)
            reset=match.build_bot_observation(True,0).details
            assert reset['elapsed_time']==reset['contact_interval']==0 and reset['contact_impulses']==[]
            np.testing.assert_allclose(reset['time_remaining'],4*interval,atol=1e-12)
            if fidelity=='high' and requested is None and repeats==2:
                record=match.run(save_video=False,quiet=True)
                np.testing.assert_allclose(record.control_dt,interval,atol=1e-12)
            count+=1
    print(f'PASS {count} timing configurations: fidelity, rounded/sub-physics control periods, action repeats, expiry and reset',flush=True)


def check_generated_articulation_names():
    jk=int(mujoco.mjtObj.mjOBJ_JOINT);tk=int(mujoco.mjtObj.mjOBJ_TENDON);ak=int(mujoco.mjtObj.mjOBJ_ACTUATOR)
    xml='<mujoco><option gravity="0 0 0"/><worldbody>'+ARENA+f'''
    <body name="red_root" pos="-2 0 4"><freejoint/><geom size=".1" mass="2"/>
      <body name="red_arm" pos=".3 0 0"><joint/><geom size=".1" mass="3"/></body>
      <body name="red_other_arm" pos="-.3 0 0"><joint name="red_@{jk}:1"/><geom size=".1" mass="5"/></body>
    </body>'''+BLUE+f'''</worldbody><tendon>
      <fixed><joint joint="red_@{jk}:1" coef="2"/></fixed>
      <fixed name="red_@{tk}:0"><joint joint="red_@{jk}:1" coef="3"/></fixed>
    </tendon><actuator><motor joint="red_@{jk}:1"/>
      <motor name="red_@{ak}:0" tendon="red_@{tk}:0"/>
    </actuator></mujoco>'''
    with arena(xml) as (m,d,env,match):
        state=match.build_bot_observation(True,0).details['my_robot']
        for category,index in (('joints',jk),('tendons',tk),('motors',ak)):
            records=state[category]
            assert len(records)==2,list(records)
            identifier=f'@{index}:{1 if category=="joints" else 0}'
            assert identifier in records and identifier+'~' in records
        for tendon in state['tendons'].values():
            assert tendon['path'][0]['joint']==f'@{jk}:1'
        for motor in state['motors'].values():
            category='joints' if motor['transmission']=='joint' else 'tendons'
            assert motor['target'] in state[category]
    print('PASS authored names colliding with generated joint/tendon/motor names and references',flush=True)


def check_extreme_shape_gaps(seed=92101):
    rng=np.random.default_rng(seed)
    kinds=('box','capsule','cylinder','ellipsoid')
    worst=0.;count=0
    for ka,kb in product(kinds,repeat=2):
        xml=f'<mujoco><worldbody><geom type="{ka}" size=".1 .2 .3" pos="1 1 1" quat=".5 .5 .5 .5"/><geom type="{kb}" size=".1 .2 .3" pos="2 1 1" quat=".5 .5 .5 .5"/></worldbody></mujoco>'
        m=mujoco.MjModel.from_xml_string(xml);d=mujoco.MjData(m)
        try:
            for trial in range(60):
                sizes=10**rng.uniform(-5,0,(2,3))
                qs=rng.normal(size=(2,4));qs/=np.linalg.norm(qs,axis=1)[:,None]
                rotations=[rotation(q) for q in qs]
                normal=rng.normal(size=3);normal/=np.linalg.norm(normal)
                gap=(0.,1e-6,1e-4,.01,.3,3.)[trial%6]
                origin=rng.uniform(-10,10,3)
                point=origin+rotations[0]@support(ka,sizes[0],rotations[0].T@normal)
                other=point-rotations[1]@support(kb,sizes[1],-rotations[1].T@normal)+gap*normal
                m.geom_size[:]=sizes;m.geom_pos[:]=[origin,other];m.geom_quat[:]=qs
                mujoco.mj_forward(m,d);queries=SurfaceQueries(m);queries.update(d)
                distance,a,b=queries.distance(d,0,1)
                error=abs(distance-gap);worst=max(worst,error);count+=1
                np.testing.assert_allclose(distance,gap,atol=2e-7,rtol=2e-6,
                    err_msg=f'seed={seed} {ka}/{kb} trial={trial} sizes={sizes.tolist()}')
                np.testing.assert_allclose(np.linalg.norm(a-b),distance,atol=2e-8)
        finally:release(d,m)
    print(f'PASS {count} high-aspect-ratio shape queries, seed={seed}, worst gap error={worst:.3g} m',flush=True)


def check_long_motion_and_resets(seed=92102, steps=600):
    rng=np.random.default_rng(seed)
    with arena(STATE_XML.replace('gravity="0 0 0"','gravity="0 0 -9.81"'),max_steps=steps) as (m,d,env,match):
        saved=None;contact_steps=0
        for step in range(steps):
            if step in (steps//3,2*steps//3):
                env.reset(seed=step)
            t=env.t
            left=match.build_bot_observation(True,t).details
            right=match.build_bot_observation(False,t).details
            def finite(value):
                if isinstance(value,dict):
                    for child in value.values():finite(child)
                elif isinstance(value,(list,tuple)):
                    for child in value:finite(child)
                elif isinstance(value,np.ndarray):assert np.isfinite(value).all()
                elif isinstance(value,(float,np.floating)):assert math.isfinite(value)
            finite(left);finite(right)
            assert left['my_mass']==right['opponent_mass']==21
            np.testing.assert_allclose(left['elapsed_time'],t*.01,atol=1e-12)
            np.testing.assert_allclose(left['time_remaining'],(steps-t)*.01,atol=1e-12)
            np.testing.assert_allclose(left['contact_interval'],0 if t==0 else .01,atol=1e-12)
            if t==0:assert left['contact_impulses']==[]
            np.testing.assert_array_equal(left['my_com_velocity'],right['opponent_com_velocity'])
            assert left['opponent_surface_distance']==right['opponent_surface_distance']
            if left['contacts']:contact_steps+=1
            for category in ('bodies','geoms','sites'):
                for name,record in left['my_robot'][category].items():
                    opponent=right['opponent_robot'][category][name]
                    np.testing.assert_array_equal(record['position'],opponent['position'])
                    np.testing.assert_allclose(np.linalg.norm(record['quaternion']),1,atol=1e-10)
            # Previously retained observations must remain unchanged after dynamics/reset.
            if saved is not None:
                prior,com,position,impulse=saved
                np.testing.assert_array_equal(prior['my_robot']['com_position'],com)
                np.testing.assert_array_equal(prior['my_robot']['bodies']['root']['position'],position)
                if impulse is not None:np.testing.assert_array_equal(prior['contact_impulses'][0]['impulse_on_me'],impulse)
            if step%23==0:
                saved=(left,left['my_robot']['com_position'].copy(),left['my_robot']['bodies']['root']['position'].copy(),left['contact_impulses'][0]['impulse_on_me'].copy() if left['contact_impulses'] else None)
            env.step({'red':rng.uniform(-.15,.15,m.nu),'blue':np.zeros(0)})
        assert contact_steps>30,contact_steps
    print(f'PASS {steps} moving observation pairs with contacts, retained snapshots and repeated reset, seed={seed}',flush=True)


def run_all():
    check_mesh_grazing_containment()
    check_mesh_winding_oracle()
    check_mesh_surface_certificate()
    check_generated_name_collisions()
    check_nondefault_control_timing()
    check_generated_articulation_names()
    check_extreme_shape_gaps()
    check_long_motion_and_resets()


if __name__=='__main__':run_all()
