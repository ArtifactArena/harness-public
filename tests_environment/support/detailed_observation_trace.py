"""Native regression checks for the detailed controller interface."""
from pathlib import Path
import json
import numpy as np
import mujoco
from mjarena.envs.surface_distance import SurfaceQueries
from mjarena.envs.detailed_observations import DetailedObservations
from mjarena.envs.sumo import SumoEnv
from mjarena.agents.runtime import BotRuntime
from mjarena.runner.episode import Match


def check_surface_distances():
    polygon=[(0,0),(2,0),(2,1),(1,1),(1,2),(0,2)]
    vertices=[(x,y,z) for z in (-.2,.2) for x,y in polygon]
    triangles=[(0,1,3),(1,2,3),(0,3,5),(3,4,5)]
    faces=[(c,b,a) for a,b,c in triangles]+[(a+6,b+6,c+6) for a,b,c in triangles]
    for a in range(6):
        b=(a+1)%6;faces.extend([(a,b,b+6),(a,b+6,a+6)])
    asset='<asset><mesh name="concave" vertex="'+ ' '.join(str(v) for p in vertices for v in p)+'" face="'+' '.join(str(v) for p in faces for v in p)+'"/></asset>'
    for kind,size,expected in [('sphere','.1',.4),('box','.1 .1 .1',.4),('capsule','.1 .1',.4),('cylinder','.1 .1',.4)]:
        xml='<mujoco>'+asset+'<worldbody><geom type="sdf" mesh="concave"/><geom type="'+kind+'" size="'+size+'" pos="1.5 1.5 0"/></worldbody></mujoco>'
        m=mujoco.MjModel.from_xml_string(xml);d=mujoco.MjData(m);mujoco.mj_forward(m,d)
        q=SurfaceQueries(m);q.update(d)
        distance,a,b=q.distance(d,0,1)
        np.testing.assert_allclose(distance,expected,atol=2e-5)
        np.testing.assert_allclose(np.linalg.norm(a-b),distance,atol=2e-5)
        print('Concave',kind,'gap',distance)
        for resource in (d,m):
            if hasattr(resource,'close'):resource.close()

    xml='<mujoco>'+asset+'<worldbody><geom type="sdf" mesh="concave"/><geom type="sdf" mesh="concave" pos="0 4 0"/></worldbody></mujoco>'
    m=mujoco.MjModel.from_xml_string(xml);d=mujoco.MjData(m);mujoco.mj_forward(m,d)
    q=SurfaceQueries(m);q.update(d)
    np.testing.assert_allclose(q.distance(d,0,1)[0],2.,atol=2e-5)
    for resource in (d,m):
        if hasattr(resource,'close'):resource.close()


XML='''<mujoco><compiler angle="radian"/><option timestep=".00025" gravity="0 0 -9.81"/>
<worldbody><geom name="outside_floor" type="plane" size="20 20 .1"/>
<geom name="sumo_ring" type="cylinder" size="7.5 1" pos="0 0 1"/>
<body name="red_root" pos="-1 0 2.2"><freejoint/><geom name="red_chassis" type="box" size=".2 .2 .2" mass="10"/>
<site name="red_anchor" pos="0 0 0"/>
<body name="red_arm" pos="0 0 .4"><joint name="red_slide" type="slide" axis="1 0 0"/><geom name="red_tip" type="sphere" size=".1" mass="2"/><site name="red_end" pos="1 0 0"/></body>
<body name="red_passive" pos="0 0 .8"><joint name="red_hinge" axis="0 1 0"/><geom name="red_passive_geom" type="sphere" size=".1" mass="1"/></body>
<body name="red_ball_body" pos="0 0 1.2"><joint name="red_ball" type="ball"/><geom name="red_ball_geom" size=".1" mass="1"/></body>
</body><body name="blue_root" pos="1 0 2.2"><freejoint/><geom name="blue_chassis" type="box" size=".2 .2 .2" mass="12"/></body></worldbody>
<tendon><fixed name="red_fixed"><joint joint="red_slide" coef="2"/><joint joint="red_hinge" coef="-3"/></fixed><spatial name="red_cable"><site site="red_anchor"/><site site="red_end"/></spatial></tendon>
<actuator><motor name="red_drive" joint="red_slide" gear="-4"/><motor name="red_pull" tendon="red_fixed" gear="5"/></actuator></mujoco>'''


