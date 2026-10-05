"""Formatting extraction must not modify code or silently choose a design."""
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

import mjarena.core.unified_builder  # Match the application's import order.
from mjarena.dspy_core import _strip_markdown_code_block, _strip_mjcf_tags
from mjarena.design_shop.policy_base import _strip_code_fences, compile_policy_function
from mjarena.design_shop.rules.hardware_rules import strip_wrappers
from mjarena.design_shop.rules.mj_validators import ModelValidationConfig
from mjarena.design_shop.pipelines.morphology_pipeline import validate_morphology
from mjarena.utils.code_blocks import extract_code_block


@pytest.mark.parametrize('code', [
    '  <mujoco/>\n\n',
    'def policy_step(obs):\n    return {}\n',
    'text = """\n```\n---\n"""\n',
    '<mujoco><!--\n```\n---\n--></mujoco>\n',
])
def test_raw_code_is_unchanged(code):
    assert extract_code_block(code) == code


@pytest.mark.parametrize('fence,label,newline', [
    ('```', 'xml', '\n'), ('```', 'python', '\n'), ('```', '', '\n'),
    ('~~~~', 'python', '\n'), ('````', 'xml', '\r\n'),
])
def test_single_block_and_surrounding_separators(fence, label, newline):
    code = '  first line' + newline + '\tsecond line' + newline + newline
    wrapped = f'\n---\n  {fence}{label}{newline}{code}  {fence}\n\n---\n***\n___\n'
    assert extract_code_block(wrapped) == code
    assert _strip_markdown_code_block(wrapped) == code
    assert _strip_code_fences(wrapped) == code


def test_gpt51_fence_then_separator_reaches_both_validators():
    xml = '<mujoco><worldbody/></mujoco>\n'
    python = 'def policy_step(obs):\n    return {"drive": 0.25}\n'
    raw_xml = '```xml\n' + xml + '```\n\n---'
    raw_python = '```python\n' + python + '```\n\n---'
    extracted = _strip_mjcf_tags(_strip_markdown_code_block(raw_xml))
    cleaned, result = strip_wrappers(extracted)
    assert result.passed
    assert ET.tostring(ET.fromstring(cleaned)) == ET.tostring(ET.fromstring(xml))
    assert compile_policy_function(raw_python)({}) == {'drive': 0.25}
    assert compile_policy_function(_strip_markdown_code_block(raw_python))({}) == {'drive': 0.25}


@pytest.mark.parametrize('raw', [
    '```xml\n<mujoco/>\n```\n---\n```xml\n<mujoco/>\n```',
    '```xml\n<mujoco/>\n```\nHere is another option.',
    '```xml\n<mujoco/>',
    '````xml\n<mujoco/>\n```',
])
def test_ambiguous_or_unclosed_blocks_are_rejected(raw):
    with pytest.raises(ValueError):
        extract_code_block(raw)
    # Early extraction must not crash the loop or destroy the diagnostic.
    assert _strip_mjcf_tags(_strip_markdown_code_block(raw)) == raw
    _, result = strip_wrappers(raw)
    assert not result.passed
    with pytest.raises(ValueError):
        _strip_code_fences(raw)


def test_longer_fence_preserves_embedded_shorter_fences():
    code = 'text = """\n```\n---\n"""\n'
    assert extract_code_block('````python\n' + code + '````\n---') == code


def test_malformed_xml_is_not_repaired():
    raw = '```xml\n<mujoco><worldbody></mujoco>\n```\n---'
    with pytest.raises(ET.ParseError):
        ET.fromstring(extract_code_block(raw))


def test_extraction_failure_is_validation_feedback():
    root = Path(__file__).resolve().parents[1]
    raw = '```xml\n<mujoco/>\n```\n```xml\n<mujoco/>\n```'
    result = validate_morphology(raw, ModelValidationConfig(root/'configs/rules/rules.yaml', physics_mode='3d'))
    assert not result.passed
    assert 'Expected one code block' in result.feedback
    assert 'Unexpected error' not in result.feedback
