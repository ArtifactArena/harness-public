{{sampling_prompt}}

## Iteration status

You have 10 revision attempts to build and improve a robot, starting from scratch.
Current iteration: {{submission_number}} of 10.
After this iteration, you will have {{submissions_remaining_after_this}} revision attempts left.
Return one complete design on this call. The harness evaluates the bot from each iteration
and provides its results on the next call.

## Previous robot XML

{{previous_robot_xml}}

## Previous controller Python

{{previous_controller_code}}

## Feedback from evaluating the previous robot against the baseline block

{{previous_evaluation_feedback}}

## Observation replay from the previous evaluation

{{previous_full_observation_replay}}

This replay contains the observation dictionaries supplied to your previous
controller's policy_step(obs), using the obs_schema section above,
with seven fields omitted from feedback: arena_grid,
arena_mass_grid, edge_distance_grid, obs_history, action_history, my_robot,
and opponent_robot. These
fields remain available to the controller during matches. Each sampled observation includes every remaining
field and all of its nested data, with no additional fields or values removed.
Each sample also includes the controller command returned for that observation. NumPy arrays and
scalars are serialized as JSON arrays and numbers. Only floating-point values
inside the contacts and opponent_proximity observation fields, including their
nested data, are rounded to 6 significant digits. All other replay fields,
including contact_impulses, controller commands, and timing values, retain
their original precision. Integers are unchanged. This rounding applies only
to replay feedback; the robot XML, controller source code, and observations
received by the controller during matches are not rounded.

Observations are sampled at 2 Hz of simulated time: one observation every
0.5 seconds (every 50 controller calls at 100 Hz), starting with the first call.
Each sample is labeled with its original control-step index and simulation time.

The feedback includes the seed, outcome, termination reason, and duration of
all three matches against the baseline block. Detailed observations and
controller commands are included for one match: a loss if there were any
losses, or the win that took the longest if all three matches were wins.
If there were no losses but at least one draw, the replay includes one draw.
The feedback and replay describe the previous robot and controller shown above. On the first iteration, there is no previous robot, controller,
evaluation feedback, or observation replay.

## Your task for this iteration

Improve the previous robot using the supplied evaluation feedback and
observation replay.

The baseline
block evaluation is evidence about your robot's performance; success against
the block alone does not establish performance against moving opponents.

You may change the hardware, the controller, or both, including replacing the design entirely.

Briefly explain the relevant feedback and your intended improvement within
the existing design_strategy section. Return all six sections required by the
Output format section above, including the complete revised robot XML and controller, even
if one is unchanged. Submit one design, not alternatives or a patch.

If there is no previous design, create your initial robot using the game rules
and design instructions above. If this is iteration 10, use the available evidence to produce your
strongest final design; there will be no further opportunity to revise it.

After all 10 iterations are complete, the 10 bots you produced, one per
iteration, will compete in a round-robin selection tournament. Each bot will
face every other bot produced over the 10 iterations. The winner of that round robin will be
selected to compete against other bots in the tournament described above.

Your ultimate goal is for the selected bot to beat the other bots in the final
tournament.
