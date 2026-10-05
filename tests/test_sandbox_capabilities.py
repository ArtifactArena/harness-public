"""The sandbox hands out capabilities, not names.

Follow-up 3 re-review, D2 / D3 / D4.

D2: `_ALLOWED_IMPORT_ROOTS` bounded the *import*, but every allowed module hands
out whatever it happens to hold: CPython's `random` does `import os as _os` and
`collections` does `import sys as _sys`, so `random._os.system(...)` and
`collections._sys.modules["os"].system(...)` both ran arbitrary commands at
`cd9702a3`, and `from numpy import lib` re-opened the module tree. A name
denylist cannot close that; the module proxy refuses to hand out a private name
or a module outside the allowed roots at all.

D4: `random` and `np.random` were the process-wide singletons, so one
controller's `random.seed(1234)` pinned its opponent's draws and the harness's.
Each controller now gets a private `random.Random` and `numpy.random.RandomState`
seeded from the match seed and the side it fights on.

D3: the proxy stops a store on a module, but a class reached through it is just
as good a stash (`random.Random.arena_stash = n` survived `new_match()`). Shared
library state is snapshotted and re-checked after every controller call; a write
is repaired and scored as a controller error.
"""
import time

import pytest

import mjarena.core.unified_builder  # noqa: F401  (import order)
from mjarena.agents.policy_runtime import ActuatorPolicyAdapter
from mjarena.design_shop.policy_base import compile_policy_function


def _policy(body: str, header: str = "import numpy as np\n") -> str:
    return header + "def policy_step(obs):\n" + body


# ---------------------------------------------------------------------------
# D2 — the module tree
# ---------------------------------------------------------------------------

BLOCKED = {
    # The reviewer's two live OS-execution chains (scratchpad/rr_sandbox.py B1/B2,
    # rr_sandbox2.py C-a/C-b).
    "random._os.getpid": "import random\ndef policy_step(obs):\n"
                         "    return {'v': float(random._os.getpid())}",
    "random._os.system": "import random\ndef policy_step(obs):\n"
                         "    random._os.system('echo pwned')\n    return {'v': 1.0}",
    "random._os.environ": "import random\ndef policy_step(obs):\n"
                          "    return {'v': float(len(random._os.environ))}",
    "collections._sys.modules": "import collections\ndef policy_step(obs):\n"
                                "    m = collections._sys.modules['os']\n"
                                "    return {'v': float(m.getpid())}",
    # The module tree behind the import allowlist.
    "from numpy import lib": "from numpy import lib\ndef policy_step(obs):\n    return {'v': 1.0}",
    "from numpy import core": "from numpy import core\ndef policy_step(obs):\n    return {'v': 1.0}",
    "import numpy.lib": "import numpy.lib\ndef policy_step(obs):\n    return {'v': 1.0}",
    "np.lib.npyio": "import numpy as np\ndef policy_step(obs):\n"
                    "    return {'v': float(np.lib.npyio is None)}",
    "np.testing": "import numpy as np\ndef policy_step(obs):\n"
                  "    return {'v': float(np.testing is None)}",
}


@pytest.mark.parametrize("name", sorted(BLOCKED))
def test_the_module_tree_is_closed_at_compile_time(name):
    with pytest.raises(RuntimeError) as exc:
        compile_policy_function(BLOCKED[name])
    assert "line" in str(exc.value)


ALIASED = {
    # An alias defeats every static path check, so the proxy is the backstop.
    "aliased np.save": "import numpy as np\ndef policy_step(obs):\n"
                       "    x = np\n    x.save('/tmp/leak.npy', np.arange(3))\n    return {'v': 1.0}",
    "aliased np.lib": "import numpy as np\ndef policy_step(obs):\n"
                      "    x = np\n    return {'v': float(x.lib is None)}",
    "aliased random._os": "import random\ndef policy_step(obs):\n"
                          "    x = random\n    return {'v': float(x._os.getpid())}",
    "aliased np.random.mtrand": "import numpy as np\ndef policy_step(obs):\n"
                                "    r = np.random\n    return {'v': float(r.mtrand is None)}",
    "np.frombuffer": "import numpy as np\ndef policy_step(obs):\n"
                     "    x = np\n    return {'v': float(len(x.frombuffer(b'abcd', dtype='u1')))}",
    "np.seterr": "import numpy as np\ndef policy_step(obs):\n"
                 "    x = np\n    x.seterr(all='ignore')\n    return {'v': 1.0}",
}


