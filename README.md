# ArtifactArena Harness

[Kushagra Tiwary](https://www.kushagratiwary.com/)<sup>\*1,2</sup>,
[David Mayo](http://david-mayo.com/)<sup>\*1</sup>,
[Nikhil Behari](https://nikhilbehari.github.io/)<sup>1,2</sup>,
Xiangzhou Sun<sup>1</sup>,
[Abdulrahman Alabdulkareem](https://arkareem.com/)<sup>1</sup>,
[Isaac Galatzer-Levy](https://med.nyu.edu/faculty/isaac-r-galatzer-levy)<sup>3</sup>,
[Boris Katz](https://people.csail.mit.edu/boris/boris.html)<sup>1</sup>, and
[Brian Cheung](https://briancheung.github.io/)<sup>†1,4</sup>

<sup>1</sup>[InfoLab, MIT CSAIL](https://www.csail.mit.edu/research/infolab) ·
<sup>2</sup>[Camera Culture, MIT Media Lab](https://www.media.mit.edu/groups/camera-culture/overview/) ·
<sup>3</sup>[Department of Psychiatry, NYU Grossman School of Medicine](https://med.nyu.edu/departments-institutes/psychiatry/) ·
<sup>4</sup>[Discovery Lab, UCSF](https://discolab.org/)

<sup>\*</sup>Equal contribution · <sup>†</sup>Corresponding PI ·
Correspondence: ktiwary@mit.edu, dmayo2@mit.edu, bcheung@ucsf.edu

**ArtifactArena evaluates models by what they build in the physical world.** Each model
designs a complete robot artifact (a MuJoCo body in MJCF XML and a Python controller),
and the artifacts compete head-to-head in the *Last Bot Standing* game on an elevated
ring. Models are ranked by the Bradley–Terry Elo of their artifacts.

This repository is the simulator, the verifier and two of the paper's three
test-time generation harnesses: the **Sampling Harness (SH)** and the
**Verifier-Grounded Refinement Harness (VGH)**. The **Design Lab Harness (DLH)** is
released separately as [design-lab-harness](https://github.com/ArtifactArena/design-lab-harness).

🌐 **Website & leaderboards:** [artifactarena.ai](https://artifactarena.ai) ·
📄 **Paper:** [ArtifactArena: Evaluating Models by What They Build in the Physical World](https://artifactarena.ai/paper) ([PDF](https://artifactarena.ai/paper/ArtifactArena.pdf)) ·
🎮 **Play:** [artifactarena.ai/play](https://artifactarena.ai/play)

## 🌍 Global Call for Robot Artifacts

ArtifactArena is harness-agnostic: only the artifact matters. We accept robots designed
entirely by models and robots built through human–AI collaboration, to see how
**human** and **human + AI** inventions rank against **AI-only** ones. Build a bot —
by hand, with your favorite AI, or any mix of the two — and enter it in the
**monthly competition** against the AI-built field.

1. Load your `robot.xml` + `controller.py` in the <a href="https://artifactarena.ai/play" target="_blank">Play arena ↗</a> and watch it fight any model-built artifact.
2. Press **Verify** to run the same qualification checks as the tournament.
3. Submit it with your design intent (bot name, design strategy, hardware plan, combat plan):

👉 **[Submission form](https://docs.google.com/forms/d/e/1FAIpQLSeJnDxoboUVzfygIj5Nwm_jCFavYs0ED0o65EcCeAXzPS3ubQ/viewform)**

Entries are collected continuously; each month's field is ranked and published on the leaderboard.

## The Last Bot Standing Game

| | |
| --- | --- |
| Arena | an elevated circular platform, 15 m in diameter, in MuJoCo 3.10.0 |
| Win | the opponent loses first; a match that reaches 300 s is a draw |
| Lose | (in priority order) controller error · floor contact · size violation (over 2.44 × 2.44 × 3.05 m in the robot's own frame) · inactivity (centre of mass inside 0.5 m for 10 s) · physics instability |
| Robot | one free-jointed root body; up to 2,000 bodies, geoms and actuators; 25–800 kg including motor mass |
| Materials | foam, plastic, rubber, carbon fiber, aluminum, titanium, steel, tungsten — each sets density and friction |
| Controller | `policy_step(obs) -> dict[str, float]`, called every 0.01 s, one command in [−1, 1] per motor |

**Qualification.** An artifact must compile, pass the static verifier (one free joint,
palette materials, mass and size limits, a controller that runs on a live
observation), and must not lose a best of three 20 s matches against a passive 342 kg
block. An artifact that fails forfeits.

**Tournament.** Every pair of qualified artifacts plays three seeds, once from each
side. Ratings are a Bradley–Terry fit with a draw counted as half a win.

The complete rules, the robot constraints, the MJCF syntax reference and the
observation schema are in the prompt every model receives,
[`configs/rules/sampling_prompt.md`](configs/rules/sampling_prompt.md); the exact
limits the verifier reads are in [`configs/rules/rules.yaml`](configs/rules/rules.yaml).

## The Harnesses

| Harness | What the model does | Here |
| --- | --- | --- |
| **SH** — Sampling | Produces independent artifacts from the fixed prompt, with no feedback; the best qualified one per run is chosen by a round robin | `configs/tournaments/sh.yaml` |
| **VGH** — Verifier-Grounded Refinement | Iterates on its artifact: each step it gets verifier feedback, full match feedback and its design history, and proposes a better artifact | `configs/tournaments/arh.yaml` |
| **DLH** — Design Lab | Works as an agent in a sandboxed lab holding the simulator and verifier source, chaining tool calls to build, test and analyse | [design-lab-harness](https://github.com/ArtifactArena/design-lab-harness) |

In the paper every harness gets **10 API calls per run**, and each model × harness is
run three times. The configs here default to larger budgets (250 samples per model for
SH, 50 commits per run for VGH); pass `--iterations` / set `commit_budget` to match.
VGH's config and prompt files keep their development name, `arh` ("AutoResearch").

## First-Time Setup

```bash
# 1) Environment (Python 3.10, MuJoCo 3.10.0)
git clone https://github.com/ArtifactArena/harness-public.git && cd harness-public
conda create -y -n artifactarena python=3.10 && conda activate artifactarena
pip install -r pip_requirements.txt
# Linux x86-64: build the default CPU accelerator (requires gcc and Python headers)
pip install 'Cython==3.1.4'
python scripts/setup_acceleration.py
export ANTHROPIC_API_KEY=... OPENAI_API_KEY=... GEMINI_API_KEY=...   # whichever providers you use

# 2) Dataset: the tournament artifacts from Hugging Face
hf auth login
hf download artifactarena/ArtifactArena --repo-type dataset \
  --revision final-ft25s2-bc68c140 --local-dir ArtifactArena

# 3) A match between two downloaded artifacts, under the tournament rules
R=ArtifactArena/bots/gpt-6-astra__autoresearch__r01_c003
B=ArtifactArena/bots/gpt-6-astra__sampling__t244_c000
python run_episode_viewer.py --config configs/tournaments/base.yaml \
  --red-morphology $R/robot.xml --red-policy $R/controller.py \
  --blue-morphology $B/robot.xml --blue-policy $B/controller.py \
  --seed 7101 --n-rollouts 1 --headless --save-match-logs matches/astra-vs-astra

# 4) Sampling Harness: one zero-shot artifact
python run_baseline_agent.py --config configs/tournaments/sh.yaml \
  --llms configs/models/anthropic/claude-sonnet-5-high.yaml \
  --iterations 1 --build-only --output-dir runs/sh-smoke

# 5) Verifier-Grounded Refinement Harness: one artifact refined over 3 commits
sed 's/commit_budget: 50/commit_budget: 3/' configs/tournaments/arh.yaml > configs/tournaments/arh-smoke.yaml
python run_baseline_agent.py --config configs/tournaments/arh-smoke.yaml \
  --llms configs/models/openai/gpt-5.4.yaml \
  --iterations 1 --build-only --output-dir runs/vgh-smoke
```

Notes:

- Matches use acceleration by default after setup; no run flag is needed.
- `base.yaml` plays 5 seeds per match (`n_rollouts: 5`) with 300 s rounds;
  `--n-rollouts 1` plays one. With several seeds, videos are written as
  `seed_<N>.mp4` next to `--video-path`.
- The Hugging Face dataset needs `hf auth login` with a token that can read
  `artifactarena/ArtifactArena`.
- A design call at high reasoning effort can run for a long time; each call has a
  100-minute timeout and is retried on failure.
- The commit budget has no command-line flag and configs inherit only one level of
  `base:`, so step 5 copies `arh.yaml` with a smaller budget.

## Run a Match

Without `--config` (or an explicit `--inactivity-timeout`), the inactivity rule is off
in the episode viewer: matches only end on ring-out, instability or time.

```bash
# Pusher vs Pusher (headless, saves video)
python run_episode_viewer.py \
  --red-morphology mjarena/core/assets/baseline_bots/baseline-pusher/robot.xml \
  --red-policy mjarena/core/assets/baseline_bots/baseline-pusher/controller.py \
  --blue-morphology mjarena/core/assets/baseline_bots/baseline-pusher/robot.xml \
  --blue-policy mjarena/core/assets/baseline_bots/baseline-pusher/controller.py \
  --headless --camera tracking --match-time 30 \
  --video-path logs/pusher-vs-pusher.mp4 --save-match-logs logs/pusher-vs-pusher

# Pusher vs the qualification block, in the interactive MuJoCo viewer
python run_episode_viewer.py \
  --red-morphology mjarena/core/assets/baseline_bots/baseline-pusher/robot.xml \
  --red-policy mjarena/core/assets/baseline_bots/baseline-pusher/controller.py \
  --blue-morphology mjarena/core/assets/stationary_block_3d.xml \
  --camera free --match-time 30
```

## Watch and Replay Matches (`run_episode_viewer.py`)

Run and watch robot battles. Supports interactive GUI, headless video recording, and match log export.

```bash
# From files (headless)
python run_episode_viewer.py \
  --red-morphology path/to/robot.xml \
  --red-policy path/to/controller.py \
  --blue-morphology path/to/opponent.xml \
  --blue-policy path/to/opponent_controller.py \
  --headless --camera tracking --match-time 30 \
  --video-path output.mp4 \
  --save-match-logs logs-baseline-debug/my-match

# From app match data
python run_episode_viewer.py --match-id match-001

# Multiple seeds
python run_episode_viewer.py \
  --red-morphology robot.xml --red-policy controller.py \
  --blue-morphology opponent.xml --blue-policy opponent.py \
  --headless --n-rollouts 3 --seed 42 \
  --video-path multi-seed.mp4
```

**Key arguments:**
- `--headless`: Run without GUI, save video
- `--camera`: Camera mode (`free`, `topdown`, `side`, `tracking`)
- `--match-time`: Match duration in seconds of sim time
- `--debug`: Enable debug logging
- `--save-match-logs DIR`: Export match data for the web viewer
- `--inactivity-timeout`: Seconds before inactive bot loses (default: from config)
- `--skip-inactivity-check`: Disable inactivity timeout
- `--score-function`: `any` (default) or `thres-50`

**Interactive controls:**
- Mouse drag: Rotate camera
- Scroll: Zoom
- Right-drag: Pan
- `R`: Reset episode
- `Space`/`P`: Pause/Resume
- `Q`: Quit

### Replay a Match Under the Tournament Rules

To replay a match with the same gameplay rules used during a tournament, either pass the
tournament config or set the game-critical parameters explicitly.

```bash
# Option 1: Use the tournament config (recommended — inherits all gameplay settings)
python run_episode_viewer.py --config configs/tournaments/your_season.yaml \
  --red-morphology path/to/red/robot.xml --red-policy path/to/red/controller.py \
  --blue-morphology path/to/blue/robot.xml --blue-policy path/to/blue/controller.py \
  --headless --video-path replay.mp4

# Option 2: Set game-critical params manually
python run_episode_viewer.py \
  --red-morphology path/to/red/robot.xml --red-policy path/to/red/controller.py \
  --blue-morphology path/to/blue/robot.xml --blue-policy path/to/blue/controller.py \
  --match-time 120 --score-function any --inactivity-timeout 10 \
  --constraints configs/rules/rules.yaml \
  --arena mjarena/assets/sumo_ring_env_studio_3d.xml \
  --headless --camera tracking --video-path replay.mp4
```

**Game-critical parameters** (these affect match outcome — defaults may differ from your tournament):
- `--match-time`: Match duration in sim seconds
- `--score-function`: `any` (instant ring-out) or `thres-50` (>50% mass off ring)
- `--inactivity-timeout`: Seconds before inactive bot loses
- `--constraints`: Rules YAML for material pipeline (mass limits, size limits)
- `--arena`: Which ring environment XML to use

## Generate Artifacts (`run_baseline_agent.py`)

```bash
# A harness config with its full model roster
python run_baseline_agent.py --config configs/tournaments/sh.yaml

# One model, a few runs
python run_baseline_agent.py --config configs/tournaments/arh.yaml \
  --llms configs/models/google/gemini-3-1-pro-high.yaml --iterations 3 --build-only \
  --output-dir runs/gemini-vgh
```

To resume an interrupted run without generating bots again:

```bash
python run_baseline_agent.py \
  --continue logs/test_season --tournament-only --iterations 1 --no-video --no-trace
```

Completed pairings are reused, including their original bot order and seeds.
An interrupted pairing restarts all its seeds; mid-match physics state is not
checkpointed. Keep the saved match rules and seed count when resuming. In a
terminal, serial matches show a live step bar, elapsed time, and ETA to the match
limit (matches can finish early). Redraws are not saved to `log.txt`. Parallel
matchups use the coordinator dashboard with a throughput-based ETA, which appears
after the first new pairing finishes. `ARENA_PROGRESS=0` hides the serial bar;
`ARENA_PROGRESS=1` forces it when output is redirected.

## Configs

| File | Purpose |
| --- | --- |
| `configs/tournaments/base.yaml` | Shared rules: qualification, match length, inactivity, tournament and Elo settings |
| `configs/tournaments/sh.yaml` | Sampling Harness: the roster, zero-shot, one design per iteration |
| `configs/tournaments/arh.yaml` | Verifier-Grounded Refinement Harness: the roster, full feedback every commit |
| `configs/tournaments/oeh.yaml` | Design Lab Harness roster of record (DLH runs from its own repository) |
| `configs/models/run-roster-2026-09.yaml` | The 24-model roster all three harness configs share |
| `configs/models/<provider>/*.yaml` | Per-model API settings: reasoning effort, output limit, retries |
| `configs/rules/sampling_prompt.md` | The prompt for SH: game rules, qualification, tournament, MJCF syntax, observation schema |
| `configs/rules/autoresearch_prompt.md` | The same document for VGH, with the iteration protocol |
| `configs/rules/rules.yaml` | Exact limits the verifier enforces, quoted verbatim in both prompts |
| `configs/rules/materials_store.yaml` | The material palette (density, friction) |

Child configs inherit from `base.yaml`:

```yaml
base: base.yaml

llms:
  - configs/models/openai/gpt-5.4.yaml
  - configs/models/google/gemini-3-1-pro-high.yaml

season:
  tournament_id: my_tournament
  iterations: 5
```

Every model call has a 100-minute timeout; a hung connection is aborted and retried
(`num_retries` in the model config).

## Scripts

| Script | What it does |
| --- | --- |
| `scripts/arh_launch.sh [N_RUNS] [MAX_PARALLEL]` | Runs VGH for every roster model, one process per run (`PY=` picks the interpreter) |
| `scripts/calculate_elo.py <season_dir> --build-stats` | Bradley–Terry Elo for a season's matches, written to `<season>/elo/elo_results.json` |
| `scripts/sampling/` | The 250-sample Sampling Harness study: launching the pool, round robins, finals, validation and cost reports |
| `scripts/two_stage/` | Round-robin tournaments over saved artifacts, cross-harness round robins, Elo and plots |
| `scripts/match_accel/`, `scripts/observation_accel/` | Build, validate and benchmark the compiled accelerators |
| `scripts/sampling/cluster/`, `scripts/iterative_runs/`, `scripts/iterative_round_robin/`, `scripts/iterative_cpu/`, `scripts/live_matches/`, `scripts/tool_use_dashboard/` | The distributed runs, round robins and dashboards behind the paper's tournament |

The scripts in the last row ran on our compute cluster; they keep its directory layout
and need adapting before use elsewhere.

## Baseline Bots

| Bot | Path | Description |
| --- | --- | --- |
| Pusher | `mjarena/core/assets/baseline_bots/baseline-pusher/` | Four-wheel pusher |
| Static | `mjarena/core/assets/baseline_bots/baseline-static/` | Stationary block |
| Qualification block | `mjarena/core/assets/stationary_block_3d.xml` | The passive opponent every artifact must not lose to |

## Tests

```bash
python -m pytest tests -q
python -m pytest tests_environment -q -k 'not full_300_second_round'
```

`tests/` covers the harness: the inactivity rule, the prompts and their substitution,
config wiring, the controller sandbox, and a stub build that runs real validation and
qualification. `tests_environment/` is the engine's acceptance suite (rules, mass and
size accounting, observations, loss conditions); drop the `-k` to include the two
full-length 300 s rounds.

## Citation

```bibtex
@article{artifactarena2026,
  title  = {ArtifactArena: Evaluating Models by What They Build in the Physical World},
  author = {Tiwary, Kushagra and Mayo, David and Behari, Nikhil and Sun, Xiangzhou and
            Alabdulkareem, Abdulrahman and Galatzer-Levy, Isaac and Katz, Boris and Cheung, Brian},
  year   = {2026},
  url    = {https://artifactarena.ai}
}
```

## License

MIT — see [LICENSE](LICENSE).
