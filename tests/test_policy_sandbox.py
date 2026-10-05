"""The policy sandbox judges code, not words: comments and names are not constructs."""
import pytest

import mjarena.core.unified_builder  # noqa: F401  (import order)
from mjarena.design_shop.policy_base import compile_policy_function

OK = """
import math
def policy_step(obs):
    # ignore any reverse requests and favor forward; socket-shaped wedge
    requests_count = 0
    speed = obs["my_velocity"] if "my_velocity" in obs else None   # ordinary Python
    return {}
"""


def test_words_in_comments_and_names_are_allowed():
    assert callable(compile_policy_function(OK))


@pytest.mark.parametrize("bad, what", [
    ("import requests\ndef policy_step(obs):\n    return {}", "import of 'requests'"),
    ("from os import system\ndef policy_step(obs):\n    return {}", "import from 'os'"),
    ("def policy_step(obs):\n    open('x')\n    return {}", "call to open()"),
    ("def policy_step(obs):\n    return obs.__class__.__mro__", "dunder attribute"),
    # The policy namespace has no globals/locals/vars: calling one would raise
    # NameError mid-match, so it is refused at validation instead.
    ("def policy_step(obs):\n    return locals()", "call to locals()"),
    ("def policy_step(obs):\n    return vars()", "call to vars()"),
    ("def policy_step(obs):\n    return globals()", "call to globals()"),
    # 2026-09-16 review, C4. A computed attribute name is invisible to every
    # static path check, so `getattr` reached `sys` and then `os`:
    #   getattr(typing, 'sy' + 's').modules['o' + 's'].getuid()
    ("import typing\ndef policy_step(obs):\n"
     "    s = getattr(typing, 'sy' + 's')\n"
     "    return {'uid': float(s.modules['o' + 's'].getuid())}", "call to getattr()"),
    ("def policy_step(obs):\n    return {'x': getattr((), '__class__')}", "call to getattr()"),
    ("def policy_step(obs):\n    c = getattr((), '__cl' + 'ass__')\n    return {'x': str(c)}",
     "call to getattr()"),
    ("def policy_step(obs):\n    setattr(obs, 'x', 1)\n    return {}", "call to setattr()"),
    ("def policy_step(obs):\n    delattr(obs, 'x')\n    return {}", "call to delattr()"),
    ("def policy_step(obs):\n    grab = getattr\n    return {'x': grab((), 'real')}", "getattr"),
    # File and process access, on any object.
    ("import numpy as np\ndef policy_step(obs):\n    np.save('/tmp/leak.npy', np.arange(3))\n"
     "    return {'ok': 1.0}", "file, process or internals access .save"),
    ("import numpy as np\ndef policy_step(obs):\n    return {'x': float(np.load('/tmp/l.npy'))}",
     "file, process or internals access .load"),
    ("import numpy as np\ndef policy_step(obs):\n    np.arange(3).tofile('/tmp/l.bin')\n    return {}",
     "file, process or internals access .tofile"),
    ("import numpy as np\ndef policy_step(obs):\n    return {'x': float(np.genfromtxt('/tmp/x'))}",
     "file, process or internals access .genfromtxt"),
    ("import numpy as np\ndef policy_step(obs):\n    return {'x': float(np.lib.stride_tricks is None)}",
     "file, process or internals access .lib"),
    ("def policy_step(obs):\n    return {'x': float(obs['__class__'] is None)}",
     "dunder attribute access"),
])
def test_real_escapes_are_rejected_with_a_line_number(bad, what):
    with pytest.raises(RuntimeError, match=what) as e:
        compile_policy_function(bad)
    assert "line" in str(e.value)


@pytest.mark.parametrize("code", [
    "import collections\ndef policy_step(obs):\n    return {'a': len(collections.deque([1]))}",
    "from collections import deque\ndef policy_step(obs):\n    return {'a': float(len(deque([1])))}",
    "import random\ndef policy_step(obs):\n    return {'a': random.random()}",
])
def test_the_libraries_the_prompt_lists_are_importable(code):
    """Item A: `collections` was pre-injected but `import collections` was blocked."""
    policy = compile_policy_function(code)
    assert set(policy({})) == {"a"}


