# Sampling harness · stage 1 results (final tournament)

Assembled 2026-09-25 18:09 UTC from the SH-250 pool `sh250-pool-5ac92bc7` Top-Bot-per-Run round robin (`pool_rr/<model>/g<run>/matches/*/match_result.json`, 5 seeds per pairing, 300 s, colors as played). No new matches were simulated.

Bots: `sampling_bots_selected_for_final_tournament.md` (seed 9591746523970967871): 21 models × 3 groups of 10, each model's 30 bots drawn from one 50-slot pool run.

Winner rule per group: points (win 1, draw 0.5) over all 45 pairings incl. forfeits, then wins, then lower slot. Forfeits: a bot the pool did not admit (not eligible in pool_ledger.json) has no games; each of its pairings counts as 5 forfeit wins for an eligible opponent, and as no games when both are ineligible. Bradley-Terry Elo (the existing MAP estimator, draws 0.5, prior N(1000, 800²)) is fitted per group over simulated games only and shown for reference.
Totals: 4085 simulated games reused, 5015 forfeit games, 63 group winners advance to stage 2.

## Group winners (63)

| model | group | winner | slot | W-L-D | forfeit W | points |
|---|:-:|---|---|---|--:|--:|
| claude-fable-5-1-high | 1 | `claude-fable-5-1-high__t115_c000` | c115 | 29-6-0 | 10 | 39.0 |
| claude-fable-5-1-high | 2 | `claude-fable-5-1-high__t128_c000` | c128 | 30-5-0 | 10 | 40.0 |
| claude-fable-5-1-high | 3 | `claude-fable-5-1-high__t144_c000` | c144 | 28-1-1 | 15 | 43.5 |
| claude-fable-5-high | 1 | `claude-fable-5-high__t107_c000` | c107 | 26-8-1 | 10 | 36.5 |
| claude-fable-5-high | 2 | `claude-fable-5-high__t122_c000` | c122 | 29-4-2 | 10 | 40.0 |
| claude-fable-5-high | 3 | `claude-fable-5-high__t140_c000` | c140 | 40-2-3 | 0 | 41.5 |
| claude-opus-4-8-high | 1 | `claude-opus-4-8-high__t10_c000` | c010 | 9-6-0 | 30 | 39.0 |
| claude-opus-4-8-high | 2 | `claude-opus-4-8-high__t17_c000` | c017 | 23-12-0 | 10 | 33.0 |
| claude-opus-4-8-high | 3 | `claude-opus-4-8-high__t33_c000` | c033 | 17-8-0 | 20 | 37.0 |
| claude-sonnet-5-high | 1 | `claude-sonnet-5-high__t215_c000` | c215 | 18-12-0 | 15 | 33.0 |
| claude-sonnet-5-high | 2 | `claude-sonnet-5-high__t231_c000` | c231 | 5-0-0 | 40 | 45.0 |
| claude-sonnet-5-high | 3 | `claude-sonnet-5-high__t232_c000` | c232 | 3-2-0 | 40 | 43.0 |
| deepseek-v4-pro-thinking | 1 | `deepseek-v4-pro-thinking__t56_c000` | c056 | 0-0-0 | 45 | 45.0 |
| deepseek-v4-pro-thinking | 2 | `deepseek-v4-pro-thinking__t83_c000` | c083 | 0-0-0 | 45 | 45.0 |
| deepseek-v4-pro-thinking | 3 | `deepseek-v4-pro-thinking__t85_c000` | c085 | 0-0-0 | 45 | 45.0 |
| gemini-3-1-pro-high | 1 | `gemini-3-1-pro-high__t155_c000` | c155 | 8-2-0 | 35 | 43.0 |
| gemini-3-1-pro-high | 2 | `gemini-3-1-pro-high__t167_c000` | c167 | 16-9-0 | 20 | 36.0 |
| gemini-3-1-pro-high | 3 | `gemini-3-1-pro-high__t192_c000` | c192 | 28-1-1 | 15 | 43.5 |
| gemini-3-8-flash-high | 1 | `gemini-3-8-flash-high__t113_c000` | c113 | 20-10-0 | 15 | 35.0 |
| gemini-3-8-flash-high | 2 | `gemini-3-8-flash-high__t122_c000` | c122 | 34-10-1 | 0 | 34.5 |
| gemini-3-8-flash-high | 3 | `gemini-3-8-flash-high__t139_c000` | c139 | 24-10-1 | 10 | 34.5 |
| glm-5.2-high | 1 | `glm-5.2-high__t69_c000` | c069 | 13-5-2 | 25 | 39.0 |
| glm-5.2-high | 2 | `glm-5.2-high__t78_c000` | c078 | 4-1-0 | 40 | 44.0 |
| glm-5.2-high | 3 | `glm-5.2-high__t99_c000` | c099 | 4-1-0 | 40 | 44.0 |
| glm-5.3-high | 1 | `glm-5.3-high__t150_c000` | c150 | 0-0-0 | 0 | 0.0 |
| glm-5.3-high | 2 | `glm-5.3-high__t166_c000` | c166 | 0-0-0 | 0 | 0.0 |
| glm-5.3-high | 3 | `glm-5.3-high__t182_c000` | c182 | 0-0-0 | 0 | 0.0 |
| gpt-5.3-codex-high | 1 | `gpt-5.3-codex-high__t113_c000` | c113 | 9-4-2 | 30 | 40.0 |
| gpt-5.3-codex-high | 2 | `gpt-5.3-codex-high__t119_c000` | c119 | 6-4-0 | 35 | 41.0 |
| gpt-5.3-codex-high | 3 | `gpt-5.3-codex-high__t143_c000` | c143 | 14-6-0 | 25 | 39.0 |
| gpt-5.4 | 1 | `gpt-5.4__t216_c000` | c216 | 15-5-0 | 25 | 40.0 |
| gpt-5.4 | 2 | `gpt-5.4__t227_c000` | c227 | 16-3-6 | 20 | 39.0 |
| gpt-5.4 | 3 | `gpt-5.4__t246_c000` | c246 | 29-1-0 | 15 | 44.0 |
| gpt-5.5 | 1 | `gpt-5.5__t162_c000` | c162 | 15-8-2 | 20 | 36.0 |
| gpt-5.5 | 2 | `gpt-5.5__t166_c000` | c166 | 10-4-1 | 30 | 40.5 |
| gpt-5.5 | 3 | `gpt-5.5__t192_c000` | c192 | 24-4-7 | 10 | 37.5 |
| gpt-5.6-luna | 1 | `gpt-5.6-luna__t117_c000` | c117 | 0-0-0 | 45 | 45.0 |
| gpt-5.6-luna | 2 | `gpt-5.6-luna__t128_c000` | c128 | 3-2-0 | 40 | 43.0 |
| gpt-5.6-luna | 3 | `gpt-5.6-luna__t146_c000` | c146 | 0-0-0 | 45 | 45.0 |
| gpt-5.6-sol | 1 | `gpt-5.6-sol__t00_c000` | c000 | 23-2-0 | 20 | 43.0 |
| gpt-5.6-sol | 2 | `gpt-5.6-sol__t30_c000` | c030 | 35-2-3 | 5 | 41.5 |
| gpt-5.6-sol | 3 | `gpt-5.6-sol__t44_c000` | c044 | 30-10-0 | 5 | 35.0 |
| gpt-5.6-terra | 1 | `gpt-5.6-terra__t104_c000` | c104 | 23-2-5 | 15 | 40.5 |
| gpt-5.6-terra | 2 | `gpt-5.6-terra__t117_c000` | c117 | 17-7-1 | 20 | 37.5 |
| gpt-5.6-terra | 3 | `gpt-5.6-terra__t149_c000` | c149 | 16-8-1 | 20 | 36.5 |
| gpt-6-astra | 1 | `gpt-6-astra__t221_c000` | c221 | 15-5-0 | 25 | 40.0 |
| gpt-6-astra | 2 | `gpt-6-astra__t224_c000` | c224 | 8-2-0 | 35 | 43.0 |
| gpt-6-astra | 3 | `gpt-6-astra__t244_c000` | c244 | 18-1-1 | 25 | 43.5 |
| grok-4.20-reasoning | 1 | `grok-4.20-reasoning__t01_c000` | c001 | 0-0-0 | 0 | 0.0 |
| grok-4.20-reasoning | 2 | `grok-4.20-reasoning__t16_c000` | c016 | 0-0-0 | 0 | 0.0 |
| grok-4.20-reasoning | 3 | `grok-4.20-reasoning__t38_c000` | c038 | 0-0-0 | 45 | 45.0 |
| grok-4.5-high | 1 | `grok-4.5-high__t115_c000` | c115 | 0-0-0 | 45 | 45.0 |
| grok-4.5-high | 2 | `grok-4.5-high__t117_c000` | c117 | 0-0-0 | 0 | 0.0 |
| grok-4.5-high | 3 | `grok-4.5-high__t133_c000` | c133 | 0-0-0 | 0 | 0.0 |
| grok-4.6-high | 1 | `grok-4.6-high__t213_c000` | c213 | 33-2-0 | 10 | 43.0 |
| grok-4.6-high | 2 | `grok-4.6-high__t219_c000` | c219 | 20-9-1 | 15 | 35.5 |
| grok-4.6-high | 3 | `grok-4.6-high__t240_c000` | c240 | 27-3-0 | 15 | 42.0 |
| kimi-k3-high | 1 | `kimi-k3-high__t07_c000` | c007 | 1-0-4 | 40 | 43.0 |
| kimi-k3-high | 2 | `kimi-k3-high__t23_c000` | c023 | 10-0-0 | 35 | 45.0 |
| kimi-k3-high | 3 | `kimi-k3-high__t45_c000` | c045 | 12-3-0 | 30 | 42.0 |
| qwen3.8-2.4t-a95b-thinking | 1 | `qwen3.8-2.4t-a95b-thinking__t155_c000` | c155 | 18-2-0 | 25 | 43.0 |
| qwen3.8-2.4t-a95b-thinking | 2 | `qwen3.8-2.4t-a95b-thinking__t164_c000` | c164 | 28-6-1 | 10 | 38.5 |
| qwen3.8-2.4t-a95b-thinking | 3 | `qwen3.8-2.4t-a95b-thinking__t192_c000` | c192 | 26-8-1 | 10 | 36.5 |


## claude-fable-5-1-high

Pool run `g2` (slots 100-149), harness `6d87c64`, tournament config md5 `9dd458946f007a22c46de945b9891820`.

### Group 1 — winner `claude-fable-5-1-high__t115_c000`

140 simulated games, 80 forfeit games.

| rank | bot | slot | eligible | W-L-D (simulated) | forfeit W | points | Elo |
|--:|---|---|:-:|---|--:|--:|--:|
| 1 | `claude-fable-5-1-high__t115_c000` | c115 | yes | 29-6-0 | 10 | 39.0 | 1270.9 |
| 2 | `claude-fable-5-1-high__t111_c000` | c111 | yes | 27-8-0 | 10 | 37.0 | 1215.2 |
| 3 | `claude-fable-5-1-high__t104_c000` | c104 | yes | 19-15-1 | 10 | 29.5 | 1041.8 |
| 4 | `claude-fable-5-1-high__t106_c000` | c106 | yes | 17-17-1 | 10 | 27.5 | 999.4 |
| 5 | `claude-fable-5-1-high__t105_c000` | c105 | yes | 17-18-0 | 10 | 27.0 | 988.9 |
| 6 | `claude-fable-5-1-high__t100_c000` | c100 | yes | 15-19-1 | 10 | 25.5 | 957.1 |
| 7 | `claude-fable-5-1-high__t113_c000` | c113 | yes | 8-26-1 | 10 | 18.5 | 797.5 |
| 8 | `claude-fable-5-1-high__t114_c000` | c114 | yes | 5-28-2 | 10 | 16.0 | 729.3 |
| 9 | `claude-fable-5-1-high__t107_c000` | c107 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 10 | `claude-fable-5-1-high__t109_c000` | c109 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |

### Group 2 — winner `claude-fable-5-1-high__t128_c000`

140 simulated games, 80 forfeit games.

