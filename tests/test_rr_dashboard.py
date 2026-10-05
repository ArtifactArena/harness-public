"""rr_dashboard: SH-250 pool-tournament status page from per-host mirrors (pure Python, no MuJoCo)."""
import json
import os
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/sampling"))
import rr_dashboard as rd  # noqa: E402

NOW = 1_800_000_000.0        # fixed "now" for the mtime-based rate
H = 3600.0


def _aid(model, idx):
    return f"{model}__t{idx:02d}_c000"


def _ledger(gdir, model, group, lo, hi, eligible_idx, n_rollouts=5):
    gdir.mkdir(parents=True, exist_ok=True)
    rows = [{"idx": i, "eligible": i in eligible_idx, "reason": "" if i in eligible_idx else "forfeit",
             "artifact_id": _aid(model, i)} for i in range(lo, hi)]
    (gdir / "pool_ledger.json").write_text(json.dumps({
        "model": model, "eligible": len(eligible_idx), "n_rollouts": n_rollouts,
        "slot_range": [lo, hi], "group": group, "ledger": rows}))
    return [_aid(model, i) for i in eligible_idx]


def _match(gdir, a, b, mtime, n_seeds=5, winner="red"):
    d = gdir / "matches" / f"{a}_vs_{b}"
    d.mkdir(parents=True)
    p = d / "match_result.json"
    p.write_text(json.dumps({"red_bot": a, "blue_bot": b, "n_seeds": n_seeds,
                             "matches": [{"seed": s, "winner": winner, "num_steps": 100} for s in range(n_seeds)]}))
    os.utime(p, (mtime, mtime))
    return p


def _pairs(ids):
    return [(ids[i], ids[j]) for i in range(len(ids)) for j in range(i + 1, len(ids))]


def _standings(ids, elos):
    return {aid: {"elo": e, "wins": 3, "losses": 1, "draws": 0, "games": 4} for aid, e in zip(ids, elos)}


def _finish_group(gdir, model, ids, elos):
    st = _standings(ids, elos)
    top = max(ids, key=lambda a: st[a]["elo"])
    (gdir / "elo.json").write_text(json.dumps({"model": model, "method": "bt", "ties_at_top": [], "standings": st}))
    (gdir / "top_1.json").write_text(json.dumps({"model": model, "artifact_id": top, "elo": st[top]["elo"],
                                                 "wins": 3, "losses": 1, "draws": 0, "games": 4, "ties_at_top": []}))
    return top


@pytest.fixture
def roots(tmp_path):
    """Two host mirrors. host_e: `alpha`, grouped (--runs 2): g0 finished (3 bots, 3 pairings, 3 recent),
    g1 running (4 bots, 6 pairings, 2 done — one recent, one old). host_a: `beta`, grouped, both runs finished
    and VERIFIED, runs.json + top_5_bots.json, and the finals (stage_b/top5/beta + the cross-model top1)."""
    man = tmp_path / "rr-x" / "host_e"
    a0 = man / "alpha" / "g0"
    ids = _ledger(a0, "alpha", "g0", 0, 50, [0, 3, 7])
    for k, (a, b) in enumerate(_pairs(ids)):
        _match(a0, a, b, NOW - 60 * (k + 1))                 # 1, 2, 3 min ago -> inside the 30 min window
    _finish_group(a0, "alpha", ids, [1050.0, 1000.0, 950.0])
    (a0 / "VERIFIED").touch()
    a1 = man / "alpha" / "g1"
    ids1 = _ledger(a1, "alpha", "g1", 50, 100, [51, 52, 60, 99])
    pairs1 = _pairs(ids1)
    _match(a1, *pairs1[0], NOW - 10 * 60)                    # 10 min ago -> inside
    _match(a1, *pairs1[1], NOW - 3 * H)                      # 3 h ago -> outside
    (man / "alpha.log").write_text("running\n")

    host_a = tmp_path / "rr-x" / "host_a"
    winners = []
    for g, (lo, hi, el) in enumerate([(0, 50, [1, 2]), (50, 100, [55, 56, 57])]):
        gd = host_a / "beta" / f"g{g}"
        bids = _ledger(gd, "beta", f"g{g}", lo, hi, el)
        for a, b in _pairs(bids):
            _match(gd, a, b, NOW - 5 * H)
        winners.append(_finish_group(gd, "beta", bids, [[1100.0, 900.0], [900.0, 1000.0, 1100.0]][g]))
        (gd / "VERIFIED").touch()
    (host_a / "beta" / "runs.json").write_text(json.dumps({"model": "beta", "runs": 2, "groups": [
        {"group": "g0", "slot_range": [0, 50], "eligible": 2, "winner": winners[0], "winner_elo": 1100.0},
        {"group": "g1", "slot_range": [50, 100], "eligible": 3, "winner": winners[1], "winner_elo": 1100.0}]}))
    (host_a / "beta" / "top_5_bots.json").write_text(json.dumps({"bots": [{"artifact_id": w} for w in winners]}))
    (host_a / "beta" / "VERIFIED").touch()
    sb = host_a / "stage_b"
    (sb / "top5" / "beta").mkdir(parents=True)
    (sb / "top5" / "beta" / "elo.json").write_text(json.dumps({
        "model": "beta", "stage": "b1", "n_games": 11, "standings": _standings(winners, [1020.0, 980.0]),
        "ties_at_top": []}))
    (sb / "top1").mkdir()
    (sb / "top1" / "elo.json").write_text(json.dumps({
        "stage": "b2", "n_games": 11, "ties_at_top": [],
        "standings": {"beta__t01_c000": {"elo": 900.0, "wins": 2, "losses": 9, "draws": 0, "games": 11},
                      "alpha__t00_c000": {"elo": 1100.0, "wins": 9, "losses": 2, "draws": 0, "games": 11}}}))
    (sb / "summary.json").write_text("{}")
    return [man, host_a]


