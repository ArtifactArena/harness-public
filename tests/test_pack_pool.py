"""pack_pool copies only the round-robin-essential files and writes a verifiable md5 manifest."""
import json, sys, hashlib
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/sampling"))
import pack_pool  # noqa: E402
from test_pool_ledger import _slot  # noqa: E402


def test_pack_copies_essentials_and_manifest_verifies(tmp_path):
    root = tmp_path / "root"; d = _slot(root, "m", 3)
    bot = d / "tournament_00/round_robin_match/bots/m"
    (bot / "refinement/commit_0/qualification").mkdir(parents=True, exist_ok=True)
    pass  # the _slot fixture already wrote a real qualification match_result.json
    (bot / "refinement/commit_0/qualification/match_data.json.gz").write_bytes(b"\0" * 100)   # must NOT be packed
    (bot / "robot.xml").write_text("<mujoco/>"); (bot / "controller.py").write_text("x")
    (bot / "refinement/usage.jsonl").write_text("{}\n")
    (d / "raw_response_0.txt").write_text("raw"); (d / "config.yaml").write_text("cfg")       # config.yaml not packed
    (root / "m/c003/sampling_prompt.md").write_text("PROMPT")
    out = tmp_path / "pack"
    pack_pool.pack(root, out, ["m"], n_samples=4, prompt_text="PROMPT", git_sha="abc")
    got = sorted(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file())
    assert got == ["MANIFEST.json", "m/c003/bot_artifact.json", "m/c003/commit_0/controller.py", "m/c003/commit_0/robot.xml",
                   "m/c003/controller.py", "m/c003/gen.json", "m/c003/journal.json", "m/c003/qualification/match_result.json",
                   "m/c003/raw_response_0.txt", "m/c003/robot.xml", "m/c003/usage.jsonl", "sampling_prompt.md"]
    man = json.loads((out / "MANIFEST.json").read_text())
    assert man["git_sha"] == "abc" and man["prompt_md5"] == hashlib.md5(b"PROMPT").hexdigest()
    assert man["models"]["m"]["eligible"] == 1 and len(man["models"]["m"]["ledger"]) == 4
    assert man["files"]["m/c003/gen.json"] == hashlib.md5((d / "gen.json").read_bytes()).hexdigest()
    assert pack_pool.verify(out) == []
    (out / "m/c003/robot.xml").write_text("tampered")
    assert pack_pool.verify(out) == ["m/c003/robot.xml: md5 mismatch"]


def test_manifest_carries_sizes_and_provenance(tmp_path):
    root = tmp_path / "root"; d = _slot(root, "m", 0)
    (d / "raw_response_0.txt").write_text("raw!")
    out = tmp_path / "pack"
    pack_pool.pack(root, out, ["m"], n_samples=1, prompt_text="PROMPT", git_sha="abc")
    man = json.loads((out / "MANIFEST.json").read_text())
    assert man["run_root"] == str(root)
    assert man["packed_at"].endswith("+00:00") or man["packed_at"].endswith("Z")
    assert man["models"]["m"]["n_samples"] == 1
    assert set(man["sizes"]) == set(man["files"])
    assert man["sizes"]["m/c000/raw_response_0.txt"] == 4
    assert man["files"]["sampling_prompt.md"] == hashlib.md5(b"PROMPT").hexdigest()
    assert "MANIFEST.json" not in man["files"]
    # the ledger rows in the manifest are the run-layout ledger of the source, not of the pack
    assert man["models"]["m"]["ledger"][0]["reason"] == "eligible"


def test_unqualified_slot_packs_gen_and_raw_only(tmp_path):
    root = tmp_path / "root"
    d = _slot(root, "m", 0, qualified=False)                     # generated, awaiting qualification
    (d / "raw_response_0.txt").write_text("r0"); (d / "raw_reasoning_0.txt").write_text("think")
    (d / "log.txt").write_text("log"); (d / "config.yaml").write_text("cfg")
    _slot(root, "m", 1, generated=False, qualified=False)         # never generated: nothing packed
    out = tmp_path / "pack"
    pack_pool.pack(root, out, ["m"], n_samples=2, prompt_text="PROMPT", git_sha="abc")
    got = sorted(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file())
    assert got == ["MANIFEST.json", "m/c000/gen.json", "m/c000/raw_reasoning_0.txt", "m/c000/raw_response_0.txt", "sampling_prompt.md"]
    assert not (out / "m/c001").exists()
    man = json.loads((out / "MANIFEST.json").read_text())
    assert man["models"]["m"]["eligible"] == 0
    assert [r["reason"] for r in man["models"]["m"]["ledger"]] == ["not qualified yet", "not generated"]
    assert pack_pool.verify(out) == []


