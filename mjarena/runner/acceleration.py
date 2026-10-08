"""Select the exact CPU backend at the shared match entry point.

Keep patches scoped to a match: coordinators retain their CPU affinity, spawned
workers initialize independently, and native model contexts are always released.
"""
from contextlib import contextmanager
from functools import wraps
import logging
import os
from pathlib import Path
import platform
import threading


_LOCK = threading.RLock()
_REPORTED = set()
_LIBRARY = Path(__file__).resolve().parents[1] / "envs/match_accel/arena_serial.so"


def _report(mode, reason=""):
    key = (os.getpid(), mode, reason)
    if key not in _REPORTED:
        _REPORTED.add(key)
        message = "Match acceleration: %s (pid=%s)" % (mode, os.getpid())
        if reason:
            message += "; " + reason
        # Visible even to callers that have not configured logging.
        logging.getLogger(__name__).warning(message)


@contextmanager
def match_acceleration():
    """auto (default), 1 (require native), or 0 (disable automatic acceleration).

    Native MuJoCo dispatch and BLAS settings are process-wide. Threaded matches
    therefore serialize here; process workers still execute independently.
    Explicit installations by specialized launchers retain their ownership.
    """
    mode = os.environ.get("ARENA_MATCH_ACCEL", "auto").lower()
    if mode not in {"auto", "0", "1"}:
        raise ValueError("ARENA_MATCH_ACCEL must be auto, 0, or 1")
    if mode == "0":
        _report("disabled")
        yield
        return
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        reason = "requires Linux x86-64; using reference backend"
        if mode == "1":
            raise RuntimeError(reason)
        _report("reference", reason)
        yield
        return

    with _LOCK:
        from mjarena.envs import match_accel, detailed_observations

        if match_accel._INSTALLED is not None:
            _report("native (externally managed)")
            yield
            return

        original_observer = detailed_observations.DetailedObservations
        accelerator = None
        limiter = None
        library = Path(os.environ.get("ARENA_MATCH_ACCEL_LIBRARY", str(_LIBRARY)))
        try:
            try:
                if not library.is_file():
                    raise FileNotFoundError(f"missing {library}")
                # NumPy is already imported in ordinary harness entry points.
                # Limit its loaded pools instead of relying on late env changes.
                from threadpoolctl import threadpool_limits

                limiter = threadpool_limits(limits=1)
                accelerator = match_accel.install(
                    library, threads=1, interval=True, require_affinity=False,
                )
            except Exception as exc:
                if limiter is not None:
                    limiter.restore_original_limits()
                    limiter = None
                reason = f"{type(exc).__name__}: {exc}"
                if mode == "1":
                    raise RuntimeError(f"Required match acceleration unavailable: {reason}") from exc
                try:
                    if os.environ.get("ARENA_OBS_ACCEL") == "0":
                        raise RuntimeError("ARENA_OBS_ACCEL=0")
                    from mjarena.envs.observation_accel import install

                    install()
                except Exception as obs_exc:
                    _report("reference", f"{reason}; observations: {obs_exc}. "
                            "See README.md: First-Time Setup")
                else:
                    _report("Cython observations only", f"native unavailable: {reason}. "
                            "See README.md: First-Time Setup")
            else:
                _report("native + Cython observations", str(library))
            yield
        finally:
            try:
                if accelerator is not None:
                    accelerator.close()
            finally:
                detailed_observations.DetailedObservations = original_observer
                if limiter is not None:
                    limiter.restore_original_limits()


def accelerated_match(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        with match_acceleration():
            return fn(*args, **kwargs)
    return wrapped
