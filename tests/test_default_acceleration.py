"""Backend selection and cleanup without requiring compiled extensions."""
from types import SimpleNamespace
from unittest.mock import Mock
import sys

import pytest

from mjarena.runner import acceleration


@pytest.fixture
def backend(monkeypatch, tmp_path):
    import mjarena.envs

    monkeypatch.delenv("ARENA_MATCH_ACCEL", raising=False)
    monkeypatch.delenv("ARENA_OBS_ACCEL", raising=False)
    monkeypatch.setattr(acceleration.platform, "system", lambda: "Linux")
    monkeypatch.setattr(acceleration.platform, "machine", lambda: "x86_64")
    library = tmp_path / "arena_serial.so"
    library.touch()
    monkeypatch.setenv("ARENA_MATCH_ACCEL_LIBRARY", str(library))
    observer = SimpleNamespace(DetailedObservations=object())
    original = observer.DetailedObservations
    native = SimpleNamespace(_INSTALLED=None, install=Mock())
    obs = SimpleNamespace(install=Mock())
    pools = SimpleNamespace(threadpool_limits=Mock())
    for name, module in (("match_accel", native), ("detailed_observations", observer),
                         ("observation_accel", obs)):
        monkeypatch.setattr(mjarena.envs, name, module, raising=False)
        monkeypatch.setitem(sys.modules, "mjarena.envs." + name, module)
    monkeypatch.setitem(sys.modules, "threadpoolctl", pools)
    return SimpleNamespace(native=native, obs=obs, observer=observer,
                           original=original, pools=pools, library=library)


def test_default_native_and_cleanup_after_match_error(backend):
    with pytest.raises(ArithmeticError, match="controller"):
        with acceleration.match_acceleration():
            backend.observer.DetailedObservations = object()
            raise ArithmeticError("controller")
    backend.native.install.assert_called_once_with(
        backend.library, threads=1, interval=True, require_affinity=False)
    backend.native.install.return_value.close.assert_called_once()
    backend.pools.threadpool_limits.return_value.restore_original_limits.assert_called_once()
    assert backend.observer.DetailedObservations is backend.original


def test_missing_library_warns_and_uses_observations(backend, caplog):
    backend.library.unlink()
    with acceleration.match_acceleration():
        backend.obs.install.assert_called_once()
    backend.native.install.assert_not_called()
    assert "Cython observations only" in caplog.text


def test_incompatible_native_and_observations_use_reference(backend, caplog):
    backend.native.install.side_effect = RuntimeError("wrong ABI")
    backend.obs.install.side_effect = RuntimeError("no extension")
    with acceleration.match_acceleration():
        assert backend.observer.DetailedObservations is backend.original
    assert "Match acceleration: reference" in caplog.text
    backend.pools.threadpool_limits.return_value.restore_original_limits.assert_called_once()


def test_require_native_does_not_fall_back(backend, monkeypatch):
    monkeypatch.setenv("ARENA_MATCH_ACCEL", "1")
    backend.native.install.side_effect = RuntimeError("bad manifest")
    with pytest.raises(RuntimeError, match="Required match acceleration unavailable"):
        with acceleration.match_acceleration():
            pytest.fail("must not run a match")
    backend.obs.install.assert_not_called()


def test_disabled_does_not_install(backend, monkeypatch):
    monkeypatch.setenv("ARENA_MATCH_ACCEL", "0")
    with acceleration.match_acceleration():
        pass
    backend.native.install.assert_not_called()
    backend.obs.install.assert_not_called()


def test_external_installation_is_not_closed(backend):
    external = Mock()
    backend.native._INSTALLED = external
    with acceleration.match_acceleration():
        pass
    external.close.assert_not_called()
    backend.native.install.assert_not_called()


def test_unsupported_platform(backend, monkeypatch, caplog):
    monkeypatch.setattr(acceleration.platform, "machine", lambda: "aarch64")
    with acceleration.match_acceleration():
        pass
    backend.native.install.assert_not_called()
    assert "requires Linux x86-64" in caplog.text


def test_invalid_mode(monkeypatch):
    monkeypatch.setenv("ARENA_MATCH_ACCEL", "typo")
    with pytest.raises(ValueError, match="ARENA_MATCH_ACCEL"):
        with acceleration.match_acceleration():
            pass