| rank | bot | slot | eligible | W-L-D (simulated) | forfeit W | points | Elo |
|--:|---|---|:-:|---|--:|--:|--:|
| 1 | `claude-fable-5-1-high__t128_c000` | c128 | yes | 30-5-0 | 10 | 40.0 | 1332.6 |
| 2 | `claude-fable-5-1-high__t130_c000` | c130 | yes | 27-8-0 | 10 | 37.0 | 1240.2 |
| 3 | `claude-fable-5-1-high__t117_c000` | c117 | yes | 23-12-0 | 10 | 33.0 | 1133.6 |
| 4 | `claude-fable-5-1-high__t120_c000` | c120 | yes | 22-13-0 | 10 | 32.0 | 1108.5 |
| 5 | `claude-fable-5-1-high__t132_c000` | c132 | yes | 14-21-0 | 10 | 24.0 | 913.7 |
| 6 | `claude-fable-5-1-high__t125_c000` | c125 | yes | 10-25-0 | 10 | 20.0 | 812.8 |
| 7 | `claude-fable-5-1-high__t127_c000` | c127 | yes | 8-27-0 | 10 | 18.0 | 758.7 |
| 8 | `claude-fable-5-1-high__t126_c000` | c126 | yes | 6-29-0 | 10 | 16.0 | 699.9 |
| 9 | `claude-fable-5-1-high__t118_c000` | c118 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 10 | `claude-fable-5-1-high__t122_c000` | c122 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |

### Group 3 — winner `claude-fable-5-1-high__t144_c000`

105 simulated games, 105 forfeit games.

| rank | bot | slot | eligible | W-L-D (simulated) | forfeit W | points | Elo |
|--:|---|---|:-:|---|--:|--:|--:|
| 1 | `claude-fable-5-1-high__t144_c000` | c144 | yes | 28-1-1 | 15 | 43.5 | 1647.0 |
| 2 | `claude-fable-5-1-high__t148_c000` | c148 | yes | 22-6-2 | 15 | 38.0 | 1380.9 |
| 3 | `claude-fable-5-1-high__t146_c000` | c146 | yes | 17-10-3 | 15 | 33.5 | 1212.9 |
| 4 | `claude-fable-5-1-high__t145_c000` | c145 | yes | 17-13-0 | 15 | 32.0 | 1158.4 |
| 5 | `claude-fable-5-1-high__t137_c000` | c137 | yes | 13-17-0 | 15 | 28.0 | 1001.2 |
| 6 | `claude-fable-5-1-high__t142_c000` | c142 | yes | 4-26-0 | 15 | 19.0 | 406.6 |
| 7 | `claude-fable-5-1-high__t138_c000` | c138 | yes | 1-29-0 | 15 | 16.0 | 193.1 |
| 8 | `claude-fable-5-1-high__t135_c000` | c135 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 9 | `claude-fable-5-1-high__t136_c000` | c136 | no · qualification failed (W0 D2 L1) | 0-0-0 | 0 | 0.0 | — |
| 10 | `claude-fable-5-1-high__t147_c000` | c147 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |

## claude-fable-5-high

Pool run `g2` (slots 100-149), harness `6d87c64`, tournament config md5 `9dd458946f007a22c46de945b9891820`.

### Group 1 — winner `claude-fable-5-high__t107_c000`

140 simulated games, 80 forfeit games.

| rank | bot | slot | eligible | W-L-D (simulated) | forfeit W | points | Elo |
|--:|---|---|:-:|---|--:|--:|--:|
| 1 | `claude-fable-5-high__t107_c000` | c107 | yes | 26-8-1 | 10 | 36.5 | 1182.6 |
| 2 | `claude-fable-5-high__t101_c000` | c101 | yes | 23-12-0 | 10 | 33.0 | 1106.8 |
| 3 | `claude-fable-5-high__t104_c000` | c104 | yes | 19-15-1 | 10 | 29.5 | 1037.9 |
| 4 | `claude-fable-5-high__t103_c000` | c103 | yes | 16-12-7 | 10 | 29.5 | 1037.9 |
| 5 | `claude-fable-5-high__t117_c000` | c117 | yes | 16-14-5 | 10 | 28.5 | 1018.8 |
| 6 | `claude-fable-5-high__t102_c000` | c102 | yes | 12-23-0 | 10 | 22.0 | 892.8 |
| 7 | `claude-fable-5-high__t100_c000` | c100 | yes | 10-24-1 | 10 | 20.5 | 861.6 |
| 8 | `claude-fable-5-high__t111_c000` | c111 | yes | 6-20-9 | 10 | 20.5 | 861.6 |
| 9 | `claude-fable-5-high__t108_c000` | c108 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 10 | `claude-fable-5-high__t114_c000` | c114 | no · qualification failed (W1 D0 L2) | 0-0-0 | 0 | 0.0 | — |

### Group 2 — winner `claude-fable-5-high__t122_c000`

140 simulated games, 80 forfeit games.

| rank | bot | slot | eligible | W-L-D (simulated) | forfeit W | points | Elo |
|--:|---|---|:-:|---|--:|--:|--:|
| 1 | `claude-fable-5-high__t122_c000` | c122 | yes | 29-4-2 | 10 | 40.0 | 1284.3 |
| 2 | `claude-fable-5-high__t120_c000` | c120 | yes | 19-14-2 | 10 | 30.0 | 1047.1 |
| 3 | `claude-fable-5-high__t130_c000` | c130 | yes | 19-14-2 | 10 | 30.0 | 1047.1 |
| 4 | `claude-fable-5-high__t133_c000` | c133 | yes | 15-14-6 | 10 | 28.0 | 1007.5 |
| 5 | `claude-fable-5-high__t118_c000` | c118 | yes | 17-17-1 | 10 | 27.5 | 997.7 |
| 6 | `claude-fable-5-high__t124_c000` | c124 | yes | 15-17-3 | 10 | 26.5 | 978.0 |
| 7 | `claude-fable-5-high__t125_c000` | c125 | yes | 11-24-0 | 10 | 21.0 | 866.2 |
| 8 | `claude-fable-5-high__t132_c000` | c132 | yes | 6-27-2 | 10 | 17.0 | 772.2 |
| 9 | `claude-fable-5-high__t119_c000` | c119 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 10 | `claude-fable-5-high__t128_c000` | c128 | no · qualification failed (W0 D2 L1) | 0-0-0 | 0 | 0.0 | — |

### Group 3 — winner `claude-fable-5-high__t140_c000`

225 simulated games, 0 forfeit games.

| rank | bot | slot | eligible | W-L-D (simulated) | forfeit W | points | Elo |
|--:|---|---|:-:|---|--:|--:|--:|
| 1 | `claude-fable-5-high__t140_c000` | c140 | yes | 40-2-3 | 0 | 41.5 | 1409.5 |
| 2 | `claude-fable-5-high__t143_c000` | c143 | yes | 32-12-1 | 0 | 32.5 | 1167.9 |
| 3 | `claude-fable-5-high__t146_c000` | c146 | yes | 22-16-7 | 0 | 25.5 | 1039.9 |
| 4 | `claude-fable-5-high__t139_c000` | c139 | yes | 23-19-3 | 0 | 24.5 | 1023.1 |
| 5 | `claude-fable-5-high__t142_c000` | c142 | yes | 23-22-0 | 0 | 23.0 | 998.1 |
| 6 | `claude-fable-5-high__t149_c000` | c149 | yes | 20-24-1 | 0 | 20.5 | 957.0 |
| 7 | `claude-fable-5-high__t148_c000` | c148 | yes | 20-25-0 | 0 | 20.0 | 948.8 |
| 8 | `claude-fable-5-high__t144_c000` | c144 | yes | 14-30-1 | 0 | 14.5 | 855.8 |
| 9 | `claude-fable-5-high__t147_c000` | c147 | yes | 12-31-2 | 0 | 13.0 | 828.9 |
| 10 | `claude-fable-5-high__t137_c000` | c137 | yes | 7-32-6 | 0 | 10.0 | 771.0 |

## claude-opus-4-8-high

Pool run `g0` (slots 000-049), harness `3c03d49`, tournament config md5 `9dd458946f007a22c46de945b9891820`.

### Group 1 — winner `claude-opus-4-8-high__t10_c000`

30 simulated games, 120 forfeit games.

| rank | bot | slot | eligible | W-L-D (simulated) | forfeit W | points | Elo |
|--:|---|---|:-:|---|--:|--:|--:|
| 1 | `claude-opus-4-8-high__t10_c000` | c010 | yes | 9-6-0 | 30 | 39.0 | 1052.3 |
| 2 | `claude-opus-4-8-high__t07_c000` | c007 | yes | 7-8-0 | 30 | 37.0 | 982.6 |
| 3 | `claude-opus-4-8-high__t09_c000` | c009 | yes | 7-8-0 | 30 | 37.0 | 982.6 |
| 4 | `claude-opus-4-8-high__t14_c000` | c014 | yes | 7-8-0 | 30 | 37.0 | 982.6 |
| 5 | `claude-opus-4-8-high__t00_c000` | c000 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 6 | `claude-opus-4-8-high__t02_c000` | c002 | no · qualification failed (W1 D0 L2) | 0-0-0 | 0 | 0.0 | — |
| 7 | `claude-opus-4-8-high__t03_c000` | c003 | no · qualification failed (W1 D1 L1) | 0-0-0 | 0 | 0.0 | — |
| 8 | `claude-opus-4-8-high__t04_c000` | c004 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 9 | `claude-opus-4-8-high__t05_c000` | c005 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 10 | `claude-opus-4-8-high__t13_c000` | c013 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |

### Group 2 — winner `claude-opus-4-8-high__t17_c000`

140 simulated games, 80 forfeit games.

| rank | bot | slot | eligible | W-L-D (simulated) | forfeit W | points | Elo |
|--:|---|---|:-:|---|--:|--:|--:|
| 1 | `claude-opus-4-8-high__t17_c000` | c017 | yes | 23-12-0 | 10 | 33.0 | 1104.9 |
| 2 | `claude-opus-4-8-high__t19_c000` | c019 | yes | 22-13-0 | 10 | 32.0 | 1085.4 |
| 3 | `claude-opus-4-8-high__t30_c000` | c030 | yes | 22-13-0 | 10 | 32.0 | 1085.4 |
| 4 | `claude-opus-4-8-high__t24_c000` | c024 | yes | 20-15-0 | 10 | 30.0 | 1047.3 |
| 5 | `claude-opus-4-8-high__t29_c000` | c029 | yes | 18-17-0 | 10 | 28.0 | 1010.2 |
| 6 | `claude-opus-4-8-high__t26_c000` | c026 | yes | 14-21-0 | 10 | 24.0 | 935.4 |
| 7 | `claude-opus-4-8-high__t31_c000` | c031 | yes | 11-24-0 | 10 | 21.0 | 876.2 |
| 8 | `claude-opus-4-8-high__t25_c000` | c025 | yes | 10-25-0 | 10 | 20.0 | 855.2 |
| 9 | `claude-opus-4-8-high__t20_c000` | c020 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 10 | `claude-opus-4-8-high__t21_c000` | c021 | no · qualification failed (W0 D2 L1) | 0-0-0 | 0 | 0.0 | — |

### Group 3 — winner `claude-opus-4-8-high__t33_c000`

75 simulated games, 120 forfeit games.

| rank | bot | slot | eligible | W-L-D (simulated) | forfeit W | points | Elo |
|--:|---|---|:-:|---|--:|--:|--:|
| 1 | `claude-opus-4-8-high__t33_c000` | c033 | yes | 17-8-0 | 20 | 37.0 | 1116.9 |
| 2 | `claude-opus-4-8-high__t44_c000` | c044 | yes | 17-8-0 | 20 | 37.0 | 1116.9 |
| 3 | `claude-opus-4-8-high__t40_c000` | c040 | yes | 14-11-0 | 20 | 34.0 | 1038.8 |
| 4 | `claude-opus-4-8-high__t46_c000` | c046 | yes | 12-13-0 | 20 | 32.0 | 988.6 |
| 5 | `claude-opus-4-8-high__t47_c000` | c047 | yes | 9-16-0 | 20 | 29.0 | 911.7 |
| 6 | `claude-opus-4-8-high__t45_c000` | c045 | yes | 6-19-0 | 20 | 26.0 | 827.1 |
| 7 | `claude-opus-4-8-high__t35_c000` | c035 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 8 | `claude-opus-4-8-high__t37_c000` | c037 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 9 | `claude-opus-4-8-high__t41_c000` | c041 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 10 | `claude-opus-4-8-high__t43_c000` | c043 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |

## claude-sonnet-5-high

Pool run `g4` (slots 200-249), harness `6d87c64`, tournament config md5 `9dd458946f007a22c46de945b9891820`.

### Group 1 — winner `claude-sonnet-5-high__t215_c000`

105 simulated games, 105 forfeit games.

