"""One mapping between tournament-tree bot ids and website artifact ids.

Tournament tree (pool_rr/, stage_b/): <model>__t<N>_c000, N as the harness printed it (t00, t09, t87, t104).
Website:                               <model>__sampling__t<NNN>_c000, NNN zero-padded to three digits.
"""
import hashlib
import re

RUN_ID = "final-sh250-5ac92bc7"
POOL_RUN_ID = "sh250-pool-5ac92bc7"
CONDITION = "sampling"

_TID = re.compile(r"^(?P<model>.+?)__t(?P<n>\d+)_c000$")
_AID = re.compile(r"^(?P<model>.+?)__sampling__t(?P<n>\d{3})_c000$")


def _parse(any_id: str) -> tuple[str, int]:
    if "__sampling__" in any_id:
        m = _AID.match(any_id)
    else:
        m = _TID.match(any_id)
    if not m:
        raise ValueError(f"not an SH-250 bot id: {any_id!r}")
    return m.group("model"), int(m.group("n"))


def model_of(any_id: str) -> str:
    return _parse(any_id)[0]


def sample_index(any_id: str) -> int:
    return _parse(any_id)[1]


def site_aid(tournament_id: str) -> str:
    if "__sampling__" in tournament_id or not _TID.match(tournament_id):
        raise ValueError(f"not a tournament id: {tournament_id!r}")
    model, n = _parse(tournament_id)
    return f"{model}__{CONDITION}__t{n:03d}_c000"


def harness_id(site_aid_: str) -> str:
    if not _AID.match(site_aid_):
        raise ValueError(f"not an SH-250 site aid: {site_aid_!r}")
    model, n = _parse(site_aid_)
    return f"{model}__t{n:02d}_c000"


def task_id(pair_idx: int, seed_idx: int) -> str:
    return f"{RUN_ID}:pair:{pair_idx}:{seed_idx}"


def qual_task_id(sample_global_idx: int, seed_idx: int) -> str:
    """Qualification Round game id: <global sample index in bots/index.json>:<seed index 0..2>."""
    return f"{RUN_ID}:qual:{sample_global_idx}:{seed_idx}"


def capsule_sha(task_id_: str) -> str:
    return hashlib.sha256(task_id_.encode()).hexdigest()
