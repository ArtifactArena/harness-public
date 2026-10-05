"""
Base policy compilation and execution utilities.

Moved from mjarena.agents.dspy_programs.verifiers.policy_base.
"""
from __future__ import annotations

import abc
import ast
import builtins as _builtins
import collections
import collections.abc
import functools
import math
import random
import threading
import typing
import zlib
from types import ModuleType
from typing import Callable, Dict, Iterable, List, Mapping

import numpy as np
import numpy.fft
import numpy.linalg
import numpy.random

from mjarena.agents.types import BotObservation
from mjarena.envs.history import DEFAULT_HISTORY_LEN
from mjarena.utils.code_blocks import extract_code_block


# =============================================================================
# Safe Code Execution Environment
# =============================================================================

# Builtins the policy namespace does not provide. Calling one raises NameError
# mid-match, which costs the round, so the validator rejects them too — see
# FORBIDDEN_CALLS, which is derived from this one list.
_DENIED_BUILTINS = {
    'open', 'exec', 'eval', 'compile', 'breakpoint', 'exit', 'quit', 'input',
    'globals', 'locals', 'vars', 'getattr', 'setattr', 'delattr',
}
_ALLOWED_IMPORT_ROOTS = {'typing', 'numpy', 'math', 'random', 'collections'}

# Subtrees of an allowed root the sandbox still refuses. The root check alone
# already closes the escape (`numpy.lib.npyio`'s `os` is named "os" and so is
# not under an allowed root), but these subtrees are NumPy's file I/O, its
# private C bridge and its build/test plumbing rather than numerics, and a
# controller has no use for them. `numpy.linalg`, `numpy.fft` and
# `collections.abc` stay; `numpy.random` is replaced by a private generator
# (see `_PrivateNumpyRandom`).
_DENIED_SUBMODULES = frozenset({
    "numpy.lib", "numpy.core", "numpy._core", "numpy.ctypeslib", "numpy.testing",
    "numpy.f2py", "numpy.distutils", "numpy.ma", "numpy.matlib", "numpy.char",
})

# Attribute names a module proxy never hands out: file I/O, memory-backed array
# construction, and the process-wide library switches one controller could flip
# under its opponent (`np.seterr`, `np.set_printoptions`, `np.setbufsize`).
_DENIED_MODULE_ATTRIBUTES = frozenset({
    "save", "savez", "savez_compressed", "load", "savetxt", "loadtxt",
    "fromfile", "tofile", "memmap", "genfromtxt", "DataSource",
    "seterr", "seterrcall", "geterr", "set_printoptions", "setbufsize",
    "add_docstring", "add_newdoc", "get_include", "show_config", "frombuffer",
})

# The classes a `random` / `np.random` proxy passes through untouched. Every
# other name comes from the controller's own private generator instance, so
# `random.seed(…)` reseeds that instance and nothing else.
_RANDOM_PASSTHROUGH = frozenset({"Random", "SystemRandom"})
_NUMPY_RANDOM_PASSTHROUGH = frozenset({
    "default_rng", "Generator", "RandomState", "SeedSequence", "BitGenerator",
    "PCG64", "PCG64DXSM", "MT19937", "Philox", "SFC64",
})

_SANDBOX_NOTE = "is not available in the controller sandbox"


def _module_is_allowed(dotted: str) -> bool:
    """True when *dotted* names something inside the modules the prompt lists."""
    if dotted.split(".", 1)[0] not in _ALLOWED_IMPORT_ROOTS:
        return False
    return not any(dotted == denied or dotted.startswith(denied + ".")
                   for denied in _DENIED_SUBMODULES)


