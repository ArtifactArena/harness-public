"""Native checks: locomotion actuation must be internal to the robot."""
from types import SimpleNamespace
import mujoco
import numpy as np
from lxml import etree
from mjarena.design_shop.utils import inject_motor_mass
from mjarena.envs.utils import _collect_name_map, _apply_name_map
from mjarena.envs.detailed_observations import DetailedObservations
from mjarena.design_shop.utils import validate_internal_actuation
from mjarena.design_shop.rules.mj_validators import validate_control_constraints
from mjarena.envs.sumo import SumoEnv
from mjarena.agents.runtime import BotRuntime
from mjarena.runner.episode import Match


def robot(motor, joint='<freejoint name="root"/>', world='', tendon=''):
    return ('<mujoco><worldbody>'+world+'<body name="red_root">'+joint+
            '<geom name="shell" size=".2" mass="10"/><site name="inside"/>'+
            '<body name="arm" pos="0 0 .5"><joint name="hinge"/><geom name="tip" size=".1" mass="1"/>'+
            '<site name="end"/></body></body></worldbody>'+tendon+
            '<actuator>'+motor+'</actuator></mujoco>')


def close(model):
    if hasattr(model,'close'):model.close()


def check_transmission_rules():
    invalid = [
        robot('<motor name="force" joint="root" gear="1 0 0 0 0 0"/>'),
        robot('<motor name="torque" joint="root" gear="0 0 0 1 0 0"/>'),
        robot('<motor joint="root"/>',joint='<joint name="root" type="free"/>'),
        robot('<motor jointinparent="root" gear="0 0 0 0 0 1"/>'),
        robot('<motor site="inside" gear="0 0 1 0 0 0"/>'),
        robot('<adhesion body="red_root" gain="1" ctrlrange="0 1"/>'),
        robot('',world='<site name="world_anchor" pos="0 0 1"/>',
              tendon='<tendon><spatial name="anchor" stiffness="10"><site site="world_anchor"/><site site="inside"/></spatial></tendon>'),
    ]
    config=SimpleNamespace(max_dof_damping=600,max_frictionloss=600,max_actuator_gear=None)
    for xml in invalid:
        model=mujoco.MjModel.from_xml_string(xml)
        errors=validate_internal_actuation(model)
        assert errors,xml
        assert not validate_control_constraints(model,config).passed
        close(model)
    valid=[robot('<motor joint="hinge"/>'),
           robot('<motor tendon="cable"/>',tendon='<tendon><spatial name="cable"><site site="inside"/><site site="end"/></spatial></tendon>'),
           robot('<motor tendon="coupling"/>',tendon='<tendon><fixed name="coupling"><joint joint="hinge" coef="2"/></fixed></tendon>')]
    for kind in ('hinge','slide','ball'):
        for transmission in ('joint','jointinparent'):
            valid.append(robot('<motor '+transmission+'="hinge"/>').replace('<joint name="hinge"/>','<joint name="hinge" type="'+kind+'"/>'))
    for xml in valid:
        model=mujoco.MjModel.from_xml_string(xml)
        assert validate_internal_actuation(model)==[]
        assert validate_control_constraints(model,config).passed
        close(model)
    print('PASS: internal joints/tendons accepted; root, unreferenced site, body, and world-anchor actuation rejected')



def check_jointinparent_mass_frame_and_observations():
    # Rotating the child changes the local torque needed for a parent-frame motor.
    for transmission, expected in [('joint', [3., 4., 0.]), ('jointinparent', [4., -3., 0.])]:
        xml=robot('<motor name="drive" '+transmission+'="hinge" gear="3 4 0"/>')
        xml=xml.replace('<joint name="hinge"/>', '<joint name="hinge" type="ball"/>')
        xml=inject_motor_mass(xml, .2)
        root=etree.fromstring(xml.encode())
        _apply_name_map(root, _collect_name_map(root, 'red_'))
        model=mujoco.MjModel.from_xml_string(etree.tostring(root, encoding='unicode'))
        data=mujoco.MjData(model)
        np.testing.assert_allclose(model.body_mass[-1], 2.)  # Original 1 kg + 5 * .2.
        data.qpos[-4:]=[np.sqrt(.5),0,0,np.sqrt(.5)]
        data.ctrl[:]=1
        mujoco.mj_forward(model,data)
        np.testing.assert_allclose(data.qfrc_actuator[:6],0,atol=1e-10)
        np.testing.assert_allclose(data.qfrc_actuator[-3:],expected,atol=1e-10)
        records=DetailedObservations._definitions(SimpleNamespace(model=model, queries=SimpleNamespace(meshes={})), 'red_',
                list(range(1,model.nbody)), list(range(model.ngeom)))
        assert records['motors']['drive']['transmission']==transmission
        assert records['motors']['drive']['target']=='hinge'
        close(data);close(model)
    print('PASS: jointinparent references, mass, torque frame, and observations')



