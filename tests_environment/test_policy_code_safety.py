"""Policy validation checks executable code without scanning comments or text."""

import textwrap

import pytest

from mjarena.design_shop.policy_base import (
    _restricted_builtins,
    _validate_policy_code_safety,
    compile_policy_function,
)


def policy_source(body):
    return 'def policy_step(obs):\n' + textwrap.indent(body, '    ')


def test_comments_strings_and_numpy_empty_are_harmless():
    policy = compile_policy_function('''
"""No requests, subprocess, socket, or pickle are needed."""
import numpy as np

def policy_step(obs):
    # The controller requests traction; do not call open(), eval(), or os.system.
    explanation = "requests pty __import__ exec( input( sys.exit"
    requests = obs['requests']
    requests_count = len(requests)
    empty_values = np.empty(3)
    empty_values.fill(0.25)
    return {'drive': float(empty_values[0]) + requests_count * 0.1}
''')
    assert policy({'requests': [1]}) == {'drive': 0.35}


@pytest.mark.parametrize('source', [
    'import math as m\nreturn {"drive": m.cos(0)}',
    'from numpy import empty as allocate\na = allocate(1)\na.fill(1)\nreturn {"drive": float(a[0])}',
    'import numpy.linalg as la\nreturn {"drive": float(la.norm([1]))}',
    'from typing import Dict\nresult: Dict[str, float] = {"drive": 1.0}\nreturn result',
    'import random\nreturn {"drive": random.uniform(1, 1)}',
])
def test_allowed_imports_and_operations(source):
    assert compile_policy_function(policy_source(source))({}) == {'drive': 1.0}


@pytest.mark.parametrize('module', [
    'subprocess', 'socket', 'requests', 'urllib.request', 'shutil', 'psutil',
    'ctypes', 'multiprocessing', 'threading', 'pexpect', 'pty', 'pickle', 'dill',
    'os', 'sys', 'builtins',
])
@pytest.mark.parametrize('statement', ['import {module} as hidden', 'from {module} import hidden'])
def test_prohibited_imports_fail_even_in_unexecuted_functions(module, statement):
    with pytest.raises(RuntimeError, match='Disallowed construct|Blocked import'):
        compile_policy_function(policy_source(statement.format(module=module) + '\nreturn {}'))


@pytest.mark.parametrize('operation', [
    'open ("unused")',
    'exec ("pass")',
    'eval\n("1")',
    'compile ("1", "unused", "eval")',
    'input ()',
    '__import__ ("math")',
    'os . system ("unused")',
    'sys . exit ()',
    'alias = open\nalias("unused")',
    'alias = eval\nalias("1")',
    'alias = os.system\nalias("unused")',
    'np.ctypeslib.load_library("unused", ".")',
    'np.ones(1).ctypes',
    'from numpy import ctypeslib as ffi',
    'from numpy.lib import os as platform\nplatform.system("unused")',
    'getattr(os, "system")("unused")',
    # getattr/setattr/delattr are denied builtins since the 2026-09-16 review
    # (C4): getattr(typing, 'sy' + 's').modules['o' + 's'] was full OS access,
    # and a computed name is invisible to every static path check here.
    'a = getattr(np, "empty")(1)\na.fill(1)',
    'setattr(obs, "x", 1)',
    'delattr(obs, "x")',
    # File and process access, on any object, by attribute name.
    'np.save("unused", np.arange(3))',
    'np.arange(3).tofile("unused")',
    'np.loadtxt("unused")',
    'getattr(np, "ctypeslib")',
    'getattr(math, "__builtins__")',
    'np.__dict__["ctypeslib"]',
    'np.ones.__globals__["__builtins__"]["__import__"]("math")',
    '__builtins__["__import__"]("math")',
    'np.load("unused", allow_pickle=True)',
    'np.load("unused", allow_pickle=obs["flag"])',
    'text = f"{eval(\'1\')}"',
    'globals()',
    'locals()',
    'vars()',
    'breakpoint()',
])
def test_prohibited_operations_fail_before_execution(operation):
    with pytest.raises(RuntimeError, match='Disallowed construct'):
        compile_policy_function(policy_source(operation + '\nreturn {}'))


def test_unreachable_import_and_relative_import_are_rejected():
    for statement in ('if False:\n    import requests', 'from .numpy import array'):
        with pytest.raises(RuntimeError, match='Disallowed construct|Blocked import'):
            compile_policy_function(policy_source(statement + '\nreturn {}'))


def test_blacklist_parameter_still_applies_to_code_references():
    _validate_policy_code_safety('# forbidden()\ntext = "forbidden"', ['forbidden('])
    with pytest.raises(RuntimeError, match='Disallowed construct.*forbidden'):
        _validate_policy_code_safety('forbidden ()', ['forbidden('])


def test_explicitly_disabling_pickle_is_allowed():
    # `np.load` is itself rejected now as file access (2026-09-16 review, C4), so
    # the allow_pickle rule is exercised on a callee that is not on that list.
    _validate_policy_code_safety('reader("unused", allow_pickle=False)', ['pickle'])
    with pytest.raises(RuntimeError, match='Disallowed construct'):
        _validate_policy_code_safety('reader("unused", allow_pickle=True)', ['pickle'])


def test_syntax_errors_keep_the_public_error_contract():
    with pytest.raises(RuntimeError, match='Policy code has syntax errors'):
        compile_policy_function('def policy_step(')




def test_runtime_builtins_and_import_restrictions_remain_in_place():
    restricted = _restricted_builtins()
    for name in ('open', 'exec', 'eval', 'compile', 'input', 'globals', 'locals', 'vars'):
        assert name not in restricted
    safe_import = restricted['__import__']
    assert safe_import('math').sqrt(4) == 2
    for module in ('os', 'requests', 'numpy_fake'):
        with pytest.raises(ImportError, match='Blocked import'):
            safe_import(module)
    with pytest.raises(ImportError, match='Blocked import'):
        safe_import('numpy', level=1)
