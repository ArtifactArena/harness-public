"""The consolidated prompts are the upstream text plus one substitution list — and the config agrees.

Every item below is a user decision of 2026-09-16. A prompt that states a number the
engine does not play is worse than no prompt at all, so each substituted sentence is
pinned in BOTH prompt files next to the config value it describes.
"""
from pathlib import Path

import yaml

import mjarena.core.unified_builder  # noqa: F401  (import order: avoids the dspy_core/design_shop cycle)

ROOT = Path(__file__).resolve().parents[1]
PROMPTS = (ROOT / "configs/rules/autoresearch_prompt.md",
           ROOT / "configs/rules/sampling_prompt.md")
RULES = ROOT / "configs/rules/rules.yaml"
BASE = ROOT / "configs/tournaments/base.yaml"


def _texts() -> list[tuple[str, str]]:
    return [(p.name, p.read_text(encoding="utf-8")) for p in PROMPTS]


def test_qualification_paragraph_is_the_users_wording():
    """Not losing is the bar; winning all three is the goal (engine gate: Task 6)."""
    expected = (
        "To qualify, your robot must not lose each of three 20-second rounds against a simple "
        "baseline block. Your goal is to make a robot that wins all three rounds, but not "
        "losing is the minimum bar to qualify. Both the block and your robot start at "
        "randomized positions. The block has no motors and can freely translate, rotate, and "
        "topple. It is exempt from inactivity loss. If your robot fails to qualify, it "
        "forfeits and loses the tournament."
    )
    for name, text in _texts():
        assert expected in text, name
        assert "must win each of three 20-second rounds" not in text, name


def test_the_block_is_described_after_the_dictated_paragraph():
    """What the model is fighting: palette plastic, 342 kg (Task 14, audit flag F-N11).

    Its own sentence, after the user's paragraph — never edited into it.
    """
    paragraph_end = "it forfeits and loses the tournament."
    sentence = ("The block is a 1.2 × 1.2 × 0.25 m plastic slab of about 342 kg "
                "with the palette's plastic friction.")
    for name, text in _texts():
        assert text.count(sentence) == 1, name
        assert text.index(paragraph_end) < text.index(sentence), name
        assert "36 kg" not in text and "foam block" not in text, name


def test_tournament_rounds_are_five_minutes_in_prompt_and_config():
    for name, text in _texts():
        assert "rounds lasting up to 300 seconds" in text, name
        assert "30000 for the tournament (300 seconds)" in text, name
    base = yaml.safe_load(BASE.read_text())
    assert base["tournament"]["match"]["match_time"] == 300


def test_max_ctrl_magnitude_is_gone_from_prompt_and_rules():
    """Item I: nothing read the key; the real clip is the [-1, 1] sentence, which stays."""
    for name, text in _texts():
        assert "max_ctrl_magnitude" not in text, name
        assert "a float in `[-1, 1]`" in text, name
        assert "Motor commands range from \u22121 to 1." in text, name
    assert "max_ctrl_magnitude" not in yaml.safe_load(RULES.read_text())["robot"]["control"]
    from mjarena.design_shop.rules.mj_validators import ModelValidationConfig
    assert not hasattr(ModelValidationConfig(RULES, physics_mode="3d"), "max_ctrl_magnitude")


def test_collections_is_importable_and_listed():
    """Item A: `import collections` is allowed by the sandbox and stated in the prompt."""
    from mjarena.design_shop.policy_base import _ALLOWED_IMPORT_ROOTS
    assert "collections" in _ALLOWED_IMPORT_ROOTS
    line = "    import collections  # deque, defaultdict, Counter"
    for name, text in _texts():
        assert line in text, name
        assert text.index("import random") < text.index("import collections"), name


def test_random_is_listed_in_the_controller_environment():
    line = "    import random       # standard PRNG (seed it yourself if you need determinism)"
    for name, text in _texts():
        assert line in text, name
        assert text.index("import typing") < text.index("import random"), name


def test_option_block_sentence_follows_the_document_skeleton():
    sentence = (
        "Do not include an `<option>` block: global physics settings (timestep, gravity, "
        "integrator, solver) belong to the arena; any `<option>` in your XML is removed "
        "before validation and reported."
    )
    for name, text in _texts():
        assert sentence in text, name
        assert text.index("</mujoco>\n```") < text.index(sentence) < text.index("### BUILDING BLOCKS"), name


def test_gear_clamp_ratio_has_one_source_and_is_disabled():
    """rules.yaml is the single source; base.yaml no longer carries a second copy."""
    assert yaml.safe_load(RULES.read_text())["robot"]["control"]["gear_clamp_ratio"] == 0
    assert "gear_clamp_ratio" not in yaml.safe_load(BASE.read_text())["models_as_engineers"]
    from mjarena.core.build_config import BuildConfig
    cfg = BuildConfig(unified_generation=True,
                      autoresearch_prompt_path="configs/rules/autoresearch_prompt.md")
    assert not hasattr(cfg, "gear_clamp_ratio")
    from mjarena.design_shop.rules.mj_validators import ModelValidationConfig
    assert ModelValidationConfig(RULES, physics_mode="3d").gear_clamp_ratio == 0
    for name, text in _texts():
        assert "    gear_clamp_ratio: 0\n" in text, name