| rank | bot | slot | eligible | W-L-D (simulated) | forfeit W | points | Elo |
|--:|---|---|:-:|---|--:|--:|--:|
| 1 | `claude-sonnet-5-high__t215_c000` | c215 | yes | 18-12-0 | 15 | 33.0 | 1068.0 |
| 2 | `claude-sonnet-5-high__t211_c000` | c211 | yes | 17-13-0 | 15 | 32.0 | 1046.7 |
| 3 | `claude-sonnet-5-high__t213_c000` | c213 | yes | 17-13-0 | 15 | 32.0 | 1046.7 |
| 4 | `claude-sonnet-5-high__t214_c000` | c214 | yes | 17-13-0 | 15 | 32.0 | 1046.7 |
| 5 | `claude-sonnet-5-high__t206_c000` | c206 | yes | 16-14-0 | 15 | 31.0 | 1025.6 |
| 6 | `claude-sonnet-5-high__t204_c000` | c204 | yes | 15-15-0 | 15 | 30.0 | 1004.5 |
| 7 | `claude-sonnet-5-high__t203_c000` | c203 | yes | 5-25-0 | 15 | 20.0 | 762.0 |
| 8 | `claude-sonnet-5-high__t201_c000` | c201 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 9 | `claude-sonnet-5-high__t209_c000` | c209 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 10 | `claude-sonnet-5-high__t210_c000` | c210 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |

### Group 2 — winner `claude-sonnet-5-high__t231_c000`

5 simulated games, 80 forfeit games.

| rank | bot | slot | eligible | W-L-D (simulated) | forfeit W | points | Elo |
|--:|---|---|:-:|---|--:|--:|--:|
| 1 | `claude-sonnet-5-high__t231_c000` | c231 | yes | 5-0-0 | 40 | 45.0 | 1344.1 |
| 2 | `claude-sonnet-5-high__t220_c000` | c220 | yes | 0-5-0 | 40 | 40.0 | 655.9 |
| 3 | `claude-sonnet-5-high__t217_c000` | c217 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 4 | `claude-sonnet-5-high__t218_c000` | c218 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 5 | `claude-sonnet-5-high__t219_c000` | c219 | no · qualification failed (W0 D1 L2) | 0-0-0 | 0 | 0.0 | — |
| 6 | `claude-sonnet-5-high__t221_c000` | c221 | no · qualification failed (W1 D0 L2) | 0-0-0 | 0 | 0.0 | — |
| 7 | `claude-sonnet-5-high__t224_c000` | c224 | no · qualification failed (W1 D0 L2) | 0-0-0 | 0 | 0.0 | — |
| 8 | `claude-sonnet-5-high__t225_c000` | c225 | no · qualification failed (W1 D0 L2) | 0-0-0 | 0 | 0.0 | — |
| 9 | `claude-sonnet-5-high__t228_c000` | c228 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 10 | `claude-sonnet-5-high__t229_c000` | c229 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |

### Group 3 — winner `claude-sonnet-5-high__t232_c000`

5 simulated games, 80 forfeit games.

| rank | bot | slot | eligible | W-L-D (simulated) | forfeit W | points | Elo |
|--:|---|---|:-:|---|--:|--:|--:|
| 1 | `claude-sonnet-5-high__t232_c000` | c232 | yes | 3-2-0 | 40 | 43.0 | 1034.5 |
| 2 | `claude-sonnet-5-high__t236_c000` | c236 | yes | 2-3-0 | 40 | 42.0 | 965.5 |
| 3 | `claude-sonnet-5-high__t235_c000` | c235 | no · qualification failed (W1 D0 L2) | 0-0-0 | 0 | 0.0 | — |
| 4 | `claude-sonnet-5-high__t238_c000` | c238 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 5 | `claude-sonnet-5-high__t241_c000` | c241 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 6 | `claude-sonnet-5-high__t243_c000` | c243 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 7 | `claude-sonnet-5-high__t244_c000` | c244 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 8 | `claude-sonnet-5-high__t245_c000` | c245 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 9 | `claude-sonnet-5-high__t246_c000` | c246 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 10 | `claude-sonnet-5-high__t247_c000` | c247 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |

## deepseek-v4-pro-thinking

Pool run `g1` (slots 050-099), harness `dedc97f`, tournament config md5 `9dd458946f007a22c46de945b9891820`.

### Group 1 — winner `deepseek-v4-pro-thinking__t56_c000`

0 simulated games, 45 forfeit games.

| rank | bot | slot | eligible | W-L-D (simulated) | forfeit W | points | Elo |
|--:|---|---|:-:|---|--:|--:|--:|
| 1 | `deepseek-v4-pro-thinking__t56_c000` | c056 | yes | 0-0-0 | 45 | 45.0 | — |
| 2 | `deepseek-v4-pro-thinking__t50_c000` | c050 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 3 | `deepseek-v4-pro-thinking__t51_c000` | c051 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 4 | `deepseek-v4-pro-thinking__t53_c000` | c053 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 5 | `deepseek-v4-pro-thinking__t54_c000` | c054 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 6 | `deepseek-v4-pro-thinking__t60_c000` | c060 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 7 | `deepseek-v4-pro-thinking__t61_c000` | c061 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 8 | `deepseek-v4-pro-thinking__t64_c000` | c064 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 9 | `deepseek-v4-pro-thinking__t65_c000` | c065 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 10 | `deepseek-v4-pro-thinking__t67_c000` | c067 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |

### Group 2 — winner `deepseek-v4-pro-thinking__t83_c000`

0 simulated games, 45 forfeit games.

| rank | bot | slot | eligible | W-L-D (simulated) | forfeit W | points | Elo |
|--:|---|---|:-:|---|--:|--:|--:|
| 1 | `deepseek-v4-pro-thinking__t83_c000` | c083 | yes | 0-0-0 | 45 | 45.0 | — |
| 2 | `deepseek-v4-pro-thinking__t68_c000` | c068 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 3 | `deepseek-v4-pro-thinking__t69_c000` | c069 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 4 | `deepseek-v4-pro-thinking__t71_c000` | c071 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 5 | `deepseek-v4-pro-thinking__t73_c000` | c073 | no · qualification failed (W1 D0 L2) | 0-0-0 | 0 | 0.0 | — |
| 6 | `deepseek-v4-pro-thinking__t74_c000` | c074 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 7 | `deepseek-v4-pro-thinking__t77_c000` | c077 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 8 | `deepseek-v4-pro-thinking__t78_c000` | c078 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 9 | `deepseek-v4-pro-thinking__t80_c000` | c080 | no · qualification failed (W1 D0 L2) | 0-0-0 | 0 | 0.0 | — |
| 10 | `deepseek-v4-pro-thinking__t81_c000` | c081 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |

### Group 3 — winner `deepseek-v4-pro-thinking__t85_c000`

0 simulated games, 45 forfeit games.

| rank | bot | slot | eligible | W-L-D (simulated) | forfeit W | points | Elo |
|--:|---|---|:-:|---|--:|--:|--:|
| 1 | `deepseek-v4-pro-thinking__t85_c000` | c085 | yes | 0-0-0 | 45 | 45.0 | — |
| 2 | `deepseek-v4-pro-thinking__t87_c000` | c087 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 3 | `deepseek-v4-pro-thinking__t89_c000` | c089 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 4 | `deepseek-v4-pro-thinking__t90_c000` | c090 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 5 | `deepseek-v4-pro-thinking__t91_c000` | c091 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 6 | `deepseek-v4-pro-thinking__t92_c000` | c092 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 7 | `deepseek-v4-pro-thinking__t93_c000` | c093 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 8 | `deepseek-v4-pro-thinking__t97_c000` | c097 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 9 | `deepseek-v4-pro-thinking__t98_c000` | c098 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 10 | `deepseek-v4-pro-thinking__t99_c000` | c099 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |

## gemini-3-1-pro-high

Pool run `g3` (slots 150-199), harness `dedc97f`, tournament config md5 `9dd458946f007a22c46de945b9891820`.

### Group 1 — winner `gemini-3-1-pro-high__t155_c000`

15 simulated games, 105 forfeit games.

| rank | bot | slot | eligible | W-L-D (simulated) | forfeit W | points | Elo |
|--:|---|---|:-:|---|--:|--:|--:|
| 1 | `gemini-3-1-pro-high__t155_c000` | c155 | yes | 8-2-0 | 35 | 43.0 | 1172.5 |
| 2 | `gemini-3-1-pro-high__t158_c000` | c158 | yes | 5-4-1 | 35 | 40.5 | 1030.1 |
| 3 | `gemini-3-1-pro-high__t151_c000` | c151 | yes | 1-8-1 | 35 | 36.5 | 797.4 |
| 4 | `gemini-3-1-pro-high__t150_c000` | c150 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 5 | `gemini-3-1-pro-high__t153_c000` | c153 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 6 | `gemini-3-1-pro-high__t156_c000` | c156 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 7 | `gemini-3-1-pro-high__t160_c000` | c160 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 8 | `gemini-3-1-pro-high__t161_c000` | c161 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 9 | `gemini-3-1-pro-high__t163_c000` | c163 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 10 | `gemini-3-1-pro-high__t165_c000` | c165 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |

### Group 2 — winner `gemini-3-1-pro-high__t167_c000`

75 simulated games, 120 forfeit games.

| rank | bot | slot | eligible | W-L-D (simulated) | forfeit W | points | Elo |
|--:|---|---|:-:|---|--:|--:|--:|
| 1 | `gemini-3-1-pro-high__t167_c000` | c167 | yes | 16-9-0 | 20 | 36.0 | 1083.7 |
| 2 | `gemini-3-1-pro-high__t183_c000` | c183 | yes | 14-11-0 | 20 | 34.0 | 1035.3 |
| 3 | `gemini-3-1-pro-high__t174_c000` | c174 | yes | 13-12-0 | 20 | 33.0 | 1011.7 |
| 4 | `gemini-3-1-pro-high__t175_c000` | c175 | yes | 12-13-0 | 20 | 32.0 | 988.1 |
| 5 | `gemini-3-1-pro-high__t173_c000` | c173 | yes | 10-15-0 | 20 | 30.0 | 940.6 |
| 6 | `gemini-3-1-pro-high__t179_c000` | c179 | yes | 10-15-0 | 20 | 30.0 | 940.6 |
| 7 | `gemini-3-1-pro-high__t166_c000` | c166 | no · qualification failed (W1 D0 L2) | 0-0-0 | 0 | 0.0 | — |
| 8 | `gemini-3-1-pro-high__t168_c000` | c168 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 9 | `gemini-3-1-pro-high__t172_c000` | c172 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 10 | `gemini-3-1-pro-high__t181_c000` | c181 | no · qualification failed (W0 D1 L2) | 0-0-0 | 0 | 0.0 | — |

### Group 3 — winner `gemini-3-1-pro-high__t192_c000`

105 simulated games, 105 forfeit games.

| rank | bot | slot | eligible | W-L-D (simulated) | forfeit W | points | Elo |
|--:|---|---|:-:|---|--:|--:|--:|
| 1 | `gemini-3-1-pro-high__t192_c000` | c192 | yes | 28-1-1 | 15 | 43.5 | 1442.9 |
| 2 | `gemini-3-1-pro-high__t188_c000` | c188 | yes | 17-12-1 | 15 | 32.5 | 1041.6 |
| 3 | `gemini-3-1-pro-high__t196_c000` | c196 | yes | 16-13-1 | 15 | 31.5 | 1016.7 |
| 4 | `gemini-3-1-pro-high__t189_c000` | c189 | yes | 14-16-0 | 15 | 29.0 | 956.6 |
| 5 | `gemini-3-1-pro-high__t199_c000` | c199 | yes | 12-18-0 | 15 | 27.0 | 909.2 |
| 6 | `gemini-3-1-pro-high__t193_c000` | c193 | yes | 8-21-1 | 15 | 23.5 | 823.0 |
| 7 | `gemini-3-1-pro-high__t197_c000` | c197 | yes | 8-22-0 | 15 | 23.0 | 810.0 |
| 8 | `gemini-3-1-pro-high__t190_c000` | c190 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 9 | `gemini-3-1-pro-high__t194_c000` | c194 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 10 | `gemini-3-1-pro-high__t195_c000` | c195 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |

## gemini-3-8-flash-high

Pool run `g2` (slots 100-149), harness `dedc97f`, tournament config md5 `9dd458946f007a22c46de945b9891820`.

### Group 1 — winner `gemini-3-8-flash-high__t113_c000`

105 simulated games, 105 forfeit games.

