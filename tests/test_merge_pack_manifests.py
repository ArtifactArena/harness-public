"""merge_pack_manifests: the release's one pack manifest from several per-platform pack manifests,
files re-hashed from the union directory and checked against every source."""
import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/sampling"))
import merge_pack_manifests  # noqa: E402

PROMPT = b"THE FROZEN PROMPT\n"


def _manifest(models, files, *, sha, root):
    return {"run_root": root, "git_sha": sha, "prompt_md5": hashlib.md5(PROMPT).hexdigest(), "packed_at": "2026-09-19T00:00:00+00:00",
            "models": models, "n_files": len(files), "total_bytes": sum(len(b) for b in files.values()),
            "files": {rel: hashlib.md5(b).hexdigest() for rel, b in files.items()},
            "sizes": {rel: len(b) for rel, b in files.items()}}


@pytest.fixture
def packs(tmp_path):
    """Two source packs (one model each) and their union directory."""
    files_a = {"alpha/c000/gen.json": b"{}", "alpha/c000/commit_0/robot.xml": b"<mujoco/>", "sampling_prompt.md": PROMPT}
    files_b = {"beta/c000/gen.json": b"{1}", "beta/c001/controller.py": b"pass\n", "sampling_prompt.md": PROMPT}
    ledger = [{"idx": 0, "generated": True, "eligible": True, "reason": "eligible"}]
    a = tmp_path / "pack-a"
    b = tmp_path / "pack-b"
    a.mkdir()
    b.mkdir()
    (a / "MANIFEST.json").write_text(json.dumps(_manifest({"alpha": {"n_samples": 1, "eligible": 1, "ledger": ledger}}, files_a, sha="a" * 40, root="LOGS/gen")))
    (b / "MANIFEST.json").write_text(json.dumps(_manifest({"beta": {"n_samples": 2, "eligible": 1, "ledger": ledger}}, files_b, sha="b" * 40, root="work/gen")))
    union = tmp_path / "pack-all"
    for files in (files_a, files_b):
        for rel, content in files.items():
            p = union / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(content)
    return a, b, union


def test_merge_tags_models_and_rehashes_the_union(packs):
    a, b, union = packs
    m = merge_pack_manifests.merge(union, [("laptop", a / "MANIFEST.json"), ("gpu", b / "MANIFEST.json")])
    assert m["n_models"] == 2 and sorted(m["models"]) == ["alpha", "beta"]
    assert m["models"]["alpha"]["qualified_on"] == "laptop" and m["models"]["alpha"]["git_sha"] == "a" * 40
    assert m["models"]["beta"]["qualified_on"] == "gpu" and m["models"]["beta"]["source_manifest"] == str(b / "MANIFEST.json")
    assert m["models"]["beta"]["n_samples"] == 2 and m["models"]["beta"]["eligible"] == 1
    assert m["prompt_md5"] == hashlib.md5(PROMPT).hexdigest()
    assert m["n_files"] == 5 and set(m["files"]) == {"alpha/c000/gen.json", "alpha/c000/commit_0/robot.xml", "beta/c000/gen.json",
                                                      "beta/c001/controller.py", "sampling_prompt.md"}
    assert m["files"]["beta/c001/controller.py"] == hashlib.md5(b"pass\n").hexdigest() and m["sizes"]["beta/c001/controller.py"] == 5
    assert [s["qualified_on"] for s in m["sources"]] == ["laptop", "gpu"] and m["sources"][1]["models"] == ["beta"]
    assert m["total_bytes"] == sum(m["sizes"].values())


def test_merge_refuses_conflicts_and_gaps(packs):
    a, b, union = packs
    with pytest.raises(RuntimeError, match="packed by both"):
        merge_pack_manifests.merge(union, [("laptop", a / "MANIFEST.json"), ("laptop", a / "MANIFEST.json")])
    (union / "beta/c001/controller.py").write_bytes(b"tampered")
    with pytest.raises(RuntimeError, match="beta/c001/controller.py: md5/size differs"):
        merge_pack_manifests.merge(union, [("laptop", a / "MANIFEST.json"), ("gpu", b / "MANIFEST.json")])
    (union / "beta/c001/controller.py").write_bytes(b"pass\n")
    (union / "stray.txt").write_bytes(b"x")
    with pytest.raises(RuntimeError, match="stray.txt: in .* but listed by no source"):
        merge_pack_manifests.merge(union, [("laptop", a / "MANIFEST.json"), ("gpu", b / "MANIFEST.json")])
    (union / "stray.txt").unlink()
    (union / "alpha/c000/gen.json").unlink()
    with pytest.raises(RuntimeError, match="alpha/c000/gen.json: listed by .* but missing"):
        merge_pack_manifests.merge(union, [("laptop", a / "MANIFEST.json"), ("gpu", b / "MANIFEST.json")])


def test_merge_refuses_prompt_disagreement(packs):
    a, b, union = packs
    doc = json.loads((b / "MANIFEST.json").read_text())
    doc["prompt_md5"] = "0" * 32
    (b / "MANIFEST.json").write_text(json.dumps(doc))
    with pytest.raises(RuntimeError, match="prompt_md5"):
        merge_pack_manifests.merge(union, [("laptop", a / "MANIFEST.json"), ("gpu", b / "MANIFEST.json")])


def test_main_writes_the_manifest(packs, tmp_path):
    a, b, union = packs
    out = tmp_path / "release/pack-MANIFEST.json"
    rc = merge_pack_manifests.main(["--pack-root", str(union), "--out", str(out),
                                    "--source", f"laptop={a / 'MANIFEST.json'}", "--source", f"gpu={b / 'MANIFEST.json'}"])
    assert rc == 0
    m = json.loads(out.read_text())
    assert m["n_models"] == 2 and m["models"]["beta"]["qualified_on"] == "gpu"
    assert merge_pack_manifests.main(["--pack-root", str(union), "--out", str(out), "--source", "nonsense"]) == 1
