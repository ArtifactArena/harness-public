# MiniMax M3 and Claude Opus 5 exclusions

On 2026-09-25 UTC, the user requested omission of both models from iterative
and tool-use runs, progress denominators and tournaments. Claude Opus 4.8 is
retained. Model matching uses exact provider model IDs.

`omit_models.py DEPLOYMENT_ROOT` previews the affected entries; `--apply`
archives the original files, removes the entries from the active registries,
updates dashboard labels, and patches tournament result handlers to acknowledge
and ignore late excluded uploads. The roster coordinator now reads its registry
instead of a hardcoded run list. The utility refuses an already-applied deployment
and refuses locked run directories. It changes no model prompt or physics code.

The deployment on Host A uses
`<work-root>/model-exclusions-20260925` for original
files, before/after hashes, removed records and service reload logs. Saved model
responses, bots, replays, selections and match files remain on disk. An
`EXCLUDED.json` marker and launch-script guard prevent old recovery commands
from restarting the omitted runs.

Active sets after removal:

| Set | Before | After |
| --- | ---: | ---: |
| Current iterative runs | 53 | 48 |
| Current iterative iteration budget | 530 | 480 |
| Current iterative selection-match budget | 14,310 | 12,960 |
| Tool-use runs | 46 | 42 |
| Tool-use turn budget | 460 | 420 |
| Historical roster runs | 14 | 13 |
| Historical roster match budget | 23,100 | 21,450 |
| Historical iterative leaderboard models | 18 | 17 |

The leaderboard already had only 17 eligible representatives: Opus 5 had no
eligible representative, so removing its placeholder leaves the completed
816-match leaderboard and its ratings unchanged. The fixed sampling-champion
opponent field and previously recorded sampling comparisons are retained.

Reload the registry-reading services on ports 8002, 8003, 8006 and 8010, then
the dashboard on 8000. Verify each process owner, start time, working directory
and command before restarting only that service. Preserve remote match workers;
their heartbeats and durable results restore ownership while coordinators scan
the retained candidates. Existing status snapshots remain visible until that
scan finishes. Inspect the regenerated snapshots before declaring completion.

Tests in `test_omit_models.py` verify exact model matching and real HTTP uploads:
excluded results do not enter memory or disk, while Opus 4.8 results still do.
