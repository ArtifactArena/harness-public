"""Real compiled-model boundaries, using the target checkout's actual rules."""
import mujoco
import pytest

from environment_fixtures import RULES
from mjarena.design_shop.rules.mj_validators import (
    ModelValidationConfig, validate_structural_constraints, validate_mass_constraints,
    validate_size_constraints,
)


@pytest.fixture
def config():
    return ModelValidationConfig(constraints_yaml_path=RULES, physics_mode='3d')


def structural_model(kind, count):
    # One internal joint can have many motors. Empty welded frames let us vary
    # body count without also exceeding the geometry/actuator limits.
    body_count = count if kind == 'body' else 2
    geom_count = count if kind == 'geom' else 2
    motor_count = count if kind == 'actuator' else 1
    child = '<body><joint name="hinge"/><geom size=".01" mass=".1"/></body>'
    child += '<body/>' * (body_count-2)
    geoms = '<geom size=".01" mass=".1"/>' * (geom_count-1)
    motors = ''.join(f'<motor name="m{i}" joint="hinge"/>' for i in range(motor_count))
    return mujoco.MjModel.from_xml_string(f'''<mujoco><worldbody>
      <geom type="plane" size="1 1 .1"/>
      <body><freejoint/>{geoms}{child}</body></worldbody>
      <actuator>{motors}</actuator></mujoco>''')


@pytest.mark.parametrize('kind,above_old_limit', [('body',16),('geom',26),('actuator',25)])
@pytest.mark.parametrize('boundary', ['above_old',1999,2000,2001])
def test_structure_limit_boundaries(config, kind, above_old_limit, boundary):
    count = above_old_limit if boundary == 'above_old' else boundary
    model = structural_model(kind, count)
    measured = {'body': model.nbody-1, 'geom': model.ngeom-1, 'actuator': model.nu}
    assert measured[kind] == count
    result = validate_structural_constraints(model, config)
    assert result.passed == (count <= 2000), result.errors
    if count > 2000:
        assert any(kind.capitalize()+' count' in error for error in result.errors)


@pytest.mark.parametrize('count,expected', [(0,False),(1,True)])
def test_minimum_actuator_count(config, count, expected):
    assert validate_structural_constraints(structural_model('actuator',count),config).passed == expected


@pytest.mark.parametrize('mass,expected', [(24.99,False),(25,True),(400.01,True),
                                         (799.99,True),(800,True),(800.01,False)])
def test_total_mass_boundary_without_per_body_cap(config, mass, expected):
    model = mujoco.MjModel.from_xml_string(f'''<mujoco><worldbody><body><freejoint/>
      <geom type="box" size=".1 .1 .1" mass="{mass}"/></body></worldbody></mujoco>''')
    assert validate_mass_constraints(model, config).passed == expected


# The size box is 2.44 x 2.44 x 3.05 m: the user's height ruling replaced
# The upstream 10 m z-limit (rules.yaml `robot.size.max_z_span_m`).
@pytest.mark.parametrize('axis,limit', [(0,2.44),(1,2.44),(2,3.05)])
@pytest.mark.parametrize('delta,expected', [(-.0001,True),(0,True),(.0001,False)])
def test_size_limit_boundaries(config, axis, limit, delta, expected):
    size = [.05,.05,.05]; size[axis] = (limit+delta)/2
    model = mujoco.MjModel.from_xml_string(f'''<mujoco><worldbody><body><freejoint/>
      <geom type="box" size="{' '.join(map(str,size))}" mass="30"/>
      </body></worldbody></mujoco>''')
    assert validate_size_constraints(model,config).passed == expected
