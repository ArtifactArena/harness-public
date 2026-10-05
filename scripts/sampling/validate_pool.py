#!/usr/bin/env python3
"""Integrity check for a sampling-pool root (LOGS-SH250/<date>).

For every model: how many of the N slots are generated / qualified / awaiting qualification /
missing, which qualified slots are STALE (gen.json newer than the qualified bot_artifact.json —
a late duplicate generation overwrote the sample the artifact was built from) and which have
generation usage rows that never got merged into the bot dir.

    python scripts/sampling/validate_pool.py --root LOGS-SH250/20260918            # report
    python scripts/sampling/validate_pool.py --root LOGS-SH250/20260918 --fix      # + repair

--fix sets each stale slot's tournament_00 aside as tournament_00.stale-<ts> (nothing is deleted)
and removes the build bookkeeping so the next qualification pass rebuilds it from the current
gen.json, and merges the orphaned usage rows.
"""
import argparse
import datetime as dt
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_pool  # noqa: E402

BOTS = "tournament_00/round_robin_match/bots"


def scan(root: Path, stems: list[str], n_samples: int) -> dict[str, dict]:
    rows = {}
    for stem in stems:
        r = {"generated": 0, "qualified": 0, "forfeit": 0, "awaiting": 0, "missing": [],
             "stale": [], "unmerged_usage": [], "dups": 0}
        for idx in range(n_samples):
            d = root / stem / f"c{idx:03d}"
            gen = d / "gen.json"
            if not gen.exists():
                r["missing"].append(idx)
                continue
            r["generated"] += 1
            r["dups"] += len(list(d.glob("gen.dup-*.json")))
            art = d / BOTS / stem / "bot_artifact.json"
            if not art.exists():
                r["awaiting"] += 1
                continue
            r["qualified"] += 1
            try:
                if json.loads(art.read_text()).get("forfeit"):
                    r["forfeit"] += 1
            except json.JSONDecodeError:
                pass
            if gen.stat().st_mtime > art.stat().st_mtime:
                r["stale"].append(idx)
            if (d / "gen/refinement/usage.jsonl").exists():
                r["unmerged_usage"].append(idx)
        rows[stem] = r
    return rows


def _ids(v: list[int]) -> str:
    return ", ".join(f"c{i:03d}" for i in v) if v else ""


def render(rows: dict[str, dict], n_samples: int) -> str:
    out = [f"# Pool validation — {dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}", "",
           f"Target {n_samples} samples per model. **stale** = gen.json regenerated after qualification "
           "(artifact no longer matches the sample; re-qualify). **unmerged** = generation usage rows still "
           "in gen/ (cost rows not yet in the bot dir).", "",
           "| model | generated | qualified | forfeit | awaiting | missing | stale | unmerged | dup gens |",
           "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    tot = {k: 0 for k in ("generated", "qualified", "forfeit", "awaiting")}
    tot_missing = tot_stale = tot_unmerged = tot_dups = 0
    for stem, r in rows.items():
        out.append(f"| {stem} | {r['generated']} | {r['qualified']} | {r['forfeit']} | {r['awaiting']} | "
                   f"{len(r['missing'])} | {len(r['stale'])} | {len(r['unmerged_usage'])} | {r['dups']} |")
        for k in tot:
            tot[k] += r[k]
        tot_missing += len(r["missing"]); tot_stale += len(r["stale"])
        tot_unmerged += len(r["unmerged_usage"]); tot_dups += r["dups"]
    out.append(f"| **total** | {tot['generated']} | {tot['qualified']} | {tot['forfeit']} | {tot['awaiting']} | "
               f"{tot_missing} | {tot_stale} | {tot_unmerged} | {tot_dups} |")
    details = []
    for stem, r in rows.items():
        for key, label in (("missing", "missing"), ("stale", "stale"), ("unmerged_usage", "unmerged usage")):
            if r[key]:
                details.append(f"- {stem} {label}: {_ids(r[key])}")
    if details:
        out += ["", "## Details", ""] + details
    return "\n".join(out) + "\n"


def fix(root: Path, rows: dict[str, dict]) -> list[str]:
    done = []
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for stem, r in rows.items():
        for idx in r["stale"]:
            d = root / stem / f"c{idx:03d}"
            (d / "tournament_00").rename(d / f"tournament_00.stale-{stamp}")
            for name in ("config.yaml", "sampling_prompt.md", "log.txt"):
                p = d / name
                if p.exists():
                    p.unlink()
            shutil.rmtree(d / ".build_progress", ignore_errors=True)
            done.append(f"{stem} c{idx:03d}: stale qualification set aside for re-qualification")
        for idx in r["unmerged_usage"]:
            if idx in r["stale"]:
                continue   # its gen usage merges when the slot is re-qualified
            d = root / stem / f"c{idx:03d}"
            run_pool.merge_usage(d, stem)
            done.append(f"{stem} c{idx:03d}: generation usage merged")
    return done


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--n-samples", type=int, default=250)
    ap.add_argument("--models", nargs="*", help="model stems (default: every model dir under root)")
    ap.add_argument("--fix", action="store_true")
    ap.add_argument("--out", type=Path, help="write the markdown report here (default: <root>/VALIDATION.md)")
    a = ap.parse_args()
    stems = a.models or sorted(p.name for p in a.root.iterdir()
                               if p.is_dir() and any(c.name.startswith("c") for c in p.iterdir()) and not p.name.startswith("."))
    rows = scan(a.root, stems, a.n_samples)
    md = render(rows, a.n_samples)
    if a.fix:
        done = fix(a.root, rows)
        md += "\n## Fixed\n\n" + ("\n".join(f"- {x}" for x in done) if done else "- nothing to fix") + "\n"
    (a.out or a.root / "VALIDATION.md").write_text(md)
    print(md)


if __name__ == "__main__":
    main()
