"""site_ids: the one mapping between tournament-tree bot ids (<model>__t<N>_c000) and website
artifact ids (<model>__sampling__t<NNN>_c000), plus the replay task-id / capsule-sha scheme."""
import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/sampling"))   # same convention as tests/test_release_readme.py
from website import site_ids as S  # noqa: E402


@pytest.mark.parametrize("tid,aid,n", [
    ("gemini-3-1-pro-high__t09_c000", "gemini-3-1-pro-high__sampling__t009_c000", 9),
    ("gemini-3-1-pro-high__t87_c000", "gemini-3-1-pro-high__sampling__t087_c000", 87),
    ("gemini-3-1-pro-high__t104_c000", "gemini-3-1-pro-high__sampling__t104_c000", 104),
    ("qwen3.8-2.4t-a95b-thinking__t137_c000", "qwen3.8-2.4t-a95b-thinking__sampling__t137_c000", 137),
])
def test_round_trip(tid, aid, n):
    assert S.site_aid(tid) == aid
    assert S.harness_id(aid) == tid
    assert S.sample_index(tid) == S.sample_index(aid) == n
    assert S.model_of(tid) == S.model_of(aid) == tid.rsplit("__t", 1)[0]


def test_rejects_foreign_ids():
    with pytest.raises(ValueError):
        S.site_aid("baseline__box")
    with pytest.raises(ValueError):
        S.harness_id("gpt-5.4__sampling__t00_c000")   # a two-digit July id is not ours
    with pytest.raises(ValueError):
        S.site_aid("gpt-5.4__sampling__t000_c000")    # already a site aid


def test_task_id_and_sha():
    t = S.task_id(3, 10)
    assert t == "final-sh250-5ac92bc7:pair:3:10"
    assert S.capsule_sha(t) == hashlib.sha256(t.encode()).hexdigest()


def test_qual_task_id():
    assert S.qual_task_id(4401, 2) == "final-sh250-5ac92bc7:qual:4401:2"