def test_scan_counts_pairings_games_eligible_and_status(roots):
    man, host_a = roots
    models = rd.merge_hosts([rd.scan_root(r, runs=2) for r in roots])["models"]
    alpha, beta = models["alpha"], models["beta"]
    assert alpha["host"] == "host_e" and beta["host"] == "host_a"
    assert [g["eligible"] for g in alpha["groups"]] == [3, 4]
    assert [g["expected"] for g in alpha["groups"]] == [3, 6]
    assert [g["done"] for g in alpha["groups"]] == [3, 2]
    assert alpha["done"] == 5 and alpha["expected"] == 9 and alpha["games"] == 25
    assert [g["status"] for g in alpha["groups"]] == ["VERIFIED", "running"]
    assert alpha["status"] == "running"
    assert alpha["winners"] == ["alpha__t00_c000"]
    assert beta["done"] == beta["expected"] == 4 and beta["status"] == "VERIFIED"
    assert beta["winners"] == ["beta__t01_c000", "beta__t57_c000"]


def test_unstarted_runs_are_queued_and_estimated(roots):
    models = rd.merge_hosts([rd.scan_root(r, runs=3) for r in roots])["models"]
    alpha = models["alpha"]
    assert [g["status"] for g in alpha["groups"]] == ["VERIFIED", "running", "queued"]
    assert len(models["beta"]["groups"]) == 2                # a finished model's runs.json says how many runs it had
    assert alpha["groups"][2]["eligible"] is None and alpha["groups"][2]["expected"] is None
    head = rd.headline(models, now=NOW)
    # known expected = 3 + 6 (alpha) + 1 + 3 (beta) = 13; one unstarted run estimated at the mean of the 4 known
    assert head["expected_known"] == 13 and head["n_unstarted"] == 1
    assert head["expected_est"] == pytest.approx(13 / 4)


def test_headline_rate_and_eta_from_mtimes(roots):
    models = rd.merge_hosts([rd.scan_root(r, runs=2) for r in roots])["models"]
    head = rd.headline(models, now=NOW)
    assert head["pairings_done"] == 9 and head["expected_known"] == 13 and head["n_unstarted"] == 0
    assert head["games_done"] == 45
    assert head["recent_pairings"] == 4                     # 3 (alpha g0) + 1 (alpha g1, 10 min ago)
    assert head["rate_per_h"] == pytest.approx(8.0)         # 4 pairings / 0.5 h
    assert head["eta_h"] == pytest.approx(4 / 8.0)          # 4 remaining
    assert head["hosts"] == ["host_a", "host_e"]
    stalled = rd.headline(models, now=NOW + 2 * H)
    assert stalled["rate_per_h"] == 0 and stalled["eta_h"] is None
    # nothing left -> ETA is "done", not a division
    done_only = {"beta": models["beta"]}
    assert rd.headline(done_only, now=NOW)["eta_h"] == 0


def test_stage_b_is_merged_and_leaderboard_sorted(roots):
    merged = rd.merge_hosts([rd.scan_root(r, runs=2) for r in roots])
    sb = merged["stage_b"]
    assert list(sb["top5"]) == ["beta"]
    assert [aid for aid, _ in sb["top1"]] == ["alpha__t00_c000", "beta__t01_c000"]
    assert sb["top1_host"] == "host_a"


def test_duplicate_model_across_roots_takes_more_pairings_and_flags(roots, tmp_path):
    man, host_a = roots
    dup = host_a / "alpha" / "g0"
    ids = _ledger(dup, "alpha", "g0", 0, 50, [0, 3, 7])
    _match(dup, *_pairs(ids)[0], NOW - 60)
    merged = rd.merge_hosts([rd.scan_root(r, runs=2) for r in roots])
    assert merged["models"]["alpha"]["host"] == "host_e"
    assert merged["flags"] == ["alpha: also under host_a (1 pairings) — using host_e (5 pairings)"]


def test_html_is_self_contained_and_names_models_in_leaderboard_order(roots):
    merged = rd.merge_hosts([rd.scan_root(r, runs=2) for r in roots])
    page = rd.render_html(merged, now=NOW)
    assert "<script" not in page.lower() and "<link" not in page.lower()
    assert not re.search(r"(src|href)=[\"']?https?://", page)
    assert 'href=""' in page and "Refresh" in page
    assert "alpha" in page and "beta" in page and "host_e" in page and "host_a" in page
    assert not re.search(r"Stage [AB]\b|\bB[12]\b|block[ _-]?test", page, re.I)                 # the page never uses stage letters
    lb = page[page.index("<h2>Scoreboard"):]
    assert lb.index("alpha__t00_c000") < lb.index("beta__t01_c000")
    assert "1100.0" in lb and "9-2-0" in lb
    assert page.index("<h2>Scoreboard") < page.index("<h2>Top Bot per Run Round")      # scoreboard first once it has data
    assert "250 samples" in page and "11 seeds" in page          # the "what this is" footer
    assert "t00" in page and "t57" in page                         # run winners, short form


def test_placeholders_without_stage_b(tmp_path):
    man = tmp_path / "rr-y" / "host_e"
    _ledger(man / "gamma" / "g0", "gamma", "g0", 0, 50, [1, 2])
    merged = rd.merge_hosts([rd.scan_root(man, runs=5)])
    assert merged["stage_b"]["top5"] == {} and merged["stage_b"]["top1"] == []
    page = rd.render_html(merged, now=NOW)
    assert "not yet" in page
    assert page.index("<h2>Top Bot per Run Round") < page.index("<h2>Scoreboard")      # placeholder after the model table
    md = rd.render_md(merged, now=NOW)
    assert "gamma" in md and "not yet" in md
    assert md.index("## Top Bot per Run Round") < md.index("## Scoreboard")