def test_gear_clamp_ratio_is_a_required_key_not_a_silent_default(tmp_path):
    """Dropping the key must fail loudly, never fall back to a hidden 5000."""
    import pytest
    from mjarena.design_shop.rules.mj_validators import ModelValidationConfig
    rules = yaml.safe_load(RULES.read_text())
    del rules["robot"]["control"]["gear_clamp_ratio"]
    path = tmp_path / "rules.yaml"
    path.write_text(yaml.safe_dump(rules), encoding="utf-8")
    with pytest.raises(KeyError, match="gear_clamp_ratio"):
        ModelValidationConfig(path, physics_mode="3d")


def test_height_limit_is_3_05_everywhere():
    for name, text in _texts():
        assert "    max_z_span_m: 3.05\n" in text, name
    robot = yaml.safe_load(RULES.read_text())["robot"]
    assert robot["size"]["max_z_span_m"] == 3.05
    # Item P: robot.size is the only size block; bounding_box_3d said the same thing twice.
    assert "bounding_box_3d" not in robot


def test_the_size_box_is_stated_as_a_match_rule_too():
    """Item B: the runtime size limit is a loss condition, and it is in the priority list."""
    runtime = (
        "During a match the limits are also checked on every control step in your robot\u2019s "
        "own root-body frame: if your robot\u2019s extents along its root axes exceed "
        "2.44 \u00d7 2.44 \u00d7 3.05 m at any step, you lose the round. Validation measures "
        "the initial pose in the root-body frame as well and rejects a robot outside the box. "
        "Design mechanisms to stay inside the box while moving."
    )
    priority = ("controller error, floor contact, size violation, inactivity, then physics "
                "instability")
    for name, text in _texts():
        assert runtime in text, name
        assert "not checked during motion" not in text, name
        assert priority in text, name


def test_the_hundred_minute_call_limit_is_stated():
    """Item C: the prompt states the timeout the harness actually arms."""
    from mjarena.dspy_core import NO_LLM_TIMEOUT_S
    sentence = (f"Each API request has a {int(NO_LLM_TIMEOUT_S // 60)}-minute wall-clock limit and a "
                "maximum output length; a request that exceeds either ends the run.")
    for name, text in _texts():
        assert sentence in text, name
        assert "There is no thinking time limit" not in text, name


def test_names_and_geom_types_the_validator_enforces_are_stated():
    """Items D, J, J2: motor names, geom names, and no type=\"mesh\"."""
    motor = ("- Every `<motor>` must have a unique `name`: your controller returns a dictionary "
             "keyed by motor name, so an unnamed motor fails validation.")
    geom = ("- Every geom must have a unique name, set by its `name` attribute. A geom without a "
            "name fails validation.")
    mesh = ("`type=\"mesh\"` is not accepted; any mesh can be expressed as an `sdf` geom from the "
            "same vertices and faces.")
    for name, text in _texts():
        assert motor in text, name
        assert geom in text, name
        assert mesh in text, name


def test_asset_stripping_ring_friction_and_the_execution_probe_are_stated():
    """Items E, F, G: three rules the code enforced while the prompt stayed silent."""
    asset = ("Any other child of `<asset>` (materials, textures) is removed before validation "
             "and reported.")
    friction = ("The platform\u2019s own friction never applies to a robot\u2013platform contact: "
                "robot geoms have contact priority 2 and the platform priority 1, so your "
                "material\u2019s friction is your traction. Priority, condim and the other contact "
                "attributes are set by the environment and cannot be changed by your XML.")
    probe = ("Before qualification, `policy_step` is called once on a real observation of your "
             "robot; an exception or a bad return there is reported as a validation failure.")
    for name, text in _texts():
        assert asset in text, name
        assert friction in text, name
        assert probe in text, name


def test_the_mesh_sentence_states_only_what_is_checked():
    """Item N: no self-intersection test exists, so the prompt no longer demands one."""
    sentence = ("The surface must be closed and outward-facing (every edge shared by exactly two "
                "triangles, positive enclosed volume).")
    for name, text in _texts():
        assert sentence in text, name
        assert "non-self-intersecting" not in text, name


def test_both_prompts_describe_the_proximity_code_the_same_way():
    """Item H: one engine, one sentence."""
    arh, sh = (p.read_text(encoding="utf-8") for p in PROMPTS)
    sentence = "Primitive proximity uses convex surface-distance queries."
    assert sentence in arh and sentence in sh
    assert "Primitive distances use MuJoCo." not in sh


def test_the_rules_block_in_the_prompt_is_the_rules_the_validator_reads():
    actual = yaml.safe_load(RULES.read_text())["robot"]
    for name, text in _texts():
        block = yaml.safe_load(text.split("```yaml\n", 1)[1].split("```", 1)[0])
        for section in ("mass", "control", "structure", "size"):
            assert actual[section] == block["robot"][section], (name, section)
        assert block["arena"]["radius_m"] == 7.5


def test_one_substitution_list_was_applied_to_both_prompts():
    """Every region a substitution touched is byte-identical in the two files.

    The two prompts are derived from the upstream iterative and performance-first
    documents by ONE shared list, so no substituted region may drift between them.
    """
    arh, sh = (p.read_text(encoding="utf-8") for p in PROMPTS)

    def region(text: str, start: str, end: str) -> str:
        cut = text.split(start, 1)[1].split(end, 1)[0]
        assert cut.strip(), (start, end)
        return cut

    for start, end in (
        ("## Qualification Round", "## MJCF syntax"),      # qualification, 300 s, rules yaml block
        ("### DOCUMENT STRUCTURE", "### BUILDING BLOCKS"),  # the <option> sentence
        ("controller_environment: |", "```"),               # the random import
        ("The simulation runs in MuJoCo", "\n"),            # {mujoco_version}
    ):
        assert region(arh, start, end) == region(sh, start, end), start
