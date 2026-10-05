# Tool-use experiment progress

`install_progress.py DASHBOARD_DIRECTORY` adds per-run progress cards beneath
the existing tool-use batch progress summary. Run it with `progress.js` and
`progress.css` in the same directory. It backs up the three dashboard files
before atomically replacing them and updates asset versions for fresh loads.
No experiment processes or dashboard server restart are required.

Cards use the existing tool-use status data and follow the existing repeat
filter. They show completed model turns, run state, remaining API-time estimate,
API cost, tool-call count, saved-bot count, and expandable error details. A
successful early finish remains completed even with unused turns; turn bars
show the actual turn count. A failed run remains stopped even at 10/10 turns.
“View run” selects the corresponding existing tool-use plots and morphology.

The refresh signature includes every displayed progress field, so other runs'
costs, stages, and timing update even when they are not the selected model.

Validated with a current 62-run snapshot, repeat filtering (21 runs for repeat
1), selection buttons, JavaScript error checks, and desktop/mobile rendering.