| rank | bot | slot | eligible | W-L-D (simulated) | forfeit W | points | Elo |
|--:|---|---|:-:|---|--:|--:|--:|
| 1 | `gemini-3-8-flash-high__t113_c000` | c113 | yes | 20-10-0 | 15 | 35.0 | 1126.7 |
| 2 | `gemini-3-8-flash-high__t102_c000` | c102 | yes | 19-11-0 | 15 | 34.0 | 1102.8 |
| 3 | `gemini-3-8-flash-high__t106_c000` | c106 | yes | 19-11-0 | 15 | 34.0 | 1102.8 |
| 4 | `gemini-3-8-flash-high__t107_c000` | c107 | yes | 19-11-0 | 15 | 34.0 | 1102.8 |
| 5 | `gemini-3-8-flash-high__t100_c000` | c100 | yes | 17-13-0 | 15 | 32.0 | 1055.8 |
| 6 | `gemini-3-8-flash-high__t108_c000` | c108 | yes | 6-24-0 | 15 | 21.0 | 771.2 |
| 7 | `gemini-3-8-flash-high__t105_c000` | c105 | yes | 5-25-0 | 15 | 20.0 | 738.0 |
| 8 | `gemini-3-8-flash-high__t101_c000` | c101 | no · qualification failed (W1 D0 L2) | 0-0-0 | 0 | 0.0 | — |
| 9 | `gemini-3-8-flash-high__t104_c000` | c104 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 10 | `gemini-3-8-flash-high__t109_c000` | c109 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |

### Group 2 — winner `gemini-3-8-flash-high__t122_c000`

225 simulated games, 0 forfeit games.

| rank | bot | slot | eligible | W-L-D (simulated) | forfeit W | points | Elo |
|--:|---|---|:-:|---|--:|--:|--:|
| 1 | `gemini-3-8-flash-high__t122_c000` | c122 | yes | 34-10-1 | 0 | 34.5 | 1197.9 |
| 2 | `gemini-3-8-flash-high__t128_c000` | c128 | yes | 28-12-5 | 0 | 30.5 | 1126.3 |
| 3 | `gemini-3-8-flash-high__t114_c000` | c114 | yes | 24-17-4 | 0 | 26.0 | 1054.0 |
| 4 | `gemini-3-8-flash-high__t116_c000` | c116 | yes | 24-17-4 | 0 | 26.0 | 1054.0 |
| 5 | `gemini-3-8-flash-high__t118_c000` | c118 | yes | 23-20-2 | 0 | 24.0 | 1023.2 |
| 6 | `gemini-3-8-flash-high__t119_c000` | c119 | yes | 23-22-0 | 0 | 23.0 | 1007.9 |
| 7 | `gemini-3-8-flash-high__t127_c000` | c127 | yes | 21-24-0 | 0 | 21.0 | 977.3 |
| 8 | `gemini-3-8-flash-high__t129_c000` | c129 | yes | 15-29-1 | 0 | 15.5 | 890.7 |
| 9 | `gemini-3-8-flash-high__t125_c000` | c125 | yes | 13-31-1 | 0 | 13.5 | 857.0 |
| 10 | `gemini-3-8-flash-high__t123_c000` | c123 | yes | 11-34-0 | 0 | 11.0 | 811.7 |

### Group 3 — winner `gemini-3-8-flash-high__t139_c000`

140 simulated games, 80 forfeit games.

| rank | bot | slot | eligible | W-L-D (simulated) | forfeit W | points | Elo |
|--:|---|---|:-:|---|--:|--:|--:|
| 1 | `gemini-3-8-flash-high__t139_c000` | c139 | yes | 24-10-1 | 10 | 34.5 | 1133.6 |
| 2 | `gemini-3-8-flash-high__t131_c000` | c131 | yes | 22-13-0 | 10 | 32.0 | 1084.0 |
| 3 | `gemini-3-8-flash-high__t130_c000` | c130 | yes | 18-13-4 | 10 | 30.0 | 1046.3 |
| 4 | `gemini-3-8-flash-high__t135_c000` | c135 | yes | 18-15-2 | 10 | 29.0 | 1027.8 |
| 5 | `gemini-3-8-flash-high__t145_c000` | c145 | yes | 16-19-0 | 10 | 26.0 | 972.8 |
| 6 | `gemini-3-8-flash-high__t147_c000` | c147 | yes | 15-20-0 | 10 | 25.0 | 954.3 |
| 7 | `gemini-3-8-flash-high__t142_c000` | c142 | yes | 14-21-0 | 10 | 24.0 | 935.6 |
| 8 | `gemini-3-8-flash-high__t137_c000` | c137 | yes | 9-25-1 | 10 | 19.5 | 845.7 |
| 9 | `gemini-3-8-flash-high__t136_c000` | c136 | no · qualification failed (W1 D0 L2) | 0-0-0 | 0 | 0.0 | — |
| 10 | `gemini-3-8-flash-high__t141_c000` | c141 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |

## glm-5.2-high

Pool run `g1` (slots 050-099), harness `dedc97f`, tournament config md5 `9dd458946f007a22c46de945b9891820`.

### Group 1 — winner `glm-5.2-high__t69_c000`

50 simulated games, 125 forfeit games.

| rank | bot | slot | eligible | W-L-D (simulated) | forfeit W | points | Elo |
|--:|---|---|:-:|---|--:|--:|--:|
| 1 | `glm-5.2-high__t69_c000` | c069 | yes | 13-5-2 | 25 | 39.0 | 1122.1 |
| 2 | `glm-5.2-high__t62_c000` | c062 | yes | 13-7-0 | 25 | 38.0 | 1090.2 |
| 3 | `glm-5.2-high__t58_c000` | c058 | yes | 9-10-1 | 25 | 34.5 | 985.0 |
| 4 | `glm-5.2-high__t51_c000` | c051 | yes | 7-12-1 | 25 | 32.5 | 925.0 |
| 5 | `glm-5.2-high__t55_c000` | c055 | yes | 6-14-0 | 25 | 31.0 | 877.7 |
| 6 | `glm-5.2-high__t52_c000` | c052 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 7 | `glm-5.2-high__t54_c000` | c054 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 8 | `glm-5.2-high__t59_c000` | c059 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 9 | `glm-5.2-high__t60_c000` | c060 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 10 | `glm-5.2-high__t67_c000` | c067 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |

### Group 2 — winner `glm-5.2-high__t78_c000`

5 simulated games, 80 forfeit games.

| rank | bot | slot | eligible | W-L-D (simulated) | forfeit W | points | Elo |
|--:|---|---|:-:|---|--:|--:|--:|
| 1 | `glm-5.2-high__t78_c000` | c078 | yes | 4-1-0 | 40 | 44.0 | 1117.0 |
| 2 | `glm-5.2-high__t84_c000` | c084 | yes | 1-4-0 | 40 | 41.0 | 883.0 |
| 3 | `glm-5.2-high__t70_c000` | c070 | no · qualification failed (W1 D1 L1) | 0-0-0 | 0 | 0.0 | — |
| 4 | `glm-5.2-high__t74_c000` | c074 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 5 | `glm-5.2-high__t75_c000` | c075 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 6 | `glm-5.2-high__t76_c000` | c076 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 7 | `glm-5.2-high__t77_c000` | c077 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 8 | `glm-5.2-high__t79_c000` | c079 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 9 | `glm-5.2-high__t83_c000` | c083 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 10 | `glm-5.2-high__t85_c000` | c085 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |

### Group 3 — winner `glm-5.2-high__t99_c000`

5 simulated games, 80 forfeit games.

| rank | bot | slot | eligible | W-L-D (simulated) | forfeit W | points | Elo |
|--:|---|---|:-:|---|--:|--:|--:|
| 1 | `glm-5.2-high__t99_c000` | c099 | yes | 4-1-0 | 40 | 44.0 | 1117.0 |
| 2 | `glm-5.2-high__t87_c000` | c087 | yes | 1-4-0 | 40 | 41.0 | 883.0 |
| 3 | `glm-5.2-high__t86_c000` | c086 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 4 | `glm-5.2-high__t89_c000` | c089 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 5 | `glm-5.2-high__t90_c000` | c090 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 6 | `glm-5.2-high__t92_c000` | c092 | no · qualification failed (W0 D2 L1) | 0-0-0 | 0 | 0.0 | — |
| 7 | `glm-5.2-high__t93_c000` | c093 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 8 | `glm-5.2-high__t94_c000` | c094 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 9 | `glm-5.2-high__t95_c000` | c095 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 10 | `glm-5.2-high__t98_c000` | c098 | no · qualification failed (W1 D0 L2) | 0-0-0 | 0 | 0.0 | — |

## glm-5.3-high

Pool run `g3` (slots 150-199), harness `dedc97f`, tournament config md5 `9dd458946f007a22c46de945b9891820`.

### Group 1 — winner `glm-5.3-high__t150_c000`

0 simulated games, 0 forfeit games.

| rank | bot | slot | eligible | W-L-D (simulated) | forfeit W | points | Elo |
|--:|---|---|:-:|---|--:|--:|--:|
| 1 | `glm-5.3-high__t150_c000` | c150 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 2 | `glm-5.3-high__t151_c000` | c151 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 3 | `glm-5.3-high__t152_c000` | c152 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 4 | `glm-5.3-high__t153_c000` | c153 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 5 | `glm-5.3-high__t155_c000` | c155 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 6 | `glm-5.3-high__t156_c000` | c156 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 7 | `glm-5.3-high__t158_c000` | c158 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 8 | `glm-5.3-high__t162_c000` | c162 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 9 | `glm-5.3-high__t163_c000` | c163 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 10 | `glm-5.3-high__t165_c000` | c165 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |

### Group 2 — winner `glm-5.3-high__t166_c000`

0 simulated games, 0 forfeit games.

| rank | bot | slot | eligible | W-L-D (simulated) | forfeit W | points | Elo |
|--:|---|---|:-:|---|--:|--:|--:|
| 1 | `glm-5.3-high__t166_c000` | c166 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 2 | `glm-5.3-high__t167_c000` | c167 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 3 | `glm-5.3-high__t168_c000` | c168 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 4 | `glm-5.3-high__t171_c000` | c171 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 5 | `glm-5.3-high__t173_c000` | c173 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 6 | `glm-5.3-high__t174_c000` | c174 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 7 | `glm-5.3-high__t176_c000` | c176 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 8 | `glm-5.3-high__t177_c000` | c177 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 9 | `glm-5.3-high__t178_c000` | c178 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 10 | `glm-5.3-high__t179_c000` | c179 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |

### Group 3 — winner `glm-5.3-high__t182_c000`

0 simulated games, 0 forfeit games.

| rank | bot | slot | eligible | W-L-D (simulated) | forfeit W | points | Elo |
|--:|---|---|:-:|---|--:|--:|--:|
| 1 | `glm-5.3-high__t182_c000` | c182 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 2 | `glm-5.3-high__t183_c000` | c183 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 3 | `glm-5.3-high__t185_c000` | c185 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 4 | `glm-5.3-high__t187_c000` | c187 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 5 | `glm-5.3-high__t188_c000` | c188 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 6 | `glm-5.3-high__t189_c000` | c189 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 7 | `glm-5.3-high__t190_c000` | c190 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 8 | `glm-5.3-high__t192_c000` | c192 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 9 | `glm-5.3-high__t196_c000` | c196 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 10 | `glm-5.3-high__t199_c000` | c199 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |

## gpt-5.3-codex-high

Pool run `g2` (slots 100-149), harness `8c28de0`, tournament config md5 `9dd458946f007a22c46de945b9891820`.

### Group 1 — winner `gpt-5.3-codex-high__t113_c000`

30 simulated games, 120 forfeit games.

| rank | bot | slot | eligible | W-L-D (simulated) | forfeit W | points | Elo |
|--:|---|---|:-:|---|--:|--:|--:|
| 1 | `gpt-5.3-codex-high__t113_c000` | c113 | yes | 9-4-2 | 30 | 40.0 | 1093.7 |
| 2 | `gpt-5.3-codex-high__t105_c000` | c105 | yes | 8-5-2 | 30 | 39.0 | 1055.9 |
| 3 | `gpt-5.3-codex-high__t103_c000` | c103 | yes | 6-7-2 | 30 | 37.0 | 982.6 |
| 4 | `gpt-5.3-codex-high__t108_c000` | c108 | yes | 3-10-2 | 30 | 34.0 | 867.7 |
| 5 | `gpt-5.3-codex-high__t100_c000` | c100 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 6 | `gpt-5.3-codex-high__t107_c000` | c107 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 7 | `gpt-5.3-codex-high__t110_c000` | c110 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 8 | `gpt-5.3-codex-high__t111_c000` | c111 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 9 | `gpt-5.3-codex-high__t112_c000` | c112 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 10 | `gpt-5.3-codex-high__t115_c000` | c115 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |

### Group 2 — winner `gpt-5.3-codex-high__t119_c000`

15 simulated games, 105 forfeit games.

