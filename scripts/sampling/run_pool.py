#!/usr/bin/env python
"""Two-stage zero-shot sampling pool: fan the API calls out, qualify on every core.

Stage 1 (generation, threads in THIS process): for every (model, sample) the real
engineer predictor is called once through configure_lm + build_engineer, exactly as the
build pipeline would, and the parsed outputs are saved to <sample>/gen.json (raw
response text next to it). Up to --per-model calls per model are in flight at once;
it is only HTTP, so hundreds of threads are fine.

Stage 2 (qualification, a pool of --qual-workers subprocesses): each finished gen.json
is replayed through the unchanged `run_baseline_agent.py --iterations 1 --build-only`
(ARENA_REPLAY_OUTPUTS makes configure_lm hand back a DummyLM with those outputs), which
validates, qualifies against the block, and writes bot_artifact.json / journal exactly
as a normal run. CPU-bound, so the worker count is the core count.

Layout under --root:
    <model>/cNNN/gen.json            parsed outputs (+ raw_response_K.txt, gen/refinement/usage.jsonl)
    <model>/cNNN/gen_error.json      generation failed (error text, refusal flag)
    <model>/cNNN/tournament_00/round_robin_match/bots/<model>/bot_artifact.json   qualified sample
    <model>/cNNN.log                 stage-2 process log
    progress.jsonl, manifest.json, STATUS.md (also copied to <repo>/SH250_STATUS.md)

Self-management: `touch <root>/STOP-<model>` halts one lane; a zero balance pauses a lane 5 min and retries (providers auto-reload) and only BILLING_STOP_MIN minutes of continuous rejections stop it; a model lane also stops after ("credits
exhausted") or MAX_CONSECUTIVE_ERRORS consecutive generation errors of any kind; stage 2
pauses when free disk drops under --min-free-gb; every finished sample has its
qualification trace gzipped and its videos removed. Re-running the same command resumes.
"""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import json
import os
import queue
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
PY = os.environ.get("PY", str(Path.home() / "miniconda3/envs/arena/bin/python"))
TIME = "/usr/bin/time"


def time_prefix() -> list:
    """Wrap a subprocess in /usr/bin/time for peak-RSS accounting: `-l` is the BSD/macOS flag, `-v` the GNU
    (Linux) one; on a box without /usr/bin/time run the command bare (GNU time exits 125 on a bad flag,
    which is how 3,000 cluster qualifications died in 0.0 s on 2026-09-19)."""
    if not os.path.exists(TIME):
        return []
    return [TIME, "-l"] if sys.platform == "darwin" else [TIME, "-v"]
MAX_CONSECUTIVE_ERRORS = 20   # unbroken non-billing failures before a lane is declared dead
MAX_GEN_ATTEMPTS = 3          # API attempts per sample (each already carries num_retries inside litellm)
BACKOFF_BASE_S = 30
BILLING_PAUSE_S = 300         # zero balance: providers auto-reload, so pause and retry instead of stopping
BILLING_STOP_MIN = 60         # a lane gives up only after this long of continuous billing rejections
BACKOFF_MAX_S = 900
BILLING_RE = re.compile(
    r"credit balance is too low|insufficient_quota|insufficient credits|no remaining credits|"
    r"out of credits|payment required|\b402\b|exceeded your current quota|spending limit|"
    r"billing", re.I)
BOTS = "tournament_00/round_robin_match/bots"


# ── pure helpers (unit-tested) ───────────────────────────────────────────────

def is_billing_error(text: str) -> bool:
    return bool(text) and BILLING_RE.search(text) is not None


RATE_LIMIT_RE = re.compile(r"RateLimitError|\b429\b|too many requests|rate limit", re.I)


def is_rate_limit(text: str) -> bool:
    """Provider throttling (not billing): back off, never give up on the lane or the sample."""
    return bool(text) and not is_billing_error(text) and RATE_LIMIT_RE.search(text) is not None


def is_deadline(text: str) -> bool:
    """Our own --gen-deadline-min abandonment: a whole batch of hung calls fails together, and the
    retries are fresh calls — never a reason to stop the lane or to wait before re-dispatching."""
    return bool(text) and "GenerationDeadline" in text