def check_observations():
    m=mujoco.MjModel.from_xml_string(XML);d=mujoco.MjData(m)
    red=BotRuntime(m,d,lambda obs:{'drive':0.,'pull':0.},'red_')
    blue=BotRuntime(m,d,lambda obs:{},'blue_')
    env=SumoEnv(m,d,'',red,blue,max_steps=3)
    match=Match(env,red,blue,max_steps=3,headless=True)
    env.reset(seed=0)
    # Controlled state after settling, with asymmetric articulation and root motion.
    d.qpos[int(m.jnt_qposadr[mujoco.mj_name2id(m,mujoco.mjtObj.mjOBJ_JOINT,'red_slide')])]=.3
    d.qvel[int(m.jnt_dofadr[mujoco.mj_name2id(m,mujoco.mjtObj.mjOBJ_JOINT,'red_slide')])]=.7
    d.qvel[int(m.jnt_dofadr[mujoco.mj_name2id(m,mujoco.mjtObj.mjOBJ_JOINT,'red_hinge')])]=-.2
    root_dof=int(m.jnt_dofadr[0]);d.qvel[root_dof:root_dof+3]=[.5,-.3,.2]
    d.qvel[root_dof+3:root_dof+6]=[.1,.2,.3]
    mujoco.mj_forward(m,d)
    detail=env.detailed_observations;detail.cached=None;detail.capture_contacts()
    before=np.array(d.qpos).copy()
    obs=match.build_bot_observation(True,0); info=obs.details
    np.testing.assert_allclose(info['platform']['center'],[0.,0.,2.])
    assert info['platform']['center'][2]==info['platform']['top_z']
    np.testing.assert_allclose(d.geom_xpos[env._boundary_geom_id],[0.,0.,1.])
    red.policy_callable=lambda data: {'drive': float(data['my_robot']['joints']['slide']['position']), 'pull': 0.}
    np.testing.assert_allclose(red.act(obs),[.3,0.],atol=1e-6)
    state=info['my_robot']
    assert state['root_body']=='root'
    assert set(state['joints'])=={'slide','hinge','ball'}
    np.testing.assert_allclose(state['joints']['slide']['position'],.3)
    np.testing.assert_allclose(state['joints']['slide']['velocity'],.7)
    np.testing.assert_allclose(state['tendons']['fixed']['velocity'],2*.7-3*(-.2))
    assert state['motors']['drive']['target']=='slide'
    assert state['motors']['pull']['target']=='fixed'
    assert state['tendons']['cable']['path'][0]['site']=='anchor'
    assert info['my_mass']==14 and info['opponent_mass']==12
    bodies=list(state['bodies'].values())
    com=sum(b['mass']*b['com_position'] for b in bodies)/14
    vel=sum(b['mass']*b['com_velocity'] for b in bodies)/14
    np.testing.assert_allclose(info['my_com_velocity'],vel)
    np.testing.assert_allclose(obs.my_pos,com,atol=1e-6)
    np.testing.assert_array_equal(d.qpos,before) # Observation query does not mutate physics.
    # Detached snapshots: changes made by one controller cannot change the next observation.
    state['bodies']['root']['mass']=-100
    other=match.build_bot_observation(False,0).details
    assert other['opponent_robot']['bodies']['root']['mass']==10
    for contact in info['contacts']:
        if contact['other_kind']=='platform':assert contact['force_on_me'][2]>=-1e-8
    env.step({'red':np.zeros(2),'blue':np.zeros(0)})
    next_info=match.build_bot_observation(True,1).details
    np.testing.assert_allclose(next_info['contact_interval'],.01)
    assert next_info['contact_impulses']
    assert next_info['elapsed_time']==.01
    assert all(c['impulse_on_me'][2]>=-1e-7 for c in next_info['contact_impulses'] if c['other_kind']=='platform')
    env.reset(seed=1)
    assert match.build_bot_observation(True,0).details['contact_impulses']==[]
    print('Detailed observation checks passed')
    detail.close()
    for resource in (d,m):
        if hasattr(resource,'close'):resource.close()


def check_proximity_contract():
    def robot(prefix,x):
        geoms=''.join('<geom name="'+prefix+'_g'+str(i)+'" type="sphere" pos="0 '+str(i*.01)+' 0" size=".1" mass="1"/>' for i in range(6))
        return '<body name="'+prefix+'_root" pos="'+str(x)+' 0 2.2"><freejoint/>'+geoms+'</body>'
    xml='<mujoco><worldbody><geom name="outside_floor" type="plane" size="20 20 .1"/><geom name="sumo_ring" type="cylinder" size="7.5 1" pos="0 0 1"/>'+robot('red',-.5)+robot('blue',.5)+'</worldbody></mujoco>'
    m=mujoco.MjModel.from_xml_string(xml);d=mujoco.MjData(m)
    red=BotRuntime(m,d,lambda obs:{},'red_');blue=BotRuntime(m,d,lambda obs:{},'blue_')
    env=SumoEnv(m,d,'',red,blue,max_steps=3);match=Match(env,red,blue,max_steps=3,headless=True)
    env.reset(seed=0);d.qpos[:]=np.asarray(m.qpos0)
    d.qvel[:3]=[1,0,0];d.qvel[6:9]=[-1,0,0];mujoco.mj_forward(m,d)
    info=match.build_bot_observation(True,0).details
    assert len(info['opponent_proximity'])==32 and info['proximity_truncated']
    np.testing.assert_allclose(info['opponent_surface_distance'],.8)
    first=info['opponent_proximity'][0]
    np.testing.assert_allclose(first['closing_speed'],2.)
    opposite=match.build_bot_observation(False,0).details['opponent_proximity'][0]
    np.testing.assert_allclose(first['my_point'],opposite['opponent_point'])
    np.testing.assert_allclose(first['closing_speed'],opposite['closing_speed'])
    d.qpos[7]=10;env.detailed_observations.cached=None
    far=match.build_bot_observation(True,0).details
    assert far['opponent_proximity']==[] and not far['proximity_truncated']
    np.testing.assert_allclose(far['opponent_surface_distance'],10.3)
    env.detailed_observations.close()
    for resource in (d,m):
        if hasattr(resource,'close'):resource.close()
    print('Proximity cutoff, limit, witnesses, and closing-speed checks passed')


if __name__=='__main__':
    check_surface_distances()
    check_observations()
    check_proximity_contract()