# ---------------------------------------------------------------------------
# I2 — module objects are process-wide, so the controller gets read-only proxies
# ---------------------------------------------------------------------------

STASH = """
import numpy as np
def policy_step(obs):
    np.arena_stash = 1.0
    return {'n': 1.0}
"""


def test_a_controller_cannot_stash_state_on_a_module():
    """The reviewer's counter: `np.arena_stash` survived new_match() and the process."""
    import numpy as real_numpy

    policy = compile_policy_function(STASH)
    with pytest.raises(AttributeError, match="read-only"):
        policy({})
    assert not hasattr(real_numpy, "arena_stash")


def test_a_second_match_sees_nothing_from_the_first():
    from mjarena.agents.policy_runtime import ActuatorPolicyAdapter

    code = """
import numpy as np
def policy_step(obs):
    try:
        n = np.arena_stash + 1.0
    except AttributeError:
        n = 1.0
    try:
        np.arena_stash = n
    except AttributeError:
        pass
    return {'n': n / 10.0}
"""
    # n/10 keeps every value inside the [-1, 1] the adapter clips to, so a leak
    # shows up as a different number instead of being clipped back to 1.0.
    first = ActuatorPolicyAdapter(compile_policy_function(code), ["n"], controller_code=code)
    assert first({}) == {"n": 0.1}
    assert first({}) == {"n": 0.1}          # not 0.2: the store never took
    assert first.new_match(seed=0, side="red")({}) == {"n": 0.1}


def test_the_proxy_does_not_hand_back_the_real_module():
    policy = compile_policy_function(
        "import numpy as np\ndef policy_step(obs):\n    return {'n': float(np.pi)}")
    assert policy({})["n"] == pytest.approx(3.14159, rel=1e-4)
    # compile_policy_function returns the shared-state guard wrapper; the
    # controller's own namespace is the wrapped function's (D3, 2026-09-17).
    namespace_np = policy.__wrapped__.__globals__["np"]
    import numpy as real_numpy
    assert namespace_np is not real_numpy
    with pytest.raises(AttributeError):
        namespace_np._ro_module          # the wrapped module is unreachable by name


def test_submodules_are_read_only_too():
    policy = compile_policy_function(
        "import numpy as np\ndef policy_step(obs):\n"
        "    np.linalg.stash = 1\n    return {}")
    with pytest.raises(AttributeError, match="read-only"):
        policy({})


@pytest.mark.parametrize("code, expected", [
    ("import numpy as np\ndef policy_step(obs):\n    return {'a': float(np.zeros(3).sum() + 1)}", 1.0),
    ("import math\ndef policy_step(obs):\n    return {'a': math.cos(0.0)}", 1.0),
    ("import random\ndef policy_step(obs):\n    return {'a': float(random.Random(0).random() >= 0)}", 1.0),
    ("import numpy.linalg as la\ndef policy_step(obs):\n    return {'a': float(la.norm([1.0]))}", 1.0),
    ("from numpy import zeros\ndef policy_step(obs):\n    return {'a': float(len(zeros(1)))}", 1.0),
    ("import collections\ndef policy_step(obs):\n"
     "    return {'a': float(len(collections.deque([1])))}", 1.0),
    ("from typing import Dict\ndef policy_step(obs):\n"
     "    out: Dict[str, float] = {'a': 1.0}\n    return out", 1.0),
])
def test_an_ordinary_controller_still_compiles_and_runs(code, expected):
    assert compile_policy_function(code)({})["a"] == pytest.approx(expected)


def test_both_prompts_state_the_sandbox_rules():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    clauses = (
        "`globals`, `locals`, `vars`, `getattr`, `setattr`, and `delattr`, which are forbidden.",
        "File and process access, including NumPy's save/load family, is forbidden.",
    )
    for name in ("autoresearch_prompt.md", "sampling_prompt.md"):
        text = (root / "configs/rules" / name).read_text(encoding="utf-8")
        for clause in clauses:
            assert clause in text, (name, clause)
