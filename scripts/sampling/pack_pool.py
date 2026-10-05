#!/usr/bin/env python3
"""Package the SH-250 sampling pool for transfer: round-robin-essential files + an md5 manifest.

Source (the sampling run root, e.g. `LOGS-SH250/20260918`, never modified):
    <root>/manifest.json                                   prompt_md5, config md5s (launcher-written)
    <root>/<model>/cNNN/gen.json, raw_response_*.txt, raw_reasoning_*.txt, sampling_prompt.md, ...
    <root>/<model>/cNNN/tournament_00/round_robin_match/bots/<model>/
        bot_artifact.json robot.xml controller.py
        refinement/{journal.json, usage.jsonl}
        refinement/commit_0/{robot.xml, controller.py, prompt.txt}
        refinement/commit_0/qualification/match_result.json  (+ match_data.json.gz, composed.xml — NOT packed)

Pack (`--out`, the flat layout `pool_ledger.scan_pool(..., layout="pack")` reads):
    <out>/MANIFEST.json                 run_root, git_sha, prompt_md5, packed_at, models{n_samples, eligible, ledger}, files{md5}, sizes{bytes}
    <out>/sampling_prompt.md            the rendered frozen prompt (md5 == MANIFEST.prompt_md5)
    <out>/<model>/cNNN/                 gen.json raw_response_*.txt raw_reasoning_*.txt bot_artifact.json robot.xml controller.py
                                        journal.json usage.jsonl commit_0/{robot.xml,controller.py,prompt.txt} qualification/match_result.json

Every listed file is copied when present and skipped when absent; nothing else is ever copied
(no videos, no match_data.json.gz, no baseline-* bots, no config.yaml/log.txt/debug/). A slot
that only has gen.json (not yet qualified) is packed with its gen.json + raw files.

    python scripts/sampling/pack_pool.py --root LOGS-SH250/20260918 --out LOGS-SH250/20260918-pack [--models m1 m2]
    python scripts/sampling/pack_pool.py --verify LOGS-SH250/20260918-pack          # exit 1 on any finding
    python scripts/sampling/pack_pool.py --manifest-of <release dir> --out <release dir>/MANIFEST.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pool_ledger  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
CHUNK = 1 << 20  # 1 MB streamed hashing
MANIFEST_NAME = "MANIFEST.json"
PROMPT_NAME = "sampling_prompt.md"
SLOT_RE = re.compile(r"^c\d{3,}$")
RAW_RE = re.compile(r"^raw_(response|reasoning)_\d+\.txt$")

# (source path relative to the bot dir, destination path relative to the packed slot)
BOT_FILES = (
    ("bot_artifact.json", "bot_artifact.json"),
    ("robot.xml", "robot.xml"),
    ("controller.py", "controller.py"),
    ("refinement/journal.json", "journal.json"),
    ("refinement/usage.jsonl", "usage.jsonl"),
    ("refinement/commit_0/robot.xml", "commit_0/robot.xml"),
    ("refinement/commit_0/controller.py", "commit_0/controller.py"),
    ("refinement/commit_0/prompt.txt", "commit_0/prompt.txt"),
    ("refinement/commit_0/qualification/match_result.json", "qualification/match_result.json"),
)


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def md5_file(path: Path) -> tuple[str, int]:
    """Streamed md5 + byte size of one file."""
    h = hashlib.md5()
    size = 0
    with open(path, "rb") as f:
        while True:
            chunk = f.read(CHUNK)
            if not chunk:
                break
            h.update(chunk)
            size += len(chunk)
    return h.hexdigest(), size


def _copy_and_hash(src: Path, dst: Path) -> tuple[str, int]:
    """Copy src → dst in 1 MB chunks, hashing the bytes as they are written."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    h = hashlib.md5()
    size = 0
    with open(src, "rb") as fin, open(dst, "wb") as fout:
        while True:
            chunk = fin.read(CHUNK)
            if not chunk:
                break
            fout.write(chunk)
            h.update(chunk)
            size += len(chunk)
    return h.hexdigest(), size


