# Ten-attempt iterative prompts

These templates extend the prompts used for the September 23, 2026 cube-feedback runs with explicit iteration counts and selection through a round robin among the ten generated bots. The original run snapshots are preserved in commit `41463859fed3948e8b3a993e15dae046c5fb6f07`; those runs used harness commit `62b916b589be2034a1500fb41c2569a623925ac8`.

- `iterative_prompt_template.md`: start from scratch.
- `starting_robot_prompt_template.md`: refine a supplied starting robot, as in the Carbon Phantom run. Its opening budget sentence and first-iteration context describe the supplied starting robot.
- `sampling_prompt.md`: the full, rendered sampling prompt inserted into either template. This frozen snapshot describes MuJoCo 3.10.0 and the rules used by those runs; it is not regenerated from the current rules.

## Rendering

Replace each `{{name}}` token literally with the corresponding value:

| Token | Value |
| --- | --- |
| `sampling_prompt` | Full contents of the adjacent `sampling_prompt.md`. |
| `submission_number` | Current attempt, 1 through 10. |
| `submissions_remaining_after_this` | 10 minus the current attempt. |
| `previous_robot_xml` | Most recent robot XML in an XML code fence. |
| `previous_controller_code` | Most recent controller in a Python code fence. |
| `previous_evaluation_feedback` | Most recent validation and baseline-block evaluation feedback, with combat score, score components, and qualification score removed. |
| `previous_full_observation_replay` | JSON replay of one baseline-block match: a loss if any, otherwise a draw if any, otherwise the slowest win. Use a JSON code fence and sample at 2 Hz as specified in the template. |

For iteration 1 from scratch, use these exact placeholder values:

- `previous_robot_xml`: `None. Create your initial robot from scratch.`
- `previous_controller_code`: `None. Create your initial controller from scratch.`
- `previous_evaluation_feedback`: `This is iteration 1. No previous robot has been created or evaluated, so there is no feedback yet.`
- `previous_full_observation_replay`: a JSON code fence containing `{"rounds":[],"unavailable_reason":"This is iteration 1. No previous robot has been created or evaluated, so there is no observation replay yet."}`.

For refinement, supply the starting robot, controller, and their evaluation. Later calls contain only the immediately previous iteration, not a history or a best-so-far replacement. The budget is ten iterations total; from scratch, that includes the initial design.

Evaluation uses the baseline block with seeds 0, 1, and 2 and a 20-second limit. Feedback omits the seven observation fields named in the templates; those fields remain available to controllers during matches. Reward monitoring and subsequent tournament measurements are external to the prompt and are not supplied as feedback.

Before inserting the replay JSON into the prompt, round floating-point values to 6 significant digits only within each observation's `contacts` and `opponent_proximity` fields, recursively including their nested data. In Python, convert NumPy arrays and scalars to ordinary lists and numbers, then apply `float(format(value, ".6g"))` only to floats inside those two fields. Leave all other replay fields at their original precision, including `contact_impulses`, recorded controller commands, and timing values. Leave integers, booleans, strings, and field names unchanged. Use compact JSON without padding trailing zeros. Apply this only to the prompt-facing replay; preserve the original recordings, robot XML, controller source, and simulation inputs. Select the replay using original, unrounded match durations.

The caller must include the seed, outcome, termination reason, and duration of all three matches in `previous_evaluation_feedback`. Include detailed observations and controller commands for exactly one match in `previous_full_observation_replay`: choose a loss if any occurred; otherwise choose a draw if any occurred; otherwise choose the win with the greatest duration. For multiple losses or draws, choose the lowest seed; break equal-duration win ties by lowest seed. Select from all captured matches, without using combat scores or the old filtered qualification matchup. The original experiment runners need this selection rule before reuse with these templates. Completed experiment artifacts retain their original feedback.

After iteration 10, the stated selection procedure runs a round robin among all ten generated bots and advances its winner to the tournament against other bots. The supplied starting robot is not an additional entrant in the ten-bot selection pool. This directory contains prompt templates only; the caller must render the iteration counts and implement the selection procedure. These edits do not change the completed runs or their selection behavior.