def test_ungrouped_model_dir_is_a_single_run(tmp_path):
    man = tmp_path / "rr-z" / "host_e"
    ids = _ledger(man / "delta", "delta", None, 0, 250, [0, 1, 2])
    _match(man / "delta", *_pairs(ids)[0], NOW - 60)
    models = rd.merge_hosts([rd.scan_root(man, runs=5)])["models"]
    d = models["delta"]
    assert len(d["groups"]) == 1 and d["groups"][0]["name"] == "all"
    assert d["done"] == 1 and d["expected"] == 3 and d["status"] == "running"


def test_main_writes_html_and_md(roots, tmp_path):
    out_html, out_md = tmp_path / "SH250_RR.html", tmp_path / "SH250_RR.md"
    rc = rd.main(["--roots", *map(str, roots), "--out", str(out_html), "--md", str(out_md), "--runs", "2"])
    assert rc == 0
    page = out_html.read_text()
    assert "alpha" in page and "<script" not in page
    md = out_md.read_text()
    assert md.startswith("# SH-250 pool tournament") and "| alpha |" in md


# ── HPC (SLURM) panel ───────────────────────────────────────────────────

STATUS_MD = """# SH-250 sampling pool — status

- root: `<user-home>/sh250/20260918-gen`
- started: 2026-09-19T12:00:00+00:00
- updated: {updated}
- git sha: abc123
- samples: **500/500 generated**, 10 qualified, 3 forfeit, 7 awaiting qualification, 0 generation failures, 0 qualification errors, 0 remaining

| model | generated | failed | qualified OK | forfeit | awaiting qual | qual err | remaining | in flight | gen min (mean) | stopped | last error |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| gpt-5.5 | 250/250 | 0 | {q1} | 1 | 4 | 0 | 0 | 0+3 | 1.0 |  |  |
| alpha | 250/250 | 2 | {q2} | 2 | 3 | 1 | 0 | 0+0 | 2.0 |  | boom |

Columns: generated = ...
"""


def _job(job_id, index, state, *, name="sh250-a", cpus=64, node="node1234", elapsed="01:23:45", limit="12:00:00", reason=""):
    return {"job_id": job_id, "array_job": job_id.split("_")[0], "array_index": index, "name": name, "state": state,
            "partition": "shared_normal", "cpus": cpus, "node": node, "elapsed": elapsed, "time_limit": limit, "reason": reason}


@pytest.fixture
def hpc(tmp_path):
    """A mirror dir: slurm.json with 7 Top Bot per Run Round tasks (2 RUNNING, 1 PENDING, 2 COMPLETED — one of them without a
    VERIFIED marker —, 1 FAILED, 1 TIMEOUT) plus one qualification job; a small rr mirror; two STATUS-qual mds
    (the newer one wins); one task log; SHIPPED_SHA."""
    d = tmp_path / "hpc"
    rr = d / "rr"
    (d / "logs").mkdir(parents=True)
    plan = [{"index": 1, "model": "gpt-5.5", "run": 0}, {"index": 2, "model": "gpt-5.5", "run": 1},
            {"index": 3, "model": "gpt-5.5", "run": 2}, {"index": 4, "model": "alpha", "run": 0},
            {"index": 5, "model": "alpha", "run": 1}, {"index": 6, "model": "alpha", "run": 2},
            {"index": 7, "model": "alpha", "run": 3}]
    jobs = [_job("12345_1", 1, "RUNNING"), _job("12345_2", 2, "PENDING", cpus=64, node="", elapsed="00:00:00", reason="Priority"),
            _job("12345_3", 3, "COMPLETED", elapsed="03:00:00"), _job("12345_4", 4, "FAILED", elapsed="00:10:00"),
            _job("12345_5", 5, "COMPLETED", elapsed="02:00:00"), _job("12345_6", 6, "TIMEOUT", elapsed="12:00:00"),
            _job("12345_7", 7, "RUNNING", cpus=32, node="node9"),
            _job("777", 0, "RUNNING", name="sh250-qual", node="node77", elapsed="00:30:00", limit="06:00:00")]
    (d / "slurm.json").write_text(json.dumps({
        "generated_at": rd._utc(NOW - 4 * 60), "user": "user", "jobs": jobs,
        "plan": {"stage_a": plan, "qual": [{"job_id": "777", "models": ["gpt-5.5", "alpha"]}]}}))
    # mirror: gpt-5.5 g0 running (3 bots, 1 of 3 pairings), g2 finished + VERIFIED; alpha g0 FAILED marker,
    # g1 finished but no marker (the "completed but unverified" case)
    ids = _ledger(rr / "gpt-5.5" / "g0", "gpt-5.5", "g0", 0, 50, [0, 1, 2])
    _match(rr / "gpt-5.5" / "g0", *_pairs(ids)[0], NOW - 60)
    ids2 = _ledger(rr / "gpt-5.5" / "g2", "gpt-5.5", "g2", 100, 150, [100, 101])
    _match(rr / "gpt-5.5" / "g2", *_pairs(ids2)[0], NOW - 2 * H)
    _finish_group(rr / "gpt-5.5" / "g2", "gpt-5.5", ids2, [1100.0, 900.0])
    (rr / "gpt-5.5" / "g2" / "VERIFIED").touch()
    _ledger(rr / "alpha" / "g0", "alpha", "g0", 0, 50, [0, 1])
    (rr / "alpha" / "g0" / "FAILED").touch()
    ida = _ledger(rr / "alpha" / "g1", "alpha", "g1", 50, 100, [50, 51])
    _match(rr / "alpha" / "g1", *_pairs(ida)[0], NOW - H)
    _finish_group(rr / "alpha" / "g1", "alpha", ida, [1000.0, 1100.0])
    (rr / "SHIPPED_SHA").write_text("deadbeefcafe\n")
    (d / "qual").mkdir()
    old, new = d / "qual" / "STATUS-qual-100.md", d / "qual" / "STATUS-qual-777.md"
    old.write_text(STATUS_MD.format(updated="2026-09-19T12:30:00+00:00", q1=1, q2=1))
    new.write_text(STATUS_MD.format(updated="2026-09-19T13:00:00+00:00", q1=7, q2=3))
    os.utime(old, (NOW - 3 * H, NOW - 3 * H))
    os.utime(new, (NOW - 60, NOW - 60))
    (d / "qual" / "progress.jsonl").write_text('{"stem":"gpt-5.5"}\n{"stem":"alpha"}\n')
    (d / "logs" / "stage_a_12345_4.out").write_text("start\nTraceback ...\n2026-09-19 FAILED-RUN alpha g0 rc=1\n")
    (d / "logs" / "stage_a_12345_6.out").write_text("start\n")
    return d


