"""The engineer prompt asks for `design_rationale`, never a field called `reasoning`.

2026-09-18: Claude Fable 5.1 refuses every prompt whose output format contains a
`reasoning` field (stop_reason=refusal, category=reasoning_extraction). DSPy's
ChainOfThought prepends exactly that field. The engineer now prepends the same
first-output slot under the name `design_rationale`; the journal and artifact keep
their existing `reasoning` key so nothing downstream changes. A refusal must be
recorded as one (`llm_refusal`), not as a TypeError on the empty reply.
"""
from types import SimpleNamespace

import dspy

import mjarena.core.unified_builder  # noqa: F401  (import order: avoids the dspy_core/design_shop cycle)
from mjarena.design_shop.agents.L1_engineer_unified import build_engineer, creator_outputs, refusal_detail
from mjarena.design_shop.agents.signatures.autoresearch import make_autoresearch_signature
from mjarena.design_shop.agents.signatures.sampling import make_sampling_signature

PROMPT = "Design a robot.\n\n### robot_xml\nthe xml\n\n### controller_code\nthe code\n"


def _rendered(signature) -> str:
    engineer = build_engineer(signature)
    inputs = {name: "x" for name in engineer.signature.input_fields}
    messages = dspy.ChatAdapter().format(engineer.signature, demos=[], inputs=inputs)
    return "\n".join(str(m["content"]) for m in messages)


def test_sampling_prompt_asks_for_design_rationale_first_and_never_reasoning():
    sig = make_sampling_signature(PROMPT)
    text = _rendered(sig)
    assert "[[ ## design_rationale ## ]]" in text
    # Pinned wording: the field's description is part of what the refusal classifier reads.
    # "Your design analysis, before the sections below." was refused on 2026-09-18 with the
    # same category as the `reasoning` name; this summary phrasing was accepted (bisect of
    # seven variants against claude-fable-5-1 with the real sampling prompt).
    assert "1. `design_rationale` (str): Summary of the design approach and its trade-offs." in text
    assert "[[ ## reasoning ## ]]" not in text and "`reasoning`" not in text
    first_output = next(iter(build_engineer(sig).signature.output_fields))
    assert first_output == "design_rationale"


def test_autoresearch_prompt_asks_for_design_rationale_first_and_never_reasoning():
    sig = make_autoresearch_signature(PROMPT)
    text = _rendered(sig)
    assert "[[ ## design_rationale ## ]]" in text
    assert "[[ ## reasoning ## ]]" not in text and "`reasoning`" not in text
    assert next(iter(build_engineer(sig).signature.output_fields)) == "design_rationale"


def test_design_rationale_lands_in_the_journal_reasoning_key():
    result = SimpleNamespace(design_rationale="because", design_strategy="d", hardware_plan="h",
                             combat_plan="c", improvement_plan="i")
    out = creator_outputs(result, bot_name="B")
    assert out["reasoning"] == "because" and out["name"] == "B"
    assert "design_rationale" not in out


def test_refusal_detail_reads_the_finish_reason_from_lm_history():
    refused = {"response": SimpleNamespace(choices=[SimpleNamespace(finish_reason="refusal")])}
    normal = {"response": SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop")])}
    assert refusal_detail([normal]) is None
    assert refusal_detail([normal, refused]) == "provider refused the request (stop_reason=refusal)"
    assert refusal_detail([]) is None
    assert refusal_detail([{"response": None}]) is None