| rank | bot | slot | eligible | W-L-D (simulated) | forfeit W | points | Elo |
|--:|---|---|:-:|---|--:|--:|--:|
| 1 | `gpt-5.3-codex-high__t119_c000` | c119 | yes | 6-4-0 | 35 | 41.0 | 1048.3 |
| 2 | `gpt-5.3-codex-high__t121_c000` | c121 | yes | 6-4-0 | 35 | 41.0 | 1048.3 |
| 3 | `gpt-5.3-codex-high__t128_c000` | c128 | yes | 3-7-0 | 35 | 38.0 | 903.3 |
| 4 | `gpt-5.3-codex-high__t118_c000` | c118 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 5 | `gpt-5.3-codex-high__t120_c000` | c120 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 6 | `gpt-5.3-codex-high__t122_c000` | c122 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 7 | `gpt-5.3-codex-high__t124_c000` | c124 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 8 | `gpt-5.3-codex-high__t126_c000` | c126 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 9 | `gpt-5.3-codex-high__t127_c000` | c127 | no · qualification failed (W0 D1 L2) | 0-0-0 | 0 | 0.0 | — |
| 10 | `gpt-5.3-codex-high__t131_c000` | c131 | no · qualification failed (W0 D1 L2) | 0-0-0 | 0 | 0.0 | — |

### Group 3 — winner `gpt-5.3-codex-high__t143_c000`

50 simulated games, 125 forfeit games.

| rank | bot | slot | eligible | W-L-D (simulated) | forfeit W | points | Elo |
|--:|---|---|:-:|---|--:|--:|--:|
| 1 | `gpt-5.3-codex-high__t143_c000` | c143 | yes | 14-6-0 | 25 | 39.0 | 1120.4 |
| 2 | `gpt-5.3-codex-high__t138_c000` | c138 | yes | 11-9-0 | 25 | 36.0 | 1029.3 |
| 3 | `gpt-5.3-codex-high__t142_c000` | c142 | yes | 11-9-0 | 25 | 36.0 | 1029.3 |
| 4 | `gpt-5.3-codex-high__t139_c000` | c139 | yes | 8-12-0 | 25 | 33.0 | 941.4 |
| 5 | `gpt-5.3-codex-high__t147_c000` | c147 | yes | 6-14-0 | 25 | 31.0 | 879.7 |
| 6 | `gpt-5.3-codex-high__t134_c000` | c134 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 7 | `gpt-5.3-codex-high__t136_c000` | c136 | no · qualification failed (W0 D2 L1) | 0-0-0 | 0 | 0.0 | — |
| 8 | `gpt-5.3-codex-high__t145_c000` | c145 | no · qualification failed (W1 D0 L2) | 0-0-0 | 0 | 0.0 | — |
| 9 | `gpt-5.3-codex-high__t146_c000` | c146 | no · qualification failed (W0 D2 L1) | 0-0-0 | 0 | 0.0 | — |
| 10 | `gpt-5.3-codex-high__t149_c000` | c149 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |

## gpt-5.4

Pool run `g4` (slots 200-249), harness `6d87c64`, tournament config md5 `9dd458946f007a22c46de945b9891820`.

### Group 1 — winner `gpt-5.4__t216_c000`

50 simulated games, 125 forfeit games.

| rank | bot | slot | eligible | W-L-D (simulated) | forfeit W | points | Elo |
|--:|---|---|:-:|---|--:|--:|--:|
| 1 | `gpt-5.4__t216_c000` | c216 | yes | 15-5-0 | 25 | 40.0 | 1175.4 |
| 2 | `gpt-5.4__t210_c000` | c210 | yes | 14-6-0 | 25 | 39.0 | 1139.2 |
| 3 | `gpt-5.4__t213_c000` | c213 | yes | 9-7-4 | 25 | 36.0 | 1037.7 |
| 4 | `gpt-5.4__t219_c000` | c219 | yes | 5-11-4 | 25 | 32.0 | 903.0 |
| 5 | `gpt-5.4__t218_c000` | c218 | yes | 3-17-0 | 25 | 28.0 | 744.7 |
| 6 | `gpt-5.4__t200_c000` | c200 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 7 | `gpt-5.4__t201_c000` | c201 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 8 | `gpt-5.4__t202_c000` | c202 | no · qualification failed (W1 D0 L2) | 0-0-0 | 0 | 0.0 | — |
| 9 | `gpt-5.4__t205_c000` | c205 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 10 | `gpt-5.4__t211_c000` | c211 | no · qualification failed (W0 D1 L2) | 0-0-0 | 0 | 0.0 | — |

### Group 2 — winner `gpt-5.4__t227_c000`

75 simulated games, 120 forfeit games.

| rank | bot | slot | eligible | W-L-D (simulated) | forfeit W | points | Elo |
|--:|---|---|:-:|---|--:|--:|--:|
| 1 | `gpt-5.4__t227_c000` | c227 | yes | 16-3-6 | 20 | 39.0 | 1179.3 |
| 2 | `gpt-5.4__t222_c000` | c222 | yes | 16-7-2 | 20 | 37.0 | 1120.5 |
| 3 | `gpt-5.4__t233_c000` | c233 | yes | 11-10-4 | 20 | 33.0 | 1013.8 |
| 4 | `gpt-5.4__t230_c000` | c230 | yes | 10-13-2 | 20 | 31.0 | 961.8 |
| 5 | `gpt-5.4__t228_c000` | c228 | yes | 7-12-6 | 20 | 30.0 | 935.4 |
| 6 | `gpt-5.4__t226_c000` | c226 | yes | 4-19-2 | 20 | 25.0 | 789.1 |
| 7 | `gpt-5.4__t220_c000` | c220 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 8 | `gpt-5.4__t224_c000` | c224 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 9 | `gpt-5.4__t225_c000` | c225 | no · qualification failed (W0 D2 L1) | 0-0-0 | 0 | 0.0 | — |
| 10 | `gpt-5.4__t232_c000` | c232 | no · qualification failed (W0 D2 L1) | 0-0-0 | 0 | 0.0 | — |

### Group 3 — winner `gpt-5.4__t246_c000`

105 simulated games, 105 forfeit games.

| rank | bot | slot | eligible | W-L-D (simulated) | forfeit W | points | Elo |
|--:|---|---|:-:|---|--:|--:|--:|
| 1 | `gpt-5.4__t246_c000` | c246 | yes | 29-1-0 | 15 | 44.0 | 1555.8 |
| 2 | `gpt-5.4__t247_c000` | c247 | yes | 22-8-0 | 15 | 37.0 | 1200.1 |
| 3 | `gpt-5.4__t242_c000` | c242 | yes | 18-12-0 | 15 | 33.0 | 1065.3 |
| 4 | `gpt-5.4__t234_c000` | c234 | yes | 13-17-0 | 15 | 28.0 | 917.8 |
| 5 | `gpt-5.4__t243_c000` | c243 | yes | 12-18-0 | 15 | 27.0 | 889.0 |
| 6 | `gpt-5.4__t236_c000` | c236 | yes | 7-23-0 | 15 | 22.0 | 738.8 |
| 7 | `gpt-5.4__t244_c000` | c244 | yes | 4-26-0 | 15 | 19.0 | 633.1 |
| 8 | `gpt-5.4__t237_c000` | c237 | no · qualification failed (W1 D0 L2) | 0-0-0 | 0 | 0.0 | — |
| 9 | `gpt-5.4__t239_c000` | c239 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 10 | `gpt-5.4__t248_c000` | c248 | no · qualification failed (W1 D0 L2) | 0-0-0 | 0 | 0.0 | — |

## gpt-5.5

Pool run `g3` (slots 150-199), harness `3c03d49`, tournament config md5 `9dd458946f007a22c46de945b9891820`.

### Group 1 — winner `gpt-5.5__t162_c000`

75 simulated games, 120 forfeit games.

| rank | bot | slot | eligible | W-L-D (simulated) | forfeit W | points | Elo |
|--:|---|---|:-:|---|--:|--:|--:|
| 1 | `gpt-5.5__t162_c000` | c162 | yes | 15-8-2 | 20 | 36.0 | 1085.0 |
| 2 | `gpt-5.5__t154_c000` | c154 | yes | 14-9-2 | 20 | 35.0 | 1060.3 |
| 3 | `gpt-5.5__t152_c000` | c152 | yes | 12-11-2 | 20 | 33.0 | 1012.2 |
| 4 | `gpt-5.5__t160_c000` | c160 | yes | 12-12-1 | 20 | 32.5 | 1000.3 |
| 5 | `gpt-5.5__t151_c000` | c151 | yes | 10-14-1 | 20 | 30.5 | 952.4 |
| 6 | `gpt-5.5__t150_c000` | c150 | yes | 8-17-0 | 20 | 28.0 | 889.8 |
| 7 | `gpt-5.5__t156_c000` | c156 | no · qualification failed (W1 D0 L2) | 0-0-0 | 0 | 0.0 | — |
| 8 | `gpt-5.5__t157_c000` | c157 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 9 | `gpt-5.5__t158_c000` | c158 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 10 | `gpt-5.5__t165_c000` | c165 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |

### Group 2 — winner `gpt-5.5__t166_c000`

30 simulated games, 120 forfeit games.

| rank | bot | slot | eligible | W-L-D (simulated) | forfeit W | points | Elo |
|--:|---|---|:-:|---|--:|--:|--:|
| 1 | `gpt-5.5__t166_c000` | c166 | yes | 10-4-1 | 30 | 40.5 | 1116.0 |
| 2 | `gpt-5.5__t179_c000` | c179 | yes | 9-6-0 | 30 | 39.0 | 1057.6 |
| 3 | `gpt-5.5__t182_c000` | c182 | yes | 7-8-0 | 30 | 37.0 | 982.7 |
| 4 | `gpt-5.5__t170_c000` | c170 | yes | 3-11-1 | 30 | 33.5 | 843.7 |
| 5 | `gpt-5.5__t168_c000` | c168 | no · qualification failed (W1 D1 L1) | 0-0-0 | 0 | 0.0 | — |
| 6 | `gpt-5.5__t169_c000` | c169 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 7 | `gpt-5.5__t172_c000` | c172 | no · qualification failed (W1 D1 L1) | 0-0-0 | 0 | 0.0 | — |
| 8 | `gpt-5.5__t176_c000` | c176 | no · qualification failed (W1 D0 L2) | 0-0-0 | 0 | 0.0 | — |
| 9 | `gpt-5.5__t181_c000` | c181 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 10 | `gpt-5.5__t184_c000` | c184 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |

### Group 3 — winner `gpt-5.5__t192_c000`

140 simulated games, 80 forfeit games.

| rank | bot | slot | eligible | W-L-D (simulated) | forfeit W | points | Elo |
|--:|---|---|:-:|---|--:|--:|--:|
| 1 | `gpt-5.5__t192_c000` | c192 | yes | 24-4-7 | 10 | 37.5 | 1204.9 |
| 2 | `gpt-5.5__t185_c000` | c185 | yes | 23-11-1 | 10 | 33.5 | 1114.7 |
| 3 | `gpt-5.5__t197_c000` | c197 | yes | 18-10-7 | 10 | 31.5 | 1074.2 |
| 4 | `gpt-5.5__t196_c000` | c196 | yes | 14-21-0 | 10 | 24.0 | 931.0 |
| 5 | `gpt-5.5__t187_c000` | c187 | yes | 12-19-4 | 10 | 24.0 | 931.0 |
| 6 | `gpt-5.5__t193_c000` | c193 | yes | 13-21-1 | 10 | 23.5 | 921.3 |
| 7 | `gpt-5.5__t189_c000` | c189 | yes | 11-19-5 | 10 | 23.5 | 921.3 |
| 8 | `gpt-5.5__t194_c000` | c194 | yes | 11-21-3 | 10 | 22.5 | 901.7 |
| 9 | `gpt-5.5__t188_c000` | c188 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 10 | `gpt-5.5__t191_c000` | c191 | no · qualification failed (W1 D1 L1) | 0-0-0 | 0 | 0.0 | — |

## gpt-5.6-luna

Pool run `g2` (slots 100-149), harness `dedc97f`, tournament config md5 `9dd458946f007a22c46de945b9891820`.

### Group 1 — winner `gpt-5.6-luna__t117_c000`

0 simulated games, 45 forfeit games.

| rank | bot | slot | eligible | W-L-D (simulated) | forfeit W | points | Elo |
|--:|---|---|:-:|---|--:|--:|--:|
| 1 | `gpt-5.6-luna__t117_c000` | c117 | yes | 0-0-0 | 45 | 45.0 | — |
| 2 | `gpt-5.6-luna__t103_c000` | c103 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 3 | `gpt-5.6-luna__t104_c000` | c104 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 4 | `gpt-5.6-luna__t106_c000` | c106 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 5 | `gpt-5.6-luna__t113_c000` | c113 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 6 | `gpt-5.6-luna__t114_c000` | c114 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 7 | `gpt-5.6-luna__t118_c000` | c118 | no · qualification failed (W0 D1 L2) | 0-0-0 | 0 | 0.0 | — |
| 8 | `gpt-5.6-luna__t119_c000` | c119 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 9 | `gpt-5.6-luna__t120_c000` | c120 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 10 | `gpt-5.6-luna__t121_c000` | c121 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |

### Group 2 — winner `gpt-5.6-luna__t128_c000`

5 simulated games, 80 forfeit games.

| rank | bot | slot | eligible | W-L-D (simulated) | forfeit W | points | Elo |
|--:|---|---|:-:|---|--:|--:|--:|
| 1 | `gpt-5.6-luna__t128_c000` | c128 | yes | 3-2-0 | 40 | 43.0 | 1034.5 |
| 2 | `gpt-5.6-luna__t133_c000` | c133 | yes | 2-3-0 | 40 | 42.0 | 965.5 |
| 3 | `gpt-5.6-luna__t122_c000` | c122 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 4 | `gpt-5.6-luna__t123_c000` | c123 | no · qualification failed (W0 D1 L2) | 0-0-0 | 0 | 0.0 | — |
| 5 | `gpt-5.6-luna__t124_c000` | c124 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 6 | `gpt-5.6-luna__t129_c000` | c129 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 7 | `gpt-5.6-luna__t130_c000` | c130 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 8 | `gpt-5.6-luna__t131_c000` | c131 | no · qualification failed (W0 D2 L1) | 0-0-0 | 0 | 0.0 | — |
| 9 | `gpt-5.6-luna__t132_c000` | c132 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 10 | `gpt-5.6-luna__t134_c000` | c134 | no · qualification failed (W0 D2 L1) | 0-0-0 | 0 | 0.0 | — |

### Group 3 — winner `gpt-5.6-luna__t146_c000`

0 simulated games, 45 forfeit games.

| rank | bot | slot | eligible | W-L-D (simulated) | forfeit W | points | Elo |
|--:|---|---|:-:|---|--:|--:|--:|
| 1 | `gpt-5.6-luna__t146_c000` | c146 | yes | 0-0-0 | 45 | 45.0 | — |
| 2 | `gpt-5.6-luna__t135_c000` | c135 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 3 | `gpt-5.6-luna__t136_c000` | c136 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 4 | `gpt-5.6-luna__t138_c000` | c138 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 5 | `gpt-5.6-luna__t140_c000` | c140 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 6 | `gpt-5.6-luna__t142_c000` | c142 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 7 | `gpt-5.6-luna__t143_c000` | c143 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 8 | `gpt-5.6-luna__t144_c000` | c144 | no · qualification failed (W0 D2 L1) | 0-0-0 | 0 | 0.0 | — |
| 9 | `gpt-5.6-luna__t145_c000` | c145 | no · qualification failed (W0 D1 L2) | 0-0-0 | 0 | 0.0 | — |
| 10 | `gpt-5.6-luna__t147_c000` | c147 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |

## gpt-5.6-sol

Pool run `g0` (slots 000-049), harness `6d87c64`, tournament config md5 `9dd458946f007a22c46de945b9891820`.

### Group 1 — winner `gpt-5.6-sol__t00_c000`

75 simulated games, 120 forfeit games.

| rank | bot | slot | eligible | W-L-D (simulated) | forfeit W | points | Elo |
|--:|---|---|:-:|---|--:|--:|--:|
| 1 | `gpt-5.6-sol__t00_c000` | c000 | yes | 23-2-0 | 20 | 43.0 | 1390.5 |
| 2 | `gpt-5.6-sol__t16_c000` | c016 | yes | 16-9-0 | 20 | 36.0 | 1109.2 |
| 3 | `gpt-5.6-sol__t12_c000` | c012 | yes | 13-12-0 | 20 | 33.0 | 1015.3 |
| 4 | `gpt-5.6-sol__t15_c000` | c015 | yes | 12-13-0 | 20 | 32.0 | 984.7 |
| 5 | `gpt-5.6-sol__t07_c000` | c007 | yes | 9-16-0 | 20 | 29.0 | 890.8 |
| 6 | `gpt-5.6-sol__t05_c000` | c005 | yes | 2-23-0 | 20 | 22.0 | 609.5 |
| 7 | `gpt-5.6-sol__t01_c000` | c001 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 8 | `gpt-5.6-sol__t03_c000` | c003 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 9 | `gpt-5.6-sol__t13_c000` | c013 | no · qualification failed (W1 D1 L1) | 0-0-0 | 0 | 0.0 | — |
| 10 | `gpt-5.6-sol__t18_c000` | c018 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |

### Group 2 — winner `gpt-5.6-sol__t30_c000`

180 simulated games, 45 forfeit games.

| rank | bot | slot | eligible | W-L-D (simulated) | forfeit W | points | Elo |
|--:|---|---|:-:|---|--:|--:|--:|
| 1 | `gpt-5.6-sol__t30_c000` | c030 | yes | 35-2-3 | 5 | 41.5 | 1420.5 |
| 2 | `gpt-5.6-sol__t23_c000` | c023 | yes | 28-11-1 | 5 | 33.5 | 1188.4 |
| 3 | `gpt-5.6-sol__t27_c000` | c027 | yes | 22-12-6 | 5 | 30.0 | 1110.7 |
| 4 | `gpt-5.6-sol__t29_c000` | c029 | yes | 22-17-1 | 5 | 27.5 | 1057.9 |
| 5 | `gpt-5.6-sol__t24_c000` | c024 | yes | 16-11-13 | 5 | 27.5 | 1057.9 |
| 6 | `gpt-5.6-sol__t20_c000` | c020 | yes | 20-19-1 | 5 | 25.5 | 1016.3 |
| 7 | `gpt-5.6-sol__t26_c000` | c026 | yes | 10-28-2 | 5 | 16.0 | 804.9 |
| 8 | `gpt-5.6-sol__t19_c000` | c019 | yes | 9-28-3 | 5 | 15.5 | 792.3 |
| 9 | `gpt-5.6-sol__t22_c000` | c022 | yes | 3-37-0 | 5 | 8.0 | 551.0 |
| 10 | `gpt-5.6-sol__t31_c000` | c031 | no · qualification failed (W0 D1 L2) | 0-0-0 | 0 | 0.0 | — |

### Group 3 — winner `gpt-5.6-sol__t44_c000`

180 simulated games, 45 forfeit games.

| rank | bot | slot | eligible | W-L-D (simulated) | forfeit W | points | Elo |
|--:|---|---|:-:|---|--:|--:|--:|
| 1 | `gpt-5.6-sol__t44_c000` | c044 | yes | 30-10-0 | 5 | 35.0 | 1206.1 |
| 2 | `gpt-5.6-sol__t46_c000` | c046 | yes | 22-12-6 | 5 | 30.0 | 1110.0 |
| 3 | `gpt-5.6-sol__t33_c000` | c033 | yes | 22-13-5 | 5 | 29.5 | 1101.0 |
| 4 | `gpt-5.6-sol__t36_c000` | c036 | yes | 21-12-7 | 5 | 29.5 | 1101.0 |
| 5 | `gpt-5.6-sol__t43_c000` | c043 | yes | 19-17-4 | 5 | 26.0 | 1038.5 |
| 6 | `gpt-5.6-sol__t48_c000` | c048 | yes | 17-19-4 | 5 | 24.0 | 1002.7 |
| 7 | `gpt-5.6-sol__t41_c000` | c041 | yes | 17-21-2 | 5 | 23.0 | 984.5 |
| 8 | `gpt-5.6-sol__t42_c000` | c042 | yes | 16-23-1 | 5 | 21.5 | 956.6 |
| 9 | `gpt-5.6-sol__t39_c000` | c039 | yes | 0-37-3 | 5 | 6.5 | 499.7 |
| 10 | `gpt-5.6-sol__t38_c000` | c038 | no · qualification failed (W0 D2 L1) | 0-0-0 | 0 | 0.0 | — |

## gpt-5.6-terra

Pool run `g2` (slots 100-149), harness `dedc97f`, tournament config md5 `9dd458946f007a22c46de945b9891820`.

### Group 1 — winner `gpt-5.6-terra__t104_c000`

105 simulated games, 105 forfeit games.

| rank | bot | slot | eligible | W-L-D (simulated) | forfeit W | points | Elo |
|--:|---|---|:-:|---|--:|--:|--:|
| 1 | `gpt-5.6-terra__t104_c000` | c104 | yes | 23-2-5 | 15 | 40.5 | 1297.6 |
| 2 | `gpt-5.6-terra__t101_c000` | c101 | yes | 20-7-3 | 15 | 36.5 | 1171.2 |
| 3 | `gpt-5.6-terra__t116_c000` | c116 | yes | 20-10-0 | 15 | 35.0 | 1129.6 |
| 4 | `gpt-5.6-terra__t112_c000` | c112 | yes | 10-16-4 | 15 | 27.0 | 923.2 |
| 5 | `gpt-5.6-terra__t102_c000` | c102 | yes | 7-13-10 | 15 | 27.0 | 923.2 |
| 6 | `gpt-5.6-terra__t115_c000` | c115 | yes | 8-18-4 | 15 | 25.0 | 870.5 |
| 7 | `gpt-5.6-terra__t108_c000` | c108 | yes | 4-26-0 | 15 | 19.0 | 684.7 |
| 8 | `gpt-5.6-terra__t106_c000` | c106 | no · qualification failed (W0 D2 L1) | 0-0-0 | 0 | 0.0 | — |
| 9 | `gpt-5.6-terra__t107_c000` | c107 | no · qualification failed (W0 D1 L2) | 0-0-0 | 0 | 0.0 | — |
| 10 | `gpt-5.6-terra__t113_c000` | c113 | no · qualification failed (W0 D1 L2) | 0-0-0 | 0 | 0.0 | — |

### Group 2 — winner `gpt-5.6-terra__t117_c000`

75 simulated games, 120 forfeit games.

| rank | bot | slot | eligible | W-L-D (simulated) | forfeit W | points | Elo |
|--:|---|---|:-:|---|--:|--:|--:|
| 1 | `gpt-5.6-terra__t117_c000` | c117 | yes | 17-7-1 | 20 | 37.5 | 1127.5 |
| 2 | `gpt-5.6-terra__t127_c000` | c127 | yes | 15-10-0 | 20 | 35.0 | 1062.3 |
| 3 | `gpt-5.6-terra__t124_c000` | c124 | yes | 14-11-0 | 20 | 34.0 | 1037.4 |
| 4 | `gpt-5.6-terra__t129_c000` | c129 | yes | 12-12-1 | 20 | 32.5 | 1000.5 |
| 5 | `gpt-5.6-terra__t130_c000` | c130 | yes | 9-16-0 | 20 | 29.0 | 913.0 |
| 6 | `gpt-5.6-terra__t120_c000` | c120 | yes | 6-17-2 | 20 | 27.0 | 859.3 |
| 7 | `gpt-5.6-terra__t118_c000` | c118 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 8 | `gpt-5.6-terra__t123_c000` | c123 | no · qualification failed (W1 D0 L2) | 0-0-0 | 0 | 0.0 | — |
| 9 | `gpt-5.6-terra__t125_c000` | c125 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 10 | `gpt-5.6-terra__t126_c000` | c126 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |

### Group 3 — winner `gpt-5.6-terra__t149_c000`

75 simulated games, 120 forfeit games.

| rank | bot | slot | eligible | W-L-D (simulated) | forfeit W | points | Elo |
|--:|---|---|:-:|---|--:|--:|--:|
| 1 | `gpt-5.6-terra__t149_c000` | c149 | yes | 16-8-1 | 20 | 36.5 | 1097.6 |
| 2 | `gpt-5.6-terra__t134_c000` | c134 | yes | 14-10-1 | 20 | 34.5 | 1048.0 |
| 3 | `gpt-5.6-terra__t146_c000` | c146 | yes | 12-11-2 | 20 | 33.0 | 1012.1 |
| 4 | `gpt-5.6-terra__t132_c000` | c132 | yes | 11-12-2 | 20 | 32.0 | 988.2 |
| 5 | `gpt-5.6-terra__t140_c000` | c140 | yes | 10-13-2 | 20 | 31.0 | 964.3 |
| 6 | `gpt-5.6-terra__t143_c000` | c143 | yes | 8-17-0 | 20 | 28.0 | 889.7 |
| 7 | `gpt-5.6-terra__t133_c000` | c133 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 8 | `gpt-5.6-terra__t135_c000` | c135 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 9 | `gpt-5.6-terra__t141_c000` | c141 | no · qualification failed (W0 D1 L2) | 0-0-0 | 0 | 0.0 | — |
| 10 | `gpt-5.6-terra__t142_c000` | c142 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |

## gpt-6-astra