class _ReadOnlyModule:
    """A module the controller may read, narrowed to what the prompt promises.

    Two things go wrong with handing a controller a real module. It is a
    process-wide object, so an attribute stored on one outlives the match, the
    process's later matches and the opponent's controller — and both prompts
    promise "Every qualification and tournament match starts with a fresh
    controller state". And a module holds whatever its own source imported:
    CPython's `random` does `import os as _os` and `collections` does
    `import sys as _sys`, so `random._os.system(…)` was arbitrary OS execution
    from model-written code with no `getattr` and no dunder in sight.

    So the proxy is capability-scoped rather than name-filtered:

    * a private name (leading underscore) is never handed out — that is `_os`,
      `_sys` and every other import an allowed module happens to hold;
    * a value that is itself a module is handed out only when it lives under one
      of `_ALLOWED_IMPORT_ROOTS` and outside `_DENIED_SUBMODULES`, and then only
      wrapped in another proxy, so `np.linalg` is no more writable than `np` and
      `np.lib` is not reachable at all;
    * the file-I/O and global-library-state names of `_DENIED_MODULE_ATTRIBUTES`
      are refused on every module;
    * a store raises instead of persisting.

    The wrapped module is unreachable by name: ``__getattribute__`` routes every
    lookup to the module, including the proxy's own slots.
    """

    __slots__ = ("_ro_module", "_ro_sandbox")

    def __init__(self, module: ModuleType, sandbox: "_ControllerSandbox"):
        object.__setattr__(self, "_ro_module", module)
        object.__setattr__(self, "_ro_sandbox", sandbox)

    def __getattribute__(self, name):
        module = object.__getattribute__(self, "_ro_module")
        modname = module.__name__
        if name.startswith("_"):
            raise AttributeError(
                f"{modname}.{name} {_SANDBOX_NOTE}: private module attributes are hidden"
            )
        if name in _DENIED_MODULE_ATTRIBUTES:
            raise AttributeError(
                f"{modname}.{name} {_SANDBOX_NOTE}: file, process and global "
                "library state are forbidden"
            )
        value = getattr(module, name)
        if isinstance(value, ModuleType):
            sandbox = object.__getattribute__(self, "_ro_sandbox")
            return sandbox.module(value)
        return value

    def __setattr__(self, name, value):
        raise AttributeError("module is read-only in the controller sandbox")

    def __delattr__(self, name):
        raise AttributeError("module is read-only in the controller sandbox")

    def __repr__(self):
        return f"<read-only module {object.__getattribute__(self, '_ro_module').__name__!r}>"


class _PrivateRandom:
    """`random`, backed by one `random.Random` instance private to a controller.

    `random.seed(1234)` used to pin the *opponent's* draws for the rest of the
    process and perturb any harness code on the global generator. Every
    module-level name here is a bound method of the controller's own instance,
    so `seed`, `getstate` and `setstate` reach nothing shared. `random.Random`
    itself is passed through: a controller that wants its own generator object
    may still build one.
    """

    __slots__ = ("_pr_rng",)

    def __init__(self, rng: random.Random):
        object.__setattr__(self, "_pr_rng", rng)

    def __getattribute__(self, name):
        if name.startswith("_"):
            raise AttributeError(
                f"random.{name} {_SANDBOX_NOTE}: private module attributes are hidden")
        if name in _RANDOM_PASSTHROUGH:
            return getattr(random, name)
        rng = object.__getattribute__(self, "_pr_rng")
        if hasattr(rng, name):
            return getattr(rng, name)
        raise AttributeError(f"random.{name} {_SANDBOX_NOTE}")

    def __setattr__(self, name, value):
        raise AttributeError("module is read-only in the controller sandbox")

    def __delattr__(self, name):
        raise AttributeError("module is read-only in the controller sandbox")

    def __repr__(self):
        return "<private random for the controller sandbox>"


class _PrivateNumpyRandom:
    """`numpy.random`, backed by one `RandomState` private to a controller.

    The same rule as `_PrivateRandom`: `np.random.seed`, `np.random.rand` and
    the rest are that instance's methods. The generator *classes* are passed
    through, so `np.random.default_rng(7)` still works and is still the
    controller's own object.
    """

    __slots__ = ("_pnr_rng",)

    def __init__(self, rng):
        object.__setattr__(self, "_pnr_rng", rng)

    def __getattribute__(self, name):
        if name.startswith("_"):
            raise AttributeError(
                f"numpy.random.{name} {_SANDBOX_NOTE}: private module attributes are hidden")
        if name in _NUMPY_RANDOM_PASSTHROUGH:
            return getattr(np.random, name)
        rng = object.__getattribute__(self, "_pnr_rng")
        if hasattr(rng, name):
            return getattr(rng, name)
        raise AttributeError(f"numpy.random.{name} {_SANDBOX_NOTE}")

    def __setattr__(self, name, value):
        raise AttributeError("module is read-only in the controller sandbox")

    def __delattr__(self, name):
        raise AttributeError("module is read-only in the controller sandbox")

    def __repr__(self):
        return "<private numpy.random for the controller sandbox>"


# ---------------------------------------------------------------------------
# Shared library state
# ---------------------------------------------------------------------------
# The proxies stop a store on a *module*. They hand classes out untouched, and a
# class is just as good a stash: `random.Random.arena_stash = n` counted 1, 2,
# 3, 4 across `new_match()` at cd9702a3. Nothing in the sandbox can make a
# process-wide class private, so the ruling is to detect the write, undo it and
# score it as a controller error.
#
# Only classes that *accept* an attribute store are watched. A static C type
# (`np.ndarray`, `collections.deque`) carries Py_TPFLAGS_IMMUTABLETYPE and
# raises TypeError on `cls.x = …`, which is already a controller error by the
# ordinary crash-forfeit rule.

_IMMUTABLE_TYPE = 1 << 8        # Py_TPFLAGS_IMMUTABLETYPE (CPython >= 3.10)
_DEEP_CHECK_EVERY = 10
_GUARD_LOCK = threading.Lock()
_LIBRARY_STATE: "_LibraryState | None" = None


