#!/usr/bin/env python3
"""Status page for the SH-250 pool tournament (Qualification Round -> Top Bot per Run Round -> Top-5 Round -> Champions
Round; no "stage" letters anywhere on the page) from the per-host mirrors that rsync pulls down. READ-ONLY: the
script only walks local directories and writes one self-contained HTML file (inline CSS, no scripts, no
auto-refresh: a sticky Refresh button reloads the file) plus a markdown twin with the same primary table.

    python scripts/sampling/rr_dashboard.py \\
        [--roots LOGS-SH250/rr-<run>/host_e LOGS-SH250/rr-<run>/host_a] \\
        [--hpc LOGS-SH250/rr-<run>/hpc] \\
        --out SH250_RR.html [--md SH250_RR.md] [--runs 5] [--pack <pack dir>] [--loop 300]

At least one of --roots / --hpc is required.

The page: a headline strip (snapshot age, jobs by state, cores in use, pairings done / expected, games, rate,
ETA), the Scoreboard (Champions Round + Top-5 Round; right after the headline once it has data, otherwise a
"not yet" placeholder after the model table), then ONE primary table with a row per model sorted by state
(failed, running, pending, done, in the Qualification Round, not submitted): model | Qualification Round (laptop
or cluster job, passed count) | job (id, state, node, cores, elapsed / limit, time left) | run 1 .. run 5
(eligible bots, pairings done / expected as a mini bar, the run winner tNN, a check mark when VERIFIED, a cross
when FAILED) | progress (pairings across the runs) | run winners. Below it the Qualification Round jobs table, the
pack job's one-line status and, only when `sh250-a` array tasks exist, the per-task table.

Each root is one host's Top Bot per Run Round output (`<out>` of pool_rr.py / run_pool_rr.sh); its basename is
the host name. Under `<root>/<model>/` a grouped run (`pool_rr.py --runs 5`) has `g0..g4/` each
with `pool_ledger.json` (written before the first game: eligible count, n_rollouts, slot range),
`matches/<a>_vs_<b>/match_result.json` (one per finished pairing — written when all seeds are in),
and on completion `elo.json` + `top_1.json`; the model dir gets `runs.json` + `top_5_bots.json`
when every run is done. An ungrouped run has the same files directly in `<root>/<model>/` and is
shown as a single run named `all`. `VERIFIED` / `FAILED` marker files (per model, and per group
when the driver writes them) are the verifier's verdict. The finals live under `<root>/stage_b/`:
`top5/<model>/elo.json` (the Top-5 Round) and `top1/elo.json` (the Champions Round, the cross-model leaderboard).

Numbers: expected pairings of a run = C(eligible, 2); games = pairings x n_rollouts (a pairing's
match_result.json exists only once all its seeds finished, so no per-file parse is needed). Runs
that have not started have no ledger yet: they are shown as `queued` with `?` bots, and the headline
estimates their pairings at the mean C(E,2) of the runs that have started (marked "est."). The rate
is the number of match_result.json files modified in the last 30 min (rsync -a keeps mtimes), and
ETA = remaining pairings / rate. A model that appears under two roots is taken from the root with
more finished pairings and the duplicate is flagged.

`--pack <dir>` is the laptop-qualified pack (pack_pool.py): its model dirs are rows even before any output
exists, and its `MANIFEST.json` gives each model's eligible (= passed) count for the Qualification Round cell.

HPC (SLURM cluster): `--hpc <dir>` is the laptop-side mirror that a loop rewrites every
few minutes (only live attempts reach it; cancelled or superseded jobs are filtered out upstream).
`<dir>/slurm.json` is the squeue/sacct snapshot ({generated_at, user, jobs[], plan}):
- `sh250-model` jobs, one per model (its five runs back to back); `plan.model[]` = [{job_id, model}].
- `sh250-qual` node jobs (the Qualification Round for models shipped as a generation root);
  `plan.qual[]` = [{job_id, models}] lists what each one replays.
- `sh250-pack`, the dependency job that packs the cluster-qualified models and submits their model jobs.
- `sh250-a` array tasks (the older one-task-per-run mode, kept working); `plan.stage_a[]` = [{index, model, run}].
`<dir>/rr/` is an rsync mirror of the Top Bot per Run Round output root on HPC (the per-host layout above;
shown as the host `hpc`; `<dir>/rr/SHIPPED_SHA` is the harness commit the jobs run). `<dir>/qual/STATUS-qual-*.md`
are the pool runner's status files, one per Qualification Round job, each listing only its own models (a model in
several files is taken from the newest by mtime); `<dir>/qual/progress.jsonl` is its per-sample log.
`<dir>/logs/stage_a_<A>_<a>.out` are the array-task logs: the last line of every finished/failed task's log is
shown. A task is a "problem" when its state is FAILED/TIMEOUT/CANCELLED/NODE_FAIL/OUT_OF_MEMORY, when it
COMPLETED but its run has no VERIFIED marker in the mirror, or when its index is not in the plan.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO = Path(__file__).resolve().parents[2]
WINDOW_MIN = 30                 # the rate window (minutes) for match_result.json mtimes
DEFAULT_RUNS = 5
REFRESH_S = 300
PACK_SKIP = {"MANIFEST.json", "sampling_prompt.md"}
STATUS_ORDER = {"FAILED": 0, "running": 1, "queued": 2, "done": 3, "VERIFIED": 4}
HPC_HOST = "hpc"
STAGE_A_JOB_NAME = "sh250-a"
QUAL_JOB_NAME = "sh250-qual"
PACK_JOB_NAME = "sh250-pack"    # packs the cluster-qualified models and submits their model jobs
MODEL_JOB_NAME = "sh250-model"  # one job per model: its five runs back to back
STALE_S = 15 * 60               # slurm.json older than this is flagged stale
PROBLEM_STATES = {"FAILED", "TIMEOUT", "CANCELLED", "NODE_FAIL", "OUT_OF_MEMORY"}
STATE_BUCKET = {"PENDING": "pending", "RUNNING": "running", "COMPLETED": "done", "FAILED": "failed", "TIMEOUT": "timeout"}
STATE_BUCKETS = ("pending", "running", "done", "failed", "timeout", "other")
LIVE_RANK = {"RUNNING": 0, "PENDING": 1}    # which attempt of a resubmitted task the "where" column shows
LOG_TAIL_BYTES = 4096
ROW_STATES = ("failed", "running", "pending", "done", "qualifying", "waiting")   # primary-table order
ROW_ORDER = {st: i for i, st in enumerate(ROW_STATES)}
ROW_LABEL = {"failed": "failed", "running": "running", "pending": "pending", "done": "done",
             "qualifying": "Qualification Round", "waiting": "not submitted"}
JOB_RANK = {"RUNNING": 0, "PENDING": 1}     # the live attempt of a resubmitted model job
HPC_WHAT = ("Qualification Round = every sample's robot is built from the model's output and plays 3 x 20 s rounds vs the "
                 "stationary block; the pool entry rule is no round lost or wins > losses. Top Bot per Run Round = the model's "
                 "250 samples are 5 runs of 50; inside each run every eligible bot plays every other bot at 5 seeds, 300 s, "
                 "on HPC as one SLURM job per model (its five runs back to back). Bradley-Terry picks the run winner; the 5 winners play the stored "
                 "11-seed round robin (Top-5 Round) and the 24 model winners play each other (Champions Round) - the scoreboard.")

e = html.escape


# ── scanning ──────────────────────────────────────────────────────────────────

def _read_json(path: Path) -> Any:
    return json.loads(path.read_text())


def scan_matches(matches_dir: Path) -> List[float]:
    """mtimes of every `<pair>/match_result.json` under `matches_dir` (one per finished pairing)."""
    if not matches_dir.is_dir():
        return []
    mtimes: List[float] = []
    with os.scandir(matches_dir) as it:
        for entry in it:
            if not entry.is_dir(follow_symlinks=False):
                continue
            try:
                mtimes.append(os.stat(os.path.join(entry.path, "match_result.json")).st_mtime)
            except FileNotFoundError:
                continue
    return mtimes


def _marker(d: Path) -> Optional[str]:
    if (d / "FAILED").is_file():
        return "FAILED"
    if (d / "VERIFIED").is_file():
        return "VERIFIED"
    return None


def scan_group(gdir: Path, name: str) -> Dict[str, Any]:
    """One run of a model: `<model>/g<k>/` or the model dir itself (ungrouped, name `all`)."""
    ledger_path = gdir / "pool_ledger.json"
    group: Dict[str, Any] = {"name": name, "eligible": None, "expected": None, "done": 0, "n_rollouts": None,
                             "slot_range": None, "mtimes": [], "winner": None, "winner_elo": None,
                             "ties_at_top": [], "status": "queued", "marker": None}
    if not ledger_path.is_file():
        return group
    ledger = _read_json(ledger_path)
    eligible = int(ledger["eligible"])
    group.update(eligible=eligible, expected=eligible * (eligible - 1) // 2, n_rollouts=int(ledger["n_rollouts"]))
    if "slot_range" in ledger:
        group["slot_range"] = [int(x) for x in ledger["slot_range"]]
    group["mtimes"] = scan_matches(gdir / "matches")
    group["done"] = len(group["mtimes"])
    top1_path = gdir / "top_1.json"
    if top1_path.is_file():
        top1 = _read_json(top1_path)
        group["winner"], group["winner_elo"] = top1["artifact_id"], float(top1["elo"])
        group["ties_at_top"] = list(top1["ties_at_top"])
    group["marker"] = _marker(gdir)
    if group["marker"]:
        group["status"] = group["marker"]
    elif group["done"] >= group["expected"] and (gdir / "elo.json").is_file():
        group["status"] = "done"
    else:
        group["status"] = "running"
    return group


def scan_model(mdir: Path, host: str, runs: int) -> Dict[str, Any]:
    if (mdir / "pool_ledger.json").is_file():
        groups = [scan_group(mdir, "all")]
    else:
        present = sorted(int(d.name[1:]) for d in mdir.iterdir() if d.is_dir() and d.name[:1] == "g" and d.name[1:].isdigit())
        if (mdir / "runs.json").is_file():           # a finished grouped run states its own run count
            n = int(_read_json(mdir / "runs.json")["runs"])
        else:
            n = max([runs] + [k + 1 for k in present]) if present else runs
        groups = [scan_group(mdir / f"g{k}", f"g{k}") for k in range(n)]
    known = [g for g in groups if g["expected"] is not None]
    model: Dict[str, Any] = {
        "model": mdir.name, "host": host, "groups": groups,
        "done": sum(g["done"] for g in known),
        "expected": sum(g["expected"] for g in known),
        "games": sum(g["done"] * g["n_rollouts"] for g in known),
        "winners": [g["winner"] for g in groups if g["winner"]],
        "top5_written": (mdir / "top_5_bots.json").is_file(),
        "marker": _marker(mdir),
        "last_mtime": max((m for g in known for m in g["mtimes"]), default=None),
        "log": (mdir.parent / f"{mdir.name}.log").is_file(),
    }
    statuses = [g["status"] for g in groups]
    if model["marker"] == "FAILED" or "FAILED" in statuses:
        model["status"] = "FAILED"
    elif model["marker"] == "VERIFIED" or all(s == "VERIFIED" for s in statuses):
        model["status"] = "VERIFIED"
    elif all(s in ("done", "VERIFIED") for s in statuses) and (model["top5_written"] or len(groups) == 1):
        model["status"] = "done"
    elif not known:
        model["status"] = "queued"
    else:
        model["status"] = "running"
    return model


def _elo_rows(elo_path: Path) -> List[List[Any]]:
    """[(artifact_id, standing)] of an elo.json, rating descending then id."""
    st = _read_json(elo_path)["standings"]
    return sorted(st.items(), key=lambda kv: (-float(kv[1]["elo"]), kv[0]))


def scan_stage_b(root: Path) -> Dict[str, Any]:
    sb = root / "stage_b"
    out: Dict[str, Any] = {"top5": {}, "top1": [], "top1_host": None, "top1_games": 0, "top1_pending": None,
                           "top5_pending": {}}
    if not sb.is_dir():
        return out
    top5 = sb / "top5"
    if top5.is_dir():
        for md in sorted(d for d in top5.iterdir() if d.is_dir()):
            if (md / "elo.json").is_file():
                out["top5"][md.name] = {"host": root.name, "rows": _elo_rows(md / "elo.json"),
                                        "ties_at_top": list(_read_json(md / "elo.json")["ties_at_top"])}
            else:
                out["top5_pending"][md.name] = len(scan_matches(md / "matches"))
    top1 = sb / "top1"
    if (top1 / "elo.json").is_file():
        payload = _read_json(top1 / "elo.json")
        out["top1"] = _elo_rows(top1 / "elo.json")
        out["top1_host"] = root.name
        out["top1_games"] = sum(int(s["games"]) for _, s in out["top1"]) // 2
        out["top1_ties_at_top"] = list(payload["ties_at_top"])
    elif top1.is_dir():
        out["top1_pending"] = len(scan_matches(top1 / "matches"))
    return out


def scan_root(root: Path, *, runs: int = DEFAULT_RUNS, host: Optional[str] = None) -> Dict[str, Any]:
    """One host mirror: every `<root>/<model>/` plus its Top-5 / Champions Round results (`stage_b/`). The host name defaults to the root's basename."""
    root = Path(root)
    host = host if host is not None else root.name
    models: Dict[str, Dict[str, Any]] = {}
    if root.is_dir():
        for d in sorted(root.iterdir()):
            if d.is_dir() and d.name not in ("stage_b", "_clean_artifacts") and not d.name.startswith("."):
                models[d.name] = scan_model(d, host, runs)
    return {"host": host, "root": str(root), "exists": root.is_dir(), "models": models, "stage_b": scan_stage_b(root)}