def test_hpc_counts_cores_and_problem_flags(hpc):
    hpc_state = rd.scan_hpc(hpc, now=NOW, runs=5)
    assert hpc_state["exists"] and hpc_state["shipped_sha"] == "deadbeefcafe"
    assert hpc_state["slurm"]["user"] == "user"
    assert hpc_state["slurm"]["age_s"] == pytest.approx(240.0) and not hpc_state["slurm"]["stale"]
    assert hpc_state["by_state"] == {"pending": 1, "running": 2, "done": 2, "failed": 1, "timeout": 1, "other": 0}
    assert hpc_state["cores_running"] == 160                                     # 64 + 32 array tasks + the 64-core qualification job
    tasks = {t["index"]: t for t in hpc_state["tasks"]}
    assert len(tasks) == 7 and [t["index"] for t in hpc_state["tasks"]] == [1, 2, 3, 4, 5, 6, 7]
    assert (tasks[1]["model"], tasks[1]["run"], tasks[1]["group"]) == ("gpt-5.5", 0, "g0")
    assert (tasks[1]["done"], tasks[1]["expected"]) == (1, 3)              # from the mirror
    assert tasks[2]["done"] == 0 and tasks[2]["expected"] is None          # pending: no ledger yet
    assert tasks[3]["marker"] == "VERIFIED" and tasks[3]["problem"] is None
    assert tasks[1]["problem"] is None and tasks[2]["problem"] is None and tasks[7]["problem"] is None
    assert tasks[4]["problem"] == "FAILED" and tasks[6]["problem"] == "TIMEOUT"
    assert tasks[5]["problem"] == "COMPLETED without VERIFIED"
    assert hpc_state["problems"] == [4, 5, 6]
    assert tasks[4]["log_tail"] == "2026-09-19 FAILED-RUN alpha g0 rc=1"
    assert tasks[6]["log_tail"] == "start" and tasks[1]["log_tail"] is None
    assert hpc_state["qual_round_jobs"] == [{"job_id": "777", "state": "RUNNING", "node": "node77", "cpus": 64, "elapsed": "00:30:00",
                                 "time_limit": "06:00:00", "reason": "", "models": ["gpt-5.5", "alpha"]}]
    assert hpc_state["where"] == {"gpt-5.5": {"g0": "RUNNING", "g1": "PENDING", "g2": "COMPLETED"},
                            "alpha": {"g0": "FAILED", "g1": "COMPLETED", "g2": "TIMEOUT", "g3": "RUNNING"}}
    assert hpc_state["qual_job_of"] == {"gpt-5.5": hpc_state["qual_round_jobs"][0], "alpha": hpc_state["qual_round_jobs"][0]}
    assert hpc_state["model_job_of"] == {}


def test_hpc_stale_slurm_and_unplanned_index(hpc):
    hpc_state = rd.scan_hpc(hpc, now=NOW + 30 * 60, runs=5)
    assert hpc_state["slurm"]["stale"] and hpc_state["slurm"]["age_s"] == pytest.approx(34 * 60)
    payload = json.loads((hpc / "slurm.json").read_text())
    payload["jobs"].append(_job("12345_9", 9, "RUNNING"))
    (hpc / "slurm.json").write_text(json.dumps(payload))
    hpc_state = rd.scan_hpc(hpc, now=NOW, runs=5)
    t9 = [t for t in hpc_state["tasks"] if t["index"] == 9][0]
    assert t9["model"] is None and t9["problem"] == "index 9 not in plan"
    assert hpc_state["by_state"]["running"] == 3


def test_hpc_resubmitted_task_prefers_the_live_attempt(hpc):
    payload = json.loads((hpc / "slurm.json").read_text())
    payload["jobs"].append(_job("12399_4", 4, "PENDING", node="", elapsed="00:00:00"))    # alpha g0 resubmitted
    (hpc / "slurm.json").write_text(json.dumps(payload))
    hpc_state = rd.scan_hpc(hpc, now=NOW, runs=5)
    assert hpc_state["where"]["alpha"]["g0"] == "PENDING"
    assert [t["job_id"] for t in hpc_state["tasks"] if t["index"] == 4] == ["12345_4", "12399_4"]
    assert hpc_state["by_state"]["failed"] == 1 and hpc_state["by_state"]["pending"] == 2