class ModelLane:
    """Per-model generation state: error streaks, backoff, per-sample attempts, stop decision."""

    def __init__(self, stem: str):
        self.stem = stem
        self.stopped: str | None = None
        self.billing_streak = 0
        self.billing_since: float | None = None
        self.rate_limit_streak = 0
        self.error_streak = 0
        self.last_error = ""
        self.last_error_ts: float | None = None
        self.attempts: dict[int, int] = {}
        self.lock = threading.Lock()

    def record_success(self) -> None:
        with self.lock:
            self.billing_streak = 0
            self.billing_since = None
            self.rate_limit_streak = 0
            self.error_streak = 0

    def record_error(self, text: str) -> str:
        """Returns "stop" if the lane is now halted, else "retry"."""
        with self.lock:
            self.last_error = text[:300]
            self.last_error_ts = time.time()
            self.error_streak += 1
            if is_billing_error(text):
                self.billing_streak += 1
                if self.billing_since is None:
                    self.billing_since = time.time()
            else:
                self.billing_streak = 0
                self.billing_since = None
            if is_rate_limit(text):
                self.rate_limit_streak += 1
            else:
                self.rate_limit_streak = 0
            if is_deadline(text):
                self.error_streak = 0          # a hung batch says nothing about the lane's health
                self.rate_limit_streak = 0
                return "stop" if self.stopped else "retry"
            if self.stopped is None:
                if self.billing_since is not None and time.time() - self.billing_since > BILLING_STOP_MIN * 60:
                    self.stopped = "credits exhausted"
                elif (self.billing_streak == 0 and self.rate_limit_streak == 0
                      and self.error_streak >= MAX_CONSECUTIVE_ERRORS):
                    self.stopped = "errors"
            return "stop" if self.stopped else "retry"

    def backoff_seconds(self) -> float:
        with self.lock:
            if self.error_streak == 0:
                return 0.0
            if self.billing_streak > 0:
                return float(BILLING_PAUSE_S)
            return float(min(BACKOFF_MAX_S, BACKOFF_BASE_S * 2 ** (self.error_streak - 1)))

    def note_attempt(self, idx: int) -> None:
        with self.lock:
            self.attempts[idx] = self.attempts.get(idx, 0) + 1

    def attempts_left(self, idx: int) -> bool:
        with self.lock:
            return self.attempts.get(idx, 0) < MAX_GEN_ATTEMPTS