def placeholder_model(name: str) -> Dict[str, Any]:
    """A model with no Top Bot per Run Round output yet (known only from the pack or the SLURM plan)."""
    return {"model": name, "host": None, "groups": [], "done": 0, "expected": 0, "games": 0,
            "winners": [], "top5_written": False, "marker": None, "last_mtime": None,
            "log": False, "status": "queued"}


def merge_hosts(scans: List[Dict[str, Any]], pack_models: Optional[List[str]] = None, *,
                runs: int = DEFAULT_RUNS) -> Dict[str, Any]:
    """Models across hosts (a model appears under exactly one host; duplicates resolve to the root with more
    finished pairings and are flagged), `stage_b/` merged, pack-only models shown as queued."""
    models: Dict[str, Dict[str, Any]] = {}
    flags: List[str] = []
    for scan in scans:
        for name, m in scan["models"].items():
            if name not in models:
                models[name] = m
                continue
            keep, drop = (models[name], m) if models[name]["done"] >= m["done"] else (m, models[name])
            flags.append(f"{name}: also under {drop['host']} ({drop['done']} pairings) — "
                         f"using {keep['host']} ({keep['done']} pairings)")
            models[name] = keep
    for name in pack_models or []:
        if name not in models:
            models[name] = placeholder_model(name)
    stage_b: Dict[str, Any] = {"top5": {}, "top1": [], "top1_host": None, "top1_games": 0, "top1_pending": None,
                               "top5_pending": {}, "top1_ties_at_top": []}
    for scan in scans:
        sb = scan["stage_b"]
        for model, rows in sb["top5"].items():
            if model in stage_b["top5"]:
                flags.append(f"stage_b/top5/{model}: under both {stage_b['top5'][model]['host']} and {rows['host']} — "
                             f"using {stage_b['top5'][model]['host']}")
                continue
            stage_b["top5"][model] = rows
        stage_b["top5_pending"].update(sb["top5_pending"])
        if sb["top1"]:
            if stage_b["top1"] and stage_b["top1_games"] >= sb["top1_games"]:
                flags.append(f"stage_b/top1: under both {stage_b['top1_host']} and {sb['top1_host']} — "
                             f"using {stage_b['top1_host']}")
                continue
            stage_b.update(top1=sb["top1"], top1_host=sb["top1_host"], top1_games=sb["top1_games"],
                           top1_ties_at_top=sb["top1_ties_at_top"])
        elif sb["top1_pending"] is not None:
            stage_b["top1_pending"] = sb["top1_pending"]
    hosts = sorted({s["host"] for s in scans})
    missing = [s["root"] for s in scans if not s["exists"]]
    return {"models": dict(sorted(models.items())), "stage_b": stage_b, "flags": flags, "hosts": hosts,
            "roots": [s["root"] for s in scans], "missing_roots": missing, "hpc": None, "pack": None,
            "runs": runs}


# ── HPC (SLURM mirror) ───────────────────────────────────────────────────

def slurm_seconds(s: str) -> Optional[int]:
    """SLURM elapsed / time-limit text (`MM:SS`, `HH:MM:SS`, `D-HH:MM:SS`) in seconds; None when not a duration."""
    s = (s or "").strip()
    if not s:
        return None
    days = 0
    if "-" in s:
        d, s = s.split("-", 1)
        if not d.isdigit():
            return None
        days = int(d)
    parts = s.split(":")
    if not all(x.isdigit() for x in parts) or not 1 <= len(parts) <= 3:
        return None
    nums = [int(x) for x in parts]
    while len(nums) < 3:
        nums.insert(0, 0)
    hh, mm, ss = nums
    return days * 86400 + hh * 3600 + mm * 60 + ss


def _iso_ts(s: str) -> Optional[float]:
    try:
        t = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=dt.timezone.utc)
    return t.timestamp()


def _log_tail(path: Path) -> Optional[str]:
    """Last non-empty line of a task log (reads only its final bytes)."""
    if not path.is_file():
        return None
    size = path.stat().st_size
    with open(path, "rb") as fh:
        fh.seek(max(0, size - LOG_TAIL_BYTES))
        chunk = fh.read().decode("utf-8", errors="replace")
    lines = [ln.strip() for ln in chunk.splitlines() if ln.strip()]
    return lines[-1] if lines else None


def _parse_status_md(path: Path) -> Dict[str, Any]:
    """One `STATUS-qual-*.md` of the pool runner: its `- updated:` line and the per-model table
    | model | generated | failed | qualified OK | forfeit | awaiting qual | qual err | remaining | ..."""
    rows: Dict[str, Dict[str, int]] = {}
    updated: Optional[str] = None
    for line in path.read_text().splitlines():
        if line.startswith("- updated:"):
            updated = line.split(":", 1)[1].strip()
            continue
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 8 or cells[0] == "model" or set(cells[0]) <= {"-", ":"}:
            continue
        gen, target = cells[1].split("/", 1)
        rows[cells[0]] = {"generated": int(gen), "target": int(target), "gen_failed": int(cells[2]),
                          "passed": int(cells[3]), "forfeit": int(cells[4]), "awaiting": int(cells[5]),
                          "qual_error": int(cells[6]), "remaining": int(cells[7])}
    return {"rows": rows, "updated": updated}


QUAL_KEYS = ("generated", "target", "gen_failed", "passed", "forfeit", "awaiting", "qual_error", "remaining")


def scan_qual_round(qual_dir: Path) -> Optional[Dict[str, Any]]:
    """Per-model Qualification Round counts (passed / forfeit / awaiting / ...) merged from EVERY `STATUS-qual-*.md`
    in the mirror: each cluster job writes its own file listing only its models, so the files are read oldest
    first and a model that appears in several is taken from the newest (by mtime). `file` / `updated` / `mtime`
    describe the newest file, `source` says which file each model's row came from; plus the record count of
    `progress.jsonl` when present. None when there is no status file."""
    qual_dir = Path(qual_dir)
    if not qual_dir.is_dir():
        return None
    mds = sorted(qual_dir.glob("STATUS-qual-*.md"), key=lambda p: (p.stat().st_mtime, p.name))
    if not mds:
        return None
    rows: Dict[str, Dict[str, int]] = {}
    source: Dict[str, str] = {}
    updated: Optional[str] = None
    for md in mds:
        parsed = _parse_status_md(md)
        for model, r in parsed["rows"].items():
            rows[model] = r
            source[model] = md.name
        updated = parsed["updated"]
    newest = mds[-1]
    totals = {k: sum(r[k] for r in rows.values()) for k in QUAL_KEYS}
    progress = qual_dir / "progress.jsonl"
    n_progress = sum(1 for ln in progress.read_text().splitlines() if ln.strip()) if progress.is_file() else None
    return {"file": newest.name, "files": [m.name for m in mds], "mtime": newest.stat().st_mtime, "updated": updated,
            "rows": rows, "source": source, "totals": totals, "progress_records": n_progress}


def _empty_hpc(d: Path) -> Dict[str, Any]:
    return {"dir": str(d), "exists": d.is_dir(), "slurm": None, "tasks": [], "problems": [],
            "by_state": {b: 0 for b in STATE_BUCKETS}, "cores_running": 0, "qual_round_jobs": [], "pack_jobs": [],
            "model_jobs": [], "model_job_of": {}, "qual_job_of": {}, "where": {},
            "shipped_sha": None, "qual_round": None, "flags": [], "rr_scan": None}