def _guarded_modules() -> List[ModuleType]:
    """The module objects a controller can reach through the proxies."""
    return [np, math, random, collections, typing,
            np.linalg, np.fft, np.random, collections.abc]


def _guarded_targets():
    """(label, object, is_module) for every namespace a controller can write to."""
    modules = _guarded_modules()
    for module in modules:
        yield module.__name__, module, True
    watched = list(modules) + [random.Random, random.SystemRandom,
                               np.random.RandomState, np.random.Generator]
    for owner in watched:
        if not isinstance(owner, ModuleType):
            if not (owner.__flags__ & _IMMUTABLE_TYPE):
                yield f"{owner.__module__}.{owner.__qualname__}", owner, False
            continue
        for name in dir(owner):
            if name.startswith("_") or f"{owner.__name__}.{name}" in _DENIED_SUBMODULES:
                continue
            try:
                value = getattr(owner, name)
            except Exception:       # numpy raises for removed 1.x aliases
                continue
            if isinstance(value, type) and not (value.__flags__ & _IMMUTABLE_TYPE):
                yield f"{value.__module__}.{value.__qualname__}", value, False


class _GuardedNamespace:
    """One module or class namespace, with the fingerprint it had when clean."""

    __slots__ = ("label", "owner", "is_module", "namespace", "snapshot",
                 "keys", "ids", "length")

    def __init__(self, label: str, owner: object, is_module: bool):
        self.label = label
        self.owner = owner
        self.is_module = is_module
        self.namespace = vars(owner)
        self.refresh()

    def refresh(self) -> None:
        live = self.namespace
        self.snapshot = dict(live)
        self.keys = tuple(live)
        self.ids = tuple(map(id, live.values()))
        self.length = len(live)

    def repair(self, added: Iterable[str], restore: Iterable[str]) -> bool:
        """Put the namespace back the way it was. True when that fully worked."""
        ok = True
        for key in added:
            try:
                delattr(self.owner, key)
            except Exception:
                ok = False
        for key in restore:
            try:
                setattr(self.owner, key, self.snapshot[key])
            except Exception:
                ok = False
        self.refresh()
        return ok


class _LibraryState:
    """Process-wide fingerprint of the shared objects the sandbox exposes.

    One baseline, not one per controller: a write is repaired the moment the
    controller that made it returns, so the opponent's guard never sees it and
    never forfeits for someone else's write.
    """

    def __init__(self):
        seen = set()
        self.entries: List[_GuardedNamespace] = []
        for label, owner, is_module in _guarded_targets():
            if id(owner) in seen:
                continue
            seen.add(id(owner))
            self.entries.append(_GuardedNamespace(label, owner, is_module))

    def check(self, deep: bool) -> None:
        for entry in self.entries:
            live = entry.namespace
            if len(live) != entry.length:
                self._resolve(entry)
            elif deep and (tuple(live) != entry.keys
                           or tuple(map(id, live.values())) != entry.ids):
                self._resolve(entry)

    def _resolve(self, entry: _GuardedNamespace) -> None:
        with _GUARD_LOCK:
            live = dict(entry.namespace)
            snapshot = entry.snapshot
            added = [k for k in live if k not in snapshot]
            removed = [k for k in snapshot if k not in live]
            changed = [k for k in snapshot if k in live and live[k] is not snapshot[k]]
            if not (added or removed or changed):
                entry.refresh()             # another thread repaired it already
                return
            if (entry.is_module and not removed and not changed
                    and all(isinstance(live[k], ModuleType) for k in added)):
                # NumPy imports a submodule on first attribute access, which
                # grows its module dict. That is the library loading itself, not
                # a controller storing state.
                entry.refresh()
                return
            offender = (added + changed + removed)[0]
            what = ("added" if offender in added
                    else "removed" if offender in removed else "replaced")
            repaired = entry.repair(added, removed + changed)
            raise RuntimeError(
                f"Controller error: the controller wrote to shared library state — "
                f"{entry.label}.{offender} was {what}. "
                f"{'Modules' if entry.is_module else 'Classes'} from numpy, math, "
                "random, collections and typing are shared with the opponent and "
                "with every later match in this process, so a controller may not "
                "store state on them. "
                + ("The write was undone." if repaired
                   else "The write could not be fully undone.")
            )


def _library_state() -> _LibraryState:
    global _LIBRARY_STATE
    if _LIBRARY_STATE is None:
        with _GUARD_LOCK:
            if _LIBRARY_STATE is None:
                _LIBRARY_STATE = _LibraryState()
    return _LIBRARY_STATE