Pool run `g4` (slots 200-249), harness `6d87c64`, tournament config md5 `9dd458946f007a22c46de945b9891820`.

### Group 1 — winner `gpt-6-astra__t221_c000`

50 simulated games, 125 forfeit games.

| rank | bot | slot | eligible | W-L-D (simulated) | forfeit W | points | Elo |
|--:|---|---|:-:|---|--:|--:|--:|
| 1 | `gpt-6-astra__t221_c000` | c221 | yes | 15-5-0 | 25 | 40.0 | 1179.9 |
| 2 | `gpt-6-astra__t204_c000` | c204 | yes | 13-7-0 | 25 | 38.0 | 1108.2 |
| 3 | `gpt-6-astra__t220_c000` | c220 | yes | 13-7-0 | 25 | 38.0 | 1108.2 |
| 4 | `gpt-6-astra__t213_c000` | c213 | yes | 6-14-0 | 25 | 31.0 | 864.5 |
| 5 | `gpt-6-astra__t215_c000` | c215 | yes | 3-17-0 | 25 | 28.0 | 739.2 |
| 6 | `gpt-6-astra__t202_c000` | c202 | no · qualification failed (W0 D1 L2) | 0-0-0 | 0 | 0.0 | — |
| 7 | `gpt-6-astra__t205_c000` | c205 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 8 | `gpt-6-astra__t207_c000` | c207 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 9 | `gpt-6-astra__t210_c000` | c210 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 10 | `gpt-6-astra__t212_c000` | c212 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |

### Group 2 — winner `gpt-6-astra__t224_c000`

15 simulated games, 105 forfeit games.

| rank | bot | slot | eligible | W-L-D (simulated) | forfeit W | points | Elo |
|--:|---|---|:-:|---|--:|--:|--:|
| 1 | `gpt-6-astra__t224_c000` | c224 | yes | 8-2-0 | 35 | 43.0 | 1165.0 |
| 2 | `gpt-6-astra__t229_c000` | c229 | yes | 5-5-0 | 35 | 40.0 | 1000.0 |
| 3 | `gpt-6-astra__t236_c000` | c236 | yes | 2-8-0 | 35 | 37.0 | 835.0 |
| 4 | `gpt-6-astra__t222_c000` | c222 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 5 | `gpt-6-astra__t223_c000` | c223 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 6 | `gpt-6-astra__t226_c000` | c226 | no · qualification failed (W1 D0 L2) | 0-0-0 | 0 | 0.0 | — |
| 7 | `gpt-6-astra__t227_c000` | c227 | no · qualification failed (W1 D0 L2) | 0-0-0 | 0 | 0.0 | — |
| 8 | `gpt-6-astra__t228_c000` | c228 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 9 | `gpt-6-astra__t230_c000` | c230 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 10 | `gpt-6-astra__t233_c000` | c233 | no · qualification failed (W1 D0 L2) | 0-0-0 | 0 | 0.0 | — |

### Group 3 — winner `gpt-6-astra__t244_c000`

50 simulated games, 125 forfeit games.

| rank | bot | slot | eligible | W-L-D (simulated) | forfeit W | points | Elo |
|--:|---|---|:-:|---|--:|--:|--:|
| 1 | `gpt-6-astra__t244_c000` | c244 | yes | 18-1-1 | 25 | 43.5 | 1394.8 |
| 2 | `gpt-6-astra__t238_c000` | c238 | yes | 14-6-0 | 25 | 39.0 | 1156.7 |
| 3 | `gpt-6-astra__t243_c000` | c243 | yes | 8-12-0 | 25 | 33.0 | 908.7 |
| 4 | `gpt-6-astra__t247_c000` | c247 | yes | 7-13-0 | 25 | 32.0 | 868.9 |
| 5 | `gpt-6-astra__t245_c000` | c245 | yes | 2-17-1 | 25 | 27.5 | 670.9 |
| 6 | `gpt-6-astra__t237_c000` | c237 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 7 | `gpt-6-astra__t239_c000` | c239 | no · qualification failed (W0 D1 L2) | 0-0-0 | 0 | 0.0 | — |
| 8 | `gpt-6-astra__t241_c000` | c241 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 9 | `gpt-6-astra__t242_c000` | c242 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 10 | `gpt-6-astra__t246_c000` | c246 | no · qualification failed (W1 D0 L2) | 0-0-0 | 0 | 0.0 | — |

## grok-4.20-reasoning

Pool run `g0` (slots 000-049), harness `dedc97f`, tournament config md5 `9dd458946f007a22c46de945b9891820`.

### Group 1 — winner `grok-4.20-reasoning__t01_c000`

0 simulated games, 0 forfeit games.

| rank | bot | slot | eligible | W-L-D (simulated) | forfeit W | points | Elo |
|--:|---|---|:-:|---|--:|--:|--:|
| 1 | `grok-4.20-reasoning__t01_c000` | c001 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 2 | `grok-4.20-reasoning__t03_c000` | c003 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 3 | `grok-4.20-reasoning__t04_c000` | c004 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 4 | `grok-4.20-reasoning__t05_c000` | c005 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 5 | `grok-4.20-reasoning__t06_c000` | c006 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 6 | `grok-4.20-reasoning__t07_c000` | c007 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 7 | `grok-4.20-reasoning__t11_c000` | c011 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 8 | `grok-4.20-reasoning__t13_c000` | c013 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 9 | `grok-4.20-reasoning__t14_c000` | c014 | no · qualification failed (W0 D1 L2) | 0-0-0 | 0 | 0.0 | — |
| 10 | `grok-4.20-reasoning__t15_c000` | c015 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |

### Group 2 — winner `grok-4.20-reasoning__t16_c000`

0 simulated games, 0 forfeit games.

| rank | bot | slot | eligible | W-L-D (simulated) | forfeit W | points | Elo |
|--:|---|---|:-:|---|--:|--:|--:|
| 1 | `grok-4.20-reasoning__t16_c000` | c016 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 2 | `grok-4.20-reasoning__t17_c000` | c017 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 3 | `grok-4.20-reasoning__t18_c000` | c018 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 4 | `grok-4.20-reasoning__t19_c000` | c019 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 5 | `grok-4.20-reasoning__t21_c000` | c021 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 6 | `grok-4.20-reasoning__t22_c000` | c022 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 7 | `grok-4.20-reasoning__t25_c000` | c025 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 8 | `grok-4.20-reasoning__t26_c000` | c026 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 9 | `grok-4.20-reasoning__t29_c000` | c029 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 10 | `grok-4.20-reasoning__t31_c000` | c031 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |

### Group 3 — winner `grok-4.20-reasoning__t38_c000`

0 simulated games, 45 forfeit games.

| rank | bot | slot | eligible | W-L-D (simulated) | forfeit W | points | Elo |
|--:|---|---|:-:|---|--:|--:|--:|
| 1 | `grok-4.20-reasoning__t38_c000` | c038 | yes | 0-0-0 | 45 | 45.0 | — |
| 2 | `grok-4.20-reasoning__t32_c000` | c032 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 3 | `grok-4.20-reasoning__t37_c000` | c037 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 4 | `grok-4.20-reasoning__t40_c000` | c040 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 5 | `grok-4.20-reasoning__t41_c000` | c041 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 6 | `grok-4.20-reasoning__t42_c000` | c042 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 7 | `grok-4.20-reasoning__t43_c000` | c043 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 8 | `grok-4.20-reasoning__t45_c000` | c045 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 9 | `grok-4.20-reasoning__t46_c000` | c046 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 10 | `grok-4.20-reasoning__t49_c000` | c049 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |

## grok-4.5-high

Pool run `g2` (slots 100-149), harness `dedc97f`, tournament config md5 `9dd458946f007a22c46de945b9891820`.

### Group 1 — winner `grok-4.5-high__t115_c000`

0 simulated games, 45 forfeit games.

| rank | bot | slot | eligible | W-L-D (simulated) | forfeit W | points | Elo |
|--:|---|---|:-:|---|--:|--:|--:|
| 1 | `grok-4.5-high__t115_c000` | c115 | yes | 0-0-0 | 45 | 45.0 | — |
| 2 | `grok-4.5-high__t101_c000` | c101 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 3 | `grok-4.5-high__t105_c000` | c105 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 4 | `grok-4.5-high__t106_c000` | c106 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 5 | `grok-4.5-high__t107_c000` | c107 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 6 | `grok-4.5-high__t108_c000` | c108 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 7 | `grok-4.5-high__t110_c000` | c110 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 8 | `grok-4.5-high__t113_c000` | c113 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 9 | `grok-4.5-high__t114_c000` | c114 | no · qualification failed (W1 D0 L2) | 0-0-0 | 0 | 0.0 | — |
| 10 | `grok-4.5-high__t116_c000` | c116 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |

### Group 2 — winner `grok-4.5-high__t117_c000`

0 simulated games, 0 forfeit games.

| rank | bot | slot | eligible | W-L-D (simulated) | forfeit W | points | Elo |
|--:|---|---|:-:|---|--:|--:|--:|
| 1 | `grok-4.5-high__t117_c000` | c117 | no · qualification failed (W0 D1 L2) | 0-0-0 | 0 | 0.0 | — |
| 2 | `grok-4.5-high__t118_c000` | c118 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 3 | `grok-4.5-high__t119_c000` | c119 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 4 | `grok-4.5-high__t122_c000` | c122 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 5 | `grok-4.5-high__t123_c000` | c123 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 6 | `grok-4.5-high__t127_c000` | c127 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 7 | `grok-4.5-high__t128_c000` | c128 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 8 | `grok-4.5-high__t129_c000` | c129 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 9 | `grok-4.5-high__t131_c000` | c131 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 10 | `grok-4.5-high__t132_c000` | c132 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |

### Group 3 — winner `grok-4.5-high__t133_c000`

0 simulated games, 0 forfeit games.

| rank | bot | slot | eligible | W-L-D (simulated) | forfeit W | points | Elo |
|--:|---|---|:-:|---|--:|--:|--:|
| 1 | `grok-4.5-high__t133_c000` | c133 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 2 | `grok-4.5-high__t136_c000` | c136 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 3 | `grok-4.5-high__t137_c000` | c137 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 4 | `grok-4.5-high__t138_c000` | c138 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 5 | `grok-4.5-high__t139_c000` | c139 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 6 | `grok-4.5-high__t142_c000` | c142 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 7 | `grok-4.5-high__t145_c000` | c145 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 8 | `grok-4.5-high__t146_c000` | c146 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 9 | `grok-4.5-high__t148_c000` | c148 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 10 | `grok-4.5-high__t149_c000` | c149 | no · qualification failed (W1 D0 L2) | 0-0-0 | 0 | 0.0 | — |

## grok-4.6-high

Pool run `g4` (slots 200-249), harness `6d87c64`, tournament config md5 `9dd458946f007a22c46de945b9891820`.

### Group 1 — winner `grok-4.6-high__t213_c000`

140 simulated games, 80 forfeit games.

| rank | bot | slot | eligible | W-L-D (simulated) | forfeit W | points | Elo |
|--:|---|---|:-:|---|--:|--:|--:|
| 1 | `grok-4.6-high__t213_c000` | c213 | yes | 33-2-0 | 10 | 43.0 | 1456.3 |
| 2 | `grok-4.6-high__t209_c000` | c209 | yes | 22-8-5 | 10 | 34.5 | 1151.9 |
| 3 | `grok-4.6-high__t203_c000` | c203 | yes | 15-11-9 | 10 | 29.5 | 1031.6 |
| 4 | `grok-4.6-high__t200_c000` | c200 | yes | 18-16-1 | 10 | 28.5 | 1009.2 |
| 5 | `grok-4.6-high__t201_c000` | c201 | yes | 14-17-4 | 10 | 26.0 | 954.0 |
| 6 | `grok-4.6-high__t216_c000` | c216 | yes | 12-22-1 | 10 | 22.5 | 876.1 |
| 7 | `grok-4.6-high__t204_c000` | c204 | yes | 9-22-4 | 10 | 21.0 | 841.3 |
| 8 | `grok-4.6-high__t202_c000` | c202 | yes | 4-29-2 | 10 | 15.0 | 679.6 |
| 9 | `grok-4.6-high__t205_c000` | c205 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 10 | `grok-4.6-high__t215_c000` | c215 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |

### Group 2 — winner `grok-4.6-high__t219_c000`

105 simulated games, 105 forfeit games.