def test_hpc_missing_dir_and_missing_slurm(tmp_path):
    hpc_state = rd.scan_hpc(tmp_path / "nope", now=NOW, runs=5)
    assert not hpc_state["exists"] and hpc_state["slurm"] is None and hpc_state["tasks"] == [] and hpc_state["qual_round"] is None
    (tmp_path / "e2" / "rr").mkdir(parents=True)
    hpc_state = rd.scan_hpc(tmp_path / "e2", now=NOW, runs=5)
    assert hpc_state["exists"] and hpc_state["slurm"] is None and hpc_state["shipped_sha"] is None
    assert hpc_state["by_state"] == {"pending": 0, "running": 0, "done": 0, "failed": 0, "timeout": 0, "other": 0}


def test_qual_round_totals_from_newest_status_md(hpc):
    q = rd.scan_qual_round(hpc / "qual")
    assert q["file"] == "STATUS-qual-777.md" and q["updated"] == "2026-09-19T13:00:00+00:00"
    assert q["rows"]["gpt-5.5"] == {"generated": 250, "target": 250, "gen_failed": 0, "passed": 7, "forfeit": 1,
                                    "awaiting": 4, "qual_error": 0, "remaining": 0}
    assert q["rows"]["alpha"]["passed"] == 3 and q["rows"]["alpha"]["qual_error"] == 1
    assert q["totals"] == {"generated": 500, "target": 500, "gen_failed": 2, "passed": 10, "forfeit": 3,
                           "awaiting": 7, "qual_error": 1, "remaining": 0}
    assert q["progress_records"] == 2
    assert q["files"] == ["STATUS-qual-100.md", "STATUS-qual-777.md"]
    assert q["source"] == {"gpt-5.5": "STATUS-qual-777.md", "alpha": "STATUS-qual-777.md"}
    assert rd.scan_qual_round(hpc / "no-such-qual") is None


def test_qual_round_merges_every_status_file_newest_wins(hpc):
    # a third job's file lists a model the others do not; a model in two files comes from the newer one
    third = hpc / "qual" / "STATUS-qual-900.md"
    third.write_text(STATUS_MD.format(updated="2026-09-19T14:00:00+00:00", q1=2, q2=9).replace("| gpt-5.5 |", "| omega |"))
    os.utime(third, (NOW - 30, NOW - 30))
    q = rd.scan_qual_round(hpc / "qual")
    assert q["file"] == "STATUS-qual-900.md"
    assert q["rows"]["omega"]["passed"] == 2 and q["rows"]["alpha"]["passed"] == 9 and q["rows"]["gpt-5.5"]["passed"] == 7
    assert q["source"] == {"gpt-5.5": "STATUS-qual-777.md", "alpha": "STATUS-qual-900.md", "omega": "STATUS-qual-900.md"}
    assert q["totals"]["passed"] == 18


def test_live_qual_ignores_status_files_of_superseded_jobs(hpc):
    hpc_state = rd.scan_hpc(hpc, now=NOW, runs=5)
    live = rd.live_qual(hpc_state)
    assert live["files"] == ["STATUS-qual-777.md"] and live["older"] == 1        # STATUS-qual-100.md is nobody's live job
    assert set(live["rows"]) == {"gpt-5.5", "alpha"} and live["totals"]["passed"] == 10
    # a resubmitted qualification job: the old file must not attach its counts to the new job's models
    payload = json.loads((hpc / "slurm.json").read_text())
    payload["jobs"] = [j for j in payload["jobs"] if j["name"] != "sh250-qual"] + [
        _job("778", 0, "PENDING", name="sh250-qual", node="", elapsed="00:00:00", limit="06:00:00", reason="Priority")]
    payload["plan"]["qual"] = [{"job_id": "778", "models": ["gpt-5.5", "alpha"]}]
    (hpc / "slurm.json").write_text(json.dumps(payload))
    hpc_state = rd.scan_hpc(hpc, now=NOW, runs=5)
    live = rd.live_qual(hpc_state)
    assert live["rows"] == {} and live["older"] == 2
    merged = rd.build([], runs=5, pack=None, hpc=hpc)
    rows = {r["model"]: r for r in rd.model_rows(merged)}
    assert rows["alpha"]["qual"]["passed"] is None and rows["alpha"]["qual"]["errors"] is None
    page = rd.render_html(merged, now=NOW)
    assert "older files of superseded jobs ignored" in page


def test_slurm_seconds():
    assert rd.slurm_seconds("01:23:45") == 5025 and rd.slurm_seconds("12:00:00") == 43200
    assert rd.slurm_seconds("1-02:00:00") == 93600 and rd.slurm_seconds("05:30") == 330
    assert rd.slurm_seconds("") is None and rd.slurm_seconds("UNLIMITED") is None