def scan_hpc(d: Path, *, now: float, runs: int = DEFAULT_RUNS) -> Dict[str, Any]:
    """The HPC mirror dir: slurm.json (model jobs, Qualification Round jobs, the pack job, and array tasks joined
    with the plan and with the rr mirror's per-run progress), the rr mirror itself (`rr_scan`, host `hpc`),
    SHIPPED_SHA and the Qualification Round status files. `model_job_of` / `qual_job_of` map a model to its live
    job (RUNNING before PENDING before the newest finished attempt); `cores_running` sums the cpus of every
    RUNNING model job, Qualification Round job and array task."""
    d = Path(d)
    hpc_state = _empty_hpc(d)
    if not d.is_dir():
        return hpc_state
    rr = d / "rr"
    hpc_state["rr_scan"] = scan_root(rr, runs=runs, host=HPC_HOST)
    sha_path = rr / "SHIPPED_SHA"
    hpc_state["shipped_sha"] = sha_path.read_text().strip() if sha_path.is_file() else None
    hpc_state["qual_round"] = scan_qual_round(d / "qual")
    slurm_path = d / "slurm.json"
    if not slurm_path.is_file():
        hpc_state["flags"].append(f"no slurm.json under {d}")
        return hpc_state
    payload = _read_json(slurm_path)
    gen_ts = _iso_ts(str(payload["generated_at"]))
    age = None if gen_ts is None else max(0.0, now - gen_ts)
    hpc_state["slurm"] = {"generated_at": payload["generated_at"], "generated_ts": gen_ts, "age_s": age,
                    "stale": age is None or age > STALE_S, "user": payload["user"]}
    plan = payload["plan"]
    by_index = {int(p["index"]): (str(p["model"]), int(p["run"])) for p in plan["stage_a"]}
    qual_models = {str(q["job_id"]): [str(m) for m in q["models"]] for q in (plan["qual"] if "qual" in plan else [])}
    model_of_job = {str(j["job_id"]): str(j["model"]) for j in (plan["model"] if "model" in plan else [])}
    models = hpc_state["rr_scan"]["models"]
    tasks: List[Dict[str, Any]] = []
    for job in payload["jobs"]:
        state = str(job["state"]).upper()
        if job["name"] == QUAL_JOB_NAME:
            jid = str(job["job_id"])
            hpc_state["qual_round_jobs"].append({"job_id": jid, "state": state, "node": job["node"], "cpus": int(job["cpus"]),
                                     "elapsed": job["elapsed"], "time_limit": job["time_limit"], "reason": job["reason"],
                                     "models": qual_models[jid] if jid in qual_models else []})
            if state == "RUNNING":
                hpc_state["cores_running"] += int(job["cpus"])
            continue
        if job["name"] == MODEL_JOB_NAME:
            jid = str(job["job_id"])
            hpc_state["model_jobs"].append({"job_id": jid, "state": state, "node": job["node"], "cpus": int(job["cpus"]),
                                      "elapsed": job["elapsed"], "time_limit": job["time_limit"], "reason": job["reason"],
                                      "model": model_of_job[jid] if jid in model_of_job else None})
            if state == "RUNNING":
                hpc_state["cores_running"] += int(job["cpus"])
            continue
        if job["name"] == PACK_JOB_NAME:
            hpc_state["pack_jobs"].append({"job_id": str(job["job_id"]), "state": state, "node": job["node"],
                                     "elapsed": job["elapsed"], "reason": job["reason"]})
            continue
        if job["name"] != STAGE_A_JOB_NAME:
            hpc_state["flags"].append(f"job {job['job_id']} has an unknown name {job['name']!r} ({state})")
            continue
        if job["array_index"] is None:            # a collapsed pending range like 12345_[1-55]; its members are listed separately
            continue
        index = int(job["array_index"])
        t: Dict[str, Any] = {"job_id": str(job["job_id"]), "array_job": str(job["array_job"]), "index": index,
                             "model": None, "run": None, "group": None, "state": state, "partition": job["partition"],
                             "cpus": int(job["cpus"]), "node": job["node"], "elapsed": job["elapsed"],
                             "time_limit": job["time_limit"], "reason": job["reason"], "done": 0, "expected": None,
                             "marker": None, "problem": None, "log_tail": None}
        if index in by_index:
            t["model"], t["run"] = by_index[index]
            t["group"] = f"g{t['run']}"
            if t["model"] in models:
                for g in models[t["model"]]["groups"]:
                    if g["name"] == t["group"]:
                        t["done"], t["expected"], t["marker"] = g["done"], g["expected"], g["marker"]
        else:
            t["problem"] = f"index {index} not in plan"
        if t["problem"] is None:
            if state in PROBLEM_STATES:
                t["problem"] = state
            elif t["marker"] == "FAILED":
                t["problem"] = f"{state} with FAILED marker"
            elif state == "COMPLETED" and t["marker"] != "VERIFIED":
                t["problem"] = "COMPLETED without VERIFIED"
        if state not in ("PENDING", "RUNNING"):
            t["log_tail"] = _log_tail(d / "logs" / f"stage_a_{t['array_job']}_{index}.out")
        bucket = STATE_BUCKET[state] if state in STATE_BUCKET else "other"
        hpc_state["by_state"][bucket] += 1
        if state == "RUNNING":
            hpc_state["cores_running"] += t["cpus"]
        tasks.append(t)

    def _order(t: Dict[str, Any]):
        return (t["index"], int(t["array_job"]) if t["array_job"].isdigit() else -1, t["job_id"])
    tasks.sort(key=_order)
    hpc_state["tasks"] = tasks
    hpc_state["problems"] = sorted({t["index"] for t in tasks if t["problem"]})
    where: Dict[str, Dict[str, Any]] = {}
    for t in tasks:
        if t["model"] is None:
            continue
        slot = where.setdefault(t["model"], {})
        prev = slot[t["group"]] if t["group"] in slot else None
        rank = (LIVE_RANK[t["state"]] if t["state"] in LIVE_RANK else 2, -_order(t)[1])
        if prev is None or rank < prev[0]:
            slot[t["group"]] = (rank, t["state"])
    hpc_state["where"] = {m: {g: st for g, (_, st) in sorted(v.items())} for m, v in sorted(where.items())}
    hpc_state["qual_round_jobs"].sort(key=lambda q: q["job_id"])
    hpc_state["model_jobs"].sort(key=lambda j: (j["model"] or "", _job_rank(j)))
    for j in hpc_state["model_jobs"]:
        if j["model"] is None:
            hpc_state["flags"].append(f"model job {j['job_id']} is not in plan.model ({j['state']})")
        elif j["model"] not in hpc_state["model_job_of"]:      # sorted: the live attempt comes first
            hpc_state["model_job_of"][j["model"]] = j
    for q in hpc_state["qual_round_jobs"]:
        for m in q["models"]:
            if m not in hpc_state["qual_job_of"] or _job_rank(q) < _job_rank(hpc_state["qual_job_of"][m]):
                hpc_state["qual_job_of"][m] = q
    return hpc_state


def _job_rank(j: Dict[str, Any]):
    """RUNNING, then PENDING, then finished attempts newest first."""
    jid = j["job_id"]
    return (JOB_RANK[j["state"]] if j["state"] in JOB_RANK else 2, -int(jid) if jid.isdigit() else 0)


# ── headline ──────────────────────────────────────────────────────────────────

def headline(models: Dict[str, Dict[str, Any]], *, now: float, window_min: int = WINDOW_MIN) -> Dict[str, Any]:
    """Totals across every model: pairings, games, unstarted-run estimate, rate over the mtime window, ETA
    (hours; 0 = nothing left, None = no progress inside the window)."""
    groups = [g for m in models.values() for g in m["groups"]]
    known = [g for g in groups if g["expected"] is not None]
    unstarted = [g for g in groups if g["expected"] is None]
    expected_known = sum(g["expected"] for g in known)
    done = sum(g["done"] for g in known)
    mean_expected = expected_known / len(known) if known else 0.0
    expected_est = mean_expected * len(unstarted)
    cutoff = now - window_min * 60
    recent = sum(1 for g in known for t in g["mtimes"] if cutoff <= t <= now)
    rate = recent / (window_min / 60.0)
    remaining = expected_known - done + expected_est
    if remaining <= 0:
        eta_h: Optional[float] = 0.0
    elif rate > 0:
        eta_h = remaining / rate
    else:
        eta_h = None
    last = max((t for g in known for t in g["mtimes"]), default=None)
    return {
        "pairings_done": done, "expected_known": expected_known, "expected_est": expected_est,
        "expected_total": expected_known + expected_est, "n_unstarted": len(unstarted), "n_runs": len(groups),
        "games_done": sum(m["games"] for m in models.values()), "recent_pairings": recent, "rate_per_h": rate,
        "eta_h": eta_h, "remaining": remaining, "last_mtime": last, "window_min": window_min,
        "hosts": sorted({m["host"] for m in models.values() if m["host"]}),
        "n_models": len(models),
        "by_status": {s: sum(1 for m in models.values() if m["status"] == s) for s in STATUS_ORDER},
    }


# ── formatting helpers ────────────────────────────────────────────────────────

def short_aid(aid: Optional[str]) -> str:
    """`<model>__t07_c000` -> `t07`."""
    if not aid:
        return "-"
    tail = aid.rsplit("__", 1)[-1]
    return tail.split("_c", 1)[0] if "_c" in tail else tail


def fmt_eta(eta_h: Optional[float]) -> str:
    if eta_h is None:
        return "no progress in the window"
    if eta_h == 0:
        return "done"
    if eta_h < 1:
        return f"{eta_h * 60:.0f} min"
    if eta_h < 48:
        return f"{eta_h:.1f} h"
    return f"{eta_h / 24:.1f} d"


def fmt_age(ts: Optional[float], now: float) -> str:
    if ts is None:
        return "-"
    s = max(0.0, now - ts)
    if s < 90:
        return f"{s:.0f} s ago"
    if s < 5400:
        return f"{s / 60:.0f} min ago"
    if s < 2 * 86400:
        return f"{s / 3600:.1f} h ago"
    return f"{s / 86400:.1f} d ago"


def _local(ts: float) -> str:
    return dt.datetime.fromtimestamp(ts).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


def _utc(ts: float) -> str:
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).isoformat(timespec="seconds")


def wld(st: Dict[str, Any]) -> str:
    return f"{int(st['wins'])}-{int(st['losses'])}-{int(st['draws'])}"


# ── primary table view ────────────────────────────────────────────────────────

def _live_state_of(name: str, hpc_state: Optional[Dict[str, Any]]) -> Optional[str]:
    """The SLURM state that stands for the model's Top Bot per Run Round: its model job, or (array mode) the
    most alive of its tasks (RUNNING > PENDING > a problem > COMPLETED)."""
    if hpc_state is None:
        return None
    if name in hpc_state["model_job_of"]:
        return hpc_state["model_job_of"][name]["state"]
    if name in hpc_state["where"]:
        states = list(hpc_state["where"][name].values())
        for st in ("RUNNING", "PENDING"):
            if st in states:
                return st
        for st in states:
            if st in PROBLEM_STATES:
                return st
        return "COMPLETED"
    return None


def qual_status_file(job_id: str) -> str:
    """The pool runner's status file of a Qualification Round job (hpc_qualify.sh: STATUS-qual-$SLURM_JOB_ID.md)."""
    return f"STATUS-qual-{job_id}.md"