def md5_text(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()


def write_manifest(root: Path, config: Path, models: list[Path], prompt_text: str, git_sha: str, allow_drift: bool) -> None:
    """Pin what defines a sample: rendered prompt, run config, model yamls. The sha is recorded, not enforced."""
    cur = {"prompt_md5": md5_text(prompt_text), "config": str(config.relative_to(REPO)), "config_md5": _md5(config),
           "models": {m.stem: _md5(m) for m in models}}
    path = root / "manifest.json"
    root.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        cur.update(git_sha=git_sha, later_shas=[], started_at=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"))
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(cur, indent=2))
        tmp.replace(path)
        return
    old = json.loads(path.read_text())
    drift = [k for k in ("prompt_md5", "config_md5") if old.get(k) != cur[k]]
    drift += [f"model:{m}" for m, h in cur["models"].items() if old.get("models", {}).get(m) not in (None, h)]
    if drift and not allow_drift:
        sys.exit(f"{path}: {', '.join(drift)} changed since this root was started (prompt/config/model yamls are "
                 f"frozen per pool; pass --allow-sha-drift to override)")
    if git_sha != old.get("git_sha") and git_sha not in old.get("later_shas", []):
        old.setdefault("later_shas", []).append(git_sha)
        old["models"] = {**old.get("models", {}), **cur["models"]}
        tmp = path.with_suffix(".json.tmp")          # atomic: another instance may be reading it right now
        tmp.write_text(json.dumps(old, indent=2))
        tmp.replace(path)



def extract_reasoning(entry: dict) -> str:
    """Provider-side reasoning text from one LM-history entry, if the provider returns any.

    Together / Gemini / DeepSeek: `message.reasoning_content` (or provider_specific_fields);
    Anthropic: `thinking_blocks` (text is empty unless display=summarized); OpenAI Responses:
    DSPy hands back dict outputs with `reasoning_content` when a summary was requested.
    """
    parts: list[str] = []
    outputs = entry.get("outputs")
    if isinstance(outputs, list):
        for x in outputs:
            if isinstance(x, dict) and x.get("reasoning_content"):
                parts.append(str(x["reasoning_content"]))
    resp = entry.get("response")
    for choice in (getattr(resp, "choices", None) or []):
        msg = getattr(choice, "message", None)
        if msg is None:
            continue
        rc = getattr(msg, "reasoning_content", None)
        psf = getattr(msg, "provider_specific_fields", None) or {}
        if not rc and isinstance(psf, dict):
            rc = psf.get("reasoning_content")
        if rc:
            parts.append(str(rc))
        for blk in (getattr(msg, "thinking_blocks", None) or []):
            txt = blk.get("thinking") if isinstance(blk, dict) else getattr(blk, "thinking", None)
            if txt:
                parts.append(str(txt))
    return "\n\n".join(parts)


def operator_stop(root: Path, lane: ModelLane, instance: str | None = None, scope: str = "global") -> bool:
    """`touch <root>/STOP-<model>` halts that lane in every global-scope instance at its next
    scheduling point; `STOP-<model>.<instance>` halts it in that instance only. An instance
    started with --stop-scope instance ignores the global file (used to hand a model over from
    an old instance to a new one with a different --per-model without double-dispatch)."""
    candidates = []
    if instance:
        candidates.append(root / f"STOP-{lane.stem}.{instance}")
    if scope == "global":
        candidates.append(root / f"STOP-{lane.stem}")
    if any(c.exists() for c in candidates):
        if lane.stopped is None:
            lane.stopped = "stopped by operator (STOP file)"
        return True
    return False



class GenerationDeadline(Exception):
    """The API call did not return within --gen-deadline-min, or was stranded by a zero balance."""


PROVIDER_DIP: dict[str, float] = {}      # provider -> time the balance was last seen at zero
_DIP_LOCK = threading.Lock()


def note_balance_dip(provider: str) -> None:
    """Record that `provider` just rejected a call for lack of credits. Every call on that provider
    that started before now is presumed stranded (Anthropic leaves such sockets open and silent
    forever) and is abandoned by call_with_deadline at its next poll."""
    with _DIP_LOCK:
        PROVIDER_DIP[provider] = time.time()


def call_with_deadline(fn, deadline_s: float, provider: str | None = None, started: float | None = None):
    """Run fn() in a helper thread (with the caller's contextvars, so USAGE_CTX and dspy's
    thread-local LM context are visible); give up after deadline_s, or as soon as the provider's
    balance is seen at zero after this call started."""
    import contextvars
    box: dict = {}
    ctx = contextvars.copy_context()
    started = time.time() if started is None else started

    def run():
        try:
            box["value"] = ctx.run(fn)
        except BaseException as exc:  # noqa: BLE001
            box["error"] = exc

    t = threading.Thread(target=run, daemon=True, name="gen-call")
    t.start()
    end = time.time() + deadline_s if deadline_s > 0 else float("inf")
    while t.is_alive():
        t.join(min(5.0, max(0.0, end - time.time())) if end != float("inf") else 5.0)
        if not t.is_alive():
            break
        dip = PROVIDER_DIP.get(provider) if provider else None
        if dip is not None and dip > started:
            raise GenerationDeadline(f"stranded: {provider} balance hit zero at "
                                     f"{dt.datetime.fromtimestamp(dip, dt.timezone.utc).strftime('%H:%M:%S')}Z; call abandoned")
        if time.time() >= end:
            raise GenerationDeadline(f"no response after {deadline_s/60:.0f} min; call abandoned")
    if "error" in box:
        raise box["error"]
    return box.get("value")


def in_flight_elsewhere(d: Path, minutes: float) -> bool:
    """True if another instance is probably generating this sample right now: its directory
    exists, holds no result yet, and was touched within `minutes`. Lets a second instance
    (e.g. a higher --per-model relaunch after STOP-ing the old lanes) take over a model
    without double-dispatching the slots still in flight in the old one."""
    if minutes <= 0 or not d.exists():
        return False
    if (d / "gen.json").exists() or (d / "gen_error.json").exists():
        return False
    return (time.time() - d.stat().st_mtime) < minutes * 60



def _forget_history() -> None:
    """dspy appends every LM call (prompt, messages, response) to a process-global list; over
    thousands of samples that is gigabytes (the overnight instance reached 2.3 GB RSS)."""
    try:
        from dspy.clients.base_lm import GLOBAL_HISTORY
        GLOBAL_HISTORY.clear()
    except Exception:
        pass



def save_result(d: Path, rec: dict) -> bool:
    """Write gen.json atomically — but never over an existing one. A slot can be generated twice
    when a retired instance's litellm retry loop completes long after a newer instance has
    already generated (and qualified) the slot; the late result is kept as gen.dup-<ts>.json
    for the record and the qualified sample stays consistent. Returns True if written."""
    target = d / "gen.json"
    if target.exists():
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%H%M%S")
        (d / f"gen.dup-{stamp}.json").write_text(json.dumps(rec, indent=1))
        return False
    tmp = d / "gen.json.tmp"
    tmp.write_text(json.dumps(rec, indent=1))
    tmp.rename(target)
    return True


def sample_dir(root: Path, stem: str, idx: int) -> Path:
    return root / stem / f"c{idx:03d}"


def artifact_path(d: Path, stem: str) -> Path:
    return d / BOTS / stem / "bot_artifact.json"


def scan_status(root: Path, stems: list[str], n_samples: int, lanes: dict[str, ModelLane],
                in_flight_gen: dict[str, int] | None = None, in_flight_qual: dict[str, int] | None = None) -> dict:
    rows = {}
    for stem in stems:
        r = {"target": n_samples, "generated": 0, "gen_failed": 0, "qualified_ok": 0, "forfeit": 0,
             "awaiting_qualification": 0, "qual_error": 0, "gen_wall_min": [], "last_error": "",
             "stopped": lanes[stem].stopped if stem in lanes else None,
             "in_flight_gen": (in_flight_gen or {}).get(stem, 0),
             "in_flight_qual": (in_flight_qual or {}).get(stem, 0)}
        for i in range(n_samples):
            d = sample_dir(root, stem, i)
            gen = d / "gen.json"
            err = d / "gen_error.json"
            art = artifact_path(d, stem)
            if gen.exists():
                r["generated"] += 1
                try:
                    w = json.loads(gen.read_text()).get("wall_s")
                    if w:
                        r["gen_wall_min"].append(w / 60)
                except Exception:
                    pass
                if art.exists():
                    try:
                        if json.loads(art.read_text()).get("forfeit"):
                            r["forfeit"] += 1
                        else:
                            r["qualified_ok"] += 1
                    except Exception:
                        r["qual_error"] += 1
                elif (d.with_suffix(".log")).exists() and (d / "qual_failed").exists():
                    r["qual_error"] += 1
                else:
                    r["awaiting_qualification"] += 1
            elif err.exists():
                r["gen_failed"] += 1
                try:
                    r["last_error"] = json.loads(err.read_text()).get("error", "")[:120]
                except Exception:
                    pass
        r["remaining"] = max(0, n_samples - r["generated"] - r["gen_failed"])
        if stem in lanes and lanes[stem].last_error and not r["last_error"]:
            r["last_error"] = lanes[stem].last_error[:120]
        r["last_error_ts"] = lanes[stem].last_error_ts if stem in lanes else None
        rows[stem] = r
    return rows


def render_status_md(root: Path, rows: dict, started: str, extra: dict | None = None) -> str:
    extra = extra or {}
    now = dt.datetime.now(dt.timezone.utc)
    tot = {k: sum(r[k] for r in rows.values()) for k in
           ("target", "generated", "gen_failed", "qualified_ok", "forfeit", "awaiting_qualification", "qual_error", "remaining")}
    lines = [f"# SH-250 sampling pool — status", "",
             f"- root: `{root}`", f"- started: {started}", f"- updated: {now.isoformat(timespec='seconds')}",
             f"- git sha: {extra.get('git_sha', '?')}",
             f"- free disk: {extra.get('free_disk_gb', '?')} GB (stage 2 pauses under {extra.get('min_free_gb', '?')} GB)",
             f"- in flight: {extra.get('in_flight_gen', 0)} API calls, {extra.get('in_flight_qual', 0)} qualification processes",
             f"- samples: **{tot['generated']}/{tot['target']} generated**, {tot['qualified_ok']} qualified, "
             f"{tot['forfeit']} forfeit, {tot['awaiting_qualification']} awaiting qualification, "
             f"{tot['gen_failed']} generation failures, {tot['qual_error']} qualification errors, {tot['remaining']} remaining",
             f"- rate: {extra.get('rate_per_h', '?')} samples/h, ETA {extra.get('eta', '?')}",
             ""]
    stopped = [(s, r["stopped"]) for s, r in rows.items() if r["stopped"]]
    if stopped:
        lines.append("**Stopped lanes:** " + ", ".join(f"{s} ({why})" for s, why in stopped))
        lines.append("")
    lines.append("| model | generated | failed | qualified OK | forfeit | awaiting qual | qual err | remaining | in flight | gen min (mean) | stopped | last error |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|")
    for stem, r in rows.items():
        mean = f"{sum(r['gen_wall_min'])/len(r['gen_wall_min']):.1f}" if r["gen_wall_min"] else "-"
        lines.append(f"| {stem} | {r['generated']}/{r['target']} | {r['gen_failed']} | {r['qualified_ok']} | {r['forfeit']} | "
                     f"{r['awaiting_qualification']} | {r['qual_error']} | {r['remaining']} | {r['in_flight_gen']}+{r['in_flight_qual']} | "
                     f"{mean} | {r['stopped'] or ''} | {r['last_error'].replace('|', '/')} |")
    lines.append("")
    lines.append(f"Columns: generated = API call succeeded and outputs saved; failed = API call failed after retries "
                 "(see gen_error.json); qualified OK / forfeit = build pipeline finished (forfeit = design failed validation "
                 "or qualification, a legitimate sample); awaiting qual = generated, waiting for a worker; "
                 "in flight = API calls + qualification processes right now; stopped = lane halted (credits exhausted = "
                 "two consecutive billing errors; errors = {MAX_CONSECUTIVE_ERRORS} consecutive failures of any kind; a transient failure retries the sample up to {MAX_GEN_ATTEMPTS} times with exponential lane backoff).")
    return "\n".join(lines) + "\n"


def compact_sample(d: Path, stem: str) -> int:
    """gzip the qualification trace, drop videos; returns bytes saved."""
    saved = 0
    bot = d / BOTS / stem
    for raw in bot.rglob("match_data.json"):
        gz = raw.with_suffix(".json.gz")
        with open(raw, "rb") as src, gzip.open(gz, "wb", compresslevel=6) as dst:
            shutil.copyfileobj(src, dst)
        saved += raw.stat().st_size - gz.stat().st_size
        raw.unlink()
    for vid in list(bot.rglob("*.webm")) + list(bot.rglob("*.mp4")):
        saved += vid.stat().st_size
        vid.unlink()
    return saved


def merge_usage(d: Path, stem: str) -> None:
    """Prepend the generation-stage usage rows to the bot's usage.jsonl."""
    gen_usage = d / "gen/refinement/usage.jsonl"
    if not gen_usage.exists():
        return
    bot_usage = d / BOTS / stem / "refinement/usage.jsonl"
    bot_usage.parent.mkdir(parents=True, exist_ok=True)
    existing = bot_usage.read_text() if bot_usage.exists() else ""
    bot_usage.write_text(gen_usage.read_text() + existing)
    gen_usage.unlink()
    try:
        gen_usage.parent.rmdir(); gen_usage.parent.parent.rmdir()
    except OSError:
        pass


# ── orchestrator ─────────────────────────────────────────────────────────────

def _git_sha() -> str:
    """HEAD of the checkout, or the commit recorded in SHIPPED_SHA for a `git archive` tree on a cluster."""
    proc = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True)
    if proc.returncode == 0:
        return proc.stdout.strip()
    shipped = REPO / "SHIPPED_SHA"
    if shipped.exists() and shipped.read_text().strip():
        return shipped.read_text().strip()
    raise RuntimeError(f"not a git checkout and no SHIPPED_SHA in {REPO}: {proc.stderr.strip()}")