def test_hpc_html_array_mode_and_footer(hpc):
    merged = rd.build([], runs=5, pack=None, hpc=hpc)
    assert merged["hosts"] == ["hpc"] and merged["models"]["gpt-5.5"]["host"] == "hpc"
    page = rd.render_html(merged, now=NOW)
    assert "<script" not in page.lower() and "<link" not in page.lower()
    assert not re.search(r"(src|href)=[\"']?https?://", page)
    assert not re.search(r"Stage [AB]\b|\bB[12]\b|block[ _-]?test", page, re.I)
    assert "Qualification Round = every sample" in page and "Top Bot per Run Round = the model" in page
    # headline strip
    strip = page[page.index("<div class=strip>"):page.index("<h2>")]
    assert "user" in page and "4 min ago" in strip and "160" in strip and "cpus of RUNNING" in strip
    assert "array tasks 2 running, 1 pending" in strip
    # the primary table: array mode puts each run's task state in the job cell and in the run cell
    table = page[page.index("<h2>Top Bot per Run Round"):page.index("<h2>Qualification Round jobs")]
    assert "<th>where</th>" not in table
    row = table[table.index("<td class=model>alpha</td>"):]
    row = row[:row.index("</tr>")]
    assert "array" in row and "g0 FAILED" in row and "g3 RUNNING" in row and "g1 COMPLETED" in row
    assert "<span class=st>FAILED</span>" in row and "&#10007;" in row                      # alpha g0: FAILED marker
    assert "g1: COMPLETED without VERIFIED" in row and "g0: FAILED" in row and "g2: TIMEOUT" in row   # the live tasks' problems
    # the array-task table only because sh250-a tasks exist
    jobs = page[page.index("<h2>Qualification Round jobs"):page.index("<h2>Scoreboard")]
    assert "Top Bot per Run Round array tasks" in jobs
    assert "COMPLETED without VERIFIED" in jobs and "FAILED-RUN alpha g0" in jobs
    assert "01:23:45 / 12:00:00" in jobs and "node1234" in jobs and "1 / 3" in jobs
    # the qualification jobs table: job 777 with the passed count from ITS status file
    assert "777" in jobs and "node77" in jobs and "gpt-5.5, alpha" in jobs and "STATUS-qual-777.md" in jobs
    qrow = jobs[jobs.index("<td>777</td>"):]
    qrow = qrow[:qrow.index("</tr>")]
    assert "<td class=n>10</td>" in qrow and "<td class=n>7</td>" in qrow                   # 7 + 3 passed, 4 + 3 awaiting
    assert "1 older file of superseded jobs ignored" in jobs
    assert "Pack job" in jobs and "none in the snapshot" in jobs
    assert "deadbeefcafe" in page and "no round lost or wins &gt; losses" in page and "one SLURM job per model" in page
    md = rd.render_md(merged, now=NOW)
    assert "## Qualification Round jobs" in md and "## Top Bot per Run Round" in md and "| 12345_4 |" in md and "deadbeefcafe" in md
    assert "| 777 | RUNNING | node77 | 64 | 00:30:00 / 06:00:00 | 5:30 | gpt-5.5, alpha | 10 | 7 | 1 |" in md   # alpha: 1 qual error
    assert not re.search(r"Stage [AB]\b|\bB[12]\b|block[ _-]?test", md, re.I)


def test_html_without_hpc_shows_hosts_in_the_job_column(roots):
    merged = rd.build(roots, runs=2, pack=None, hpc=None)
    page = rd.render_html(merged, now=NOW)
    assert "Qualification Round jobs" not in page and "<h2>Top Bot per Run Round" in page
    table = page[page.index("<table class=primary>"):page.index("</table>", page.index("<table class=primary>"))]
    assert len(re.findall(r"<th>run \d</th>", table)) == 2                                # --runs 2: two run columns
    row = table[table.index("<td class=model>alpha</td>"):]
    row = row[:row.index("</tr>")]
    assert "<td class=w>host_e</td>" in row and "t00" in row and "&#10003;" in row   # host, g0 winner, VERIFIED
    assert row.index("<td class=model>alpha") < table.index("<td class=model>beta")        # running before done


def test_main_hpc_only_without_roots(hpc, tmp_path):
    out_html, out_md = tmp_path / "SH250_RR.html", tmp_path / "SH250_RR.md"
    rc = rd.main(["--hpc", str(hpc), "--out", str(out_html), "--md", str(out_md)])
    assert rc == 0
    page = out_html.read_text()
    assert "<h2>Qualification Round jobs" in page and "gpt-5.5" in page and "<script" not in page
    with pytest.raises(SystemExit):
        rd.main(["--out", str(out_html)])


def test_remaining_time_and_collapsed_array_ranges():
    from rr_dashboard import remaining_text
    assert remaining_text("01:30:00", "12:00:00") == "10:30"
    assert remaining_text("1-02:00:00", "2-00:00:00") == "22:00"
    assert remaining_text("0:00", "12:00:00") == "12:00"
    assert remaining_text("", "12:00:00") == "-"


def test_model_jobs_are_listed_with_time_left(tmp_path):
    d = tmp_path / "hpc_state"; (d / "rr").mkdir(parents=True)
    (d / "slurm.json").write_text(json.dumps({
        "generated_at": "2026-09-19T15:00:00+00:00", "user": "u",
        "jobs": [{"job_id": "77", "array_job": "77", "array_index": None, "name": "sh250-model", "state": "RUNNING",
                  "partition": "group_low", "cpus": 96, "node": "n1", "elapsed": "01:00:00", "time_limit": "23:30:00", "reason": ""}],
        "plan": {"stage_a": [], "qual": [], "model": [{"job_id": "77", "model": "gpt-5.5"}]}}))
    hpc_state = rd.scan_hpc(d, now=NOW, runs=5)
    assert hpc_state["model_jobs"][0]["model"] == "gpt-5.5" and hpc_state["cores_running"] == 96
    assert hpc_state["model_job_of"]["gpt-5.5"]["job_id"] == "77"
    merged = rd.build([], runs=5, pack=None, hpc=d, now=NOW)
    assert list(merged["models"]) == ["gpt-5.5"]                          # a row from the plan alone
    page = rd.render_html(merged, now=NOW)
    assert "gpt-5.5" in page and "left 22:30" in page and "n1 &middot; 96 cores" in page
    assert len(re.findall(r"<th>run \d</th>", page)) == 5                  # no output yet: --runs columns


# ── the primary table ────────────────────────────────────────────────────────

def _model_job(job_id, model_state, *, cpus=96, node="node1", elapsed="03:00:00", limit="23:30:00", reason=""):
    return {"job_id": job_id, "array_job": job_id, "array_index": None, "name": "sh250-model", "state": model_state,
            "partition": "group_low", "cpus": cpus, "node": node, "elapsed": elapsed, "time_limit": limit, "reason": reason}