def check_ball_motor_velocities():
    gears = {'y': [0., 5., 0.], 'scaled_y': [0., 600., 0.],
             'negative_y': [0., -5., 0.], 'diagonal': [3., 4., 0.],
             'zero': [0., 0., 0.]}
    for transmission, expected in [
        ('joint', {'y': 3., 'scaled_y': 3., 'negative_y': -3., 'diagonal': 3.6, 'zero': 0.}),
        ('jointinparent', {'y': 2., 'scaled_y': 2., 'negative_y': -2., 'diagonal': -.2, 'zero': 0.}),
    ]:
        motors=''.join('<motor name="'+name+'" '+transmission+'="hinge" gear="'+
                       ' '.join(map(str,gear))+'"/>' for name,gear in gears.items())
        xml=robot(motors).replace('<joint name="hinge"/>','<joint name="hinge" type="ball"/>')
        tree=etree.fromstring(xml.encode());_apply_name_map(tree,_collect_name_map(tree,'red_'))
        model=mujoco.MjModel.from_xml_string(etree.tostring(tree,encoding='unicode'))
        data=mujoco.MjData(model)
        # Root motion must not be mistaken for relative motion at the joint.
        data.qpos[3:7]=[.5,.5,.5,.5]
        data.qpos[-4:]=[np.sqrt(.5),0,0,np.sqrt(.5)]
        data.qvel[:6]=[1.,2.,3.,4.,5.,6.]
        data.qvel[-3:]=[2.,3.,4.]
        mujoco.mj_forward(model,data)
        bot=BotRuntime(model,data,lambda obs:{},'red_')
        velocities=bot.actuator_joint_velocity()
        for name,value in expected.items():
            np.testing.assert_allclose(velocities[name],value,atol=1e-10)
        # A caller-supplied observation snapshot must override the live data.
        snapshot=mujoco.MjData(model);snapshot.qpos[:]=data.qpos
        snapshot.qvel[:]=-np.asarray(data.qvel);mujoco.mj_forward(model,snapshot)
        for name,value in expected.items():
            np.testing.assert_allclose(bot.actuator_joint_velocity(snapshot)[name],-value,atol=1e-10)
        close(snapshot);close(data);close(model)
    print('PASS: ball motor rates follow torque axes, gear signs, and transmission frames without magnitude scaling')


def check_internal_site_mechanisms():
    motors = [
        ('site', '<motor name="drive" site="end" refsite="inside" gear="0 0 100 0 0 0"/>', 'end', 'inside', 70.),
        ('site', '<motor name="drive" site="inside" refsite="end" gear="0 0 100 0 0 0"/>', 'inside', 'end', -70.),
        ('slidercrank', '<motor name="drive" cranksite="end" slidersite="inside" cranklength="1" gear="100"/>', 'end', 'inside', .7),
    ]
    for kind, motor, target, reference, velocity in motors:
        xml=robot(motor).replace('<joint name="hinge"/>', '<joint name="hinge" type="slide" axis="0 0 1"/>')
        # Motor mass must be present for both mechanisms, including a root site.
        xml=inject_motor_mass(xml,.01)
        tree=etree.fromstring(xml.encode());_apply_name_map(tree,_collect_name_map(tree,'red_'))
        model=mujoco.MjModel.from_xml_string(etree.tostring(tree,encoding='unicode'))
        data=mujoco.MjData(model)
        assert validate_internal_actuation(model)==[]
        np.testing.assert_allclose(sum(model.body_mass),12.)
        mount = 2 if kind == 'site' and target == 'end' else 1
        np.testing.assert_allclose(model.body_mass[mount], 2. if mount == 2 else 11.)
        # Nontrivial root orientation and displacement exercise frame invariance.
        data.qpos[3:7]=[.5,.5,.5,.5];data.qpos[-1]=.1
        data.ctrl[:]=1;data.qvel[-1]=.7
        mujoco.mj_forward(model,data)
        np.testing.assert_allclose(data.qfrc_actuator[:6],0,atol=1e-10)
        assert abs(float(data.qfrc_actuator[-1])) > 1
        bot=BotRuntime(model,data,lambda obs:{},'red_')
        np.testing.assert_allclose(bot.actuator_joint_velocity()['drive'],velocity,atol=1e-9)
        records=DetailedObservations._definitions(SimpleNamespace(model=model,queries=SimpleNamespace(meshes={})),
                    'red_',list(range(1,model.nbody)),list(range(model.ngeom)))
        record=records['motors']['drive']
        assert record['transmission']==kind and record['target']==target
        assert record['refsite' if kind == 'site' else 'slidersite']==reference
        if kind == 'slidercrank':assert record['cranklength']==1.
        assert len(records['sites']['end']['local_quaternion'])==4
        close(data);close(model)

    # Torque actuation can act between the chassis and an articulated part.
    xml=robot('<motor site="end" refsite="inside" gear="0 0 0 10 20 30"/>').replace(
        '<joint name="hinge"/>','<joint name="hinge" type="ball"/>')
    model=mujoco.MjModel.from_xml_string(xml);data=mujoco.MjData(model)
    data.ctrl[:]=1;mujoco.mj_forward(model,data)
    assert validate_internal_actuation(model)==[]
    np.testing.assert_allclose(data.qfrc_actuator[:6],0,atol=1e-10)
    np.testing.assert_allclose(data.qfrc_actuator[-3:],[10,20,30],atol=1e-10)
    close(data);close(model)
    print('PASS: relative-site and slider-crank mass, references, observations, and internal reaction forces')