class _SharedStateGuard:
    """Re-checks the shared namespaces after each of one controller's calls.

    Two tiers, because the full comparison costs ~100 us and a control step is
    10 ms of simulated time: every call compares namespace *lengths* (~4 us),
    which catches an added or removed attribute — a stash — on the very call
    that writes it; the first call and every tenth after it also compare keys
    and value identities, which catches a *replaced* attribute (patching
    `random.Random.random`).

    Both tiers compare namespace contents, and one shared write never shows up
    there: `ABCMeta.register` rewrites an abstract base class's registry in
    place, adding no key to `vars(collections.abc.Mapping)` and replacing no
    value. CPython bumps a process-wide counter on every `register` call, so the
    cheap tier reads that counter instead. It is read immediately before the
    call as well as after, so a registration the *host* makes between two calls
    is never charged to the controller.
    """

    __slots__ = ("_calls", "_abc_token")

    def __init__(self):
        self._calls = 0
        self._abc_token = abc.get_cache_token()

    def arm(self) -> None:
        """Take the pre-call baseline, so only changes during the call count."""
        self._abc_token = abc.get_cache_token()

    def check(self) -> None:
        self._calls += 1
        if abc.get_cache_token() != self._abc_token:
            raise RuntimeError(
                "Controller error: the controller registered a class on a shared "
                "abstract base class (the ABC registry changed during the call). "
                "The abstract base classes in collections.abc are shared with the "
                "opponent and with every later match in this process, so shared "
                "library objects are read-only. A registration cannot be undone."
            )
        _library_state().check(deep=(self._calls % _DEEP_CHECK_EVERY == 1))


class _ControllerSandbox:
    """Everything one compiled controller gets instead of the real libraries."""

    def __init__(self, rng_seed: int):
        self._proxies: Dict[str, object] = {}
        self._random = _PrivateRandom(random.Random(rng_seed))
        self._numpy_random = _PrivateNumpyRandom(
            np.random.RandomState(rng_seed % (2 ** 32)))
        # Take the clean fingerprint now, before the controller's module-level
        # code runs: a baseline captured on the first *call* would already
        # contain anything the controller stored on the way in.
        _library_state()
        self.guard = _SharedStateGuard()

    def module(self, module: ModuleType) -> object:
        """The proxy for *module*, or AttributeError if it is out of scope."""
        name = module.__name__
        if name == "random":
            return self._random
        if name == "numpy.random":
            return self._numpy_random
        if not _module_is_allowed(name):
            raise AttributeError(f"module {name!r} {_SANDBOX_NOTE}")
        if name not in self._proxies:
            self._proxies[name] = _ReadOnlyModule(module, self)
        return self._proxies[name]


def controller_rng_seed(match_seed: int, side: str) -> int:
    """The private-RNG seed for one side of one match.

    Deterministic across processes (CRC32, not `hash()`), and different for the
    two sides so red and blue do not draw the same stream.
    """
    return zlib.crc32(f"{side}:{int(match_seed)}".encode("utf-8"))


def _restricted_builtins(sandbox: "_ControllerSandbox | None" = None) -> dict:
    """Create restricted builtins dictionary for safe policy execution.

    Uses a denylist approach: all builtins are allowed EXCEPT dangerous ones.
    This avoids the fragile allowlist pattern where missing a builtin (e.g.
    `hasattr`) crashes every policy that uses it. `getattr`/`setattr`/`delattr`
    are denied: `getattr(typing, 'sy' + 's')` reached `sys` and then `os`, and a
    computed name defeats every static path check the validator makes.

    Args:
        sandbox: the per-controller sandbox whose proxies and private generators
            an import resolves to. Defaults to a throwaway sandbox, for callers
            that only want to inspect the builtins table.
    """
    if sandbox is None:
        sandbox = _ControllerSandbox(0)

    def _safe_import(name, globals=None, locals=None, fromlist=(), level=0):
        # Compare the package root, not a prefix: 'numpy_fake' is not numpy.
        # A relative import (level > 0) resolves against the policy's own
        # package and can reach anything, so it is never allowed. The same
        # subtree rules as the proxy apply, so `import numpy.lib` and
        # `from numpy import lib` are both refused.
        if level == 0 and _module_is_allowed(name):
            return sandbox.module(_builtins.__import__(name, globals, locals, fromlist, level))
        raise ImportError(f"Blocked import in policy: {name}")

    restricted = {k: v for k, v in vars(_builtins).items() if k not in _DENIED_BUILTINS}
    restricted['__import__'] = _safe_import
    return restricted