@pytest.fixture
def cluster(tmp_path):
    """The current HPC setup. Pack (laptop-qualified, MANIFEST eligible counts): `able` (model job RUNNING; runs g0, g1
    VERIFIED with winners, g2 running 2/6, g3, g4 not started), `baker` (model job PENDING, no output), `charlie` (model job
    COMPLETED, every run VERIFIED, model VERIFIED). `dog` is queued for the Qualification Round (job 900 PENDING);
    `easy` has neither a job nor a pack entry (known only from an old status file). Pack job 950 PENDING."""
    d = tmp_path / "hpc"
    rr = d / "rr"
    (d / "qual").mkdir(parents=True)
    pack = tmp_path / "pack"
    for m in ("able", "baker", "charlie"):
        (pack / m).mkdir(parents=True)
    (pack / "MANIFEST.json").write_text(json.dumps({"models": {
        "able": {"n_samples": 250, "eligible": 21}, "baker": {"n_samples": 250, "eligible": 9},
        "charlie": {"n_samples": 250, "eligible": 12}}}))
    for k, el in enumerate([[0, 1, 2], [50, 51, 52, 53]]):                     # able g0, g1: finished + VERIFIED
        gd = rr / "able" / f"g{k}"
        ids = _ledger(gd, "able", f"g{k}", 50 * k, 50 * k + 50, el)
        for a, b in _pairs(ids):
            _match(gd, a, b, NOW - 2 * H)
        _finish_group(gd, "able", ids, [1100.0, 1000.0, 900.0, 800.0][:len(ids)])
        (gd / "VERIFIED").touch()
    g2 = rr / "able" / "g2"
    ids = _ledger(g2, "able", "g2", 100, 150, [100, 101, 102, 103])            # able g2: running, 2 of 6
    _match(g2, *_pairs(ids)[0], NOW - 60)
    _match(g2, *_pairs(ids)[1], NOW - 120)
    for k in range(5):                                                         # charlie: all done + VERIFIED
        gd = rr / "charlie" / f"g{k}"
        ids = _ledger(gd, "charlie", f"g{k}", 50 * k, 50 * k + 50, [50 * k, 50 * k + 1])
        _match(gd, *_pairs(ids)[0], NOW - 5 * H)
        _finish_group(gd, "charlie", ids, [1100.0, 900.0])
        (gd / "VERIFIED").touch()
    (rr / "charlie" / "runs.json").write_text(json.dumps({"model": "charlie", "runs": 5, "groups": []}))
    (rr / "charlie" / "top_5_bots.json").write_text("{}")
    (rr / "charlie" / "VERIFIED").touch()
    jobs = [_model_job("101", "RUNNING"), _model_job("102", "PENDING", node="", elapsed="0:00", reason="Priority"),
            _model_job("103", "COMPLETED", elapsed="10:00:00"),
            _job("900", 0, "PENDING", name="sh250-qual", node="", elapsed="0:00", limit="06:00:00", reason="Priority"),
            _job("950", 0, "PENDING", name="sh250-pack", cpus=4, node="", elapsed="0:00", limit="30:00", reason="Dependency")]
    (d / "slurm.json").write_text(json.dumps({
        "generated_at": rd._utc(NOW - 120), "user": "user", "jobs": jobs,
        "plan": {"stage_a": [], "qual": [{"job_id": "900", "models": ["dog"]}],
                 "model": [{"job_id": "101", "model": "able"}, {"job_id": "102", "model": "baker"}, {"job_id": "103", "model": "charlie"}]}}))
    old = d / "qual" / "STATUS-qual-1.md"
    old.write_text(STATUS_MD.format(updated="2026-09-19T12:30:00+00:00", q1=1, q2=1).replace("| gpt-5.5 |", "| easy |").replace("| alpha |", "| dog |"))
    return {"dir": d, "pack": pack}


def test_primary_table_has_one_row_per_model_in_state_order(cluster):
    merged = rd.build([], runs=5, pack=cluster["pack"], hpc=cluster["dir"], now=NOW)
    rows = rd.model_rows(merged)
    assert [(r["model"], r["state"]) for r in rows] == [("able", "running"), ("baker", "pending"), ("charlie", "done"),
                                                        ("dog", "qualifying"), ("easy", "waiting")]
    assert [r["label"] for r in rows] == ["running", "pending", "done", "Qualification Round PENDING", "not submitted"]
    assert rd.run_columns(merged) == 5
    able, baker, charlie, dog, easy = rows
    # able: laptop-qualified (manifest count), running job with time left, 2 runs VERIFIED, one running, two queued
    assert able["qual"] == {"where": "laptop", "job": None, "passed": 21, "awaiting": None, "forfeit": None, "errors": None}
    assert able["job"]["job_id"] == "101" and able["live"] == "RUNNING" and able["problem"] is None
    assert [g["status"] for g in able["runs"]] == ["VERIFIED", "VERIFIED", "running", "queued", "queued"]
    assert [g["eligible"] for g in able["runs"]] == [3, 4, 4, None, None]
    assert [rd.short_aid(g["winner"]) if g["winner"] else None for g in able["runs"]] == ["t00", "t50", None, None, None]
    assert (able["done"], able["expected"], able["unknown_runs"]) == (11, 15, 2)
    assert able["winners"] == ["able__t00_c000", "able__t50_c000"]
    # baker: pending job, nothing on disk
    assert baker["job"]["state"] == "PENDING" and baker["runs"] == [] and baker["qual"]["passed"] == 9
    # charlie: verified everywhere, job completed
    assert charlie["status"] == "VERIFIED" and charlie["live"] == "COMPLETED" and charlie["problem"] is None
    # dog: queued for the Qualification Round; the stale status file (job 1 is not live) gives it no counts
    assert dog["qual"]["where"] == "cluster" and dog["qual"]["job"]["job_id"] == "900" and dog["qual"]["passed"] is None
    assert dog["job"] is None and dog["runs"] == []
    assert easy["qual"] == {"where": None, "job": None, "passed": None, "awaiting": None, "forfeit": None, "errors": None}