def live_qual(hpc_state: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """The Qualification Round status restricted to LIVE jobs: with jobs in the snapshot only rows read from a live
    job's own status file count (a superseded job's file stays in the mirror and would otherwise attach its
    counts to the resubmitted job's models); without any job in the snapshot every file counts.
    {rows, files, older (ignored files), totals} — rows / files empty when there is no status at all."""
    out: Dict[str, Any] = {"rows": {}, "files": [], "older": 0, "totals": {k: 0 for k in QUAL_KEYS}}
    q = hpc_state["qual_round"] if hpc_state is not None else None
    if q is None:
        return out
    if hpc_state["qual_round_jobs"]:
        live_files = {qual_status_file(j["job_id"]) for j in hpc_state["qual_round_jobs"]}
        out["rows"] = {m: r for m, r in q["rows"].items() if q["source"][m] in live_files}
        out["files"] = [f for f in q["files"] if f in live_files]
        out["older"] = len(q["files"]) - len(out["files"])
    else:
        out["rows"], out["files"] = dict(q["rows"]), list(q["files"])
    out["totals"] = {k: sum(r[k] for r in out["rows"].values()) for k in QUAL_KEYS}
    return out


def model_rows(merged: Dict[str, Any]) -> List[Dict[str, Any]]:
    """One row per model for the primary table, sorted by ROW_STATES (failed, running, pending, done, in the
    Qualification Round, not submitted) then name. Qualification counts come from the pack manifest (laptop) or the
    live job's status file (cluster, see live_qual), else from the run ledgers once every run has one. Each row: model, state, label, qual {where: laptop|cluster|None,
    job, passed, awaiting, forfeit, errors}, job (the live model job or None), live (its SLURM state), problem, runs
    (the groups plus `task_state` in array mode), done/expected/unknown_runs/games, winners, host, last_mtime."""
    hpc_state = merged["hpc"]
    pack = merged["pack"]
    qual_rows = live_qual(hpc_state)["rows"]
    rows: List[Dict[str, Any]] = []
    for name, m in merged["models"].items():
        job = hpc_state["model_job_of"][name] if hpc_state is not None and name in hpc_state["model_job_of"] else None
        qjob = hpc_state["qual_job_of"][name] if hpc_state is not None and name in hpc_state["qual_job_of"] else None
        q: Dict[str, Any] = {"where": None, "job": qjob, "passed": None, "awaiting": None, "forfeit": None, "errors": None}
        if pack is not None and name in pack["models"]:
            q["where"] = "laptop"
            if name in pack["eligible"]:
                q["passed"] = pack["eligible"][name]
        elif qjob is not None:
            q["where"] = "cluster"
        if name in qual_rows:
            r = qual_rows[name]
            q["passed"], q["awaiting"], q["forfeit"], q["errors"] = r["passed"], r["awaiting"], r["forfeit"], r["qual_error"]
            if q["where"] is None:
                q["where"] = "cluster"
        if q["passed"] is None and m["groups"] and all(g["eligible"] is not None for g in m["groups"]):
            q["passed"] = sum(g["eligible"] for g in m["groups"])
        live = _live_state_of(name, hpc_state)
        problem: Optional[str] = None
        if job is None and hpc_state is not None and name in hpc_state["where"]:        # array mode: the live tasks' problems
            live_tasks = [t for t in hpc_state["tasks"] if t["model"] == name and t["problem"]
                          and t["state"] == hpc_state["where"][name][t["group"]]]
            problem = "; ".join(f"{t['group']}: {t['problem']}" for t in live_tasks) or None
        elif live in PROBLEM_STATES:
            problem = live
        elif live == "COMPLETED" and m["status"] not in ("VERIFIED", "done"):
            problem = "COMPLETED without VERIFIED"
        if m["status"] == "FAILED" or live in PROBLEM_STATES:
            state = "failed"
        elif live == "RUNNING" or m["status"] == "running":
            state = "running"
        elif live == "PENDING":
            state = "pending"
        elif m["status"] in ("VERIFIED", "done") or live == "COMPLETED":
            state = "done"
        elif qjob is not None:
            state = "qualifying"
        else:
            state = "waiting"
        where = hpc_state["where"][name] if hpc_state is not None and name in hpc_state["where"] else {}
        runs = [dict(g, task_state=where[g["name"]] if g["name"] in where else None) for g in m["groups"]]
        label = ROW_LABEL[state]
        if state == "qualifying":
            label += f" {qjob['state']}"
        rows.append({"model": name, "state": state, "label": label, "qual": q, "job": job, "live": live,
                     "problem": problem, "runs": runs, "done": m["done"], "expected": m["expected"],
                     "unknown_runs": sum(1 for g in m["groups"] if g["expected"] is None), "games": m["games"],
                     "winners": m["winners"], "host": m["host"], "status": m["status"],
                     "last_mtime": m["last_mtime"]})
    qual_rank = {"RUNNING": 0, "PENDING": 1}
    rows.sort(key=lambda r: (ROW_ORDER[r["state"]],
                             (qual_rank[r["qual"]["job"]["state"]] if r["qual"]["job"] is not None
                              and r["qual"]["job"]["state"] in qual_rank else 2) if r["state"] == "qualifying" else 0,
                             r["model"]))
    return rows


def run_columns(merged: Dict[str, Any]) -> int:
    """How many run columns the primary table shows: the widest model, or --runs when no model has output yet."""
    widths = [len(m["groups"]) for m in merged["models"].values() if m["groups"]]
    return max(widths) if widths else merged["runs"]


def count_states(jobs: List[Dict[str, Any]]) -> Dict[str, int]:
    """SLURM jobs by bucket (pending / running / done / failed / timeout / other)."""
    out = {b: 0 for b in STATE_BUCKETS}
    for j in jobs:
        out[STATE_BUCKET[j["state"]] if j["state"] in STATE_BUCKET else "other"] += 1
    return out


# ── HTML ──────────────────────────────────────────────────────────────────────

_CSS = """
:root{color-scheme:light}
body{margin:0;padding:16px 18px 48px;background:#f7f7f5;color:#1f2328;font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif}
main{max-width:none;margin:0 auto}
h1{font-size:22px;margin:0 0 6px;font-weight:650}
h2{font-size:16px;margin:28px 0 10px;font-weight:650;border-bottom:1px solid #d9d9d4;padding-bottom:6px}
h3{font-size:14px;margin:18px 0 6px;font-weight:650}
.topbar{position:sticky;top:0;z-index:5;display:flex;align-items:center;gap:16px;flex-wrap:wrap;background:#f7f7f5;padding:10px 0;margin:0 0 12px;border-bottom:1px solid #d9d9d4}
.btn{display:inline-block;padding:9px 22px;background:#2f6fd6;color:#fff;font-weight:650;font-size:15px;border-radius:6px;text-decoration:none;box-shadow:0 1px 2px rgba(0,0,0,.15)}
.btn:hover{background:#245cb5}
.topbar .upd{font-size:14px}
.topbar .hint{color:#57606a;font-size:12.5px}
.meta{color:#57606a;font-size:13px;margin:0 0 4px}
code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px;background:#ececea;padding:1px 5px;border-radius:3px}
.strip{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0 4px}
.stat{flex:1 1 0;background:#fff;border:1px solid #d9d9d4;border-radius:6px;padding:8px 10px;min-width:0}
.stat .k{display:block;color:#57606a;font-size:10.5px;text-transform:uppercase;letter-spacing:.03em;line-height:1.2}
.stat .v{display:block;font-size:15px;font-weight:650;font-variant-numeric:tabular-nums;line-height:1.25}
.stat .s{display:block;color:#57606a;font-size:11.5px;line-height:1.3}
.wrap{overflow-x:auto}
table{border-collapse:collapse;width:100%;table-layout:auto;background:#fff;border:1px solid #d9d9d4;font-size:12.5px}
th,td{padding:4px 6px;border-bottom:1px solid #e6e6e2;text-align:left;white-space:nowrap;vertical-align:top}
th{white-space:normal;font-size:11.5px;line-height:1.2;vertical-align:bottom;background:#f0f0ed;font-weight:600;color:#3b4148}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
td.w{white-space:normal}
td.note{white-space:normal;color:#57606a;font-size:12px;min-width:160px}
tr:last-child td{border-bottom:none}
tr.total td{font-weight:650;background:#fafaf8;border-top:2px solid #c9c9c3}
tr.failed td{background:#fff5f5}
tr.waiting td,tr.qualifying td{color:#6b7076}
table.primary td.model{font-weight:650;white-space:normal;overflow-wrap:anywhere;min-width:120px;max-width:190px}
table.primary td.run{white-space:normal;min-width:78px;font-size:12px;line-height:1.3;font-variant-numeric:tabular-nums}
table.primary td.run .nums{white-space:nowrap}
table.primary td.run.queued{color:#8b8f95}
table.primary td.run .w{font-weight:650}
table.primary td.run .st{font-size:10.5px;color:#57606a}
.tag{display:inline-block;font-size:11px;padding:0 6px;border-radius:3px;font-weight:600;white-space:nowrap}
.tag.VERIFIED,.tag.done,.tag.COMPLETED{background:#e2f2e6;color:#1d6b3a}
.tag.running,.tag.RUNNING{background:#e6eefb;color:#245cb5}
.tag.queued,.tag.pending,.tag.PENDING,.tag.waiting{background:#ececea;color:#57606a}
.tag.qualifying{background:#f1ecfa;color:#5b3f8f}
.tag.FAILED,.tag.failed,.tag.TIMEOUT,.tag.CANCELLED,.tag.NODE_FAIL,.tag.OUT_OF_MEMORY{background:#fbe3e3;color:#9b2c2c}
.red{color:#9b2c2c;font-weight:650}
.ok{color:#1d6b3a;font-weight:650}
.dim{color:#8b8f95}
.foot{color:#57606a;font-size:12.5px;margin-top:10px;max-width:1100px}
.bar{position:relative;background:#e6e6e2;border-radius:4px;overflow:hidden;box-sizing:border-box}
.bar>i{display:block;height:100%;background:#2f6fd6}
.bar>b{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-weight:600;color:#1f2328;white-space:nowrap}
.bar.big{height:30px;margin-top:12px}
.bar.big>b{font-size:14px}
.bar.cell{width:150px;height:15px;display:inline-block;vertical-align:middle}
.bar.cell>b{font-size:11px}
.bar.mini{height:6px;width:70px;margin:2px 0 1px;display:block}
.bar.g>i{background:#5cbf7a}
.bar.b>i{background:#7fa7e6}
.bar.r>i{background:#e07070}
.bar.i>i{background:#c9d6ea}
.legend{color:#57606a;font-size:12px;margin:6px 0 0}
.legend i{display:inline-block;width:11px;height:11px;border-radius:2px;vertical-align:-1px;margin:0 3px 0 10px}
.cols{display:flex;gap:18px;flex-wrap:wrap;align-items:flex-start}
.cols>div{flex:1 1 420px;min-width:0}
.what{background:#fff;border:1px solid #d9d9d4;border-radius:6px;padding:14px 18px;margin-top:28px;font-size:13px;max-width:1100px}
.what h3{margin:0 0 8px}
.what ol{margin:0;padding-left:20px}
.what li{margin:3px 0}
.what p{margin:0 0 8px}
.where{display:inline-flex;gap:4px;flex-wrap:wrap}
.where span{display:inline-block;padding:0 5px;border-radius:3px;font-size:11px;font-weight:600;background:#ececea;color:#57606a}
.where .RUNNING{background:#e6eefb;color:#245cb5}
.where .COMPLETED{background:#e2f2e6;color:#1d6b3a}
.where .FAILED,.where .TIMEOUT,.where .CANCELLED,.where .NODE_FAIL,.where .OUT_OF_MEMORY{background:#fbe3e3;color:#9b2c2c}
.bar.seg{display:flex}
.bar.seg>i{display:block;height:100%;width:auto}
.bar.seg>i.running{background:#7fa7e6}
.bar.seg>i.done{background:#5cbf7a}
.bar.seg>i.pending{background:#c9c9c3}
.bar.seg>i.failed,.bar.seg>i.timeout{background:#e07070}
.bar.seg>i.other{background:#b08ad6}
tr.problem td{background:#fff5f5}
td.tail{white-space:normal;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11px;color:#57606a;max-width:420px}
"""


def _bar(num: float, den: float, cls: str = "", label: Optional[str] = None) -> str:
    """A pure-CSS progress bar: filled <i> of width pct%, centred <b> label ('' = no label)."""
    pct = 100.0 * num / den if den else 0.0
    if label is None:
        label = f"{num:,.0f} / {den:,.0f} &middot; {pct:.1f}%"
    return f"<div class='bar {cls}'><i style='width:{min(100.0, pct):.1f}%'></i>{'<b>' + label + '</b>' if label else ''}</div>"


def _tag(status: str) -> str:
    return f"<span class='tag {e(status)}'>{e(status)}</span>"


def _seg_bar(counts: Dict[str, int], label: str) -> str:
    """One bar split into coloured segments (pending/running/done/failed/timeout/other)."""
    total = sum(counts.values())
    segs = "".join(f"<i class='{b}' style='width:{100.0 * counts[b] / total:.1f}%'></i>" for b in STATE_BUCKETS if total and counts[b])
    return f"<div class='bar big seg'>{segs}<b>{label}</b></div>"


def remaining_text(elapsed: str, limit: str) -> str:
    """Wall-clock left before SLURM kills the task: limit - elapsed as H:MM, or '-' when unknown."""
    used, lim = slurm_seconds(elapsed), slurm_seconds(limit)
    if used is None or lim is None:
        return "-"
    left = max(0, lim - used)
    return f"{left // 3600}:{(left % 3600) // 60:02d}"


def _elapsed_cell(t: Dict[str, Any]) -> str:
    txt = f"{t['elapsed']} / {t['time_limit']} (left {remaining_text(t['elapsed'], t['time_limit'])})"
    used, limit = slurm_seconds(t["elapsed"]), slurm_seconds(t["time_limit"])
    if t["state"] == "RUNNING" and used is not None and limit:
        return _bar(used, limit, "cell b", e(txt))
    return e(txt)


BAR_CLS = {"VERIFIED": "g", "done": "g", "running": "b", "FAILED": "r", "queued": "i"}


def _run_cell_html(g: Optional[Dict[str, Any]]) -> str:
    """One run of the primary table: eligible bots, pairings done / expected as a mini bar, the winner tNN,
    a check mark when VERIFIED, a cross when FAILED; a task-state tag in array mode."""
    if g is None:
        return "<td class='run queued'><span class=dim>-</span></td>"
    st = g["status"]
    if g["eligible"] is None:
        body = "<span class=dim>? bots</span>"
        if g["task_state"]:
            body += f"<br><span class=st>{e(g['task_state'])}</span>"
        return f"<td class='run queued' title='{e(g['name'])}: queued, no ledger yet'>{body}</td>"
    title = f"{g['name']}: {st}, {g['done']}/{g['expected']} pairings"
    if g["slot_range"]:
        title += f", slots {g['slot_range'][0]}-{g['slot_range'][1] - 1}"
    parts = [f"<span class=nums>{g['eligible']} bots &middot; {g['done']}/{g['expected']}</span>",
             _bar(g["done"], g["expected"], "mini " + BAR_CLS[st], "")]
    win = ""
    if g["winner"]:
        win = f"<span class=w title='{e(g['winner'])} elo {g['winner_elo']:.1f}'>{e(short_aid(g['winner']))}</span>"
        if len(g["ties_at_top"]) > 1:
            win += f" <span class=red title='tie at the top: {e(', '.join(g['ties_at_top']))}'>tie</span>"
    if st == "VERIFIED":
        win += " <span class=ok title='VERIFIED'>&#10003;</span>"
    elif st == "FAILED":
        win += " <span class=red title='FAILED'>&#10007;</span>"
    if win:
        parts.append(win.strip())
    if g["task_state"]:
        parts.append(f"<span class=st>{e(g['task_state'])}</span>")
    return f"<td class='run {e(st)}' title='{e(title)}'>{'<br>'.join(parts)}</td>"


def _qual_cell_html(r: Dict[str, Any]) -> str:
    q = r["qual"]
    counts = []
    if q["passed"] is not None:
        counts.append(f"<b>{q['passed']}</b> passed")
    if q["awaiting"]:
        counts.append(f"{q['awaiting']} awaiting")
    if q["errors"]:
        counts.append(f"<span class=red>{q['errors']} errors</span>")
    tail = (" &middot; " if q["where"] == "laptop" else "<br>") + " &middot; ".join(counts) if counts else ""
    if q["where"] == "laptop":
        return f"laptop{tail}"
    if q["job"] is not None:
        j = q["job"]
        return f"job {e(j['job_id'])} {_tag(j['state'])}{tail}"
    if q["where"] == "cluster":
        return f"cluster{tail}"
    return "<span class=dim>not submitted</span>"


def _cores(j: Dict[str, Any]) -> str:
    """`96 cores`, or `-` for a finished job that sacct reports without a cpu count."""
    return f"{j['cpus']} cores" if j["cpus"] else "-"


def _elapsed_text(j: Dict[str, Any]) -> str:
    """`elapsed / limit · left H:MM`; a finished job (no limit in the snapshot) shows its elapsed alone."""
    if not j["time_limit"]:
        return f"{j['elapsed']} elapsed"
    return f"{j['elapsed']} / {j['time_limit']} · left {remaining_text(j['elapsed'], j['time_limit'])}"


def _job_cell_html(r: Dict[str, Any], hpc_state: Optional[Dict[str, Any]]) -> str:
    j = r["job"]
    if j is not None:
        head = f"{e(j['job_id'])} {_tag(j['state'])}"
        if j["state"] == "PENDING":
            head += f" <span class=dim>{e(j['reason'])}</span>" if j["reason"] else ""
            return head + f"<br><span class=dim>{j['cpus']} cores &middot; limit {e(j['time_limit'])}</span>"
        line2 = f"{e(j['node'] or '-')} &middot; {_cores(j)}<br>{e(_elapsed_text(j))}"
        if r["problem"]:
            line2 += f"<br><span class=red>{e(r['problem'])}</span>"
        return head + "<br>" + line2
    if hpc_state is not None and r["model"] in hpc_state["where"]:
        cells = "".join(f"<span class='{e(st)}'>{e(g)} {e(st)}</span>" for g, st in hpc_state["where"][r["model"]].items())
        return f"array <span class=where>{cells}</span>" + (f"<br><span class=red>{e(r['problem'])}</span>" if r["problem"] else "")
    if r["host"]:
        return e(r["host"])
    if r["state"] == "qualifying" and hpc_state is not None and hpc_state["pack_jobs"]:
        p = hpc_state["pack_jobs"][0]
        return f"<span class=dim>after pack job {e(p['job_id'])}</span> {_tag(p['state'])}"
    return "<span class=dim>-</span>"


def _winners_html(r: Dict[str, Any]) -> str:
    parts = [f"<span title='{e(w)}'>{e(short_aid(w))}</span>" for w in r["winners"]]
    return " ".join(parts) if parts else "<span class=dim>-</span>"


def render_primary_table_html(merged: Dict[str, Any], *, now: float) -> str:
    rows = model_rows(merged)
    hpc_state = merged["hpc"]
    n_runs = run_columns(merged)
    head = headline(merged["models"], now=now)
    h: List[str] = ["<div class=wrap><table class=primary><tr><th>model</th><th>state</th><th>Qualification Round</th><th>job</th>"
                    + "".join(f"<th>run {k + 1}</th>" for k in range(n_runs))
                    + "<th>progress<br><span style='font-weight:400'>pairings done / expected</span></th><th>run winners</th></tr>"]
    for r in rows:
        runs = r["runs"] + [None] * (n_runs - len(r["runs"]))
        unknown = f" <span class=dim>+{r['unknown_runs']}?</span>" if r["unknown_runs"] else ""
        prog = (_bar(r["done"], r["expected"], "cell " + BAR_CLS[r["status"]], f"{r['done']:,} / {r['expected']:,}") + unknown
                if r["runs"] else "<span class=dim>-</span>")
        h.append(f"<tr class='{e(r['state'])}'><td class=model>{e(r['model'])}</td><td>{_tag(r['state'])}</td>"
                 f"<td class=w>{_qual_cell_html(r)}</td><td class=w>{_job_cell_html(r, hpc_state)}</td>"
                 + "".join(_run_cell_html(g) for g in runs)
                 + f"<td>{prog}</td><td class=w>{_winners_html(r)}</td></tr>")
    if not rows:
        h.append(f"<tr><td colspan={6 + n_runs} class=dim>no models yet (no model dirs, pack or SLURM plan)</td></tr>")
    total_label = f"{head['pairings_done']:,} / {head['expected_known']:,}"
    h.append(f"<tr class=total><td>total</td><td>{len(rows)} models</td><td></td><td></td>"
             + "".join("<td class=run></td>" for _ in range(n_runs))
             + f"<td>{_bar(head['pairings_done'], head['expected_known'], 'cell b', total_label)}</td><td></td></tr>")
    h.append("</table></div>")
    h.append("<p class=legend>rows: failed, running, pending, done, in the Qualification Round, not submitted. "
             "run cell: eligible bots &middot; pairings done/expected, bar <i style='background:#5cbf7a'></i>done/VERIFIED "
             "<i style='background:#7fa7e6'></i>running <i style='background:#c9d6ea'></i>queued <i style='background:#e07070'></i>FAILED; "
             "winner = the run's BT argmax (top_1.json), <span class=red>tie</span> when it declares ties_at_top; "
             "&#10003; VERIFIED, &#10007; FAILED (the verifier's marker files). Qualification Round: laptop = shipped as a pack "
             "(passed = the pack manifest's eligible count); job = the cluster node job replaying the model's samples. "
             "job = the model's SLURM job (its five runs back to back); time left = limit - elapsed.</p>")
    return "\n".join(h)


def render_headline_html(merged: Dict[str, Any], *, now: float) -> str:
    head = headline(merged["models"], now=now)
    hpc_state = merged["hpc"]
    rows = model_rows(merged)
    by_row = {st: sum(1 for r in rows if r["state"] == st) for st in ROW_STATES}
    est_note = f" + ~{head['expected_est']:,.0f} est." if head["n_unstarted"] else ""
    pct = 100.0 * head["pairings_done"] / head["expected_total"] if head["expected_total"] else 0.0
    tiles: List[str] = []

    def tile(k: str, v: str, s: str = "", cls: str = "") -> None:
        tiles.append(f"<div class='stat {cls}'><span class=k>{k}</span><span class=v>{v}</span><span class=s>{s}</span></div>")

    if hpc_state is not None:
        sl = hpc_state["slurm"]
        if sl is None:
            tile("snapshot", "<span class=red>no slurm.json</span>", e(hpc_state["dir"]))
        else:
            age = e(fmt_age(sl["generated_ts"], now))
            tile("snapshot", f"<span class='{'red' if sl['stale'] else ''}'>{age}{' (stale)' if sl['stale'] else ''}</span>",
                 f"slurm.json {e(str(sl['generated_at']))}")
        mj = count_states(hpc_state["model_jobs"])
        qj = count_states(hpc_state["qual_round_jobs"])
        bad = mj["failed"] + mj["timeout"] + mj["other"]
        tile("model jobs", f"{mj['running']} running &middot; {mj['pending']} pend.",
             f"{mj['done']} done" + (f" &middot; <span class=red>{bad} failed</span>" if bad else "")
             + (f" &middot; array tasks {hpc_state['by_state']['running']} running, {hpc_state['by_state']['pending']} pending" if hpc_state["tasks"] else ""))
        tile("Qualification Round jobs", f"{qj['running']} running &middot; {qj['pending']} pend.",
             f"{qj['done']} done" + (f" &middot; <span class=red>{qj['failed'] + qj['timeout'] + qj['other']} failed</span>"
                                     if qj["failed"] + qj["timeout"] + qj["other"] else ""))
        tile("cores in use", f"{hpc_state['cores_running']:,}", "cpus of RUNNING jobs")
    tile("models", str(len(rows)), f"{by_row['running']} running &middot; {by_row['pending']} pending &middot; {by_row['done']} done"
         + (f" &middot; <span class=red>{by_row['failed']} failed</span>" if by_row["failed"] else "")
         + f" &middot; {by_row['qualifying'] + by_row['waiting']} not started")
    tile("pairings", f"{head['pairings_done']:,} / {head['expected_total']:,.0f}", f"{pct:.1f}%{e(est_note)}")
    tile("games", f"{head['games_done']:,}", "5 seeds per pairing")
    rate_txt = f"{head['rate_per_h']:,.0f} /h" if head["rate_per_h"] else "0 /h"
    tile("rate", rate_txt, f"{head['recent_pairings']:,} pairings in {head['window_min']} min")
    if head["eta_h"] is None:
        tile("ETA", "no progress", f"in the last {head['window_min']} min &middot; last pairing {e(fmt_age(head['last_mtime'], now))}")
    elif head["eta_h"] == 0:
        tile("ETA", "done", f"last pairing {e(fmt_age(head['last_mtime'], now))}")
    else:
        tile("ETA", e(fmt_eta(head["eta_h"])), e(f"~{_local(now + head['eta_h'] * 3600)}"))
    h = ["<div class=strip>" + "".join(tiles) + "</div>"]
    h.append(_bar(head["pairings_done"], head["expected_total"], "big " + ("g" if head["eta_h"] == 0 else "b"),
                  f"Top Bot per Run Round pairings &middot; {head['pairings_done']:,} / {head['expected_total']:,.0f}{e(est_note)} &middot; {pct:.1f}%"))
    flags = list(merged["flags"]) + (hpc_state["flags"] if hpc_state is not None else [])
    if flags:
        h.append("<p class=foot><span class=red>flags:</span> " + "; ".join(e(f) for f in flags) + "</p>")
    return "\n".join(h)


def render_jobs_html(hpc_state: Dict[str, Any], *, now: float) -> str:
    """Below the primary table: the Qualification Round jobs table, the pack job's line, and the array-task table
    only when `sh250-a` tasks exist."""
    h: List[str] = ["<h2>Qualification Round jobs</h2>"]
    if not hpc_state["exists"]:
        h.append(f"<p class=meta><span class=red>mirror dir not found:</span> <code>{e(hpc_state['dir'])}</code></p>")
        return "\n".join(h)
    q = live_qual(hpc_state)
    if hpc_state["qual_round_jobs"]:
        h.append("<div class=wrap><table><tr><th>job</th><th>state</th><th>node</th><th class=n>cores</th>"
                 "<th>elapsed / limit</th><th class=n>left</th><th>models</th><th class=n>passed</th><th class=n>awaiting</th>"
                 "<th class=n>errors</th><th>reason / exit</th></tr>")
        for j in hpc_state["qual_round_jobs"]:
            known = [q["rows"][m] for m in j["models"] if m in q["rows"]]
            passed = f"{sum(r['passed'] for r in known)}" if known else "<span class=dim>-</span>"
            awaiting = f"{sum(r['awaiting'] for r in known)}" if known else "<span class=dim>-</span>"
            errors = sum(r["qual_error"] for r in known)
            err = f"<span class=red>{errors}</span>" if errors else ("0" if known else "<span class=dim>-</span>")
            h.append(f"<tr><td>{e(j['job_id'])}</td><td>{_tag(j['state'])}</td><td>{e(j['node'] or '-')}</td><td class=n>{j['cpus'] or '-'}</td>"
                     f"<td>{e(j['elapsed'])}{' / ' + e(j['time_limit']) if j['time_limit'] else ''}</td>"
                     f"<td class=n>{e(remaining_text(j['elapsed'], j['time_limit']))}</td>"
                     f"<td class=w>{e(', '.join(j['models']) or '-')}</td><td class=n>{passed}</td><td class=n>{awaiting}</td>"
                     f"<td class=n>{err}</td><td class=dim>{e(j['reason'])}</td></tr>")
        h.append("</table></div>")
    else:
        h.append("<p class=meta>none in the snapshot</p>")
    qr = hpc_state["qual_round"]
    if qr is not None:
        tot = q["totals"]
        files = ", ".join(f"<code>{e(f)}</code>" for f in q["files"]) or "<span class=dim>none of a live job yet</span>"
        older = f" &middot; {q['older']} older file{'s' if q['older'] != 1 else ''} of superseded jobs ignored" if q["older"] else ""
        h.append(f"<p class=meta>status files {files} (newest file {e(fmt_age(qr['mtime'], now))}){older}: "
                 f"{tot['passed']} passed, {tot['forfeit']} forfeit, {tot['awaiting']} awaiting, "
                 f"<span class='{'red' if tot['qual_error'] else ''}'>{tot['qual_error']} errors</span>, {tot['generated']} / {tot['target']} generated"
                 + (f" &middot; progress.jsonl {qr['progress_records']} records" if qr["progress_records"] is not None else "") + "</p>")
    if hpc_state["pack_jobs"]:
        ps = "; ".join(f"{e(p['job_id'])} {_tag(p['state'])} {e(p['node'] or '-')} {e(p['elapsed'])}"
                       + (f" <span class=dim>{e(p['reason'])}</span>" if p["reason"] else "") for p in hpc_state["pack_jobs"])
        h.append(f"<p><b>Pack job</b> (after the Qualification Round jobs: packs their models and submits their model jobs): {ps}</p>")
    else:
        h.append("<p><b>Pack job</b>: <span class=dim>none in the snapshot</span></p>")
    if hpc_state["tasks"]:
        bs = hpc_state["by_state"]
        h.append("<h3>Top Bot per Run Round array tasks (one task per run)</h3>")
        h.append(_seg_bar(bs, f"{bs['done']} done &middot; {bs['running']} running &middot; {bs['pending']} pending &middot; "
                              f"{bs['failed'] + bs['timeout'] + bs['other']} failed/timeout/other"))
        if hpc_state["problems"]:
            h.append(f"<p><span class=red>{len(hpc_state['problems'])} problem task{'s' if len(hpc_state['problems']) != 1 else ''}: "
                     f"index {', '.join(str(i) for i in hpc_state['problems'])}</span></p>")
        h.append("<div class=wrap><table><tr><th class=n>index</th><th>job</th><th>model</th><th>run</th><th>state</th><th>node</th>"
                 "<th>elapsed / limit (time left)</th><th>pairings<br><span style='font-weight:400'>done / expected (mirror)</span></th>"
                 "<th>marker</th><th>problem</th><th>last log line</th></tr>")
        for t in hpc_state["tasks"]:
            pair = "<span class=dim>no ledger yet</span>" if t["expected"] is None else f"{t['done']} / {t['expected']}"
            problem = f"<span class=red>{e(t['problem'])}</span>" if t["problem"] else ""
            reason = f" <span class=dim>{e(t['reason'])}</span>" if t["reason"] else ""
            h.append(f"<tr class='{'problem' if t['problem'] else ''}'><td class=n>{t['index']}</td><td><code>{e(t['job_id'])}</code></td>"
                     f"<td><b>{e(t['model'] or '?')}</b></td><td>{e(t['group'] or '?')}</td><td>{_tag(t['state'])}{reason}</td>"
                     f"<td>{e(t['node'] or '-')}</td><td>{_elapsed_cell(t)}</td><td class=n>{pair}</td>"
                     f"<td>{_tag(t['marker']) if t['marker'] else '<span class=dim>-</span>'}</td><td>{problem}</td>"
                     f"<td class=tail>{e(t['log_tail']) if t['log_tail'] else ''}</td></tr>")
        h.append("</table></div>")
        h.append("<p class=legend>state = SLURM (squeue/sacct); pairings = match_result.json files in the rr mirror for that run; "
                 "marker = VERIFIED/FAILED written by the task after verify_pool_rr; problem = FAILED/TIMEOUT/CANCELLED, "
                 "COMPLETED without a VERIFIED marker, or an index missing from the plan.</p>")
    return "\n".join(h)


def scoreboard_has_data(sb: Dict[str, Any]) -> bool:
    return bool(sb["top1"] or sb["top5"])


def render_scoreboard_html(sb: Dict[str, Any]) -> str:
    h: List[str] = ["<h2>Scoreboard</h2>"]
    if not scoreboard_has_data(sb) and sb["top1_pending"] is None and not sb["top5_pending"]:
        h.append("<p class=meta>not yet &middot; the Top-5 Round runs once a model's five run winners are known; "
                 "the Champions Round after every model's Top-5 Round winner is known</p>")
        return "\n".join(h)
    h.append("<div class=cols>")
    h.append("<div><h3>Champions Round (24 model winners, 11 seeds, BT)</h3>")
    if sb["top1"]:
        h.append(f"<p class=meta>host {e(sb['top1_host'] or '-')} &middot; {sb['top1_games']:,} games")
        if len(sb["top1_ties_at_top"]) > 1:
            h.append(f" &middot; <span class=red>tie at the top: {e(', '.join(sb['top1_ties_at_top']))}</span>")
        h.append("</p><div class=wrap><table><tr><th class=n>#</th><th>model</th><th>bot</th><th class=n>Champions Elo</th><th class=n>W-L-D</th><th class=n>games</th></tr>")
        for i, (aid, st) in enumerate(sb["top1"], start=1):
            model = aid.rsplit("__", 1)[0]
            h.append(f"<tr><td class=n>{i}</td><td><b>{e(model)}</b></td><td><code>{e(aid)}</code></td><td class=n>{float(st['elo']):.1f}</td>"
                     f"<td class=n>{e(wld(st))}</td><td class=n>{int(st['games'])}</td></tr>")
        h.append("</table></div>")
    elif sb["top1_pending"] is not None:
        h.append(f"<p class=meta>not yet &middot; Champions Round in progress: {sb['top1_pending']} pairings on disk, no elo.json</p>")
    else:
        h.append("<p class=meta>not yet &middot; the Champions Round runs after every model's Top-5 Round winner is known</p>")
    h.append("</div>")
    h.append("<div><h3>Top-5 Round (per model, 11 seeds, BT)</h3>")
    if sb["top5"]:
        h.append("<div class=wrap><table><tr><th>model</th><th class=n>#</th><th>bot</th><th class=n>Top-5 Elo</th><th class=n>W-L-D</th></tr>")
        for model, entry in sb["top5"].items():
            rows = entry["rows"]
            for i, (aid, st) in enumerate(rows, start=1):
                first = f"<td rowspan={len(rows)}><b>{e(model)}</b>" + (
                    f"<br><span class=red>tie at top</span>" if len(entry["ties_at_top"]) > 1 else "") + "</td>" if i == 1 else ""
                h.append(f"<tr>{first}<td class=n>{i}</td><td><code>{e(short_aid(aid))}</code></td>"
                         f"<td class=n>{float(st['elo']):.1f}</td><td class=n>{e(wld(st))}</td></tr>")
        h.append("</table></div>")
    else:
        h.append("<p class=meta>not yet &middot; the Top-5 Round runs once a model's five run winners are known</p>")
    if sb["top5_pending"]:
        h.append("<p class=meta>Top-5 Round in progress: " + ", ".join(f"{e(m)} {n}/10 pairings" for m, n in sorted(sb["top5_pending"].items())) + "</p>")
    h.append("</div></div>")
    return "\n".join(h)


WHAT_THIS_IS = [
    "Every model produced <b>250 samples</b> (zero-shot bots), read as <b>5 runs of 50</b> consecutive samples (c000-049, c050-099, ...).",
    "Top Bot per Run Round: a <b>full round robin inside each run</b> at <b>5 seeds</b> per pairing (every eligible bot of the run plays every other), "
    "300 s games, inactivity rule armed, no telemetry. Bradley-Terry over the run's games picks the <b>run winner</b>; "
    "the five run winners are the model's top-5.",
    "Top-5 Round: the 10 pairings among a model's five run winners at <b>11 seeds</b> (with telemetry) - BT picks the <b>model's winner</b>.",
    "Champions Round: every model's winner in one cross-model round robin at <b>11 seeds</b> - BT <b>ranks the models</b>: that is the scoreboard.",
    "Expected pairings of a run = C(eligible, 2); games = pairings x seeds. Rate = pairings whose match_result.json changed in the last "
    f"{WINDOW_MIN} min (rsync -a keeps the hosts' mtimes); ETA = remaining pairings / rate. Runs that have not started are estimated at the "
    "mean pairing count of the runs that have.",
]


def render_html(merged: Dict[str, Any], *, now: float, loop_s: int = 0) -> str:
    sb = merged["stage_b"]
    hpc_state = merged["hpc"]
    h: List[str] = ["<!doctype html><html><head><meta charset=utf-8>",
                    "<meta name=viewport content='width=device-width,initial-scale=1'>",
                    "<title>SH-250 pool tournament</title>", f"<style>{_CSS}</style></head><body><main>"]
    regen = f"the file is regenerated every {loop_s} s; " if loop_s else ""
    h.append(f"<div class=topbar><a href=\"\" class=btn>Refresh</a>"
             f"<span class=upd>generated <b>{e(_local(now))}</b> ({e(_utc(now))})</span>"
             f"<span class=hint>{e(regen)}static file, no scripts, no auto-refresh: press Refresh to load the latest</span></div>")
    h.append("<h1>SH-250 pool tournament</h1>")
    hosts = ", ".join(merged["hosts"]) or "-"
    h.append(f"<p class=meta>hosts <b>{e(hosts)}</b> &middot; roots {' '.join(f'<code>{e(r)}</code>' for r in merged['roots'])}"
             + (f" &middot; mirror <code>{e(hpc_state['dir'])}</code> &middot; user <b>{e(str(hpc_state['slurm']['user']))}</b>"
                if hpc_state is not None and hpc_state["slurm"] is not None else "") + "</p>")
    for r in merged["missing_roots"]:
        h.append(f"<p class=meta><span class=red>root not found:</span> <code>{e(r)}</code></p>")

    # 1. headline strip
    h.append(render_headline_html(merged, now=now))

    # 2. scoreboard first once it has data
    if scoreboard_has_data(sb):
        h.append(render_scoreboard_html(sb))

    # 3. the primary table
    h.append("<h2>Top Bot per Run Round &middot; one row per model</h2>")
    h.append(render_primary_table_html(merged, now=now))

    # 4. jobs below it
    if hpc_state is not None:
        h.append(render_jobs_html(hpc_state, now=now))

    # 5. scoreboard placeholder
    if not scoreboard_has_data(sb):
        h.append(render_scoreboard_html(sb))

    # 6. what this is
    h.append("<div class=what><h3>What this is</h3><ol>" + "".join(f"<li>{s}</li>" for s in WHAT_THIS_IS) + "</ol>")
    if hpc_state is not None:
        sha = f"<code>{e(hpc_state['shipped_sha'])}</code>" if hpc_state["shipped_sha"] else "<span class=dim>unknown (no rr/SHIPPED_SHA in the mirror)</span>"
        h.append(f"<p style='margin-top:10px'>code on HPC: SHIPPED_SHA {sha}</p><p>{e(HPC_WHAT)}</p>")
    h.append("</div>")
    h.append("</main></body></html>")
    return "\n".join(h) + "\n"


# ── markdown twin ─────────────────────────────────────────────────────────────

def _run_cell_md(g: Optional[Dict[str, Any]]) -> str:
    if g is None:
        return "-"
    if g["eligible"] is None:
        return "? bots" + (f" {g['task_state']}" if g["task_state"] else "")
    txt = f"{g['eligible']} bots {g['done']}/{g['expected']}"
    if g["winner"]:
        txt += f" {short_aid(g['winner'])}" + (" tie" if len(g["ties_at_top"]) > 1 else "")
    if g["status"] == "VERIFIED":
        txt += " ✓"
    elif g["status"] == "FAILED":
        txt += " ✗"
    if g["task_state"]:
        txt += f" {g['task_state']}"
    return txt


def _qual_cell_md(r: Dict[str, Any]) -> str:
    q = r["qual"]
    counts = (([f"{q['passed']} passed"] if q["passed"] is not None else []) + ([f"{q['awaiting']} awaiting"] if q["awaiting"] else [])
              + ([f"{q['errors']} errors"] if q["errors"] else []))
    tail = (" · " + " · ".join(counts)) if counts else ""
    if q["where"] == "laptop":
        return "laptop" + tail
    if q["job"] is not None:
        return f"job {q['job']['job_id']} {q['job']['state']}" + tail
    if q["where"] == "cluster":
        return "cluster" + tail
    return "not submitted"


def _job_cell_md(r: Dict[str, Any], hpc_state: Optional[Dict[str, Any]]) -> str:
    j = r["job"]
    if j is not None:
        if j["state"] == "PENDING":
            return f"{j['job_id']} PENDING" + (f" ({j['reason']})" if j["reason"] else "") + f" · {j['cpus']} cores"
        txt = f"{j['job_id']} {j['state']} · {j['node'] or '-'} · {_cores(j)} · {_elapsed_text(j)}"
        return txt + (f" · {r['problem']}" if r["problem"] else "")
    if hpc_state is not None and r["model"] in hpc_state["where"]:
        return "array " + " ".join(f"{g}:{st}" for g, st in hpc_state["where"][r["model"]].items()) + (f" · {r['problem']}" if r["problem"] else "")
    if r["host"]:
        return r["host"]
    if r["state"] == "qualifying" and hpc_state is not None and hpc_state["pack_jobs"]:
        return f"after pack job {hpc_state['pack_jobs'][0]['job_id']} {hpc_state['pack_jobs'][0]['state']}"
    return "-"


def render_md(merged: Dict[str, Any], *, now: float) -> str:
    models = merged["models"]
    head = headline(models, now=now)
    sb = merged["stage_b"]
    hpc_state = merged["hpc"]
    rows = model_rows(merged)
    n_runs = run_columns(merged)
    by_row = {st: sum(1 for r in rows if r["state"] == st) for st in ROW_STATES}
    est_note = (f" (+ ~{head['expected_est']:,.0f} est. for {head['n_unstarted']} unstarted run{'s' if head['n_unstarted'] != 1 else ''})"
                if head["n_unstarted"] else "")
    pct = 100.0 * head["pairings_done"] / head["expected_total"] if head["expected_total"] else 0.0
    out = ["# SH-250 pool tournament", "", f"- generated: {_utc(now)}", f"- hosts: {', '.join(merged['hosts']) or '-'}"]
    if hpc_state is not None:
        sl = hpc_state["slurm"]
        if sl is None:
            out.append(f"- snapshot: no slurm.json under {hpc_state['dir']}")
        else:
            mj, qj = count_states(hpc_state["model_jobs"]), count_states(hpc_state["qual_round_jobs"])
            out += [f"- snapshot: slurm.json {sl['generated_at']} ({fmt_age(sl['generated_ts'], now)}{', STALE' if sl['stale'] else ''}), user {sl['user']}",
                    f"- model jobs: {mj['running']} running, {mj['pending']} pending, {mj['done']} done, {mj['failed'] + mj['timeout'] + mj['other']} failed; "
                    f"Qualification Round jobs: {qj['running']} running, {qj['pending']} pending, {qj['done']} done, "
                    f"{qj['failed'] + qj['timeout'] + qj['other']} failed; {hpc_state['cores_running']} cores in use"]
            if hpc_state["tasks"]:
                bs = hpc_state["by_state"]
                out.append(f"- array tasks: {bs['pending']} pending, {bs['running']} running, {bs['done']} done, {bs['failed']} failed, "
                           f"{bs['timeout']} timeout, {bs['other']} other; problems: {', '.join(str(i) for i in hpc_state['problems']) or 'none'}")
    out += [f"- models: {len(rows)} ({by_row['running']} running, {by_row['pending']} pending, {by_row['done']} done, {by_row['failed']} failed, "
            f"{by_row['qualifying'] + by_row['waiting']} not started)",
            f"- Top Bot per Run Round pairings: {head['pairings_done']:,} / {head['expected_known']:,}{est_note} ({pct:.1f}%), {head['games_done']:,} games",
            f"- rate: {head['rate_per_h']:,.0f} pairings/h over the last {head['window_min']} min; ETA: {fmt_eta(head['eta_h'])}; "
            f"last finished pairing {fmt_age(head['last_mtime'], now)}"]
    out += [f"- FLAG: {f}" for f in merged["flags"] + (hpc_state["flags"] if hpc_state is not None else [])]
    if scoreboard_has_data(sb):
        out += _scoreboard_md(sb)
    out += ["", "## Top Bot per Run Round · one row per model", "",
            "| model | state | Qualification Round | job | " + " | ".join(f"run {k + 1}" for k in range(n_runs)) + " | progress | run winners |",
            "|---|---|---|---|" + "---|" * n_runs + "---|---|"]
    for r in rows:
        runs = r["runs"] + [None] * (n_runs - len(r["runs"]))
        prog = (f"{r['done']:,}/{r['expected']:,}" + (f" +{r['unknown_runs']}?" if r["unknown_runs"] else "")) if r["runs"] else "-"
        out.append(f"| {r['model']} | {r['label']} | {_qual_cell_md(r)} | {_job_cell_md(r, hpc_state)} | "
                   + " | ".join(_run_cell_md(g) for g in runs)
                   + f" | {prog} | {' '.join(short_aid(w) for w in r['winners']) or '-'} |")
    if hpc_state is not None:
        out += _jobs_md(hpc_state, now)
    if not scoreboard_has_data(sb):
        out += _scoreboard_md(sb)
    out += ["", "## What this is", ""]
    out += [f"{i}. {_strip_tags(s)}" for i, s in enumerate(WHAT_THIS_IS, start=1)]
    if hpc_state is not None:
        out += ["", f"code on HPC: SHIPPED_SHA {hpc_state['shipped_sha'] or 'unknown'}", "", HPC_WHAT]
    return "\n".join(out) + "\n"


def _scoreboard_md(sb: Dict[str, Any]) -> List[str]:
    out = ["", "## Scoreboard", "", "### Champions Round", ""]
    if sb["top1"]:
        out += ["| # | model | bot | Champions Elo | W-L-D |", "|---|---|---|---|---|"]
        out += [f"| {i} | {aid.rsplit('__', 1)[0]} | {aid} | {float(st['elo']):.1f} | {wld(st)} |"
                for i, (aid, st) in enumerate(sb["top1"], start=1)]
    else:
        out.append("not yet")
    out += ["", "### Top-5 Round per model", ""]
    if sb["top5"]:
        out += ["| model | # | bot | Top-5 Elo | W-L-D |", "|---|---|---|---|---|"]
        for model, entry in sb["top5"].items():
            out += [f"| {model} | {i} | {short_aid(aid)} | {float(st['elo']):.1f} | {wld(st)} |"
                    for i, (aid, st) in enumerate(entry["rows"], start=1)]
    else:
        out.append("not yet")
    return out


def _jobs_md(hpc_state: Dict[str, Any], now: float) -> List[str]:
    out = ["", "## Qualification Round jobs", ""]
    if not hpc_state["exists"]:
        return out + [f"mirror dir not found: {hpc_state['dir']}"]
    q = live_qual(hpc_state)
    if hpc_state["qual_round_jobs"]:
        out += ["| job | state | node | cores | elapsed / limit | left | models | passed | awaiting | errors |", "|---|---|---|---|---|---|---|---|---|---|"]
        for j in hpc_state["qual_round_jobs"]:
            known = [q["rows"][m] for m in j["models"] if m in q["rows"]]
            out.append(f"| {j['job_id']} | {j['state']}{' (' + j['reason'] + ')' if j['reason'] else ''} | {j['node'] or '-'} | {j['cpus'] or '-'} | "
                       f"{j['elapsed']}{' / ' + j['time_limit'] if j['time_limit'] else ''} | {remaining_text(j['elapsed'], j['time_limit'])} | "
                       f"{', '.join(j['models']) or '-'} | {sum(r['passed'] for r in known) if known else '-'} | "
                       f"{sum(r['awaiting'] for r in known) if known else '-'} | {sum(r['qual_error'] for r in known) if known else '-'} |")
    else:
        out.append("none in the snapshot")
    qr = hpc_state["qual_round"]
    if qr is not None:
        tot = q["totals"]
        out.append(f"\nstatus files {', '.join(q['files']) or 'none of a live job yet'} (newest file {fmt_age(qr['mtime'], now)})"
                   + (f"; {q['older']} older files of superseded jobs ignored" if q["older"] else "") + ": "
                   f"{tot['passed']} passed, {tot['forfeit']} forfeit, {tot['awaiting']} awaiting, {tot['qual_error']} errors, "
                   f"{tot['generated']}/{tot['target']} generated")
    for p in hpc_state["pack_jobs"]:
        out.append(f"\nPack job {p['job_id']}: {p['state']} on {p['node'] or '-'}, {p['elapsed']}" + (f" ({p['reason']})" if p["reason"] else ""))
    if not hpc_state["pack_jobs"]:
        out.append("\nPack job: none in the snapshot")
    if hpc_state["tasks"]:
        out += ["", "### Top Bot per Run Round array tasks", "", "| job | index | model | run | state | node | elapsed / limit (left) | pairings | marker | problem | last log line |",
                "|---|---|---|---|---|---|---|---|---|---|---|"]
        for t in hpc_state["tasks"]:
            pair = "-" if t["expected"] is None else f"{t['done']}/{t['expected']}"
            out.append(f"| {t['job_id']} | {t['index']} | {t['model'] or '?'} | {t['group'] or '?'} | {t['state']} | {t['node'] or '-'} | "
                       f"{t['elapsed']} / {t['time_limit']} ({remaining_text(t['elapsed'], t['time_limit'])}) | {pair} | {t['marker'] or '-'} | {t['problem'] or ''} | "
                       f"{(t['log_tail'] or '').replace('|', '/')} |")
    return out


def _strip_tags(s: str) -> str:
    import re
    return html.unescape(re.sub(r"<[^>]+>", "", s))


# ── CLI ───────────────────────────────────────────────────────────────────────

def pack_model_names(pack: Path) -> List[str]:
    return sorted(d.name for d in Path(pack).iterdir() if d.is_dir() and d.name not in PACK_SKIP)


def scan_pack(pack: Path) -> Dict[str, Any]:
    """The laptop-qualified pack: its model dirs and, from `MANIFEST.json` (pack_pool.py), each model's eligible
    count = the bots that passed the Qualification Round. A pack without a manifest is flagged."""
    pack = Path(pack)
    out: Dict[str, Any] = {"dir": str(pack), "models": pack_model_names(pack), "eligible": {}, "flags": []}
    manifest = pack / "MANIFEST.json"
    if not manifest.is_file():
        out["flags"].append(f"pack {pack} has no MANIFEST.json (passed counts unknown)")
        return out
    for name, entry in _read_json(manifest)["models"].items():
        out["eligible"][name] = int(entry["eligible"])
    return out


def build(roots: List[Path], *, runs: int, pack: Optional[Path], hpc: Optional[Path] = None,
          now: Optional[float] = None) -> Dict[str, Any]:
    """Scan every host root plus (optionally) the HPC mirror, whose `rr/` joins the hosts as `hpc`.
    Every model named by the pack or by the SLURM plan (model jobs, Qualification Round jobs) gets a row."""
    scans = [scan_root(r, runs=runs) for r in roots]
    hpc_state = None
    if hpc is not None:
        hpc_state = scan_hpc(hpc, now=time.time() if now is None else now, runs=runs)
        if hpc_state["rr_scan"] is not None:
            scans.append(hpc_state["rr_scan"])
    pk = scan_pack(pack) if pack else None
    merged = merge_hosts(scans, pk["models"] if pk else None, runs=runs)
    merged["hpc"] = hpc_state
    merged["pack"] = pk
    if pk:
        merged["flags"] += pk["flags"]
    if hpc_state is not None:
        for name in list(hpc_state["model_job_of"]) + list(hpc_state["qual_job_of"]):
            if name not in merged["models"]:
                merged["models"][name] = placeholder_model(name)
        if hpc_state["qual_round"] is not None:
            for name in hpc_state["qual_round"]["rows"]:
                if name not in merged["models"]:
                    merged["models"][name] = placeholder_model(name)
        merged["models"] = dict(sorted(merged["models"].items()))
    return merged


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--roots", nargs="+", type=Path, default=[], help="per-host Top Bot per Run Round mirrors (basename = host)")
    ap.add_argument("--hpc", type=Path, default=None,
                    help="HPC mirror dir (slurm.json, rr/, qual/, logs/); its rr/ is the host `hpc`")
    ap.add_argument("--out", type=Path, required=True, help="HTML file to write")
    ap.add_argument("--md", type=Path, default=None, help="markdown twin (default: <out> with .md)")
    ap.add_argument("--runs", type=int, default=DEFAULT_RUNS, help="runs per model in grouped mode (g0..g<runs-1>)")
    ap.add_argument("--pack", type=Path, default=None, help="pack dir: models without output yet are listed as queued")
    ap.add_argument("--loop", type=int, nargs="?", const=REFRESH_S, default=0,
                    help=f"rewrite every N seconds (bare --loop = {REFRESH_S}; omitted = once)")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)
    if not a.roots and a.hpc is None:
        ap.error("give --roots and/or --hpc")
    md_path = a.md if a.md is not None else a.out.with_suffix(".md")
    while True:
        now = time.time()
        merged = build(a.roots, runs=a.runs, pack=a.pack, hpc=a.hpc, now=now)
        a.out.write_text(render_html(merged, now=now, loop_s=a.loop))
        md = render_md(merged, now=now)
        md_path.write_text(md)
        if not a.quiet:
            head = headline(merged["models"], now=now)
            print(f"{_utc(now)} pairings {head['pairings_done']:,}/{head['expected_known']:,} "
                  f"(+{head['n_unstarted']} unstarted runs) games {head['games_done']:,} rate {head['rate_per_h']:,.0f}/h "
                  f"ETA {fmt_eta(head['eta_h'])} -> {a.out}")
        if not a.loop:
            break
        time.sleep(a.loop)
    return 0


if __name__ == "__main__":
    sys.exit(main())
