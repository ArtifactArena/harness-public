#!/usr/bin/env python
"""Per-model progress + spend for an SH-250 root: done / valid / remaining and the money
already spent and still expected, so credits can be topped up per provider.

    python scripts/sampling/cost_report.py --root LOGS-SH250/20260918            # prints + writes <root>/COST.{md,html} and <repo>/SH250_COST.{md,html}
    python scripts/sampling/cost_report.py --root LOGS-SH250/20260918 --loop     # rewrite every 60 s (--loop 300 for 5 min)

Spend is computed from every usage.jsonl row (prompt + completion tokens x litellm's
per-token price for that model; provider cache discounts ignored, so it is a slight
over-estimate). "Expected to finish" = remaining samples x the model's mean cost per
generated sample so far. A model with no priced samples yet is priced at the mean
$/sample of the most expensive SAME-PROVIDER model that has samples (roster-median
token counts at its own list prices only when the provider has no samples at all) and
marked "est.". A lane with a `STOP-<model>` file in the root is killed: its remaining
samples will not be generated, so it expects $0; it is hidden from the tables and listed under them.

The HTML dashboard is self-contained (inline CSS, no scripts, no auto-refresh: a sticky Refresh
button — an empty-href link — reloads the file) and opens as a local file. It also merges the live `<root>/status*.json` files that
the run_pool instances write (main / claude / openai ...): per model the row of the instance that
has work in flight wins, else the un-stopped row, else the most recently updated file.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import math
import os
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
BOTS = "tournament_00/round_robin_match/bots"
RECENT_ERROR_MIN = 10   # a lane's last error is shown only if it happened this recently
PROVIDER = {"anthropic": "Anthropic", "openai": "OpenAI", "gemini": "Google", "xai": "xAI", "together_ai": "Together"}

# Credits already loaded onto each provider account for this run (hand-maintained, USD).
ALREADY_LOADED: dict[str, float] = {"Anthropic": 850, "OpenAI": 420}
TOPUP_MARGIN = 1.25      # recommended top-up = minimum x margin, rounded UP to the nearest $10
TOPUP_ROUND = 10
REFRESH_S = 60           # the --loop default (how often the files are regenerated)
STALE_MIN = 3.0          # a status file older than this is flagged: the instance is probably dead

# The run_pool instances sharing the root, keyed by status-file suffix ("" = status.json = main).
# Used only for the Controls box (resume commands); pid files are <repo>/<root-parent>-<root-name>[-<inst>].pid.
INSTANCE_CMDS: dict[str, str] = {
    "main": "--per-model 20 --qual-workers 10 --status-every 30",
    "claude": ("--per-model 20 --qual-workers 4 --status-every 30 --gen-deadline-min 45 "
               "--models claude-fable-5-1 claude-fable-5-high claude-opus-5 claude-sonnet-5 claude-opus-4-8 "
               "--status-name STATUS-claude.md"),
    "openai": "--per-model 20 --qual-workers 3 --status-every 30 --gen-deadline-min 45 --models openai/ --status-name STATUS-openai.md",
}


def _prices(model: str) -> tuple[float, float]:
    # NOTE: do not import mjarena before this — mjarena.dspy_core rewrites some litellm.model_cost
    # entries (reasoning flags / max_tokens) and the rewritten entries carry no prices.
    import litellm
    for key in (model, model.split("/", 1)[1]):
        info = litellm.model_cost.get(key) or {}
        if info.get("input_cost_per_token") is not None:
            return float(info["input_cost_per_token"]), float(info.get("output_cost_per_token") or 0)
    return 0.0, 0.0



def _running_now(root: Path) -> dict[str, int]:
    """model -> in-flight API calls across every live status file (cached per process second)."""
    key = (str(root), int(time.time()))
    if _running_now.cache.get("key") != key:
        try:
            live = merge_status(load_status(root))
            _running_now.cache = {"key": key, "val": {m: int(v.get("in_flight_gen") or 0) for m, v in live.items()}}
        except Exception:
            _running_now.cache = {"key": key, "val": {}}
    return _running_now.cache["val"]


_running_now.cache = {}


def report(root: Path, config: Path, n_samples: int) -> tuple[list[dict], dict]:
    roster = yaml.safe_load(config.read_text())["llms"]
    rows = []
    for rel in roster:
        stem = Path(rel).stem
        spec = yaml.safe_load((REPO / rel).read_text())
        model = spec["model"]
        p_in, p_out = _prices(model)
        r = {"model": stem, "provider": PROVIDER.get(model.split("/")[0], model.split("/")[0]),
             "generated": 0, "valid": 0, "forfeit": 0, "awaiting": 0, "failed": 0,
             "spent": 0.0, "per_sample": [], "gen_min": [], "tok_prompt": [], "tok_comp": [], "p_in": p_in, "p_out": p_out,
             "killed": False, "est_basis": None}   # decided below once counts are known
        for i in range(n_samples):
            d = root / stem / f"c{i:03d}"
            if (d / "gen_error.json").exists():
                r["failed"] += 1
            if not (d / "gen.json").exists():
                continue
            r["generated"] += 1
            try:
                g = json.loads((d / "gen.json").read_text())
                if g.get("wall_s"):
                    r["gen_min"].append(g["wall_s"] / 60)
            except Exception:
                pass
            art = d / BOTS / stem / "bot_artifact.json"
            if art.exists():
                try:
                    if json.loads(art.read_text()).get("forfeit"):
                        r["forfeit"] += 1
                    else:
                        r["valid"] += 1
                except Exception:
                    r["awaiting"] += 1
            else:
                r["awaiting"] += 1
            cost = 0.0
            for usage in (d / BOTS / stem / "refinement/usage.jsonl", d / "gen/refinement/usage.jsonl"):
                if usage.exists():
                    for line in usage.read_text().splitlines():
                        try:
                            u = json.loads(line)
                        except Exception:
                            continue
                        cost += (u.get("prompt_tokens") or 0) * p_in + (u.get("completion_tokens") or 0) * p_out
                        if u.get("completion_tokens"):
                            r["tok_prompt"].append(u.get("prompt_tokens") or 0); r["tok_comp"].append(u["completion_tokens"])
            r["spent"] += cost
            if cost:
                r["per_sample"].append(cost)
        r["remaining"] = max(0, n_samples - r["generated"])
        # killed = an operator STOP file, nothing running the lane anywhere, and work left undone.
        # A finished lane or one being handed over between instances is not killed.
        r["killed"] = (root / f"STOP-{stem}").exists() and _running_now(root).get(stem, 0) == 0 and r["remaining"] > 0
        rows.append(r)
    # Priced models first; then price the rest at same-provider mean token counts x this model's
    # own list price. Last resort (provider with no samples at all): the roster's median prompt/
    # completion token counts at THIS model's own list prices (a Fable sample is not a Luna sample).
    for r in rows:
        if r["per_sample"]:
            r["mean_cost"] = statistics.mean(r["per_sample"]); r["estimated"] = False
    all_prompt = [t for r in rows for t in r["tok_prompt"]]
    all_comp = [t for r in rows for t in r["tok_comp"]]
    med_prompt = statistics.median(all_prompt) if all_prompt else 20000
    med_comp = statistics.median(all_comp) if all_comp else 25000
    for r in rows:
        if r["per_sample"]:
            continue
        r["estimated"] = True
        # Same-provider TOKEN counts (how long a design runs on this provider) at THIS model's
        # own list prices: a Sonnet sample is not a Fable sample in dollars, but it is in tokens.
        peers = [q for q in rows if q["provider"] == r["provider"] and q["per_sample"]]
        if peers:
            pp = statistics.mean(t for q in peers for t in q["tok_prompt"])
            pc = statistics.mean(t for q in peers for t in q["tok_comp"])
            r["mean_cost"] = pp * r["p_in"] + pc * r["p_out"]
            r["est_basis"] = f"{r['provider']} mean tokens ({pp:,.0f} in / {pc:,.0f} out) at this model's price"
        else:
            r["mean_cost"] = med_prompt * r["p_in"] + med_comp * r["p_out"]; r["est_basis"] = "roster median"
    for r in rows:
        r["expected"] = 0.0 if r["killed"] else r["remaining"] * r["mean_cost"]
        r["remaining_active"] = 0 if r["killed"] else r["remaining"]
    by_provider: dict[str, dict] = defaultdict(lambda: {"spent": 0.0, "expected": 0.0, "remaining": 0, "remaining_active": 0,
                                                         "valid": 0, "generated": 0, "killed": [], "estimated": []})
    for r in rows:
        p = by_provider[r["provider"]]
        p["spent"] += r["spent"]                 # real money, killed or not
        if r["killed"]:                          # hidden from the tables; listed under them
            p["killed"].append(r)
            continue
        for k in ("expected", "remaining", "remaining_active", "valid", "generated"):
            p[k] += r[k]
        if r["estimated"] and r["remaining"]:
            p["estimated"].append(r)
    return rows, by_provider


def load_status(root: Path, now: dt.datetime | None = None) -> list[dict]:
    """One entry per <root>/status*.json: name (main / claude / openai ...), updated, age_min, data."""
    now = now or dt.datetime.now(dt.timezone.utc)
    out = []
    for f in sorted(root.glob("status*.json")):       # non-recursive: <root>/retired/ is ignored
        if not f.is_file():
            continue
        name = f.stem[len("status"):].lstrip("-") or "main"
        alive, pid = _instance_alive(root, name)
        try:
            d = json.loads(f.read_text())
            upd = dt.datetime.fromisoformat(d["updated"])
            if upd.tzinfo is None:
                upd = upd.replace(tzinfo=dt.timezone.utc)
        except Exception as ex:
            out.append({"name": name, "file": f, "updated": None, "age_min": math.inf, "data": {}, "error": f"{type(ex).__name__}: {ex}",
                        "alive": alive, "pid": pid})
            continue
        out.append({"name": name, "file": f, "updated": upd, "age_min": (now - upd).total_seconds() / 60, "data": d, "error": None,
                    "alive": alive, "pid": pid})
    return out


def _instance_alive(root: Path, name: str) -> tuple[bool | None, int | None]:
    """(alive, pid) from <repo>/<pid file>: True/False when the pid file exists (os.kill(pid, 0)), None when there is none."""
    pf = REPO / _pid_file(root, name)
    if not pf.exists():
        return None, None
    try:
        pid = int(pf.read_text().split()[0])
    except Exception:
        return None, None
    try:
        os.kill(pid, 0)
        return True, pid
    except ProcessLookupError:
        return False, pid
    except PermissionError:      # exists, owned by someone else
        return True, pid


def instance_state(inst: dict) -> str:
    """'alive' | 'retired' (process gone) | 'dead' (no pid file, stale snapshot still claiming work) | 'idle' (no pid file, stale, nothing claimed)."""
    if inst["alive"] is True:
        return "alive"
    if inst["alive"] is False:
        return "retired"
    if inst["age_min"] <= STALE_MIN:
        return "alive"
    d = inst["data"]
    claims = bool((d.get("in_flight_gen") or 0) or (d.get("in_flight_qual") or 0) or any(
        (row.get("in_flight_gen") or 0) or (row.get("in_flight_qual") or 0) for row in (d.get("rows") or {}).values()))
    return "dead" if claims else "retired"


def merge_status(instances: list[dict]) -> dict[str, dict]:
    """model stem -> its live row + 'instance' (the owning instance name).

    Preference per model: an alive instance with work in flight; else the alive instance with the
    freshest snapshot; only then anything retired/dead (whose in-flight counts are zeroed)."""
    cands: dict[str, list[tuple[dict, dict]]] = defaultdict(list)
    for inst in instances:
        gone = instance_state(inst) in ("retired", "dead")
        for m, row in (inst["data"].get("rows") or {}).items():
            if gone:
                row = {**row, "in_flight_gen": 0, "in_flight_qual": 0}
            cands[m].append((inst, row))
    merged = {}
    for m, lst in cands.items():
        def key(c):
            inst, row = c
            active = (row.get("in_flight_gen") or 0) > 0 or (row.get("in_flight_qual") or 0) > 0
            # alive first; then work in flight; then a lane that is NOT stopped (a newer instance holding
            # the lane open beats an older alive instance's stale stop); freshness only breaks ties.
            return (instance_state(inst) == "alive", active, row.get("stopped") is None,
                    inst["updated"] or dt.datetime.min.replace(tzinfo=dt.timezone.utc))
        inst, row = max(lst, key=key)
        merged[m] = {**row, "instance": inst["name"]}
    return merged


def topup_rows(by_provider: dict) -> list[dict]:
    """The decision table: one row per provider plus a totals row (key 'provider' == 'total')."""
    out = []
    for p, v in sorted(by_provider.items()):
        minimum = v["expected"]
        rec = math.ceil(minimum * TOPUP_MARGIN / TOPUP_ROUND) * TOPUP_ROUND if minimum > 0 else 0
        loaded = float(ALREADY_LOADED.get(p, 0))
        notes = []
        for r in v["estimated"]:
            notes.append(f"{r['model']} est. at {r['est_basis']} rate ${r['mean_cost']:.2f}/sample")
        for r in v["killed"]:
            notes.append(f"{r['model']} killed ({r['remaining']} not run, $0)")
        if v["remaining_active"] == 0:
            notes.insert(0, "complete" if not v["killed"] else "no active lanes left")
        out.append({"provider": p, "remaining": v["remaining_active"], "minimum": minimum, "recommended": rec,
                    "loaded": loaded, "still": max(0.0, rec - loaded), "note": "; ".join(notes)})
    tot = {"provider": "total", "note": ""}
    for k in ("remaining", "minimum", "recommended", "loaded", "still"):
        tot[k] = sum(x[k] for x in out)
    out.append(tot)
    return out


def _totals(rows: list[dict]) -> dict:
    """Totals over the active lanes; only `spent` counts killed lanes too (the money is gone either way)."""
    active = [r for r in rows if not r["killed"]]
    t = {k: sum(r[k] for r in active) for k in ("generated", "valid", "forfeit", "awaiting", "remaining", "remaining_active", "expected")}
    t["spent"] = sum(r["spent"] for r in rows)
    return t


def excluded_lanes(rows: list[dict]) -> list[str]:
    """One entry per killed lane: 'model — N generated, M valid'."""
    return [f"{r['model']} — {r['generated']} generated, {r['valid']} valid" for r in rows if r["killed"]]


FOOTNOTE = ("done = API call succeeded and outputs saved; valid = passed validation and qualification (a usable pool bot); "
            "forfeit = a real sample whose design failed; awaiting qual = generated, not yet replayed through the build; "
            "$/sample = mean over this model's generated samples (prompt + completion tokens x list price, cache discounts "
            "ignored; est. = no samples yet: priced at the same-provider mean token counts x this model's list price); expected = remaining x $/sample "
            "($0 for a killed lane — a STOP-<model> file in the root).")


def render(root: Path, rows: list[dict], by_provider: dict, n_samples: int) -> str:
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    tot = _totals(rows)
    out = [f"# SH-250 progress and spend", "", f"- root: `{root}`", f"- updated: {now}",
           f"- target: {n_samples} samples x {sum(1 for r in rows if not r['killed'])} active models = "
           f"{n_samples * sum(1 for r in rows if not r['killed'])}" + (f" ({len(excluded_lanes(rows))} killed lane(s) excluded)" if excluded_lanes(rows) else ""),
           f"- **generated {tot['generated']}**, valid {tot['valid']}, forfeit {tot['forfeit']}, awaiting qualification {tot['awaiting']}, remaining {tot['remaining']}"
           + (f" ({tot['remaining'] - tot['remaining_active']} in killed lanes)" if tot['remaining'] != tot['remaining_active'] else ""),
           f"- **spent so far ≈ ${tot['spent']:,.0f}**, expected to finish everything ≈ ${tot['expected']:,.0f}",
           "", "## Top-up needed by provider", "",
           "| provider | remaining samples | minimum to finish | recommended top-up | already loaded | still to add | note |",
           "|---|---:|---:|---:|---:|---:|---|"]
    for t in topup_rows(by_provider):
        name = "**total**" if t["provider"] == "total" else t["provider"]
        out.append(f"| {name} | {t['remaining']} | ${t['minimum']:,.0f} | ${t['recommended']:,.0f} | ${t['loaded']:,.0f} | ${t['still']:,.0f} | {t['note']} |")
    out += ["", f"recommended = minimum x {TOPUP_MARGIN} rounded up to ${TOPUP_ROUND}; still to add = max(0, recommended - already loaded); "
                "minimum excludes killed lanes.",
            "", "## By provider", "",
            "| provider | generated | valid | remaining | spent so far | expected to finish |",
            "|---|---:|---:|---:|---:|---:|"]
    for p, v in sorted(by_provider.items()):
        out.append(f"| {p} | {v['generated']} | {v['valid']} | {v['remaining']} | ${v['spent']:,.0f} | ${v['expected']:,.0f} |")
    out += ["", "## Per model", "",
            "| model | provider | done | valid | forfeit | awaiting qual | remaining | $/sample | spent | expected to finish | gen min |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for r in rows:
        if r["killed"]:
            continue
        mc = f"${r['mean_cost']:.2f}" + (" (est.)" if r["estimated"] else "")
        exp = f"${r['expected']:,.0f}"
        rem = str(r["remaining"])
        gm = f"{statistics.mean(r['gen_min']):.1f}" if r["gen_min"] else "-"
        out.append(f"| {r['model']} | {r['provider']} | {r['generated']}/{n_samples} | {r['valid']} | {r['forfeit']} | "
                   f"{r['awaiting']} | {rem} | {mc} | ${r['spent']:,.0f} | {exp} | {gm} |")
    if excluded_lanes(rows):
        out += ["", "Excluded (killed by operator): " + "; ".join(excluded_lanes(rows))]
    out += ["", FOOTNOTE]
    return "\n".join(out) + "\n"


_CSS = """
:root{color-scheme:light}
body{margin:0;padding:20px 18px 48px;background:#f7f7f5;color:#1f2328;font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif}
main{max-width:none;margin:0 auto}
h1{font-size:22px;margin:0 0 6px;font-weight:650}
h2{font-size:16px;margin:32px 0 10px;font-weight:650;border-bottom:1px solid #d9d9d4;padding-bottom:6px}
.topbar{position:sticky;top:0;z-index:5;display:flex;align-items:center;gap:16px;flex-wrap:wrap;background:#f7f7f5;padding:10px 0;margin:0 0 14px;border-bottom:1px solid #d9d9d4}
.btn{display:inline-block;padding:9px 22px;background:#2f6fd6;color:#fff;font-weight:650;font-size:15px;border-radius:6px;text-decoration:none;box-shadow:0 1px 2px rgba(0,0,0,.15)}
.btn:hover{background:#245cb5}
.topbar .upd{font-size:14px}
.topbar .hint{color:#57606a;font-size:12.5px}
.meta{color:#57606a;font-size:13px;margin:0 0 4px}
code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px;background:#ececea;padding:1px 5px;border-radius:3px}
.totals{margin:14px 0 0;font-size:15px}
.totals b{font-weight:650}
.regen{margin:6px 0 0;color:#57606a;font-size:12.5px}
.wrap{overflow-x:auto}
table{border-collapse:collapse;width:100%;table-layout:auto;background:#fff;border:1px solid #d9d9d4;font-size:12.5px}
th,td{padding:4px 6px;border-bottom:1px solid #e6e6e2;text-align:left;white-space:nowrap;vertical-align:top}
th{white-space:normal;font-size:11.5px;line-height:1.2;vertical-align:bottom}
th{background:#f0f0ed;font-weight:600;color:#3b4148}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
td.note{white-space:normal;color:#57606a;font-size:12px;min-width:160px}
td.err{white-space:normal;color:#9b2c2c;font-size:11.5px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;max-width:300px}
tr:last-child td{border-bottom:none}
tr.total td{font-weight:650;background:#fafaf8;border-top:2px solid #c9c9c3}
tr.killed td{color:#8b8f95}
tr.killed td.model{text-decoration:line-through}
tr.stale td{background:#fff5f5}
tr.retired td{color:#8b8f95;background:#fafaf8}
.tag{display:inline-block;font-size:11px;padding:0 5px;border-radius:3px;margin-left:5px;vertical-align:1px}
.tag.k{background:#fbe3e3;color:#9b2c2c}
.tag.e{background:#fff1d6;color:#8a5a00}
.tag.d{background:#e2f2e6;color:#1d6b3a}
.still{color:#9b2c2c;font-weight:650}
.zero{color:#1d6b3a}
.red{color:#9b2c2c;font-weight:650}
.ok{color:#1d6b3a}
.dim{color:#8b8f95}
.foot{color:#57606a;font-size:12.5px;margin-top:10px;max-width:1100px}
.controls{background:#fff;border:1px solid #d9d9d4;border-radius:6px;padding:14px 18px;margin-top:12px;font-size:13px}
.controls h3{margin:0 0 8px;font-size:14px;font-weight:650}
.controls dt{font-weight:600;margin-top:10px}
.controls dd{margin:3px 0 0 0}
.controls pre{margin:4px 0 0;padding:8px 10px;background:#f0f0ed;border-radius:4px;font:12px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;white-space:pre-wrap;word-break:break-all}
.bar{position:relative;background:#e6e6e2;border-radius:4px;overflow:hidden;box-sizing:border-box}
.bar>i{display:block;height:100%;background:#2f6fd6}
.bar>b{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-weight:600;color:#1f2328;white-space:nowrap}
.bar.big{height:30px;margin-top:16px}
.bar.big>b{font-size:14px}
.bar.thin{height:16px;margin-top:6px;background:#eeeeeb}
.bar.thin>i{background:#8cc3a0}
.bar.thin>b{font-size:11.5px;font-weight:500}
.barlbl{color:#57606a;font-size:12px;margin:4px 0 0}
.bar.cell{width:120px;height:15px;display:inline-block;vertical-align:middle}
.bar.cell>b{font-size:11px}
.bar.prov{width:170px;height:15px;display:inline-block;vertical-align:middle}
.bar.prov>b{font-size:11px}
.bar.g>i{background:#5cbf7a}
.bar.b>i{background:#7fa7e6}
.bar.o>i{background:#f0b35a}
.bar.k>i{background:#b9bcc1}
.bar.r>i{background:#e07070}
.bar.i>i{background:#c9d6ea}
.legend{color:#57606a;font-size:12px;margin:6px 0 0}
.legend i{display:inline-block;width:11px;height:11px;border-radius:2px;vertical-align:-1px;margin:0 3px 0 10px}
"""


def _bar(num: float, den: float, cls: str = "", label: str | None = None) -> str:
    """A pure-CSS progress bar: filled <i> of width pct%, centred <b> label."""
    pct = 100.0 * num / den if den else 0.0
    if label is None:
        label = f"{num:,.0f} / {den:,.0f} &middot; {pct:.1f}%"
    return f"<div class='bar {cls}'><i style='width:{min(100.0, pct):.1f}%'></i><b>{label}</b></div>"



def _pid_file(root: Path, inst: str) -> str:
    base = f"{root.parent.name}-{root.name}" + ("" if inst == "main" else f"-{inst}")
    return f"{base}.pid"


def render_html(root: Path, rows: list[dict], by_provider: dict, n_samples: int, instances: list[dict] | None = None) -> str:
    now_utc = dt.datetime.now(dt.timezone.utc)
    now_local = now_utc.astimezone()
    instances = load_status(root, now_utc) if instances is None else instances
    live = merge_status(instances)
    tot = _totals(rows)
    running: dict[str, int] = defaultdict(int)   # provider -> API calls in flight right now
    for r in rows:
        running[r["provider"]] += (live.get(r["model"]) or {}).get("in_flight_gen") or 0
    running_total = sum(running.values())
    inst_state = {inst["name"]: instance_state(inst) for inst in instances}
    inst_age = {inst["name"]: inst["age_min"] for inst in instances}
    active_rows = [r for r in rows if not r["killed"]]
    pool_target = n_samples * len(active_rows)
    pool_gen = sum(r["generated"] for r in active_rows)
    pool_pct = 100.0 * pool_gen / pool_target if pool_target else 0.0
    qualified = tot["valid"] + tot["forfeit"]
    e = html.escape
    usd = lambda x: f"${x:,.0f}"  # noqa: E731
    try:
        root_rel = str(root.relative_to(REPO))
    except ValueError:
        root_rel = str(root)

    h: list[str] = []
    h.append("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">")
    h.append("<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">")
    h.append("<title>SH-250 progress and spend</title>")
    h.append(f"<style>{_CSS}</style></head><body><main>")
    h.append(f"<div class=topbar><a href=\"\" class=btn>Refresh</a>"
             f"<span class=upd>updated <b>{e(now_local.strftime('%Y-%m-%d %H:%M:%S %Z'))}</b> ({e(now_utc.isoformat(timespec='seconds'))})</span>"
             f"<span class=hint>the file is regenerated every {REFRESH_S} s; press Refresh to load the latest</span></div>")
    h.append("<h1>SH-250 progress and spend</h1>")
    h.append(f"<p class=meta>root <code>{e(str(root))}</code></p>")
    h.append(f"<p class=meta>target {n_samples} samples &times; {len(active_rows)} active models = {pool_target:,}"
             + (f" &middot; {len(rows) - len(active_rows)} killed lane(s) excluded, listed under the per-model table" if len(rows) != len(active_rows) else "") + "</p>")
    killed_rem = tot["remaining"] - tot["remaining_active"]
    h.append(f"<p class=totals><b>generated {tot['generated']}</b> &middot; valid {tot['valid']} &middot; forfeit {tot['forfeit']} &middot; "
             f"awaiting qualification {tot['awaiting']} &middot; remaining {tot['remaining']}"
             + (f" ({killed_rem} in killed lanes)" if killed_rem else "") +
             f"<br><b>spent so far &asymp; {usd(tot['spent'])}</b> &middot; expected to finish &asymp; {usd(tot['expected'])}</p>")
    h.append(f"<p class=regen>The file is regenerated every {REFRESH_S} s by <code>scripts/sampling/cost_report.py --loop</code>; "
             f"press Refresh (top) to load the latest. Static file, no scripts, no auto-refresh.</p>")
    h.append(_bar(pool_gen, pool_target, "big", f"Pool progress &middot; {pool_gen:,} / {pool_target:,} generated &middot; {pool_pct:.1f}%"))
    h.append(_bar(qualified, tot["generated"], "thin",
                  f"qualified {qualified:,} / {tot['generated']:,} generated &middot; "
                  f"{(100.0 * qualified / tot['generated'] if tot['generated'] else 0):.1f}% (valid {tot['valid']:,} + forfeit {tot['forfeit']:,})"))
    if len(rows) != len(active_rows):
        h.append(f"<p class=barlbl>killed lanes are excluded from every number on this page except spend: "
                 f"{e('; '.join(excluded_lanes(rows)))}.</p>")

    # 0. Live instances
    h.append("<h2>Live instances</h2><div class=wrap><table>")
    h.append("<tr><th>instance</th><th>status file</th><th>updated</th><th class=n>age (min)</th><th class=n>in-flight API calls</th>"
             "<th class=n>in-flight qualification</th><th class=n>rate /h</th><th>ETA</th><th class=n>free disk (GB)</th><th>process</th></tr>")
    if not instances:
        h.append("<tr><td colspan=10 class=dim>no status*.json in the root</td></tr>")
    far_past = dt.datetime.min.replace(tzinfo=dt.timezone.utc)
    for inst in sorted(instances, key=lambda i: i["updated"] or far_past, reverse=True):
        d = inst["data"]
        stale = inst["age_min"] > STALE_MIN
        state = inst_state[inst["name"]]
        retired = state == "retired"
        pidf = _pid_file(root, inst["name"])
        if inst["alive"] is True:
            proc_cell = f"<span class=ok>pid {inst['pid']} alive</span> <span class=dim>({e(pidf)})</span>"
        elif inst["alive"] is False:
            proc_cell = f"<span class=dim>pid {inst['pid']} gone</span> <span class=dim>({e(pidf)})</span>"
        else:
            proc_cell = f"<span class=dim>no pid file ({e(pidf)}); age rule</span>"
        if inst["error"]:
            h.append(f"<tr class=\"{'retired' if retired else 'stale'}\"><td>{e(inst['name'])}</td><td><code>{e(inst['file'].name)}</code></td>"
                     f"<td colspan=7 class=red>unreadable: {e(inst['error'])}</td><td>{proc_cell}</td></tr>")
            continue
        upd = inst["updated"].astimezone().strftime("%H:%M:%S %Z")
        age = f"{inst['age_min']:.1f}"
        if retired:
            age_cell = f"<span class=dim>{age} &mdash; retired</span>"
        elif state == "dead":
            age_cell = f"<span class=red>{age} &mdash; probably dead</span>"
        elif stale:
            age_cell = f"<span style='color:#8a5a00;font-weight:650'>{age} &mdash; stale snapshot</span>"
        else:
            age_cell = f"<span class=ok>{age}</span>"
        disk = d.get("free_disk_gb")
        disk_cell = "-" if disk is None else f"{disk:.1f}"
        if disk is not None and d.get("min_free_gb") is not None and disk < 2 * d["min_free_gb"]:
            disk_cell = f"<span class=red>{disk_cell}</span>"
        h.append(f"<tr class=\"{'retired' if retired else ('stale' if state == 'dead' else '')}\"><td><b>{e(inst['name'])}</b></td><td><code>{e(inst['file'].name)}</code></td>"
                 f"<td>{e(upd)}</td><td class=n>{age_cell}</td><td class=n>{d.get('in_flight_gen', '-')}</td>"
                 f"<td class=n>{d.get('in_flight_qual', '-')}</td><td class=n>{d.get('rate_per_h', '-')}</td><td>{e(str(d.get('eta', '-')))}</td>"
                 f"<td class=n>{disk_cell}</td><td>{proc_cell}</td></tr>")
    h.append("</table></div>")
    h.append(f"<p class=foot>newest-updated instance first. Liveness comes from the instance's pid file (<code>os.kill(pid, 0)</code>): "
             f"process alive = green (a snapshot older than {STALE_MIN:g} min is marked 'stale snapshot'); process gone = greyed as retired, "
             f"whatever its last snapshot claimed. Only without a pid file does the age rule apply (&gt; {STALE_MIN:g} min and still claiming "
             f"in-flight work = red, probably dead; nothing claimed = retired). Files under <code>retired/</code> are ignored. "
             "Instances share the root; a model's live row comes from the instance that has it in flight (else the un-stopped row, "
             "else the most recent file).</p>")

    # a. Top-up needed by provider
    h.append("<h2>Top-up needed by provider</h2><div class=wrap><table>")
    h.append("<tr><th>provider</th><th class=n>running</th><th class=n>remaining samples</th><th class=n>minimum to finish</th>"
             f"<th class=n>recommended top-up<br><span style='font-weight:400'>(&times;{TOPUP_MARGIN}, to ${TOPUP_ROUND})</span></th>"
             "<th class=n>already loaded</th><th class=n>still to add</th><th>note</th></tr>")
    for t in topup_rows(by_provider):
        is_tot = t["provider"] == "total"
        still_cls = "still" if t["still"] > 0 else "zero"
        run_cell = running_total if is_tot else running.get(t["provider"], 0)
        h.append(f"<tr class=\"{'total' if is_tot else ''}\"><td>{e(t['provider'])}</td><td class=n>{run_cell}</td>"
                 f"<td class=n>{t['remaining']}</td><td class=n>{usd(t['minimum'])}</td><td class=n>{usd(t['recommended'])}</td>"
                 f"<td class=n>{usd(t['loaded'])}</td><td class=\"n {still_cls}\">{usd(t['still'])}</td>"
                 f"<td class=note>{e(t['note'])}</td></tr>")
    h.append("</table></div>")
    h.append(f"<p class=foot>minimum = sum of per-model expected-to-finish, excluding killed lanes (a <code>STOP-&lt;model&gt;</code> file in the root); "
             f"models with no priced samples yet are priced at the same-provider mean token counts x this model's list price (est.); "
             f"recommended = minimum &times; {TOPUP_MARGIN} rounded up to ${TOPUP_ROUND}; already loaded is hand-maintained "
             f"(<code>ALREADY_LOADED</code> in the script); still to add = max(0, recommended &minus; already loaded); "
             f"running = API calls in flight right now across the provider's models (live status).</p>")

    # b. By provider
    h.append("<h2>By provider</h2><div class=wrap><table>")
    h.append("<tr><th>provider</th><th>progress<br><span style='font-weight:400'>generated / target, killed lanes excluded</span></th>"
             "<th class=n>running</th><th class=n>generated</th><th class=n>valid</th><th class=n>remaining</th>"
             "<th class=n>spent so far</th><th class=n>expected to finish</th></tr>")
    for p, v in sorted(by_provider.items()):
        p_models = sum(1 for r in rows if r["provider"] == p)
        p_target = n_samples * (p_models - len(v["killed"]))
        p_gen = v["generated"]
        p_cls = "g" if p_target and p_gen >= p_target else ("b" if running.get(p, 0) else "i")
        h.append(f"<tr><td>{e(p)}</td><td>{_bar(p_gen, p_target, 'prov ' + p_cls)}</td><td class=n>{running.get(p, 0)}</td><td class=n>{v['generated']}</td><td class=n>{v['valid']}</td><td class=n>{v['remaining']}</td>"
                 f"<td class=n>{usd(v['spent'])}</td><td class=n>{usd(v['expected'])}</td></tr>")
    h.append(f"<tr class=total><td>total</td><td>{_bar(pool_gen, pool_target, 'prov ' + ('g' if pool_gen >= pool_target else 'b'))}</td>"
             f"<td class=n>{running_total}</td><td class=n>{tot['generated']}</td><td class=n>{tot['valid']}</td><td class=n>{tot['remaining']}</td>"
             f"<td class=n>{usd(tot['spent'])}</td><td class=n>{usd(tot['expected'])}</td></tr>")
    h.append("</table></div>")

    # c. Per model (disk-derived counts + the live status row merged from status*.json)
    h.append("<h2>Per model</h2><div class=wrap><table>")
    h.append("<tr><th>model</th><th>provider</th><th>instance</th><th>progress</th><th class=n>done</th><th class=n>valid</th><th class=n>forfeit</th>"
             "<th class=n>awaiting qual</th><th class=n>running<br><span style='font-weight:400'>API calls</span></th>"
             "<th class=n>in qual<br><span style='font-weight:400'>processes</span></th><th class=n>remaining</th>"
             "<th>stopped</th><th class=n>$/sample</th><th class=n>spent</th>"
             "<th class=n>expected to finish</th><th class=n>gen min</th><th>last error</th></tr>")
    for r in rows:
        if r["killed"]:
            continue
        s = live.get(r["model"])
        cls = ""
        tag = ""
        if r["killed"]:
            tag = "<span class='tag k'>killed</span>"
        elif r["remaining"] == 0:
            tag = "<span class='tag d'>done</span>"
        mc = f"${r['mean_cost']:.2f}" + (f"<span class='tag e' title='{e(str(r['est_basis']))}'>est.</span>" if r["estimated"] else "")
        rem = "killed" if r["killed"] else str(r["remaining"])
        gm = f"{statistics.mean(r['gen_min']):.1f}" if r["gen_min"] else "-"
        ig = (s.get("in_flight_gen") or 0) if s else 0
        inst_dead = bool(s) and inst_state.get(s["instance"]) in ("retired", "dead")
        if r["killed"]:
            bar_cls = "k"
        elif r["generated"] >= n_samples:
            bar_cls = "g"
        elif inst_dead:
            bar_cls = "r"
        elif s and s.get("stopped"):
            bar_cls = "o"
        elif ig > 0:
            bar_cls = "b"
        else:
            bar_cls = "i"
        bar_lbl = f"{100.0 * r['generated'] / n_samples:.0f}%" + (f" &middot; {ig} running" if ig and bar_cls == "b" else "")
        prog = _bar(r["generated"], n_samples, "cell " + bar_cls, bar_lbl)
        if s:
            ig, iq = s.get("in_flight_gen") or 0, s.get("in_flight_qual") or 0
            run_c = str(ig) if ig else "<span class=dim>0</span>"
            qual_c = str(iq) if iq else "<span class=dim>0</span>"
            owner = e(s["instance"])
            # stopped / last error are shown only while they are current: the owning instance must be alive,
            # and an error must explain live work (calls in flight) or a live stop (fresh snapshot + stopped set).
            owner_alive = inst_state.get(s["instance"]) == "alive"
            fresh = inst_age.get(s["instance"], math.inf) < STALE_MIN
            if r["remaining"] == 0:
                owner_alive = False      # a finished lane has nothing current to report
            if owner_alive and s.get("stopped"):
                stopped = f"<span class=red>{e(str(s['stopped']))}</span>"
            else:
                stopped = "<span class=dim>-</span>"
            err = (s.get("last_error") or "").strip()
            err_ts = s.get("last_error_ts")
            recent_err = err_ts is not None and (time.time() - float(err_ts)) < RECENT_ERROR_MIN * 60
            err_current = owner_alive and recent_err and (ig > 0 or (fresh and bool(s.get("stopped"))))
            err_cell = e(err[:80] + ("…" if len(err) > 80 else "")) if (err and err_current) else "<span class=dim>-</span>"
            awaiting = f"{r['awaiting']}" + (f" <span class=dim>(live {s['awaiting_qualification']})</span>"
                                             if s.get("awaiting_qualification") not in (None, r["awaiting"]) else "")
        else:
            run_c = qual_c = "<span class=dim>-</span>"; owner = "<span class=dim>none</span>"
            stopped = "<span class=dim>-</span>"
            err_cell, awaiting = "<span class=dim>-</span>", str(r["awaiting"])
        h.append(f"<tr class=\"{cls}\"><td class=model>{e(r['model'])}</td><td>{e(r['provider'])}</td><td>{owner}</td>"
                 f"<td>{prog}</td><td class=n>{r['generated']}/{n_samples}{tag}</td><td class=n>{r['valid']}</td><td class=n>{r['forfeit']}</td>"
                 f"<td class=n>{awaiting}</td><td class=n>{run_c}</td><td class=n>{qual_c}</td><td class=n>{rem}</td><td>{stopped}</td><td class=n>{mc}</td>"
                 f"<td class=n>{usd(r['spent'])}</td><td class=n>{usd(r['expected'])}</td><td class=n>{gm}</td><td class=err>{err_cell}</td></tr>")
    h.append("</table></div>")
    if excluded_lanes(rows):
        h.append(f"<p class=foot><b>Excluded (killed by operator):</b> {e('; '.join(excluded_lanes(rows)))}</p>")
    h.append("<p class=legend>progress bar colour: <i style='background:#5cbf7a'></i>complete <i style='background:#7fa7e6'></i>running "
             "<i style='background:#f0b35a'></i>stopped (credits / errors) "
             "<i style='background:#e07070'></i>owning instance gone (process exited / stale, unclaimed) <i style='background:#c9d6ea'></i>idle</p>")
    h.append(f"<p class=foot>{e(FOOTNOTE)} instance = which run_pool instance currently owns the lane (status*.json merge); "
             "running = API calls in flight right now, in qual = qualification processes running, both from that instance's live status; awaiting qual = files on disk (the instance's "
             "own live count in parentheses when it differs); stopped = the lane halted itself (credits exhausted / errors), shown only "
             "while its owning instance is alive; last error = the owning instance's last error text (80 chars), shown only when it is "
             f"current: the instance is alive and the lane has calls in flight, or its snapshot is &lt; {STALE_MIN:g} min old and the lane is stopped.</p>")

    # d. Controls
    py = "~/miniconda3/envs/arena/bin/python"
    h.append("<div class=controls><h3>Controls</h3><dl>")
    h.append(f"<dt>Pause one lane</dt><dd>the owning instance halts it at its next scheduling point; the lane stays halted for that "
             f"instance's lifetime, so to run it again remove the file <em>and</em> restart the instance.</dd>"
             f"<dd><pre>touch {e(root_rel)}/STOP-&lt;model&gt;      # e.g. STOP-claude-opus-4-7-high\nrm {e(root_rel)}/STOP-&lt;model&gt;</pre></dd>")
    kills = "\n".join(f"kill $(cat {_pid_file(root, inst)})      # {inst}" for inst in ("main", "claude", "openai"))
    h.append(f"<dt>Stop an instance</dt><dd>in-flight API calls are abandoned; finished samples stay on disk and are skipped on resume.</dd>"
             f"<dd><pre>{e(kills)}</pre></dd>")
    resumes = []
    for inst, extra in INSTANCE_CMDS.items():
        cmd = (f"nohup {py} scripts/sampling/run_pool.py --root {root_rel} --n-samples {n_samples} {extra} --retry-failed "
               f"> /dev/null 2>&1 & echo $! > {_pid_file(root, inst)}")
        resumes.append(f"# {inst}\n{cmd}")
    h.append(f"<dt>Resume an instance</dt><dd>same flags as the live run plus <code>--retry-failed</code> (clears gen_error.json so failed "
             f"samples get their attempts back); a second instance on the same root must keep its own <code>--status-name</code>.</dd>"
             f"<dd><pre>{e(chr(10).join(resumes))}</pre></dd>")
    h.append(f"<dt>Where the files are</dt><dd><pre>"
             f"{e(root_rel)}/status.json | status-claude.json | status-openai.json   live status per instance (glob status*.json)\n"
             f"{e(root_rel)}/STATUS.md | STATUS-claude.md | STATUS-openai.md          the instances' markdown status\n"
             f"{e(root_rel)}/COST.md, COST.html  and  SH250_COST.md, SH250_COST.html  this report (repo-root copies)\n"
             f"{e(root_rel)}/&lt;model&gt;/cNNN/gen.json | gen_error.json                  per-sample outputs / failures\n"
             f"{e(_pid_file(root, 'main'))} | {e(_pid_file(root, 'claude'))} | {e(_pid_file(root, 'openai'))} | "
             f"{e(_pid_file(root, 'cost'))}   pids\n"
             f"cost loop: {py} scripts/sampling/cost_report.py --root {e(root_rel)} --loop {REFRESH_S} --quiet</pre></dd>")
    h.append("</dl></div>")
    h.append("</main></body></html>")
    return "\n".join(h) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", required=True)
    ap.add_argument("--config", default="configs/tournaments/sh.yaml")
    ap.add_argument("--n-samples", type=int, default=250)
    ap.add_argument("--loop", type=int, nargs="?", const=REFRESH_S, default=0,
                    help=f"rewrite every N seconds (bare --loop = {REFRESH_S}; omitted = once)")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    root = Path(a.root) if Path(a.root).is_absolute() else REPO / a.root
    while True:
        rows, by_provider = report(root, REPO / a.config, a.n_samples)
        md = render(root, rows, by_provider, a.n_samples)
        page = render_html(root, rows, by_provider, a.n_samples)
        (root / "COST.md").write_text(md)
        (REPO / "SH250_COST.md").write_text(md)
        (root / "COST.html").write_text(page)
        (REPO / "SH250_COST.html").write_text(page)
        if not a.quiet:
            print(md)
        if not a.loop:
            break
        time.sleep(a.loop)


if __name__ == "__main__":
    main()