def test_primary_table_cells_html_and_md(cluster):
    merged = rd.build([], runs=5, pack=cluster["pack"], hpc=cluster["dir"], now=NOW)
    page = rd.render_html(merged, now=NOW)
    assert "<script" not in page.lower() and "<link" not in page.lower()
    assert not re.search(r"Stage [AB]\b|\bB[12]\b|block[ _-]?test", page, re.I)
    table = page[page.index("<table class=primary>"):page.index("</table>", page.index("<table class=primary>"))]
    header = table[:table.index("</tr>")]
    assert len(re.findall(r"<th>run \d</th>", header)) == 5 and "<th>Qualification Round</th>" in header and "<th>job</th>" in header
    models = re.findall(r"<td class=model>([^<]+)</td>", table)
    assert models == ["able", "baker", "charlie", "dog", "easy"]
    rows = table.split("<tr class=")[1:]
    able, baker, charlie, dog, easy = rows[:5]
    assert able.startswith("'running'") and "laptop &middot; <b>21</b> passed" in able
    assert "101 <span class='tag RUNNING'>RUNNING</span>" in able and "node1 &middot; 96 cores" in able
    assert "03:00:00 / 23:30:00 · left 20:30" in able
    run_cells = re.findall(r"<td class='run ([A-Za-z]+)'[^>]*>(.*?)</td>", able)
    assert [c for c, _ in run_cells] == ["VERIFIED", "VERIFIED", "running", "queued", "queued"]
    assert "3 bots &middot; 3/3" in run_cells[0][1] and "t00" in run_cells[0][1] and "&#10003;" in run_cells[0][1]
    assert "4 bots &middot; 2/6" in run_cells[2][1] and "&#10003;" not in run_cells[2][1] and "bar mini b" in run_cells[2][1]
    assert "? bots" in run_cells[3][1]
    assert "11 / 15" in able and "+2?" in able and "t00 t50" in re.sub(r"<[^>]+>", "", able)
    assert baker.startswith("'pending'") and "102 <span class='tag PENDING'>PENDING</span>" in baker and "Priority" in baker
    assert charlie.startswith("'done'") and charlie.count("&#10003;") == 5 and "103 <span class='tag COMPLETED'>" in charlie
    assert dog.startswith("'qualifying'") and "job 900 <span class='tag PENDING'>PENDING</span>" in dog
    assert "after pack job 950" in dog and "Pack job" in page
    assert easy.startswith("'waiting'") and "not submitted" in easy
    # headline strip
    strip = page[page.index("<div class=strip>"):page.index("<h2>")]
    assert "1 running &middot; 1 pend." in strip and "1 done" in strip and ">96<" in strip     # model jobs 101/102/103
    assert "0 running &middot; 1 pend." in strip                                                 # qualification job 900
    assert "1 running &middot; 1 pending &middot; 1 done" in strip and "2 not started" in strip
    assert "16 / 25" in strip and "~5 est." in strip                       # 11/15 able + 5/5 charlie; able's 2 unstarted runs estimated
    # markdown twin: same table, same order
    md = rd.render_md(merged, now=NOW)
    assert "| model | state | Qualification Round | job | run 1 | run 2 | run 3 | run 4 | run 5 | progress | run winners |" in md
    lines = [ln for ln in md.splitlines() if ln.startswith("| ") and ln.split(" | ")[0][2:] in ("able", "baker", "charlie", "dog", "easy")]
    assert [ln.split(" | ")[0][2:] for ln in lines] == ["able", "baker", "charlie", "dog", "easy"]
    assert lines[0] == ("| able | running | laptop · 21 passed | 101 RUNNING · node1 · 96 cores · 03:00:00 / 23:30:00 · left 20:30 | "
                        "3 bots 3/3 t00 ✓ | 4 bots 6/6 t50 ✓ | 4 bots 2/6 | ? bots | ? bots | 11/15 +2? | t00 t50 |")
    assert lines[3] == "| dog | Qualification Round PENDING | job 900 PENDING | after pack job 950 PENDING | - | - | - | - | - | - | - |"
    assert lines[4] == "| easy | not submitted | not submitted | - | - | - | - | - | - | - | - |"


def test_primary_table_flags_a_completed_job_without_verified_and_sorts_failed_first(cluster):
    d = cluster["dir"]
    (d / "rr" / "charlie" / "VERIFIED").unlink()
    (d / "rr" / "charlie" / "g4" / "VERIFIED").unlink()
    (d / "rr" / "charlie" / "g4" / "FAILED").touch()
    payload = json.loads((d / "slurm.json").read_text())
    payload["jobs"][0]["state"] = "COMPLETED"                                     # able's job finished, its runs are not
    (d / "slurm.json").write_text(json.dumps(payload))
    merged = rd.build([], runs=5, pack=cluster["pack"], hpc=d, now=NOW)
    rows = {r["model"]: r for r in rd.model_rows(merged)}
    assert rows["charlie"]["state"] == "failed" and rows["able"]["problem"] == "COMPLETED without VERIFIED"
    assert [r["model"] for r in rd.model_rows(merged)][:2] == ["charlie", "able"]
    page = rd.render_html(merged, now=NOW)
    assert "COMPLETED without VERIFIED" in page and "&#10007;" in page