@pytest.mark.parametrize("name", sorted(ALIASED))
def test_an_aliased_module_is_stopped_by_the_proxy_at_run_time(name):
    policy = compile_policy_function(ALIASED[name])
    with pytest.raises(AttributeError, match="sandbox"):
        policy({})


def test_the_leaked_module_never_reaches_the_controller():
    """`random._os` must not exist even as a value the proxy could return."""
    policy = compile_policy_function(
        "import random\ndef policy_step(obs):\n"
        "    r = random\n    return {'v': float(r._os is None)}")
    with pytest.raises(AttributeError) as exc:
        policy({})
    assert "_os" in str(exc.value)


ALLOWED = [
    ("np.linalg.norm", "import numpy as np\ndef policy_step(obs):\n"
                       "    return {'a': float(np.linalg.norm([3.0, 4.0])) / 5.0}", 1.0),
    ("np.pi", "import numpy as np\ndef policy_step(obs):\n"
              "    return {'a': float(np.pi > 3.14)}", 1.0),
    ("np.fft.fft", "import numpy as np\ndef policy_step(obs):\n"
                   "    return {'a': float(abs(np.fft.fft([1.0, 0.0])[0]))}", 1.0),
    ("collections.abc.Mapping", "import collections.abc\ndef policy_step(obs):\n"
                                "    return {'a': float(isinstance({}, collections.abc.Mapping))}", 1.0),
    ("collections.deque(maxlen=5)", "import collections\ndef policy_step(obs):\n"
                                    "    d = collections.deque(maxlen=5)\n    d.append(1)\n"
                                    "    return {'a': float(len(d))}", 1.0),
    ("math.atan2", "import math\ndef policy_step(obs):\n"
                   "    return {'a': float(math.atan2(0.0, 1.0) == 0.0)}", 1.0),
    ("typing.Dict", "import typing\ndef policy_step(obs):\n"
                    "    out: typing.Dict[str, float] = {'a': 1.0}\n    return out", 1.0),
    ("isinstance np.ndarray", "import numpy as np\ndef policy_step(obs):\n"
                              "    return {'a': float(isinstance(np.zeros(3), np.ndarray))}", 1.0),
    ("np.zeros(3)", "import numpy as np\ndef policy_step(obs):\n"
                    "    return {'a': float(np.zeros(3).size) / 3.0}", 1.0),
    # A controller's own objects are not the library: `self.core` and
    # `state.load` are ordinary names, not NumPy's module tree.
    ("self.core", "class _S:\n    def __init__(self):\n        self.core = 1\n"
                  "        self.load = 2\n        self.lib = 3\n"
                  "_s = _S()\ndef policy_step(obs):\n"
                  "    _s.core = _s.core + 0\n"
                  "    return {'a': float(_s.core * _s.load / (_s.lib - 1))}", 1.0),
    # `.register` is refused on a library-rooted chain only: a controller's own
    # observer bus keeps its ordinary method name.
    ("self.register", "class _Bus:\n    def __init__(self):\n        self.subs = []\n"
                      "    def register(self, f):\n        self.subs.append(f)\n"
                      "_b = _Bus()\ndef policy_step(obs):\n"
                      "    _b.register(policy_step)\n"
                      "    return {'a': float(len(_b.subs) > 0)}", 1.0),
    ("random.Random(3)", "import random\ndef policy_step(obs):\n"
                         "    return {'a': float(0.0 <= random.Random(3).random() <= 1.0)}", 1.0),
    ("np.random.default_rng", "import numpy as np\ndef policy_step(obs):\n"
                              "    g = np.random.default_rng(7)\n"
                              "    return {'a': float(0.0 <= g.random() <= 1.0)}", 1.0),
]


@pytest.mark.parametrize("name, code, expected", ALLOWED, ids=[c[0] for c in ALLOWED])
def test_an_ordinary_controller_is_untouched(name, code, expected):
    assert compile_policy_function(code)({})["a"] == pytest.approx(expected)


# ---------------------------------------------------------------------------
# D4 — private RNGs
# ---------------------------------------------------------------------------