| rank | bot | slot | eligible | W-L-D (simulated) | forfeit W | points | Elo |
|--:|---|---|:-:|---|--:|--:|--:|
| 1 | `grok-4.6-high__t219_c000` | c219 | yes | 20-9-1 | 15 | 35.5 | 1131.4 |
| 2 | `grok-4.6-high__t229_c000` | c229 | yes | 19-11-0 | 15 | 34.0 | 1096.0 |
| 3 | `grok-4.6-high__t221_c000` | c221 | yes | 18-10-2 | 15 | 34.0 | 1096.0 |
| 4 | `grok-4.6-high__t223_c000` | c223 | yes | 17-13-0 | 15 | 32.0 | 1050.4 |
| 5 | `grok-4.6-high__t226_c000` | c226 | yes | 15-12-3 | 15 | 31.5 | 1039.1 |
| 6 | `grok-4.6-high__t227_c000` | c227 | yes | 7-22-1 | 15 | 22.5 | 823.1 |
| 7 | `grok-4.6-high__t233_c000` | c233 | yes | 5-24-1 | 15 | 20.5 | 764.0 |
| 8 | `grok-4.6-high__t225_c000` | c225 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 9 | `grok-4.6-high__t231_c000` | c231 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 10 | `grok-4.6-high__t232_c000` | c232 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |

### Group 3 — winner `grok-4.6-high__t240_c000`

105 simulated games, 105 forfeit games.

| rank | bot | slot | eligible | W-L-D (simulated) | forfeit W | points | Elo |
|--:|---|---|:-:|---|--:|--:|--:|
| 1 | `grok-4.6-high__t240_c000` | c240 | yes | 27-3-0 | 15 | 42.0 | 1357.6 |
| 2 | `grok-4.6-high__t243_c000` | c243 | yes | 19-11-0 | 15 | 34.0 | 1100.7 |
| 3 | `grok-4.6-high__t239_c000` | c239 | yes | 18-12-0 | 15 | 33.0 | 1074.9 |
| 4 | `grok-4.6-high__t248_c000` | c248 | yes | 14-16-0 | 15 | 29.0 | 975.1 |
| 5 | `grok-4.6-high__t238_c000` | c238 | yes | 13-17-0 | 15 | 28.0 | 950.1 |
| 6 | `grok-4.6-high__t234_c000` | c234 | yes | 11-19-0 | 15 | 26.0 | 899.1 |
| 7 | `grok-4.6-high__t236_c000` | c236 | yes | 3-27-0 | 15 | 18.0 | 642.6 |
| 8 | `grok-4.6-high__t237_c000` | c237 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 9 | `grok-4.6-high__t242_c000` | c242 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 10 | `grok-4.6-high__t246_c000` | c246 | no · qualification failed (W1 D1 L1) | 0-0-0 | 0 | 0.0 | — |

## kimi-k3-high

Pool run `g0` (slots 000-049), harness `6d87c64`, tournament config md5 `9dd458946f007a22c46de945b9891820`.

### Group 1 — winner `kimi-k3-high__t07_c000`

5 simulated games, 80 forfeit games.

| rank | bot | slot | eligible | W-L-D (simulated) | forfeit W | points | Elo |
|--:|---|---|:-:|---|--:|--:|--:|
| 1 | `kimi-k3-high__t07_c000` | c007 | yes | 1-0-4 | 40 | 43.0 | 1034.5 |
| 2 | `kimi-k3-high__t16_c000` | c016 | yes | 0-1-4 | 40 | 42.0 | 965.5 |
| 3 | `kimi-k3-high__t01_c000` | c001 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 4 | `kimi-k3-high__t05_c000` | c005 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 5 | `kimi-k3-high__t08_c000` | c008 | no · qualification failed (W1 D0 L2) | 0-0-0 | 0 | 0.0 | — |
| 6 | `kimi-k3-high__t09_c000` | c009 | no · qualification failed (W0 D1 L2) | 0-0-0 | 0 | 0.0 | — |
| 7 | `kimi-k3-high__t13_c000` | c013 | no · qualification failed (W1 D0 L2) | 0-0-0 | 0 | 0.0 | — |
| 8 | `kimi-k3-high__t14_c000` | c014 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 9 | `kimi-k3-high__t15_c000` | c015 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 10 | `kimi-k3-high__t19_c000` | c019 | no · qualification failed (W0 D1 L2) | 0-0-0 | 0 | 0.0 | — |

### Group 2 — winner `kimi-k3-high__t23_c000`

15 simulated games, 105 forfeit games.

| rank | bot | slot | eligible | W-L-D (simulated) | forfeit W | points | Elo |
|--:|---|---|:-:|---|--:|--:|--:|
| 1 | `kimi-k3-high__t23_c000` | c023 | yes | 10-0-0 | 35 | 45.0 | 1504.3 |
| 2 | `kimi-k3-high__t20_c000` | c020 | yes | 3-6-1 | 35 | 38.5 | 817.8 |
| 3 | `kimi-k3-high__t22_c000` | c022 | yes | 1-8-1 | 35 | 36.5 | 677.9 |
| 4 | `kimi-k3-high__t21_c000` | c021 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 5 | `kimi-k3-high__t25_c000` | c025 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 6 | `kimi-k3-high__t26_c000` | c026 | no · qualification failed (W1 D0 L2) | 0-0-0 | 0 | 0.0 | — |
| 7 | `kimi-k3-high__t27_c000` | c027 | no · qualification failed (W1 D0 L2) | 0-0-0 | 0 | 0.0 | — |
| 8 | `kimi-k3-high__t32_c000` | c032 | no · qualification failed (W0 D2 L1) | 0-0-0 | 0 | 0.0 | — |
| 9 | `kimi-k3-high__t33_c000` | c033 | no · qualification failed (W0 D1 L2) | 0-0-0 | 0 | 0.0 | — |
| 10 | `kimi-k3-high__t34_c000` | c034 | no · qualification failed (W1 D0 L2) | 0-0-0 | 0 | 0.0 | — |

### Group 3 — winner `kimi-k3-high__t45_c000`

30 simulated games, 120 forfeit games.

| rank | bot | slot | eligible | W-L-D (simulated) | forfeit W | points | Elo |
|--:|---|---|:-:|---|--:|--:|--:|
| 1 | `kimi-k3-high__t45_c000` | c045 | yes | 12-3-0 | 30 | 42.0 | 1206.7 |
| 2 | `kimi-k3-high__t38_c000` | c038 | yes | 8-6-1 | 30 | 38.5 | 1051.5 |
| 3 | `kimi-k3-high__t37_c000` | c037 | yes | 8-7-0 | 30 | 38.0 | 1030.4 |
| 4 | `kimi-k3-high__t42_c000` | c042 | yes | 1-13-1 | 30 | 31.5 | 711.3 |
| 5 | `kimi-k3-high__t39_c000` | c039 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 6 | `kimi-k3-high__t43_c000` | c043 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 7 | `kimi-k3-high__t44_c000` | c044 | no · qualification failed (W1 D0 L2) | 0-0-0 | 0 | 0.0 | — |
| 8 | `kimi-k3-high__t46_c000` | c046 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 9 | `kimi-k3-high__t47_c000` | c047 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |
| 10 | `kimi-k3-high__t49_c000` | c049 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |

## qwen3.8-2.4t-a95b-thinking

Pool run `g3` (slots 150-199), harness `3c03d49`, tournament config md5 `9dd458946f007a22c46de945b9891820`.

### Group 1 — winner `qwen3.8-2.4t-a95b-thinking__t155_c000`

50 simulated games, 125 forfeit games.

| rank | bot | slot | eligible | W-L-D (simulated) | forfeit W | points | Elo |
|--:|---|---|:-:|---|--:|--:|--:|
| 1 | `qwen3.8-2.4t-a95b-thinking__t155_c000` | c155 | yes | 18-2-0 | 25 | 43.0 | 1313.2 |
| 2 | `qwen3.8-2.4t-a95b-thinking__t157_c000` | c157 | yes | 11-9-0 | 25 | 36.0 | 1024.9 |
| 3 | `qwen3.8-2.4t-a95b-thinking__t158_c000` | c158 | yes | 9-10-1 | 25 | 34.5 | 974.4 |
| 4 | `qwen3.8-2.4t-a95b-thinking__t152_c000` | c152 | yes | 7-12-1 | 25 | 32.5 | 907.3 |
| 5 | `qwen3.8-2.4t-a95b-thinking__t159_c000` | c159 | yes | 4-16-0 | 25 | 29.0 | 780.2 |
| 6 | `qwen3.8-2.4t-a95b-thinking__t151_c000` | c151 | no · qualification failed (W0 D2 L1) | 0-0-0 | 0 | 0.0 | — |
| 7 | `qwen3.8-2.4t-a95b-thinking__t153_c000` | c153 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 8 | `qwen3.8-2.4t-a95b-thinking__t154_c000` | c154 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 9 | `qwen3.8-2.4t-a95b-thinking__t162_c000` | c162 | no · qualification failed (W0 D1 L2) | 0-0-0 | 0 | 0.0 | — |
| 10 | `qwen3.8-2.4t-a95b-thinking__t163_c000` | c163 | no · qualification failed (W0 D1 L2) | 0-0-0 | 0 | 0.0 | — |

### Group 2 — winner `qwen3.8-2.4t-a95b-thinking__t164_c000`

140 simulated games, 80 forfeit games.

| rank | bot | slot | eligible | W-L-D (simulated) | forfeit W | points | Elo |
|--:|---|---|:-:|---|--:|--:|--:|
| 1 | `qwen3.8-2.4t-a95b-thinking__t164_c000` | c164 | yes | 28-6-1 | 10 | 38.5 | 1252.0 |
| 2 | `qwen3.8-2.4t-a95b-thinking__t167_c000` | c167 | yes | 25-8-2 | 10 | 36.0 | 1186.1 |
| 3 | `qwen3.8-2.4t-a95b-thinking__t178_c000` | c178 | yes | 23-11-1 | 10 | 33.5 | 1127.0 |
| 4 | `qwen3.8-2.4t-a95b-thinking__t179_c000` | c179 | yes | 14-19-2 | 10 | 25.0 | 946.4 |
| 5 | `qwen3.8-2.4t-a95b-thinking__t171_c000` | c171 | yes | 13-18-4 | 10 | 25.0 | 946.4 |
| 6 | `qwen3.8-2.4t-a95b-thinking__t165_c000` | c165 | yes | 13-22-0 | 10 | 23.0 | 903.9 |
| 7 | `qwen3.8-2.4t-a95b-thinking__t168_c000` | c168 | yes | 12-21-2 | 10 | 23.0 | 903.9 |
| 8 | `qwen3.8-2.4t-a95b-thinking__t173_c000` | c173 | yes | 5-28-2 | 10 | 16.0 | 734.3 |
| 9 | `qwen3.8-2.4t-a95b-thinking__t174_c000` | c174 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 10 | `qwen3.8-2.4t-a95b-thinking__t180_c000` | c180 | no · forfeit:controller | 0-0-0 | 0 | 0.0 | — |

### Group 3 — winner `qwen3.8-2.4t-a95b-thinking__t192_c000`

140 simulated games, 80 forfeit games.

| rank | bot | slot | eligible | W-L-D (simulated) | forfeit W | points | Elo |
|--:|---|---|:-:|---|--:|--:|--:|
| 1 | `qwen3.8-2.4t-a95b-thinking__t192_c000` | c192 | yes | 26-8-1 | 10 | 36.5 | 1191.2 |
| 2 | `qwen3.8-2.4t-a95b-thinking__t196_c000` | c196 | yes | 22-6-7 | 10 | 35.5 | 1167.7 |
| 3 | `qwen3.8-2.4t-a95b-thinking__t190_c000` | c190 | yes | 20-14-1 | 10 | 30.5 | 1061.2 |
| 4 | `qwen3.8-2.4t-a95b-thinking__t183_c000` | c183 | yes | 15-12-8 | 10 | 29.0 | 1031.1 |
| 5 | `qwen3.8-2.4t-a95b-thinking__t181_c000` | c181 | yes | 15-14-6 | 10 | 28.0 | 1011.1 |
| 6 | `qwen3.8-2.4t-a95b-thinking__t198_c000` | c198 | yes | 11-18-6 | 10 | 24.0 | 930.8 |
| 7 | `qwen3.8-2.4t-a95b-thinking__t187_c000` | c187 | yes | 8-26-1 | 10 | 18.5 | 809.6 |
| 8 | `qwen3.8-2.4t-a95b-thinking__t182_c000` | c182 | yes | 8-27-0 | 10 | 18.0 | 797.3 |
| 9 | `qwen3.8-2.4t-a95b-thinking__t185_c000` | c185 | no · qualification failed (W0 D0 L3) | 0-0-0 | 0 | 0.0 | — |
| 10 | `qwen3.8-2.4t-a95b-thinking__t188_c000` | c188 | no · qualification failed (W0 D2 L1) | 0-0-0 | 0 | 0.0 | — |