def slot_files(root: Path, model: str, idx: int) -> list[tuple[Path, str]]:
    """The (source, packed-relpath) pairs for one slot: exactly the essential files that exist."""
    paths = pool_ledger.slot_paths(root, model, idx, "run")
    d = paths["slot"]
    bot = paths["artifact"].parent
    rel = f"{model}/c{idx:03d}"
    pairs: list[tuple[Path, str]] = []
    if (d / "gen.json").is_file():
        pairs.append((d / "gen.json", f"{rel}/gen.json"))
    if d.is_dir():
        for p in sorted(d.iterdir()):
            if p.is_file() and RAW_RE.match(p.name):
                pairs.append((p, f"{rel}/{p.name}"))
    for src_rel, dst_rel in BOT_FILES:
        src = bot / src_rel
        if src.is_file():
            pairs.append((src, f"{rel}/{dst_rel}"))
    return pairs


def discover_models(root: Path) -> list[str]:
    """Every directory under root that holds at least one cNNN slot directory."""
    models = []
    for p in sorted(root.iterdir()):
        if p.is_dir() and not p.name.startswith(".") and any(SLOT_RE.match(c.name) and c.is_dir() for c in p.iterdir()):
            models.append(p.name)
    return models


def pack(root: Path, out: Path, models: list[str], *, n_samples: int = 250, prompt_text: str, git_sha: str,
         log=None) -> dict:
    """Write the pack under `out` (must not exist) and return the manifest dict."""
    root, out = Path(root), Path(out)
    if out.exists():
        raise FileExistsError(f"refusing to pack into an existing directory: {out}")
    if not root.is_dir():
        raise FileNotFoundError(f"run root not found: {root}")
    out.mkdir(parents=True)
    files: dict[str, str] = {}
    sizes: dict[str, int] = {}
    model_entries: dict[str, dict] = {}
    for model in models:
        if not (root / model).is_dir():
            raise FileNotFoundError(f"model directory not found: {root / model}")
        _eligible, ledger = pool_ledger.scan_pool(root, model, n_samples=n_samples, layout="run")
        n_files_before = len(files)
        for idx in range(n_samples):
            for src, rel in slot_files(root, model, idx):
                files[rel], sizes[rel] = _copy_and_hash(src, out / rel)
        model_entries[model] = {"n_samples": n_samples, "eligible": sum(1 for r in ledger if r["eligible"]),
                                "ledger": ledger}
        if log:
            log(f"{model}: {len(files) - n_files_before} files, eligible {model_entries[model]['eligible']}/{n_samples}")
    prompt_bytes = prompt_text.encode("utf-8")
    (out / PROMPT_NAME).write_bytes(prompt_bytes)
    files[PROMPT_NAME] = hashlib.md5(prompt_bytes).hexdigest()
    sizes[PROMPT_NAME] = len(prompt_bytes)
    manifest = {
        "run_root": str(root),
        "git_sha": git_sha,
        "prompt_md5": files[PROMPT_NAME],
        "packed_at": _utc_now(),
        "models": model_entries,
        "n_files": len(files),
        "total_bytes": sum(sizes.values()),
        "files": dict(sorted(files.items())),
        "sizes": dict(sorted(sizes.items())),
    }
    (out / MANIFEST_NAME).write_text(json.dumps(manifest, indent=1) + "\n")
    return manifest


def _walk_files(base: Path) -> list[str]:
    return sorted(p.relative_to(base).as_posix() for p in base.rglob("*") if p.is_file())


def verify(out: Path) -> list[str]:
    """Re-hash every manifest entry; report missing, mismatched, and unlisted files. Empty list = clean."""
    out = Path(out)
    manifest = json.loads((out / MANIFEST_NAME).read_text())
    files: dict[str, str] = manifest["files"]
    sizes: dict[str, int] = manifest["sizes"]
    findings: list[str] = []
    for rel in sorted(files):
        p = out / rel
        if not p.is_file():
            findings.append(f"{rel}: missing")
            continue
        digest, size = md5_file(p)
        if digest != files[rel]:
            findings.append(f"{rel}: md5 mismatch")
        elif size != sizes[rel]:
            findings.append(f"{rel}: size mismatch")
    for rel in _walk_files(out):
        if rel != MANIFEST_NAME and rel not in files:
            findings.append(f"{rel}: not in manifest")
    return findings