def check_site_external_anchors_rejected():
    for outside in ('<site name="outside"/>', '<body name="blue_root"><freejoint/><geom size=".1"/><site name="outside"/></body>'):
        for motor in (
            '<motor site="end" refsite="outside"/>',
            '<motor site="outside" refsite="end"/>',
            '<motor cranksite="end" slidersite="outside" cranklength="1"/>',
            '<motor cranksite="outside" slidersite="end" cranklength="1"/>',
        ):
            model=mujoco.MjModel.from_xml_string(robot(motor,world=outside))
            assert validate_internal_actuation(model),motor
            close(model)
    for target in ('inside','end'):
        model=mujoco.MjModel.from_xml_string(robot('<motor site="'+target+'"/>'))
        assert validate_internal_actuation(model)
        close(model)
    print('PASS: unreferenced forces on any body, world anchors, and cross-robot site transmissions rejected')



def check_site_match_observations():
    xml=robot('<motor name="drive" site="end" refsite="inside" gear="0 0 10 0 0 0"/><motor name="crank" cranksite="end" slidersite="inside" cranklength="1" gear="10"/>')
    xml=xml.replace('<joint name="hinge"/>','<joint name="hinge" type="slide" axis="0 0 1"/>')
    root=etree.fromstring(xml.encode());_apply_name_map(root,_collect_name_map(root,'red_'))
    xml=etree.tostring(root,encoding='unicode').replace('</worldbody>',
        '<geom name="sumo_ring" type="cylinder" size="7.5 1" pos="0 0 -5"/>'
        '<body name="blue_root" pos="3 0 0"><freejoint/><geom size=".2" mass="10"/></body></worldbody>')
    model=mujoco.MjModel.from_xml_string(xml);data=mujoco.MjData(model)
    red=BotRuntime(model,data,lambda obs:{'drive':1.,'crank':1.},'red_')
    blue=BotRuntime(model,data,lambda obs:{},'blue_')
    env=SumoEnv(model,data,'',red,blue,max_steps=10)
    match=Match(env,red,blue,max_steps=10,headless=True)
    env.reset(seed=0)
    data.qpos[:]=np.asarray(model.qpos0);data.qvel[:]=0
    mujoco.mj_forward(model,data)
    env.detailed_observations.begin_interval()
    for t in range(2):
        obs=match.build_bot_observation(True,t)
        sites=obs.details['my_robot']['sites']
        assert set(('quaternion','local_quaternion','linear_velocity','angular_velocity')) <= set(sites['end'])
        assert obs.details['my_robot']['motors']['crank']['slidersite']=='inside'
        env.step({'red':red.act(obs),'blue':np.zeros(0)})
    # Internal actuation cannot cancel free fall of the whole robot's COM.
    mujoco.mj_forward(model,data)
    masses=np.asarray(model.body_mass)[1:3]
    com_z=float(np.dot(masses,np.asarray(data.xipos)[1:3,2])/sum(masses))
    initial_com_z=.5/11.
    assert com_z < initial_com_z
    env.detailed_observations.close();close(data);close(model)
    print('PASS: match execution and moving site observations; internal motors cannot prevent free fall')


def check_runtime_rejects_preprocessed_root_motor():
    xml='''<mujoco><worldbody><geom name="sumo_ring" type="cylinder" size="7.5 1"/>
    <body name="red_root"><freejoint name="red_free"/><geom size=".2" mass="10"/></body>
    <body name="blue_root"><freejoint/><geom size=".2" mass="10"/></body>
    </worldbody><actuator><motor name="red_fly" joint="red_free" gear="0 0 100 0 0 0"/></actuator></mujoco>'''
    model=mujoco.MjModel.from_xml_string(xml);data=mujoco.MjData(model)
    red=BotRuntime(model,data,lambda obs:{'fly':1},'red_')
    blue=BotRuntime(model,data,lambda obs:{},'blue_')
    try:
        SumoEnv(model,data,'',red,blue,max_steps=1)
    except ValueError as error:
        assert 'Root-joint actuation is forbidden' in str(error)
    else:
        raise AssertionError('Preprocessed match bypassed the actuation rule')
    close(data);close(model)
    print('PASS: preprocessed match cannot bypass root-actuation validation')


if __name__=='__main__':
    check_transmission_rules()
    check_runtime_rejects_preprocessed_root_motor()
    check_jointinparent_mass_frame_and_observations()
    check_ball_motor_velocities()
    check_internal_site_mechanisms()
    check_site_external_anchors_rejected()
    check_site_match_observations()
