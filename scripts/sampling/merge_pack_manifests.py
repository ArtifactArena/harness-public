#!/usr/bin/env python3
"""Merge several pack manifests (pack_pool.py) into the ONE pack manifest of a release.

The SH-250 pool was packed in pieces — one pack per platform that ran a model's Qualification
Round — and the release's `samples/` folder is their union (`pack-all`). This helper writes the
merged `pack-MANIFEST.json`: the models map of every source manifest (each model tagged with
the pack it came from and the platform that qualified it), and the md5 + byte size of every
file re-hashed from the union directory.

    python scripts/sampling/merge_pack_manifests.py --pack-root LOGS-SH250/pack-all --out <release>/pack-MANIFEST.json \
        --source laptop=LOGS-SH250/20260918-pack-a/MANIFEST.json \
        --source hpc=LOGS-SH250/gpu/pack-gpu-1/MANIFEST.json ... \
        --source gpu=LOGS-SH250/gpu/qp/pack-gpu-3-gpt-5.5/MANIFEST.json ...

`--source <platform>=<MANIFEST.json>`: the platform key names where that pack's models were
qualified (a key of release_readme.PLATFORMS). Refuses (exit 1) when: a model is in two source
manifests; the source manifests disagree on prompt_md5, or the union's sampling_prompt.md has
another md5; a file listed by a source is missing from the union or has another md5/size; the
union holds a file no source lists. Missing keys raise — no silent defaults.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pack_pool import PROMPT_NAME, md5_file  # noqa: E402


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def parse_source(spec: str) -> Tuple[str, Path]:
    if "=" not in spec:
        raise ValueError(f"--source expects <platform>=<MANIFEST.json>, got {spec!r}")
    platform, path = spec.split("=", 1)
    if not platform:
        raise ValueError(f"--source {spec!r}: empty platform key")
    return platform, Path(path)


def merge(pack_root: Path, sources: Sequence[Tuple[str, Path]]) -> Dict[str, Any]:
    """The merged manifest dict (see module doc). Raises RuntimeError on any inconsistency."""
    pack_root = Path(pack_root)
    if not pack_root.is_dir():
        raise FileNotFoundError(f"pack root {pack_root} is not a directory")
    if not sources:
        raise ValueError("at least one --source is required")

    models: Dict[str, Any] = {}
    expected_files: Dict[str, Tuple[str, int, str]] = {}   # rel -> (md5, size, source manifest)
    prompt_md5s = set()
    source_entries: List[Dict[str, Any]] = []
    findings: List[str] = []
    for platform, manifest_path in sources:
        if not manifest_path.is_file():
            raise FileNotFoundError(f"source manifest {manifest_path} is missing")
        m = json.loads(manifest_path.read_text())
        prompt_md5s.add(m["prompt_md5"])
        source_entries.append({
            "manifest": str(manifest_path), "run_root": m["run_root"], "git_sha": m["git_sha"],
            "packed_at": m["packed_at"], "qualified_on": platform, "models": sorted(m["models"]),
            "n_files": int(m["n_files"]), "total_bytes": int(m["total_bytes"]),
        })
        for model, entry in m["models"].items():
            if model in models:
                findings.append(f"{model}: packed by both {models[model]['source_manifest']} and {manifest_path}")
                continue
            models[model] = {
                "n_samples": int(entry["n_samples"]), "eligible": int(entry["eligible"]), "ledger": entry["ledger"],
                "source_manifest": str(manifest_path), "git_sha": m["git_sha"], "packed_at": m["packed_at"],
                "qualified_on": platform,
            }
        for rel, md5 in m["files"].items():
            size = int(m["sizes"][rel])
            if rel in expected_files and expected_files[rel][:2] != (md5, size):
                findings.append(f"{rel}: {expected_files[rel][2]} and {manifest_path} list different content")
            expected_files.setdefault(rel, (md5, size, str(manifest_path)))
    if len(prompt_md5s) != 1:
        findings.append(f"source manifests disagree on prompt_md5: {sorted(prompt_md5s)}")
    prompt_md5 = sorted(prompt_md5s)[0]

    files: Dict[str, str] = {}
    sizes: Dict[str, int] = {}
    for p in sorted(pack_root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(pack_root).as_posix()
        files[rel], sizes[rel] = md5_file(p)
        if rel not in expected_files:
            findings.append(f"{rel}: in {pack_root} but listed by no source manifest")
        elif (files[rel], sizes[rel]) != expected_files[rel][:2]:
            findings.append(f"{rel}: md5/size differs from {expected_files[rel][2]}")
    for rel in sorted(set(expected_files) - set(files)):
        findings.append(f"{rel}: listed by {expected_files[rel][2]} but missing from {pack_root}")
    if PROMPT_NAME not in files:
        findings.append(f"{PROMPT_NAME} missing from {pack_root}")
    elif files[PROMPT_NAME] != prompt_md5:
        findings.append(f"{PROMPT_NAME} md5 {files[PROMPT_NAME]} != sources' prompt_md5 {prompt_md5}")
    if findings:
        raise RuntimeError("refusing to merge:\n  " + "\n  ".join(findings[:50]) +
                           (f"\n  ... {len(findings) - 50} more" if len(findings) > 50 else ""))

    return {
        "merged_at": _utc_now(),
        "pack_root": str(pack_root),
        "prompt_md5": prompt_md5,
        "sources": source_entries,
        "models": dict(sorted(models.items())),
        "n_models": len(models),
        "n_files": len(files),
        "total_bytes": sum(sizes.values()),
        "files": files,
        "sizes": sizes,
    }


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pack-root", type=Path, required=True, help="the union pack directory (samples/ of the release)")
    ap.add_argument("--out", type=Path, required=True, help="merged manifest to write")
    ap.add_argument("--source", action="append", default=[], metavar="PLATFORM=MANIFEST",
                    help="a source pack manifest and the platform that qualified its models (repeatable)")
    a = ap.parse_args(argv)
    try:
        sources = [parse_source(s) for s in a.source]
        merged = merge(a.pack_root, sources)
    except (RuntimeError, ValueError, FileNotFoundError) as e:
        print(e, file=sys.stderr)
        return 1
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(merged, indent=1) + "\n")
    print(f"wrote {a.out}: {merged['n_models']} models from {len(sources)} packs, "
          f"{merged['n_files']} files, {merged['total_bytes']} bytes, prompt {merged['prompt_md5']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