def test_pack_never_copies_baselines_or_extras(tmp_path):
    root = tmp_path / "root"; d = _slot(root, "m", 0)
    bots = d / "tournament_00/round_robin_match/bots"
    (bots / "baseline-pusher/refinement/commit_0").mkdir(parents=True)
    (bots / "baseline-pusher/robot.xml").write_text("<mujoco/>")
    (bots / ".build_progress").mkdir(); (bots / ".build_progress/m.json").write_text("{}")
    (bots / "m/debug").mkdir(); (bots / "m/debug/unified_prompt.txt").write_text("p")
    (bots / "m/refinement/design_ledger.txt").write_text("ledger")
    (bots / "m/refinement/commit_0/prompt.txt").write_text("the prompt")
    (bots / "m/refinement/commit_0/qualification").mkdir(parents=True, exist_ok=True)
    (bots / "m/refinement/commit_0/qualification/composed.xml").write_text("<mujoco/>")
    (bots / "m/refinement/commit_0/qualification/block.xml").write_text("<mujoco/>")
    (root / "m/c000.log").write_text("proc log")
    out = tmp_path / "pack"
    pack_pool.pack(root, out, ["m"], n_samples=1, prompt_text="PROMPT", git_sha="abc")
    got = sorted(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file())
    assert got == ["MANIFEST.json", "m/c000/bot_artifact.json", "m/c000/commit_0/controller.py",
                   "m/c000/commit_0/prompt.txt", "m/c000/commit_0/robot.xml", "m/c000/gen.json",
                   "m/c000/journal.json", "m/c000/qualification/match_result.json", "sampling_prompt.md"]


def test_verify_reports_missing_and_unlisted_files(tmp_path):
    root = tmp_path / "root"; _slot(root, "m", 0)
    out = tmp_path / "pack"
    pack_pool.pack(root, out, ["m"], n_samples=1, prompt_text="PROMPT", git_sha="abc")
    (out / "m/c000/gen.json").unlink()
    (out / "m/c000/stray.txt").write_text("not in the manifest")
    assert pack_pool.verify(out) == ["m/c000/gen.json: missing", "m/c000/stray.txt: not in manifest"]


def test_pack_refuses_to_overwrite_an_existing_pack(tmp_path):
    root = tmp_path / "root"; _slot(root, "m", 0)
    out = tmp_path / "pack"
    pack_pool.pack(root, out, ["m"], n_samples=1, prompt_text="PROMPT", git_sha="abc")
    try:
        pack_pool.pack(root, out, ["m"], n_samples=1, prompt_text="PROMPT", git_sha="abc")
    except FileExistsError:
        pass
    else:
        raise AssertionError("second pack into the same directory must refuse")


def test_manifest_of_arbitrary_directory(tmp_path):
    rel = tmp_path / "release"
    (rel / "a/b").mkdir(parents=True)
    (rel / "README.md").write_text("hello")
    (rel / "a/b/x.bin").write_bytes(b"\1\2\3")
    out = rel / "MANIFEST.json"
    pack_pool.manifest_of(rel, out)
    man = json.loads(out.read_text())
    assert man["files"] == {"README.md": hashlib.md5(b"hello").hexdigest(), "a/b/x.bin": hashlib.md5(b"\1\2\3").hexdigest()}
    assert man["sizes"] == {"README.md": 5, "a/b/x.bin": 3}
    assert man["n_files"] == 2 and man["total_bytes"] == 8
    assert "MANIFEST.json" not in man["files"] and man["generated_at"]
    # idempotent: re-running with the manifest already on disk still excludes it
    pack_pool.manifest_of(rel, out)
    assert json.loads(out.read_text())["n_files"] == 2


def test_cli_verify_exit_codes(tmp_path, capsys):
    root = tmp_path / "root"; _slot(root, "m", 0)
    out = tmp_path / "pack"
    pack_pool.pack(root, out, ["m"], n_samples=1, prompt_text="PROMPT", git_sha="abc")
    assert pack_pool.main(["--verify", str(out)]) == 0
    (out / "m/c000/commit_0/robot.xml").write_text("tampered")
    assert pack_pool.main(["--verify", str(out)]) == 1
    assert "m/c000/commit_0/robot.xml: md5 mismatch" in capsys.readouterr().out


def test_cli_pack_checks_prompt_md5_against_run_manifest(tmp_path):
    root = tmp_path / "root"; d = _slot(root, "m", 0)
    (d / "sampling_prompt.md").write_text("PROMPT")
    out = tmp_path / "pack"
    # no <root>/manifest.json → refuse
    try:
        pack_pool.main(["--root", str(root), "--out", str(out), "--models", "m", "--n-samples", "1", "--git-sha", "abc"])
    except SystemExit as e:
        assert e.code != 0
    else:
        raise AssertionError("must refuse without <root>/manifest.json")
    (root / "manifest.json").write_text(json.dumps({"prompt_md5": "0" * 32}))
    try:
        pack_pool.main(["--root", str(root), "--out", str(out), "--models", "m", "--n-samples", "1", "--git-sha", "abc"])
    except SystemExit as e:
        assert e.code != 0
    else:
        raise AssertionError("must refuse when the rendered prompt's md5 differs from manifest.json")
    assert not out.exists()
    (root / "manifest.json").write_text(json.dumps({"prompt_md5": hashlib.md5(b"PROMPT").hexdigest()}))
    assert pack_pool.main(["--root", str(root), "--out", str(out), "--models", "m", "--n-samples", "1", "--git-sha", "abc"]) == 0
    man = json.loads((out / "MANIFEST.json").read_text())
    assert man["prompt_md5"] == hashlib.md5(b"PROMPT").hexdigest() and man["git_sha"] == "abc"
    assert (out / "sampling_prompt.md").read_text() == "PROMPT"
    assert pack_pool.main(["--verify", str(out)]) == 0
