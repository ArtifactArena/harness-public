import io
from unittest.mock import Mock

from tqdm import tqdm

from mjarena.runner import progress


def test_bar_has_eta_and_bypasses_tee_log(monkeypatch):
    terminal = io.StringIO()
    logfile = io.StringIO()
    tee = Mock()
    tee.isatty.return_value = True
    tee.write.side_effect = logfile.write
    tee.write_ephemeral.side_effect = terminal.write
    monkeypatch.setattr(progress.sys, "stderr", tee)
    monkeypatch.delenv("ARENA_PROGRESS", raising=False)
    with tqdm(total=100, **progress.match_progress_options(42)) as bar:
        bar.update(10)
        bar.refresh()
    assert "Match seed 42" in terminal.getvalue()
    assert "10/100" in terminal.getvalue()
    assert "ETA" in terminal.getvalue()
    assert logfile.getvalue() == ""


def test_redirected_or_disabled_output_has_no_bar(monkeypatch):
    monkeypatch.setattr(progress.sys, "stderr", io.StringIO())
    monkeypatch.delenv("ARENA_PROGRESS", raising=False)
    assert progress.match_progress_options(42)["disable"]
    monkeypatch.setenv("ARENA_PROGRESS", "1")
    assert not progress.match_progress_options(42)["disable"]
    monkeypatch.setenv("ARENA_PROGRESS", "0")
    assert progress.match_progress_options(42)["disable"]
