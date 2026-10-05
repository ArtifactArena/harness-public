import mjarena.core.unified_builder  # noqa: F401
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
AUDIT = (ROOT / "docs/rules-audit-2026-09.md").read_text()


def test_every_validator_is_in_the_audit():
    names = re.findall(r"^def (validate_\w+)", (ROOT / "mjarena/design_shop/rules/mj_validators.py").read_text(), re.M)
    missing = [n for n in names if n not in AUDIT]
    assert not missing, missing


def test_every_rules_yaml_check_is_in_the_audit():
    checks = yaml.safe_load((ROOT / "configs/rules/rules.yaml").read_text())["validation"]["checks"]
    missing = [c for c in checks if c.split("(")[0].strip()[:30] not in AUDIT]
    assert not missing, missing


def test_every_termination_reason_is_in_the_audit():
    reasons = set(re.findall(r'termination_reason"\] = "(\w+)"', (ROOT / "mjarena/envs/sumo.py").read_text()))
    missing = [r for r in reasons if f"`{r}`" not in AUDIT]
    assert not missing, missing


# ---------------------------------------------------------------------------
# Prompt line citations (`ARH:<n>` / `SH:<m>`) must still point at the line they
# quote. They rotted once already: Task 15 inserted sentences into both prompts
# and every citation from the Qualification Round onward drifted 2–6 lines.
# ---------------------------------------------------------------------------

PROMPTS = {
    "ARH": (ROOT / "configs/rules/autoresearch_prompt.md").read_text().splitlines(),
    "SH": (ROOT / "configs/rules/sampling_prompt.md").read_text().splitlines(),
}
_CITE = re.compile(r"\b(ARH|SH):(\d+)(?:–(\d+))?")
_FRAG = re.compile(r'"((?:[^"\\]|\\.){5,})"' + r"|`([^`]{3,})`")
# A backticked path is a file the audit points at, not a phrase quoted from the prompt.
_FILE_REF = re.compile(r"^[\w./+-]+\.(?:md|ya?ml|py|xml|json|sh|csv)(?::\d+(?:–\d+)?)?$")


def _flat(text: str) -> str:
    """Whitespace-insensitive form, so a quote may re-wrap without breaking."""
    return " ".join(text.replace("\\\"", '"').split())


def _fragment_texts(chunk: str, after: int):
    """The quoted / backticked phrases that follow the citations in one chunk."""
    out = []
    for m in _FRAG.finditer(chunk):
        if m.start() < after:
            continue
        raw = m.group(1) if m.group(1) is not None else m.group(2)
        # "a … b" is an elided quote: the longest verbatim run is what we check.
        longest = max(re.split(r"…|\.\.\.", raw), key=len).strip().strip(",.;:")
        if len(longest) >= 8 and not _FILE_REF.match(longest):
            out.append(_flat(longest))
    return out


def _citation_groups():
    """(audit line no, chunk, ARH citations, SH citations, fragments) per group.

    A group is one `;`-separated clause of a table cell (or of a prose line):
    `ARH:a / SH:b "quote"`. The quote follows the whole group, so it is checked
    against the group's citations, not against one of them.
    """
    for lineno, row in enumerate(AUDIT.splitlines(), 1):
        if not _CITE.search(row):
            continue
        for cell in row.replace("&lt;", "<").replace("&gt;", ">").split("|"):
            for chunk in cell.split(";"):
                cites = list(_CITE.finditer(chunk))
                if not cites:
                    continue
                arh = [c for c in cites if c.group(1) == "ARH"]
                sh = [c for c in cites if c.group(1) == "SH"]
                yield lineno, chunk, arh, sh, _fragment_texts(chunk, cites[-1].end())


def _cited_lines(cite):
    first = int(cite.group(2))
    last = int(cite.group(3)) if cite.group(3) else first
    return cite.group(1), range(first, last + 1)


def test_every_cited_prompt_line_exists_and_is_not_blank():
    bad = []
    for lineno, chunk, arh, sh, _ in _citation_groups():
        for cite in arh + sh:
            key, span = _cited_lines(cite)
            lines = PROMPTS[key]
            for n in span:
                if n > len(lines) or not lines[n - 1].strip():
                    bad.append(f"audit:{lineno} {cite.group(0)} -> blank/out-of-range line {n}")
    assert not bad, bad


def test_paired_citations_point_at_the_same_sentence_in_both_prompts():
    """`ARH:a / SH:b` is one rule quoted from two files whose rule text is
    byte-identical, so the two cited lines must read the same. This pins the
    citations that carry no quotable fragment of their own."""
    bad = []
    for lineno, chunk, arh, sh, _ in _citation_groups():
        if len(arh) != len(sh) or not arh:
            continue
        for a, s in zip(arh, sh):
            _, aspan = _cited_lines(a)
            _, sspan = _cited_lines(s)
            atext = _flat("\n".join(PROMPTS["ARH"][n - 1] for n in aspan))
            stext = _flat("\n".join(PROMPTS["SH"][n - 1] for n in sspan))
            if atext != stext:
                bad.append(f"audit:{lineno} {a.group(0)} != {s.group(0)}: {atext[:70]!r} vs {stext[:70]!r}")
    assert not bad, bad


def test_quoted_fragments_appear_within_one_line_of_the_citation():
    """Every phrase the audit quotes must still sit at (or beside) the line it cites."""
    bad = []
    for lineno, chunk, arh, sh, frags in _citation_groups():
        if not frags:
            continue
        for key, cites in (("ARH", arh), ("SH", sh)):
            if not cites:
                continue
            lines = PROMPTS[key]
            window = set()
            for cite in cites:
                _, span = _cited_lines(cite)
                for n in span:
                    window.update(range(max(1, n - 1), min(len(lines), n + 1) + 1))
            hay = _flat("\n".join(lines[n - 1] for n in sorted(window)))
            for frag in frags:
                if frag not in hay:
                    bad.append(f"audit:{lineno} {key} {[c.group(0) for c in cites]}: {frag[:60]!r} not within ±1")
    assert not bad, bad


def test_termination_reason_inventory_cites_the_line_that_sets_it():
    """§G pairs each `termination_reason` with a `sumo.py:<n>`. The audit's code
    citations rot exactly like its prompt citations, and this table is the one
    where the claim is checkable verbatim."""
    sumo = (ROOT / "mjarena/envs/sumo.py").read_text().splitlines()
    rows = re.findall(r"^\| `(\w+)` \| `sumo\.py:(\d+)` \|", AUDIT, re.M)
    assert rows, "no §G rows parsed — did the table change shape?"
    bad = []
    for reason, lineno in rows:
        n = int(lineno)
        cited = sumo[n - 1] if n <= len(sumo) else "<out of range>"
        if f'termination_reason"] = "{reason}"' not in cited:
            bad.append(f"{reason} cites sumo.py:{n}, which reads {cited.strip()[:60]!r}")
    assert not bad, bad
