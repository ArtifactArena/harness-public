#!/usr/bin/env python
"""Zero-shot sampling launcher: N independent single-commit samples per model, build phase only.

One `run_baseline_agent.py --iterations 1 --build-only` process per sample, so every
sample is a fresh prompt with its own directory and its own log:

    <root>/<model-stem>/cNNN/                       run output (bots/<model-stem>/bot_artifact.json ...)
    <root>/<model-stem>/cNNN.log                    stdout+stderr of that process (+ /usr/bin/time -l tail)
    <root>/progress.jsonl                           one line per finished sample (exit, wall, rss, llm calls, forfeit)
    <root>/manifest.json                            git sha + config/model md5s; refuses to mix code versions

Concurrency: at most --per-model samples of one model in flight and at most --global-max
processes overall (RAM is the binding limit on a laptop, provider rate limits the second).
Resumable: a sample whose bot_artifact.json exists is skipped, so re-running the same
command fills in the gaps.

    python scripts/sampling/launch.py --root LOGS-SH250/dryrun --n-samples 1 --per-model 1 --global-max 12
    python scripts/sampling/launch.py --root LOGS-SH250/20260918 --n-samples 250 --per-model 20 --global-max 40
    python scripts/sampling/launch.py --root LOGS-SH250/dryrun --summary
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
PY = os.environ.get("PY", str(Path.home() / "miniconda3/envs/arena/bin/python"))
TIME = "/usr/bin/time"  # macOS: `-l` appends "maximum resident set size" to stderr


def _md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def _git_sha() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()


def _models(config: Path, filters: list[str]) -> list[Path]:
    llms = yaml.safe_load(config.read_text())["llms"]
    paths = [REPO / p for p in llms]
    if filters:
        paths = [p for p in paths if any(f in str(p) for f in filters)]
    if not paths:
        sys.exit(f"no models selected from {config} with filters {filters}")
    return paths


def _sample_dir(root: Path, stem: str, idx: int) -> Path:
    return root / stem / f"c{idx:03d}"


def _artifact(out: Path, stem: str) -> Path:
    return out / "tournament_00/round_robin_match/bots" / stem / "bot_artifact.json"


def _write_manifest(root: Path, config: Path, models: list[Path], allow_drift: bool) -> None:
    sha = _git_sha()
    manifest = {
        "git_sha": sha,
        "config": str(config.relative_to(REPO)),
        "config_md5": _md5(config),
        "models": {m.stem: _md5(m) for m in models},
        "started_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    path = root / "manifest.json"
    if path.exists():
        old = json.loads(path.read_text())
        if old["git_sha"] != sha or old["config_md5"] != manifest["config_md5"]:
            msg = (f"{path} was written at git {old['git_sha'][:8]} / config md5 {old['config_md5'][:8]}, "
                   f"now at {sha[:8]} / {manifest['config_md5'][:8]}: samples would mix code versions")
            if not allow_drift:
                sys.exit(msg + " (pass --allow-sha-drift to override)")
            print("[launch] WARNING:", msg)
        return
    root.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2))


def _run_sample(config: Path, model: Path, root: Path, idx: int, progress: Path, lock: threading.Lock) -> dict:
    stem = model.stem
    out = _sample_dir(root, stem, idx)
    out.mkdir(parents=True, exist_ok=True)
    log = out.with_suffix(".log")
    cmd = [TIME, "-l", PY, "run_baseline_agent.py", "--config", str(config), "--llms", str(model),
           "--iterations", "1", "--build-only", "--output-dir", str(out)]
    env = dict(os.environ)
    env.pop("MUJOCO_GL", None)  # macOS: leave unset (egl only on a headless Linux box)
    t0 = time.time()
    with open(log, "w") as fh:
        rc = subprocess.call(cmd, cwd=REPO, stdout=fh, stderr=subprocess.STDOUT, env=env)
    wall = time.time() - t0
    rec = {"model": stem, "idx": idx, "exit": rc, "wall_s": round(wall, 1),
           "finished_at": dt.datetime.now(dt.timezone.utc).isoformat()}
    text = log.read_text(errors="replace")
    m = re.search(r"(\d+)\s+maximum resident set size", text)
    rec["max_rss_mb"] = round(int(m.group(1)) / 2**20, 1) if m else None
    usage = out / "tournament_00/round_robin_match/bots" / stem / "refinement/usage.jsonl"
    rows = [json.loads(l) for l in open(usage)] if usage.exists() else []
    ok_rows = [r for r in rows if "error" not in r]
    rec["llm_calls"] = len(ok_rows)                      # completed generations
    rec["failed_attempts"] = len(rows) - len(ok_rows)    # litellm retries that raised
    rec["completion_tokens"] = sum(r.get("completion_tokens") or 0 for r in ok_rows)
    rec["reasoning_tokens"] = sum(r.get("reasoning_tokens") or 0 for r in ok_rows)
    art = _artifact(out, stem)
    if art.exists():
        a = json.loads(art.read_text())
        rec["forfeit"] = a.get("forfeit")
        rec["forfeit_stage"] = a.get("forfeit_stage")
        rec["controller_score"] = a.get("controller_score")
    else:
        rec["forfeit"] = None
    rec["disk_mb"] = round(sum(p.stat().st_size for p in out.rglob("*") if p.is_file()) / 2**20, 1)
    with lock:
        with open(progress, "a") as fh:
            fh.write(json.dumps(rec) + "\n")
    status = "OK" if rc == 0 and art.exists() and not rec["forfeit"] else ("FORFEIT" if art.exists() else "ERROR")
    print(f"[launch] {stem:28} c{idx:03d} {status:7} exit={rc} wall={wall/60:5.1f}m "
          f"calls={rec['llm_calls']} failed={rec['failed_attempts']} rss={rec['max_rss_mb']}MB disk={rec['disk_mb']}MB", flush=True)
    return rec


def _summary(root: Path) -> None:
    progress = root / "progress.jsonl"
    if not progress.exists():
        sys.exit(f"no {progress}")
    rows = [json.loads(l) for l in open(progress)]
    by: dict[str, list[dict]] = {}
    for r in rows:
        by.setdefault(r["model"], []).append(r)
    print(f"{'model':28} {'n':>3} {'ok':>3} {'forf':>4} {'err':>3} {'wall_min':>8} {'max_wall':>8} "
          f"{'calls/s':>7} {'fallback%':>9} {'failed':>6} {'rss_MB':>6} {'disk_MB':>7}")
    tot = {"n": 0, "ok": 0, "forf": 0, "err": 0, "disk": 0.0}
    for stem, rs in sorted(by.items()):
        ok = sum(1 for r in rs if r["exit"] == 0 and r.get("forfeit") is False)
        forf = sum(1 for r in rs if r.get("forfeit"))
        err = sum(1 for r in rs if r.get("forfeit") is None)
        walls = [r["wall_s"] / 60 for r in rs]
        calls = [r["llm_calls"] for r in rs]
        rss = max((r["max_rss_mb"] or 0) for r in rs)
        disk = sum(r.get("disk_mb") or 0 for r in rs)
        fallback = 100 * sum(1 for c in calls if c > 1) / len(calls)
        failed = sum(r.get("failed_attempts") or 0 for r in rs)
        print(f"{stem:28} {len(rs):3} {ok:3} {forf:4} {err:3} {sum(walls)/len(walls):8.1f} {max(walls):8.1f} "
              f"{sum(calls)/len(calls):7.2f} {fallback:9.0f} {failed:6} {rss:6.0f} {disk:7.1f}")
        tot["n"] += len(rs); tot["ok"] += ok; tot["forf"] += forf; tot["err"] += err; tot["disk"] += disk
    print(f"{'TOTAL':28} {tot['n']:3} {tot['ok']:3} {tot['forf']:4} {tot['err']:3} {'':8} {'':8} {'':7} {'':9} {'':6} {'':6} {tot['disk']:7.1f}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="configs/tournaments/sh.yaml")
    ap.add_argument("--root", required=True, help="output root (relative to the repo or absolute)")
    ap.add_argument("--n-samples", type=int, default=250, help="samples per model (indices 0..N-1)")
    ap.add_argument("--per-model", type=int, default=20, help="max in-flight samples per model")
    ap.add_argument("--global-max", type=int, default=40, help="max in-flight processes overall")
    ap.add_argument("--models", nargs="*", default=[], help="substring filters on model yaml paths")
    ap.add_argument("--allow-sha-drift", action="store_true")
    ap.add_argument("--list", action="store_true", help="print what would run and exit")
    ap.add_argument("--summary", action="store_true", help="print the per-model table for --root and exit")
    a = ap.parse_args()

    root = Path(a.root) if Path(a.root).is_absolute() else REPO / a.root
    if a.summary:
        _summary(root)
        return
    config = REPO / a.config
    models = _models(config, a.models)
    todo = [(m, i) for m in models for i in range(a.n_samples)
            if not _artifact(_sample_dir(root, m.stem, i), m.stem).exists()]
    print(f"[launch] {len(models)} models x {a.n_samples} samples: {len(todo)} to run, "
          f"per-model {a.per_model}, global {a.global_max}, root={root}")
    if a.list:
        for m, i in todo:
            print(f"  {m.stem} c{i:03d}")
        return
    if not todo:
        return
    _write_manifest(root, config, models, a.allow_sha_drift)

    progress = root / "progress.jsonl"
    lock = threading.Lock()
    global_sem = threading.BoundedSemaphore(a.global_max)
    queues: dict[str, queue.Queue] = {m.stem: queue.Queue() for m in models}
    for m, i in todo:
        queues[m.stem].put((m, i))

    def worker(stem: str) -> None:
        q = queues[stem]
        while True:
            try:
                m, i = q.get_nowait()
            except queue.Empty:
                return
            with global_sem:
                try:
                    _run_sample(config, m, root, i, progress, lock)
                except Exception as exc:  # keep the lane alive; the sample stays un-marked and reruns on resume
                    print(f"[launch] {stem} c{i:03d} launcher error: {exc!r}", flush=True)

    threads = [threading.Thread(target=worker, args=(m.stem,), daemon=True, name=f"{m.stem}-{k}")
               for m in models for k in range(a.per_model)]
    t0 = time.time()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    print(f"[launch] ALL DONE in {(time.time()-t0)/60:.1f} min")
    _summary(root)


if __name__ == "__main__":
    main()