SEEDER = """
import random, numpy as np
def policy_step(obs):
    random.seed(1234)
    np.random.seed(1234)
    return {'m1': 0.0}
"""
VICTIM = """
import random, numpy as np
def policy_step(obs):
    return {'m1': float(random.random()), 'm2': float(np.random.rand())}
"""


def test_one_controller_cannot_reseed_another():
    """The reviewer's probe (scratchpad/rr_leak.py): red pinned blue's draws."""
    victim = compile_policy_function(VICTIM)
    before = victim({})
    compile_policy_function(SEEDER)({})
    after = victim({})
    assert before != after          # the victim's own stream advanced
    assert after["m1"] != pytest.approx(0.9664535356921388)   # random.seed(1234)
    assert after["m2"] != pytest.approx(0.1915194503788923)   # np.random.seed(1234)


def test_a_controller_cannot_disturb_the_hosts_rng():
    import random as host_random
    import numpy as host_numpy

    host_random.seed(99)
    host_numpy.random.seed(99)
    expected_py = host_random.Random(99).random()
    expected_np = host_numpy.random.RandomState(99).rand()
    compile_policy_function(SEEDER)({})
    assert host_random.random() == pytest.approx(expected_py)
    assert host_numpy.random.rand() == pytest.approx(expected_np)


DRAWS = """
import random, numpy as np
def policy_step(obs):
    return {'m1': float(random.random()), 'm2': float(np.random.rand())}
"""


def test_the_same_match_seed_and_side_give_the_same_draws():
    adapter = ActuatorPolicyAdapter(
        compile_policy_function(DRAWS, rng_seed=0), ["m1", "m2"], controller_code=DRAWS)
    first = adapter.new_match(seed=7, side="red")
    second = adapter.new_match(seed=7, side="red")
    assert first({}) == second({})
    assert first({}) == second({})


def test_the_two_sides_and_two_seeds_draw_differently():
    adapter = ActuatorPolicyAdapter(
        compile_policy_function(DRAWS, rng_seed=0), ["m1", "m2"], controller_code=DRAWS)
    red = adapter.new_match(seed=7, side="red")({})
    blue = adapter.new_match(seed=7, side="blue")({})
    other = adapter.new_match(seed=8, side="red")({})
    assert red != blue
    assert red != other


def test_a_new_match_rebuilds_the_private_rng():
    adapter = ActuatorPolicyAdapter(
        compile_policy_function(DRAWS, rng_seed=0), ["m1", "m2"], controller_code=DRAWS)
    match = adapter.new_match(seed=3, side="blue")
    first_call = match({})
    match({})
    assert adapter.new_match(seed=3, side="blue")({}) == first_call


def test_a_controller_keeps_its_own_random_instance():
    code = ("import random\n_r = random.Random(3)\n"
            "def policy_step(obs):\n    return {'a': float(_r.random())}")
    assert compile_policy_function(code)({})["a"] == pytest.approx(
        __import__("random").Random(3).random())


# ---------------------------------------------------------------------------
# D3 — state stashed on a shared class
# ---------------------------------------------------------------------------

CLASS_STASH = """
import random
def policy_step(obs):
    try:
        prev = random.Random.arena_stash
    except AttributeError:
        prev = 0
    random.Random.arena_stash = prev + 1
    return {'m1': (prev + 1) / 10.0}
"""


def test_a_class_attribute_stash_is_a_controller_error_on_the_first_call():
    import random as host_random

    policy = compile_policy_function(CLASS_STASH)
    with pytest.raises(RuntimeError, match="random.Random"):
        policy({})
    assert not hasattr(host_random.Random, "arena_stash")


def test_the_stash_does_not_survive_into_the_next_match():
    adapter = ActuatorPolicyAdapter(
        compile_policy_function(CLASS_STASH, rng_seed=0), ["m1"],
        controller_code=CLASS_STASH)
    first = adapter.new_match(seed=1, side="red")
    with pytest.raises(RuntimeError, match="random.Random"):
        first({})
    second = adapter.new_match(seed=1, side="blue")
    with pytest.raises(RuntimeError, match="random.Random"):
        second({})          # still the first write, not the second