def _md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def _free_gb(path: Path) -> float:
    return shutil.disk_usage(path).free / 1e9


class Pool:
    def __init__(self, a):
        self.a = a
        self.root = Path(a.root) if Path(a.root).is_absolute() else REPO / a.root
        self.config = REPO / a.config
        llms = yaml.safe_load(self.config.read_text())["llms"]
        self.models = [REPO / p for p in llms if not a.models or any(f in p for f in a.models)]
        if not self.models:
            sys.exit("no models selected")
        self.stems = [m.stem for m in self.models]
        self.lanes = {s: ModelLane(s) for s in self.stems}
        self.in_flight_gen: dict[str, int] = {s: 0 for s in self.stems}
        self.in_flight_qual: dict[str, int] = {s: 0 for s in self.stems}
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.qual_q: queue.Queue = queue.Queue()
        self.queued: set[tuple[str, int]] = set()
        self.done_since_start = 0
        self.started = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        self.t0 = time.time()
        self.sha = _git_sha()
        self.instance = Path(a.status_name).stem.replace("STATUS-", "").replace("STATUS", "main") or "main"

    # -- manifest / prompt ------------------------------------------------------
    def setup(self):
        self.root.mkdir(parents=True, exist_ok=True)
        import mjarena.core.unified_builder  # noqa: F401
        from run_baseline_agent import config_to_args, load_tournament_config
        from mjarena.core.unified_builder import load_consolidated_prompt
        args = config_to_args(load_tournament_config(self.config))
        cfg = args["cfg"]
        assert cfg.zero_shot_mode and cfg.commit_budget == 1, "run_pool is for the zero-shot sampling config"
        _, self.prompt_text = load_consolidated_prompt(cfg)
        write_manifest(self.root, self.config, self.models, self.prompt_text, self.sha, self.a.allow_sha_drift)
        (self.root / "sampling_prompt.rendered.md").write_text(self.prompt_text)
        (self.root / "prompt.md5").write_text(md5_text(self.prompt_text) + "\n")
        if self.a.retry_failed:
            n = 0
            for m in self.models:
                for i in range(self.a.n_samples):
                    e = sample_dir(self.root, m.stem, i) / "gen_error.json"
                    if e.exists():
                        e.unlink(); n += 1
                        os.utime(e.parent, (0, 0))   # not "in flight elsewhere": free for this instance
            print(f"[pool] --retry-failed: cleared {n} gen_error.json", flush=True)

    # -- stage 1: one API call ----------------------------------------------------
    def generate_one(self, model: Path, idx: int) -> str:
        import dspy
        from mjarena.dspy_core import USAGE_CTX, configure_lm
        from mjarena.design_shop.agents.L1_engineer_unified import build_engineer, refusal_detail
        from mjarena.design_shop.agents.signatures.sampling import make_sampling_signature
        stem = model.stem
        d = sample_dir(self.root, stem, idx)
        d.mkdir(parents=True, exist_ok=True)
        os.utime(d, None)              # mark "in flight" for in_flight_elsewhere() in other instances
        gen_bot_dir = d / "gen"          # usage rows land here, merged into the bot dir after stage 2
        lm = configure_lm(str(model), use_cache=False)
        provider = lm.model.split("/")[0]
        engineer = build_engineer(make_sampling_signature(self.prompt_text))
        token = USAGE_CTX.set({"bot": stem, "commit": 0, "role": "engineer", "output_dir": str(gen_bot_dir)})
        t0 = time.time()
        try:
            def _call():
                with dspy.context(lm=lm):
                    return engineer()
            deadline = self.a.gen_deadline_min * 60
            result = call_with_deadline(_call, deadline, provider=provider, started=t0)
            outputs = {k: getattr(result, k, "") for k in engineer.signature.output_fields}
            rec = {"model": str(model.relative_to(REPO)), "stem": stem, "idx": idx, "outputs": outputs,
                   "llm_calls": len(lm.history), "wall_s": round(time.time() - t0, 1),
                   "ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "git_sha": self.sha}
            for k, entry in enumerate(lm.history):
                resp = entry.get("outputs", entry.get("response"))
                txt = ""
                if isinstance(resp, list):
                    txt = "\n".join(x.get("text", "") if isinstance(x, dict) else str(x) for x in resp)
                elif isinstance(resp, str):
                    txt = resp
                else:
                    try:
                        txt = resp.choices[0].message.content or ""
                    except Exception:
                        txt = str(resp)[:20000]
                suffix = "" if not (d / "gen.json").exists() else f".dup-{dt.datetime.now(dt.timezone.utc).strftime('%H%M%S')}"
                (d / f"raw_response_{k}{suffix}.txt").write_text(txt)
                reasoning = extract_reasoning(entry)
                if reasoning:
                    (d / f"raw_reasoning_{k}{suffix}.txt").write_text(reasoning)
            rec["reasoning_chars"] = sum(len(extract_reasoning(e)) for e in lm.history)
            written = save_result(d, rec)
            _forget_history()   # dspy's GLOBAL_HISTORY keeps every prompt+response for the process lifetime
            self.lanes[stem].record_success()
            if not written:
                print(f"[gen ] {stem:28} c{idx:03d} late duplicate result kept as gen.dup-*.json (slot already generated)", flush=True)
                return "ok"
            with self.lock:
                self.enqueue_qual(stem, idx)
            return "ok"
        except Exception as exc:
            refusal = refusal_detail(lm.history)
            text = f"{type(exc).__name__}: {str(exc)[:1500]}"
            full = text if not refusal else f"{refusal}; {text}"
            lane = self.lanes[stem]
            if is_billing_error(full):
                note_balance_dip(provider)  # every call on this provider started before now is stranded
            if not is_billing_error(full) and not is_rate_limit(full):
                lane.note_attempt(idx)      # a zero balance or throttling is not the sample's fault
            decision = lane.record_error(full)
            if decision == "retry" and lane.attempts_left(idx):
                print(f"[gen ] {stem:28} c{idx:03d} attempt failed, will retry after {lane.backoff_seconds():.0f}s backoff: {text[:120]}", flush=True)
                return "retry"
            _forget_history()
            (d / "gen_error.json").write_text(json.dumps({"error": full, "refusal": refusal,
                                                          "attempts": lane.attempts.get(idx, 1),
                                                          "wall_s": round(time.time() - t0, 1),
                                                          "ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}, indent=1))
            print(f"[gen ] {stem:28} c{idx:03d} FAILED after {lane.attempts.get(idx, 1)} attempts: {text[:160]}", flush=True)
            return "failed"
        finally:
            USAGE_CTX.reset(token)

    def gen_worker(self, model: Path, q: queue.Queue) -> None:
        stem = model.stem
        lane = self.lanes[stem]
        while not self.stop.is_set():
            if lane.stopped or operator_stop(self.root, lane, self.instance, self.a.stop_scope):
                return
            try:
                idx = q.get(timeout=5)
            except queue.Empty:
                if self.in_flight_gen[stem] == 0:
                    return          # nothing queued and nobody about to requeue
                continue
            wait = lane.backoff_seconds()
            if wait and self.stop.wait(wait):
                q.put(idx); return
            if lane.stopped or operator_stop(self.root, lane, self.instance, self.a.stop_scope):
                q.put(idx); return
            with self.lock:
                self.in_flight_gen[stem] += 1
            try:
                outcome = self.generate_one(model, idx)
                if outcome == "retry":
                    q.put(idx)          # requeue BEFORE the in-flight count drops, so no worker exits early
            except Exception as exc:
                print(f"[gen ] {stem} c{idx:03d} launcher error: {exc!r}", flush=True)
            finally:
                with self.lock:
                    self.in_flight_gen[stem] -= 1

    # -- stage 2: replay through the real build ------------------------------------
    def enqueue_qual(self, stem: str, idx: int) -> None:
        if (stem, idx) not in self.queued:
            self.queued.add((stem, idx))
            self.qual_q.put((stem, idx))

    def qualify_one(self, stem: str, idx: int) -> None:
        model = next(m for m in self.models if m.stem == stem)
        d = sample_dir(self.root, stem, idx)
        log = d.with_suffix(".log")
        env = dict(os.environ)
        env.pop("MUJOCO_GL", None)
        env["ARENA_REPLAY_OUTPUTS"] = str(d / "gen.json")
        cmd = time_prefix() + [PY, "run_baseline_agent.py", "--config", str(self.config), "--llms", str(model),
               "--iterations", "1", "--build-only", "--output-dir", str(d)]
        t0 = time.time()
        with open(log, "w") as fh:
            rc = subprocess.call(cmd, cwd=REPO, stdout=fh, stderr=subprocess.STDOUT, env=env)
        wall = time.time() - t0
        art = artifact_path(d, stem)
        rec = {"model": stem, "idx": idx, "stage": "qual", "exit": rc, "wall_s": round(wall, 1),
               "finished_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
        if art.exists():
            a = json.loads(art.read_text())
            rec.update(forfeit=a.get("forfeit"), forfeit_stage=a.get("forfeit_stage"),
                       forfeit_error=(a.get("forfeit_error") or "")[:200], controller_score=a.get("controller_score"))
            merge_usage(d, stem)
            rec["saved_mb"] = round(compact_sample(d, stem) / 2**20, 1)
        else:
            rec["forfeit"] = None
            (d / "qual_failed").write_text(f"exit={rc}\n")
        rec["disk_mb"] = round(sum(p.stat().st_size for p in d.rglob("*") if p.is_file()) / 2**20, 1)
        with self.lock:
            with open(self.root / "progress.jsonl", "a") as fh:
                fh.write(json.dumps(rec) + "\n")
            self.done_since_start += 1
        status = "OK" if art.exists() and not rec["forfeit"] else ("FORFEIT" if art.exists() else "QUAL-ERROR")
        print(f"[qual] {stem:28} c{idx:03d} {status:10} exit={rc} wall={wall/60:4.1f}m disk={rec['disk_mb']}MB "
              f"{rec.get('forfeit_error', '')[:80]}", flush=True)

    def qual_worker(self) -> None:
        while not self.stop.is_set():
            try:
                stem, idx = self.qual_q.get(timeout=5)
            except queue.Empty:
                if self.gen_done.is_set():
                    return
                continue
            while _free_gb(self.root) < self.a.min_free_gb and not self.stop.is_set():
                self.paused_disk = True
                time.sleep(60)
            self.paused_disk = False
            with self.lock:
                self.in_flight_qual[stem] += 1
            try:
                self.qualify_one(stem, idx)
            except Exception as exc:
                print(f"[qual] {stem} c{idx:03d} worker error: {exc!r}", flush=True)
            finally:
                with self.lock:
                    self.in_flight_qual[stem] -= 1

    # -- balance canary ------------------------------------------------------------
    def canary_loop(self) -> None:
        """While a provider has calls in flight, probe it every 60 s with a 1-token call; a billing
        rejection means the balance hit zero and every in-flight call on it is stranded — abandon
        them now rather than at the deadline (a busy lane never dispatches, so it would never see
        the rejection itself)."""
        import litellm
        by_provider: dict[str, Path] = {}
        for m in self.models:
            spec = yaml.safe_load(m.read_text())
            by_provider.setdefault(spec["model"].split("/")[0], m)
        while not self.stop.is_set():
            self.stop.wait(60)
            for provider, m in by_provider.items():
                busy = any(self.in_flight_gen.get(x.stem, 0) for x in self.models
                           if yaml.safe_load(x.read_text())["model"].split("/")[0] == provider)
                if not busy:
                    continue
                try:
                    litellm.completion(model=yaml.safe_load(m.read_text())["model"], max_tokens=1, timeout=30,
                                       messages=[{"role": "user", "content": "hi"}], num_retries=0)
                except Exception as exc:  # noqa: BLE001
                    if is_billing_error(str(exc)):
                        note_balance_dip(provider)
                        print(f"[canary] {provider}: balance at zero — abandoning its in-flight calls", flush=True)

    # -- status ------------------------------------------------------------------
    def write_status(self) -> None:
        rows = scan_status(self.root, self.stems, self.a.n_samples, self.lanes, self.in_flight_gen, self.in_flight_qual)
        done = sum(r["qualified_ok"] + r["forfeit"] for r in rows.values())
        remaining = sum(r["remaining"] + r["awaiting_qualification"] for r in rows.values())
        hours = (time.time() - self.t0) / 3600
        rate = self.done_since_start / hours if hours > 0.05 else 0
        eta = f"{remaining / rate:.1f} h" if rate > 0 else "n/a"
        extra = {"git_sha": self.sha[:10], "free_disk_gb": round(_free_gb(self.root), 1), "min_free_gb": self.a.min_free_gb,
                 "in_flight_gen": sum(self.in_flight_gen.values()), "in_flight_qual": sum(self.in_flight_qual.values()),
                 "rate_per_h": round(rate, 1), "eta": eta + (" (stage 2 PAUSED: low disk)" if getattr(self, "paused_disk", False) else "")}
        md = render_status_md(self.root, rows, self.started, extra)
        name = self.a.status_name
        (self.root / name).write_text(md)
        (REPO / f"SH250_{name}").write_text(md)
        json.dump({"updated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "rows": {k: {kk: vv for kk, vv in v.items() if kk != "gen_wall_min"} for k, v in rows.items()}, **extra},
                  open(self.root / name.replace(".md", ".json").replace("STATUS", "status"), "w"), indent=1)

    def status_loop(self) -> None:
        while not self.stop.is_set():
            try:
                self.write_status()
            except Exception as exc:
                print(f"[status] error: {exc!r}", flush=True)
            self.stop.wait(self.a.status_every)
        self.write_status()

    # -- main -------------------------------------------------------------------
    def run(self) -> None:
        self.setup()
        self.paused_disk = False
        self.gen_done = threading.Event()
        # queues: every sample without gen.json / gen_error.json, per model, in index order
        gen_queues: dict[str, queue.Queue] = {}
        n_gen = 0
        n_skip = 0
        for m in self.models:
            q = queue.Queue()
            for i in range(self.a.n_samples):
                d = sample_dir(self.root, m.stem, i)
                if (d / "gen.json").exists():
                    if not artifact_path(d, m.stem).exists() and not (d / "qual_failed").exists():
                        self.enqueue_qual(m.stem, i)
                elif not (d / "gen_error.json").exists():
                    if in_flight_elsewhere(d, self.a.skip_recent_min):
                        n_skip += 1
                        continue
                    q.put(i); n_gen += 1
            gen_queues[m.stem] = q
        print(f"[pool] {len(self.models)} models x {self.a.n_samples}: {n_gen} to generate, "
              f"{n_skip} skipped (in flight in another instance), "
              f"{self.qual_q.qsize()} awaiting qualification; per-model {self.a.per_model}, "
              f"qual workers {self.a.qual_workers}, root={self.root}, sha={self.sha[:10]}", flush=True)
        threads = []
        for m in self.models:
            for k in range(self.a.per_model):
                t = threading.Thread(target=self.gen_worker, args=(m, gen_queues[m.stem]), daemon=True, name=f"gen-{m.stem}-{k}")
                t.start(); threads.append(t)
        quals = [threading.Thread(target=self.qual_worker, daemon=True, name=f"qual-{k}") for k in range(self.a.qual_workers)]
        for t in quals:
            t.start()
        st = threading.Thread(target=self.status_loop, daemon=True, name="status")
        st.start()
        threading.Thread(target=self.canary_loop, daemon=True, name="canary").start()

        def _sig(signum, frame):
            print(f"[pool] signal {signum}: stopping (in-flight samples finish, nothing new starts)", flush=True)
            self.stop.set()
        signal.signal(signal.SIGTERM, _sig)
        signal.signal(signal.SIGINT, _sig)

        for t in threads:
            t.join()
        self.gen_done.set()
        print("[pool] generation stage finished; draining qualification queue", flush=True)
        for t in quals:
            t.join()
        self.stop.set()
        st.join(timeout=30)
        self.write_status()
        print(f"[pool] ALL DONE in {(time.time()-self.t0)/3600:.2f} h", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="configs/tournaments/sh.yaml")
    ap.add_argument("--root", required=True)
    ap.add_argument("--n-samples", type=int, default=250)
    ap.add_argument("--per-model", type=int, default=20, help="API calls in flight per model")
    ap.add_argument("--qual-workers", type=int, default=os.cpu_count() or 8, help="qualification subprocesses")
    ap.add_argument("--min-free-gb", type=float, default=2.5, help="stage 2 pauses below this much free disk")
    ap.add_argument("--stop-scope", choices=["global", "instance"], default="global", help="which STOP files halt this instance's lanes: global = STOP-<model> and STOP-<model>.<instance>; instance = only the latter")
    ap.add_argument("--skip-recent-min", type=float, default=0, help="skip sample slots whose directory was touched within N minutes and has no result: another instance is generating them (0 = off)")
    ap.add_argument("--gen-deadline-min", type=float, default=0, help="abandon an API call that has not returned after this many minutes (0 = never); it is retried like any failure")
    ap.add_argument("--status-every", type=int, default=30, help="seconds between STATUS.md rewrites")
    ap.add_argument("--models", nargs="*", default=[], help="substring filters on model yaml paths")
    ap.add_argument("--allow-sha-drift", action="store_true", help="continue a root whose prompt/config/model yamls changed")
    ap.add_argument("--retry-failed", action="store_true", help="on resume, clear gen_error.json so failed samples get MAX_GEN_ATTEMPTS again")
    ap.add_argument("--status-name", default="STATUS.md", help="status file name (a second instance on the same root, e.g. --models anthropic/, must use its own, e.g. STATUS-claude.md)")
    ap.add_argument("--status", action="store_true", help="print the status file for --root and exit")
    a = ap.parse_args()
    if a.status:
        root = Path(a.root) if Path(a.root).is_absolute() else REPO / a.root
        print((root / a.status_name).read_text())
        return
    Pool(a).run()


if __name__ == "__main__":
    main()