FORBIDDEN_MODULES = frozenset({
    "os", "sys", "subprocess", "socket", "requests", "urllib", "shutil", "psutil",
    "ctypes", "multiprocessing", "threading", "pexpect", "pty", "pickle", "dill",
    "importlib", "builtins", "signal", "asyncio", "http", "ftplib", "pathlib",
})
# Reject at validation exactly what the runtime namespace denies, plus the
# import hook. Failing with a line number beats a NameError mid-match: the
# model can fix the controller instead of forfeiting a qualification seed.
# getattr/setattr/delattr are in _DENIED_BUILTINS and so are here too: a
# computed attribute name is invisible to every static path check below, and
# `getattr(typing, 'sy' + 's').modules['o' + 's']` was full OS access.
FORBIDDEN_CALLS = frozenset(_DENIED_BUILTINS | {"__import__"})
# Attribute names that write a file whatever the object is: `arr.tofile(path)`
# and `arr.dump(path)` are methods of an array the controller already holds, so
# no module-level rule reaches them.
FORBIDDEN_ATTRIBUTES = frozenset({"tofile", "dump"})
# Attribute names refused on a chain rooted at a *library* name — an imported
# module, an alias of one, or a pre-injected `np` / `math` / `collections`.
# These are the runtime proxy's own denials, reported at compile time with a
# line number instead of mid-match. They are deliberately NOT applied to a
# controller's own objects: `self.load` and `state.core` are ordinary names.
FORBIDDEN_LIBRARY_ATTRIBUTES = _DENIED_MODULE_ATTRIBUTES | frozenset({
    "lib", "core", "_core", "ctypeslib", "testing", "f2py", "distutils",
    "ma", "matlib", "char", "__config__",
})
# Attribute names refused on a library-rooted chain because *calling* them
# rewrites state the controller shares with its opponent and with every later
# match in the process. `ABCMeta.register` is the one: it rewrites an abstract
# base class's registry in place, so `collections.abc.Mapping.register(int)`
# makes `isinstance` say yes for everyone, cannot be undone, and adds no key
# that the shared-state fingerprint could notice. `_SharedStateGuard` catches it
# from `abc.get_cache_token()` and costs the round; this rejects the direct
# spelling with a line number instead, so the model can fix the controller.
FORBIDDEN_LIBRARY_MUTATORS = frozenset({"register"})
# The modules `compile_policy_function` puts in the namespace without an import.
_PREINJECTED_MODULE_NAMES = ("math", "np", "numpy", "collections")