def manifest_of(directory: Path, out_file: Path) -> dict:
    """md5 + byte size of every file under `directory` (the output file itself excluded)."""
    directory, out_file = Path(directory).resolve(), Path(out_file).resolve()
    files: dict[str, str] = {}
    sizes: dict[str, int] = {}
    for p in sorted(directory.rglob("*")):
        if not p.is_file() or p.resolve() == out_file:
            continue
        rel = p.relative_to(directory).as_posix()
        files[rel], sizes[rel] = md5_file(p)
    manifest = {"generated_at": _utc_now(), "root": str(directory), "n_files": len(files),
                "total_bytes": sum(sizes.values()), "files": files, "sizes": sizes}
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(manifest, indent=1) + "\n")
    return manifest


def _find_prompt(root: Path, models: list[str]) -> Path:
    for model in models:
        for slot in sorted(p for p in (root / model).iterdir() if p.is_dir() and SLOT_RE.match(p.name)):
            p = slot / PROMPT_NAME
            if p.is_file():
                return p
    sys.exit(f"refusing: no <root>/<model>/cNNN/{PROMPT_NAME} found under {root} for {models}")


def _git_sha() -> str:
    """HEAD of the checkout, or the commit recorded in SHIPPED_SHA for a `git archive` tree on a cluster."""
    proc = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True)
    if proc.returncode == 0:
        return proc.stdout.strip()
    shipped = REPO / "SHIPPED_SHA"
    if shipped.exists() and shipped.read_text().strip():
        return shipped.read_text().strip()
    raise RuntimeError(f"not a git checkout and no SHIPPED_SHA in {REPO}: {proc.stderr.strip()}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, help="sampling run root (e.g. LOGS-SH250/20260918)")
    ap.add_argument("--out", type=Path, help="pack directory to create (with --root) or manifest file (with --manifest-of)")
    ap.add_argument("--models", nargs="+", help="models to pack (default: every model directory under --root)")
    ap.add_argument("--n-samples", type=int, default=250)
    ap.add_argument("--prompt-md5", help="expected md5 of the rendered prompt (default: <root>/manifest.json prompt_md5)")
    ap.add_argument("--git-sha", help="provenance sha to record (default: git rev-parse HEAD of this repo)")
    ap.add_argument("--verify", type=Path, metavar="PACK_DIR", help="re-hash a pack; exit 1 on any finding")
    ap.add_argument("--manifest-of", type=Path, metavar="DIR", help="write an md5+size manifest of every file under DIR to --out")
    a = ap.parse_args(argv)

    if a.verify:
        findings = verify(a.verify)
        for f in findings:
            print(f)
        print(f"{'FAIL' if findings else 'OK'}: {a.verify} ({len(findings)} findings)")
        return 1 if findings else 0

    if a.manifest_of:
        if not a.out:
            ap.error("--manifest-of needs --out <file>")
        m = manifest_of(a.manifest_of, a.out)
        print(f"wrote {a.out}: {m['n_files']} files, {m['total_bytes']} bytes")
        return 0

    if not a.root or not a.out:
        ap.error("pack mode needs --root and --out")
    root = a.root
    run_manifest = root / "manifest.json"
    if not run_manifest.is_file():
        sys.exit(f"refusing: {run_manifest} is missing (the launcher writes it; the pack needs its prompt_md5)")
    expected_md5 = a.prompt_md5 or json.loads(run_manifest.read_text())["prompt_md5"]
    models = a.models or discover_models(root)
    if not models:
        sys.exit(f"refusing: no model directories under {root}")
    prompt_path = _find_prompt(root, models)
    prompt_bytes = prompt_path.read_bytes()
    actual_md5 = hashlib.md5(prompt_bytes).hexdigest()
    if actual_md5 != expected_md5:
        sys.exit(f"refusing: rendered prompt {prompt_path} md5 {actual_md5} != expected {expected_md5}")
    git_sha = a.git_sha or _git_sha()
    t0 = dt.datetime.now()
    m = pack(root, a.out, models, n_samples=a.n_samples, prompt_text=prompt_bytes.decode("utf-8"), git_sha=git_sha,
             log=lambda s: print(s, flush=True))
    print(f"packed {m['n_files']} files, {m['total_bytes']} bytes into {a.out} "
          f"({len(models)} models, sha {git_sha[:8]}, prompt {actual_md5}) in {(dt.datetime.now() - t0).total_seconds():.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
