#!/usr/bin/env python3
"""Pool ledger: which SH-250 samples enter a model's round robin and why the others do not.

Eligibility (decision D5): validated, passed qualification, did not forfeit. `commit_dir` in the
returned records is relative to `repo` when one is given and the path lies inside it, else
absolute/as-given — `run_intra_rr_for_model` joins it onto `repo_root`.

Two on-disk layouts are understood (`layout=`):
  "run"  — the sampling run root (`LOGS-SH250/<date>`):
             <root>/<model>/cNNN/gen.json
             <root>/<model>/cNNN/tournament_00/round_robin_match/bots/<model>/bot_artifact.json
             <root>/<model>/cNNN/tournament_00/round_robin_match/bots/<model>/refinement/journal.json
             <root>/<model>/cNNN/tournament_00/round_robin_match/bots/<model>/refinement/commit_0/{robot.xml,controller.py}
  "pack" — the flat transfer pack written by `pack_pool.py`:
             <root>/<model>/cNNN/{gen.json,bot_artifact.json,journal.json}
             <root>/<model>/cNNN/commit_0/{robot.xml,controller.py}
"""
import json
from pathlib import Path

BOTS = "tournament_00/round_robin_match/bots"
LAYOUTS = ("run", "pack")

REASON_ELIGIBLE = "eligible"
REASON_NOT_GENERATED = "not generated"
REASON_NOT_QUALIFIED_YET = "not qualified yet"
REASON_VALIDATION_FAILED = "validation failed"
REASON_QUALIFICATION_FAILED = "qualification failed"


def _rel(p: Path, repo: Path | None) -> str:
    return str(p.relative_to(repo)) if repo and p.is_relative_to(repo) else str(p)


def slot_paths(root: Path, model: str, idx: int, layout: str) -> dict[str, Path]:
    """The four paths the ledger reads for one slot, keyed `slot`, `artifact`, `journal`, `commit`."""
    if layout not in LAYOUTS:
        raise ValueError(f"unknown layout {layout!r}; expected one of {LAYOUTS}")
    d = root / model / f"c{idx:03d}"
    if layout == "run":
        bot = d / BOTS / model
        return {"slot": d, "artifact": bot / "bot_artifact.json",
                "journal": bot / "refinement/journal.json", "commit": bot / "refinement/commit_0",
                "qual_result": bot / "refinement/commit_0/qualification/match_result.json"}
    return {"slot": d, "artifact": d / "bot_artifact.json",
            "journal": d / "journal.json", "commit": d / "commit_0",
            "qual_result": d / "qualification/match_result.json"}



def qualification_wdl(match_result: Path) -> list[int]:
    """[wins, draws, losses] of the sample's three qualification rounds against the block (the sample is red)."""
    games = json.loads(match_result.read_text())["matches"]
    wins = sum(1 for g in games if g["winner"] == "red")
    losses = sum(1 for g in games if g["winner"] == "blue")
    return [wins, len(games) - wins - losses, losses]


def passes_entry_gate(wins: int, draws: int, losses: int) -> bool:
    """Tournament entry (user ruling 2026-09-19): no round lost — the prompt's "not losing is the minimum
    bar" — OR more rounds won than lost (a strong bot that fell out once, e.g. W2 L1, is in). W1 D1 L1 is out.
    This is the POOL gate; the harness's own `qualification_passed` flag stays the stricter no-loss verdict."""
    return losses == 0 or wins > losses


def scan_pool(root: Path, model: str, *, n_samples: int = 250, require_qualified: bool = True,
              repo: Path | None = None, layout: str = "run"):
    """Return `(eligible, ledger)` for one model.

    `eligible` rows are what `run_intra_rr_for_model` consumes:
      {"commit_dir", "commit_idx": 0, "tournament_idx": NNN, "qualification_score": float}
    `ledger` has one row per slot c000..c(n_samples-1):
      {"idx", "generated", "qualified", "forfeit", "forfeit_stage", "validation_passed",
       "qualification_passed", "qualification_score", "eligible", "reason"}
    `reason` is one of: "eligible", "not generated", "not qualified yet", "forfeit:<stage>", "qualification failed (W. D. L.)",
    "validation failed", "qualification failed".
    With `require_qualified=False` every slot whose commit_0/robot.xml and controller.py exist is
    eligible regardless of `reason` (sensitivity check only).
    """
    root = Path(root)
    eligible, ledger = [], []
    for idx in range(n_samples):
        paths = slot_paths(root, model, idx, layout)
        d, commit = paths["slot"], paths["commit"]
        row = {"idx": idx, "generated": (d / "gen.json").exists(), "qualified": paths["artifact"].exists(),
               "forfeit": None, "forfeit_stage": "", "validation_passed": None, "qualification_passed": None,
               "qualification_score": None, "wdl": None, "eligible": False, "reason": ""}
        if not row["generated"]:
            row["reason"] = REASON_NOT_GENERATED
        elif not row["qualified"]:
            row["reason"] = REASON_NOT_QUALIFIED_YET
        else:
            art = json.loads(paths["artifact"].read_text())
            row["forfeit"] = bool(art["forfeit"])
            row["forfeit_stage"] = art["forfeit_stage"] if row["forfeit"] else ""
            c0 = json.loads(paths["journal"].read_text())["commits"][0]
            row["validation_passed"] = bool(c0["validation_passed"])
            row["qualification_passed"] = bool(c0["qualification_passed"])
            row["qualification_score"] = c0["score"]
            if row["forfeit"]:
                row["reason"] = f"forfeit:{row['forfeit_stage'] or 'unknown'}"
            elif not row["validation_passed"]:
                row["reason"] = REASON_VALIDATION_FAILED
            else:
                row["wdl"] = wdl = qualification_wdl(paths["qual_result"])
                if passes_entry_gate(*wdl):
                    row["reason"] = REASON_ELIGIBLE
                else:
                    row["reason"] = f"{REASON_QUALIFICATION_FAILED} (W{wdl[0]} D{wdl[1]} L{wdl[2]})"
        gate_ok = row["reason"] == REASON_ELIGIBLE
        xml_ok = (commit / "robot.xml").exists() and (commit / "controller.py").exists()
        if (gate_ok and xml_ok) if require_qualified else xml_ok:
            row["eligible"] = True
            eligible.append({"commit_dir": _rel(commit, repo), "commit_idx": 0, "tournament_idx": idx,
                             "qualification_score": float(row["qualification_score"] or 0.0)})
        ledger.append(row)
    return eligible, ledger