def _validate_policy_code_safety(code: str, blacklist: Iterable[str] = ()) -> None:
    """Static safety check on the parsed code (comments and strings are not code).

    Names are compared as Python identifier paths, never as source substrings:
    'pty' is not 'empty', a local variable called `requests` is not the requests
    module, and a docstring that mentions os.system is prose. Imports are
    inspected wherever they appear — inside a function, in an unreachable branch
    — and import aliases are followed, so `from numpy.lib import os as platform`
    is rejected at the import and again at every use of `platform`.

    Args:
        code: Python source code to validate.
        blacklist: Extra forbidden identifiers, qualified names ("os.system"),
            or names written with a trailing "(" to mean "this name, called".

    Raises:
        RuntimeError: with the construct and its line number.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        raise RuntimeError(f"Policy code has syntax errors: {exc}") from exc

    blacklist = (tuple(blacklist) + tuple(FORBIDDEN_MODULES)
                 + tuple(f"{name}(" for name in FORBIDDEN_CALLS))
    forbidden = {tuple(bad.removesuffix("(").split(".")) for bad in blacklist}
    # Names that are dangerous even when merely referenced (aliasing `open` and
    # calling the alias is still calling open).
    forbidden_names = {bad[:-1] for bad in blacklist if bad.endswith("(")}
    forbidden_names |= {"__import__", "__builtins__"}
    # Do not let string-key lookup of the builtins table bypass name checks.
    forbidden.add(("__builtins__",))
    # ctypeslib is NumPy's bridge to ctypes, and _ctypes its extension module.
    if ("ctypes",) in forbidden:
        forbidden.update({("ctypeslib",), ("_ctypes",)})

    def _attribute_name_constants(node: ast.AST) -> list[str]:
        """String constants *node* names an attribute with (not data)."""
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id in ("getattr", "setattr", "delattr", "hasattr")
                and len(node.args) >= 2 and isinstance(node.args[1], ast.Constant)
                and isinstance(node.args[1].value, str)):
            return [node.args[1].value]
        return []

    def _subscript_key_constants(node: ast.AST) -> list[str]:
        """String constants *node* uses as a subscript key.

        A dict lookup is ordinary data (`obs["my_pos"]`), so only the dunder rule
        applies here — a key holding `__` is a `__dict__`/`__builtins__` table
        walk spelled as a string, not an observation field.
        """
        if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
            key = node.slice.value
            return [key] if isinstance(key, str) else []
        return []

    def reject(what: str, node: ast.AST) -> None:
        raise RuntimeError(
            f"Disallowed construct in policy: {what} (line {node.lineno})"
        )

    def check_path(path: tuple[str, ...], node: ast.AST, what: str = "") -> None:
        for banned in forbidden:
            if any(path[i:i + len(banned)] == banned
                   for i in range(len(path) - len(banned) + 1)):
                reject(what or ".".join(banned), node)

    # Inspect imports even inside functions or unreachable branches. Retain all
    # aliases conservatively so a later import cannot hide an earlier reference.
    aliases: dict[str, set[tuple[str, ...]]] = {}
    # Local names bound to a library: the chains the module rules apply to.
    library_names: set[str] = set(_PREINJECTED_MODULE_NAMES)
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        from_import = isinstance(node, ast.ImportFrom)
        module = (node.module or "") if from_import else ""
        for item in node.names:
            imported = f"{module}.{item.name}" if module else item.name
            what = (f"import from '{node.module or '.'}'" if from_import
                    else f"import of '{item.name}'")
            check_path(tuple(imported.split(".")), node, what)
            root = (module or item.name).split(".", 1)[0]
            if (from_import and node.level) or root not in _ALLOWED_IMPORT_ROOTS:
                raise RuntimeError(
                    f"Blocked import in policy: {imported} (line {node.lineno})"
                )
            # `numpy.lib` / `from numpy import lib` re-open the module tree the
            # root allowlist exists to close; the proxy refuses them at run time
            # and this says so with a line number.
            if not _module_is_allowed(imported):
                raise RuntimeError(
                    f"Blocked import in policy: {imported} (line {node.lineno})"
                )
            if isinstance(node, ast.Import) and not item.asname:
                local, path = root, (root,)
            else:
                local, path = item.asname or item.name, tuple(imported.split("."))
            aliases.setdefault(local, set()).add(path)
            library_names.add(local)

    def reference_paths(node: ast.AST) -> set[tuple[str, ...]]:
        if isinstance(node, ast.Name):
            return {(node.id,)} | aliases.get(node.id, set())
        if isinstance(node, ast.Attribute):
            bases = reference_paths(node.value)
            return {base + (node.attr,) for base in bases} or {(node.attr,)}
        if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
            key = node.slice.value
            if key in ("__builtins__", "__import__"):
                return {(key,)}
            if (isinstance(key, str) and isinstance(node.value, ast.Attribute)
                    and node.value.attr == "__dict__"):
                bases = reference_paths(node.value.value)
                return {base + (key,) for base in bases} or {(key,)}
        # Literal getattr lookups are attribute access too, rather than ordinary
        # string data. This keeps getattr(obj, '__import__') from evading checks.
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "getattr" and len(node.args) >= 2
                and isinstance(node.args[1], ast.Constant)
                and isinstance(node.args[1].value, str)):
            attr = node.args[1].value
            bases = reference_paths(node.args[0])
            return {base + (attr,) for base in bases} or {(attr,)}
        return set()

    def library_rooted(node: ast.AST) -> bool:
        """True when this attribute chain starts at an imported library name."""
        while True:
            if isinstance(node, (ast.Attribute, ast.Subscript)):
                node = node.value
            elif isinstance(node, ast.Call):
                node = node.func
            else:
                break
        return isinstance(node, ast.Name) and node.id in library_names

    for node in ast.walk(tree):
        # ast.walk is breadth-first, so a call is seen before the name it calls:
        # the direct case gets the more precise "call to open()" wording, and
        # everything else (aliases, attributes) falls through to the paths below.
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id in FORBIDDEN_CALLS):
            reject(f"call to {node.func.id}()", node)
        # A local variable called 'requests' is not a requests import. Dangerous
        # builtin references are still rejected, including assigning an alias.
        if isinstance(node, ast.Name) and node.id not in forbidden_names and node.id not in aliases:
            continue
        if isinstance(node, (ast.Name, ast.Attribute, ast.Call, ast.Subscript)):
            for path in reference_paths(node):
                check_path(path, node)
        # The escape hatch to __builtins__ / __subclasses__ is a dunder
        # attribute; policies have no legitimate use for one.
        if (isinstance(node, ast.Attribute)
                and node.attr.startswith("__") and node.attr.endswith("__")):
            reject(f"dunder attribute access .{node.attr}", node)
        # File access through a method of an object the controller holds.
        if isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_ATTRIBUTES:
            reject(f"file, process or internals access .{node.attr}", node)
        # The module rules, on module-rooted chains only. `random._os` and
        # `collections._sys` are the private imports an allowed module happens
        # to hold; `np.lib` and `np.save` are the module tree and the file I/O.
        if isinstance(node, ast.Attribute) and library_rooted(node):
            if node.attr.startswith("_"):
                reject(f"private library attribute .{node.attr}", node)
            if node.attr in FORBIDDEN_LIBRARY_ATTRIBUTES:
                reject(f"file, process or internals access .{node.attr}", node)
            if node.attr in FORBIDDEN_LIBRARY_MUTATORS:
                reject(f"shared library mutation .{node.attr}", node)
        # An attribute named by a string constant is attribute access, not data.
        # A dunder written that way is the same escape hatch spelled differently.
        for name in _attribute_name_constants(node):
            if "__" in name:
                reject(f"dunder attribute access '{name}'", node)
            if name in FORBIDDEN_ATTRIBUTES:
                reject(f"file, process or internals access '{name}'", node)
            if name in FORBIDDEN_LIBRARY_ATTRIBUTES and library_rooted(node.args[0]):
                reject(f"file, process or internals access '{name}'", node)
        for key in _subscript_key_constants(node):
            if "__" in key:
                reject(f"dunder attribute access '{key}'", node)
        # NumPy exposes pickle through a keyword rather than a module reference.
        # Explicitly disabling it is safe; enabling it (including dynamically)
        # must not bypass the prohibition on pickle deserialization.
        if isinstance(node, ast.keyword) and node.arg == "allow_pickle" and ("pickle",) in forbidden:
            if not (isinstance(node.value, ast.Constant) and node.value.value is False):
                reject("allow_pickle", node.value)


# =============================================================================
# Policy Compilation
# =============================================================================

def _strip_code_fences(code: str) -> str:
    """Return the one fenced block of controller source, or *code* unchanged.

    Raises:
        ValueError: the reply fences more than one block, or leaves one open.
    """
    return extract_code_block(code)


def compile_policy_function(code: str, *, rng_seed: int = 0) -> callable:
    """
    Safely compile policy source code into executable function.

    Args:
        code: Python policy source code containing policy_step function
        rng_seed: seed for the private `random` / `np.random` this controller
            gets. `ActuatorPolicyAdapter.new_match` passes
            `controller_rng_seed(match_seed, side)`; the default is for compiles
            that are not a match (verification, qualification smoke calls).

    Returns:
        Callable policy_step function

    Raises:
        RuntimeError: If code is unsafe or compilation fails
    """
    # Strip markdown code fences if present
    code = _strip_code_fences(code)

    # Security validation (AST-based; see _validate_policy_code_safety)
    _validate_policy_code_safety(code)

    # Create restricted execution environment
    # Pre-inject commonly used libraries so LLM-generated code works
    # even if it forgets to import them. Each controller gets its own read-only
    # proxies and its own random generators: the modules themselves are
    # process-wide, and an attribute stored on one — or a seed set on one —
    # would outlive the match the prompt promises starts fresh.
    sandbox = _ControllerSandbox(rng_seed)
    namespace: Dict[str, object] = {
        "__name__": "__policy__",
        "__builtins__": _restricted_builtins(sandbox),
        "math": sandbox.module(math),
        "np": sandbox.module(np),
        "numpy": sandbox.module(np),
        "collections": sandbox.module(collections),
    }

    # Execute policy code
    try:
        exec(compile(code, "<policy>", "exec"), namespace, namespace)  # noqa: S102
    except Exception as exc:
        raise RuntimeError(f"Policy code execution failed: {exc}") from exc

    # Extract policy_step function
    policy_step = namespace.get("policy_step")
    if not callable(policy_step):
        raise RuntimeError("policy_step(obs) function not found in policy code")

    guard = sandbox.guard

    @functools.wraps(policy_step)
    def guarded_policy_step(obs):
        guard.arm()
        result = policy_step(obs)
        guard.check()
        return result

    return guarded_policy_step


# =============================================================================
# Observation Utilities
# =============================================================================

def _empty_robot_state() -> Dict[str, object]:
    """Named robot record with no parts, for observations built without a robot."""
    return {
        "bodies": {},
        "geoms": {},
        "joints": {},
        "tendons": {},
        "motors": {},
        "sites": {},
        "mass": 0.0,
        "com_position": np.zeros(3),
        "com_velocity": np.zeros(3),
        "root_body": "",
    }


def create_dummy_observation_dict() -> Dict[str, object]:
    """
    Create dummy observation dictionary for policy testing.

    Returns:
        Dictionary observation compatible with policies (full 3D schema).
    """
    from mjarena.envs.detailed_observations import SURFACE_CUTOFF, SURFACE_LIMIT

    dummy_obs = BotObservation.get_dummy_bot_obs()

    # Dummy grids (41x41, cell_size=0.25)
    grid_size = 41
    dummy_int_grid = np.zeros((grid_size, grid_size), dtype=np.int8)
    dummy_float_grid = np.zeros((grid_size, grid_size), dtype=np.float32)

    # Convert to dict format matching every field in the prompt's obs_schema block
    return {
        # Position
        "my_pos": dummy_obs.my_pos,
        "opponent_pos": dummy_obs.opponent_pos,
        # Orientation
        "my_yaw": dummy_obs.my_yaw,
        "my_pitch": dummy_obs.my_pitch,
        "my_roll": dummy_obs.my_roll,
        "opponent_yaw": dummy_obs.opponent_yaw,
        "opponent_pitch": dummy_obs.opponent_pitch,
        "opponent_roll": dummy_obs.opponent_roll,
        # Velocity
        "my_velocity": dummy_obs.my_velocity,
        "my_angular_velocity": dummy_obs.my_angular_velocity,
        "opponent_velocity": dummy_obs.opponent_velocity,
        "opponent_angular_velocity": dummy_obs.opponent_angular_velocity,
        "my_actuator_velocity": dummy_obs.my_actuator_velocity,
        "opponent_actuator_velocity": dummy_obs.opponent_actuator_velocity,
        # Distances
        "distance_to_opponent": dummy_obs.distance_to_opponent,
        "my_edge_distance": dummy_obs.my_edge_distance,
        "opponent_edge_distance": dummy_obs.opponent_edge_distance,
        # Contact
        "opponent_contact": dummy_obs.opponent_contact,
        "opponent_contact_force": dummy_obs.opponent_contact_force,
        "ground_contact": dummy_obs.ground_contact,
        # Stability
        "is_tipping": dummy_obs.is_tipping,
        # Time
        "t": dummy_obs.t,
        "max_t": dummy_obs.max_t,
        # Robot properties
        "my_bounding_radius": dummy_obs.my_bounding_radius,
        "opponent_bounding_radius": dummy_obs.opponent_bounding_radius,
        "ring_radius": dummy_obs.ring_radius,
        # Spatial grids
        "arena_grid": dummy_int_grid.copy(),
        "arena_mass_grid": dummy_float_grid.copy(),
        "edge_distance_grid": dummy_float_grid.copy(),
        # Inactivity
        "my_inactivity_timer": dummy_obs.my_inactivity_timer,
        "opponent_inactivity_timer": dummy_obs.opponent_inactivity_timer,
        # Game context
        "game": dummy_obs.game,
        # Legacy aliases
        "my_heading": dummy_obs.my_yaw,
        "my_closest_distance_to_ring": dummy_obs.my_edge_distance,
        # History (empty at t=0)
        "obs_history": [],
        "action_history": [],
        # Timing (simulated seconds)
        "control_dt": 0.01,
        "elapsed_time": 0.0,
        "time_remaining": 0.0,
        # Platform the match is fought on
        "platform": {
            "shape": "cylinder",
            "center": np.zeros(3),
            "radius": 7.5,
            "half_extents": np.array([7.5, 7.5]),
            "top_z": 0.0,
            "floor_z": -2.0,
        },
        # Named physical state (empty without a composed robot)
        "my_robot": _empty_robot_state(),
        "opponent_robot": _empty_robot_state(),
        "my_mass": 0.0,
        "opponent_mass": 0.0,
        "my_com_velocity": np.zeros(3),
        "opponent_com_velocity": np.zeros(3),
        # Exact surface proximity to the opponent
        "opponent_surface_distance": 0.0,
        "opponent_proximity": [],
        "proximity_cutoff": SURFACE_CUTOFF,
        "proximity_limit": SURFACE_LIMIT,
        "proximity_truncated": False,
        # Contacts and their impulses over the last control interval
        "contacts": [],
        "contact_impulses": [],
        "contact_interval": 0.0,
    }


def observation_to_dict(obs) -> Dict[str, object]:
    """
    Convert observation object to dictionary format for policies.

    Args:
        obs: BotObservation object or existing dict

    Returns:
        Dictionary format observation
    """
    if hasattr(obs, "to_dict") and callable(getattr(obs, "to_dict")):
        return obs.to_dict()
    elif isinstance(obs, Mapping):
        return dict(obs)
    else:
        return obs


# =============================================================================
# Policy Wrapper Base Class
# =============================================================================

class BasePolicyWrapper:
    """
    Base class for policy wrappers providing common functionality.

    Handles safe policy execution, observation conversion, and error handling.
    """

    def __init__(self, policy_step_func: callable):
        """
        Initialize policy wrapper.

        Args:
            policy_step_func: Compiled policy_step function.
        """
        self.policy_step_func = policy_step_func

    def _prepare_observation(self, obs) -> Dict[str, object]:
        """
        Prepare observation for policy execution.

        Converts observation to dict format.
        """
        return observation_to_dict(obs)

    def execute_policy(self, obs) -> object:
        """
        Execute policy with observation and return raw result.

        Args:
            obs: Observation data.

        Returns:
            Raw policy output.

        Raises:
            RuntimeError: If policy execution fails.
        """
        try:
            prepared_obs = self._prepare_observation(obs)
            return self.policy_step_func(prepared_obs)
        except Exception as exc:
            raise RuntimeError(f"Policy execution failed: {exc}") from exc


__all__ = [
    "compile_policy_function",
    "FORBIDDEN_ATTRIBUTES",
    "create_dummy_observation_dict",
    "observation_to_dict",
    "BasePolicyWrapper",
]
