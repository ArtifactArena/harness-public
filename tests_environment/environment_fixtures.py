"""Small native models for independent environment integration checks."""
from pathlib import Path

import mujoco
import numpy as np

import mjarena
from mjarena.agents.runtime import BotRuntime
from mjarena.envs.sumo import SumoEnv
from mjarena.runner.episode import Match

ROOT = Path(mjarena.__file__).resolve().parents[1]
RULES = ROOT / 'configs/rules/rules.yaml'
CORNERS = np.array([[-1,-1,-1],[1,-1,-1],[1,1,-1],[-1,1,-1],
                    [-1,-1,1],[1,-1,1],[1,1,1],[-1,1,1]], dtype=float)
FACES = '0 2 1 0 3 2 4 5 6 4 6 7 0 1 5 0 5 4 1 2 6 1 6 5 2 3 7 2 7 6 3 0 4 3 4 7'


def box_mesh(name='surface', half=(.3,.2,.1)):
    vertices = ' '.join(map(str, (CORNERS*np.array(half)).flat))
    return f'<mesh name="{name}" inertia="exact" vertex="{vertices}" face="{FACES}"/>'


def arena_xml(*, articulated=False):
    bodies, motors = [], []
    for color, x in [('red', -1), ('blue', 1)]:
        child = ''
        if articulated:
            child = f'''<body name="{color}_wheel" pos="0 0 .2">
              <joint name="{color}_axle" type="hinge" axis="0 1 0"/>
              <geom name="{color}_wheel_geom" size=".03" mass=".1"/>
            </body>'''
            motors.append(f'<motor name="{color}_drive" joint="{color}_axle" gear="10"/>')
        bodies.append(f'''<body name="{color}_root" pos="{x} 0 .31">
          <freejoint name="{color}_free"/>
          <geom name="{color}_hull" type="box" size=".2 .2 .1" mass="30"/>
          {child}</body>''')
    return f'''<mujoco><compiler angle="radian"/>
      <worldbody><geom name="sumo_ring" type="cylinder" size="7.5 .2"/>
      <geom name="outside_floor" type="plane" size="20 20 .1" pos="0 0 -1"/>
      {''.join(bodies)}</worldbody><actuator>{''.join(motors)}</actuator></mujoco>'''


def make_match(red_policy=lambda obs: {}, blue_policy=lambda obs: {}, *,
               steps=8, seed=0, env_class=SumoEnv, articulated=False, **kwargs):
    model = mujoco.MjModel.from_xml_string(arena_xml(articulated=articulated))
    data = mujoco.MjData(model)
    red = BotRuntime(model, data, red_policy, 'red_')
    blue = BotRuntime(model, data, blue_policy, 'blue_')
    env = env_class(model, data, '', red, blue, max_steps=steps,
                    inactivity_timeout_seconds=None, **kwargs)
    return Match(env, red, blue, max_steps=steps, headless=True, seed=seed)


def close_match(match):
    details = getattr(match.env, 'detailed_observations', None)
    if details is not None:
        details.close()
    match.env.close()