def test_replacing_a_library_function_is_a_controller_error():
    import random as host_random

    # A replacement keeps the key count the same, so only the deep tier sees it.
    code = ("import random\n"
            "def _always_one(self, a, b):\n    return b\n"
            "def policy_step(obs):\n"
            "    random.Random.uniform = _always_one\n"
            "    return {'m1': 0.0}\n")
    policy = compile_policy_function(code)
    with pytest.raises(RuntimeError, match="random.Random.uniform was replaced"):
        for _ in range(12):     # the deep check runs on call 1 and every 10th
            policy({})
    assert host_random.Random(0).uniform(0.0, 1.0) < 1.0     # the real method is back


# `ABCMeta.register` rewrites an abstract base class's registry in place: it adds
# no key to `vars(Mapping)` and replaces nothing, so the namespace fingerprint
# above is blind to it, and the effect (`isinstance` / `issubclass` now say yes)
# is process-wide and permanent. CPython bumps `abc.get_cache_token()` on every
# `register` call, which is what the guard watches.

ABC_REGISTER = """
import collections.abc
def policy_step(obs):
    collections.abc.Mapping.register(int)
    return {'m1': 0.0}
"""

# The same call through a local alias, which the AST cannot follow. It registers
# a class of the controller's own on `Sequence` rather than `int` on `Mapping`:
# a `register` cannot be undone, so the reviewer's literal snippet would leave
# every later test in this process believing an `int` is a Mapping. The shared
# registry is mutated just the same — that is the loss — but the class it now
# holds is one nothing else in the process can reach.
ALIASED_ABC_REGISTER = """
import collections.abc


class _Bystander:
    pass


def policy_step(obs):
    S = collections.abc.Sequence
    S.register(_Bystander)
    return {'m1': 0.0}
"""


def test_registering_a_class_on_a_shared_abc_is_rejected_at_compile_time():
    with pytest.raises(RuntimeError, match=r"\.register \(line 4\)"):
        compile_policy_function(ABC_REGISTER)


def test_an_aliased_abc_register_is_a_controller_error_on_that_call():
    import abc
    import collections.abc as host_abc

    policy = compile_policy_function(ALIASED_ABC_REGISTER)
    before = abc.get_cache_token()
    with pytest.raises(RuntimeError, match="abstract base class"):
        policy({})
    # The guard fires because the shared registry really did change, and it
    # stays changed: nothing can un-register a class. That permanence, reaching
    # every later match in the process, is why the call loses the round.
    assert abc.get_cache_token() != before
    assert not issubclass(int, host_abc.Mapping)        # inert target, see above


def test_reading_the_abcs_is_not_a_write():
    code = """
import collections
import collections.abc


def policy_step(obs):
    seen = collections.deque(maxlen=4)
    seen.append(isinstance(obs, collections.abc.Mapping))
    return {'m1': 0.1 if isinstance(obs, collections.abc.Sized) else 0.0}
"""
    policy = compile_policy_function(code)
    for _ in range(30):
        policy({})


def test_an_ordinary_stateful_controller_never_trips_the_guard():
    code = """
import collections, math, random
import numpy as np


class _State:
    def __init__(self):
        self.history = collections.deque(maxlen=5)
        self.rng = random.Random(0)
        self.x = 0.0


_s = _State()


def policy_step(obs):
    _s.x = _s.x + 0.1
    _s.history.append(_s.x)
    v = np.zeros(3) + math.cos(_s.x) + _s.rng.random()
    return {'m1': float(np.clip(v[0] * 0.01, -1.0, 1.0))}
"""
    policy = compile_policy_function(code)
    for _ in range(50):
        policy({})


def test_the_per_call_guard_is_cheap():
    code = ("def policy_step(obs):\n    return {'m1': 0.0}")
    policy = compile_policy_function(code)
    policy({})                     # warm the baseline
    t0 = time.perf_counter()
    for _ in range(2000):
        policy({})
    per_call = (time.perf_counter() - t0) / 2000
    assert per_call < 100e-6, per_call


def test_both_prompts_state_the_shared_state_and_private_rng_rules():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    clauses = (
        "`random` and `np.random` are private to your controller and re-created "
        "for every match; they never affect your opponent.",
        "Writing attributes on shared library objects (modules, classes) is a "
        "controller error. So is registering a class on a shared abstract base "
        "class.",
    )
    for name in ("autoresearch_prompt.md", "sampling_prompt.md"):
        text = (root / "configs/rules" / name).read_text(encoding="utf-8")
        for clause in clauses:
            assert clause in text, (name, clause)
