# Sampling harness · stage 1 Elo leaderboards per model

Generated 2026-09-25 18:18 UTC. For each model, Elo is fitted over every SH-250 pool game between any two of its 30 selected bots (all three groups together, since all 30 come from one pool run and the pool played every eligible pairing in that run). Same estimator as the existing tournaments: Bradley-Terry MAP, draws 0.5, prior N(1000, 800²), centred at 1000 within each model. Ratings are comparable within a model only, not across models.

Bots the pool did not admit (failed build, validation or the qualification round) have no games and appear at the bottom without a rating. Group winners from `sampling_stage1_results.md` are marked ★.
Totals: 13125 pool games across the 21 models.


## claude-fable-5-1-high

Pool run `g2`, 1265 games among 23 rated bots.

| rank | bot | group | slot | W-L-D | games | Elo |
|--:|---|:-:|---|---|--:|--:|
| 1 | `claude-fable-5-1-high__t128_c000` ★ | 2 | c128 | 92-17-1 | 110 | 1368.7 |
| 2 | `claude-fable-5-1-high__t115_c000` ★ | 1 | c115 | 91-17-2 | 110 | 1362.6 |
| 3 | `claude-fable-5-1-high__t111_c000` | 1 | c111 | 89-20-1 | 110 | 1333.1 |
| 4 | `claude-fable-5-1-high__t130_c000` | 2 | c130 | 86-22-2 | 110 | 1305.5 |
| 5 | `claude-fable-5-1-high__t120_c000` | 2 | c120 | 74-31-5 | 110 | 1203.2 |
| 6 | `claude-fable-5-1-high__t117_c000` | 2 | c117 | 74-35-1 | 110 | 1185.3 |
| 7 | `claude-fable-5-1-high__t148_c000` | 3 | c148 | 68-34-8 | 110 | 1163.6 |
| 8 | `claude-fable-5-1-high__t144_c000` ★ | 3 | c144 | 64-38-8 | 110 | 1129.7 |
| 9 | `claude-fable-5-1-high__t104_c000` | 1 | c104 | 65-42-3 | 110 | 1117.2 |
| 10 | `claude-fable-5-1-high__t106_c000` | 1 | c106 | 61-47-2 | 110 | 1080.2 |
| 11 | `claude-fable-5-1-high__t100_c000` | 1 | c100 | 55-54-1 | 110 | 1027.4 |
| 12 | `claude-fable-5-1-high__t132_c000` | 2 | c132 | 54-53-3 | 110 | 1027.4 |
| 13 | `claude-fable-5-1-high__t146_c000` | 3 | c146 | 49-54-7 | 110 | 1003.0 |
| 14 | `claude-fable-5-1-high__t127_c000` | 2 | c127 | 44-58-8 | 110 | 965.9 |
| 15 | `claude-fable-5-1-high__t105_c000` | 1 | c105 | 47-62-1 | 110 | 961.8 |
| 16 | `claude-fable-5-1-high__t125_c000` | 2 | c125 | 45-65-0 | 110 | 940.7 |
| 17 | `claude-fable-5-1-high__t113_c000` | 1 | c113 | 32-69-9 | 110 | 865.6 |
| 18 | `claude-fable-5-1-high__t137_c000` | 3 | c137 | 35-73-2 | 110 | 861.0 |
| 19 | `claude-fable-5-1-high__t126_c000` | 2 | c126 | 34-75-1 | 110 | 846.8 |
| 20 | `claude-fable-5-1-high__t114_c000` | 1 | c114 | 28-75-7 | 110 | 817.3 |
| 21 | `claude-fable-5-1-high__t145_c000` | 3 | c145 | 29-77-4 | 110 | 812.2 |
| 22 | `claude-fable-5-1-high__t142_c000` | 3 | c142 | 10-100-0 | 110 | 497.9 |
| 23 | `claude-fable-5-1-high__t138_c000` | 3 | c138 | 1-109-0 | 110 | 124.3 |
| — | `claude-fable-5-1-high__t107_c000` | 1 | c107 | no games | 0 | — (forfeit:controller) |
| — | `claude-fable-5-1-high__t109_c000` | 1 | c109 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `claude-fable-5-1-high__t118_c000` | 2 | c118 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `claude-fable-5-1-high__t122_c000` | 2 | c122 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `claude-fable-5-1-high__t135_c000` | 3 | c135 | no games | 0 | — (forfeit:controller) |
| — | `claude-fable-5-1-high__t136_c000` | 3 | c136 | no games | 0 | — (qualification failed (W0 D2 L1)) |
| — | `claude-fable-5-1-high__t147_c000` | 3 | c147 | no games | 0 | — (qualification failed (W0 D0 L3)) |

## claude-fable-5-high

Pool run `g2`, 1625 games among 26 rated bots.

| rank | bot | group | slot | W-L-D | games | Elo |
|--:|---|:-:|---|---|--:|--:|
| 1 | `claude-fable-5-high__t122_c000` ★ | 2 | c122 | 92-21-12 | 125 | 1241.5 |
| 2 | `claude-fable-5-high__t120_c000` | 2 | c120 | 88-29-8 | 125 | 1194.1 |
| 3 | `claude-fable-5-high__t101_c000` | 1 | c101 | 91-34-0 | 125 | 1186.6 |
| 4 | `claude-fable-5-high__t107_c000` ★ | 1 | c107 | 88-34-3 | 125 | 1175.7 |
| 5 | `claude-fable-5-high__t130_c000` | 2 | c130 | 85-34-6 | 125 | 1164.9 |
| 6 | `claude-fable-5-high__t140_c000` ★ | 3 | c140 | 83-32-10 | 125 | 1164.9 |
| 7 | `claude-fable-5-high__t124_c000` | 2 | c124 | 80-39-6 | 125 | 1130.5 |
| 8 | `claude-fable-5-high__t104_c000` | 1 | c104 | 71-45-9 | 125 | 1081.7 |
| 9 | `claude-fable-5-high__t103_c000` | 1 | c103 | 63-38-24 | 125 | 1078.5 |
| 10 | `claude-fable-5-high__t133_c000` | 2 | c133 | 57-46-22 | 125 | 1034.8 |
| 11 | `claude-fable-5-high__t117_c000` | 1 | c117 | 58-48-19 | 125 | 1031.7 |
| 12 | `claude-fable-5-high__t118_c000` | 2 | c118 | 59-56-10 | 125 | 1010.2 |
| 13 | `claude-fable-5-high__t143_c000` | 3 | c143 | 58-62-5 | 125 | 988.7 |
| 14 | `claude-fable-5-high__t146_c000` | 3 | c146 | 45-50-30 | 125 | 985.7 |
| 15 | `claude-fable-5-high__t125_c000` | 2 | c125 | 57-68-0 | 125 | 967.2 |
| 16 | `claude-fable-5-high__t142_c000` | 3 | c142 | 56-69-0 | 125 | 961.0 |
| 17 | `claude-fable-5-high__t100_c000` | 1 | c100 | 48-68-9 | 125 | 939.2 |
| 18 | `claude-fable-5-high__t102_c000` | 1 | c102 | 49-71-5 | 125 | 932.9 |
| 19 | `claude-fable-5-high__t139_c000` | 3 | c139 | 43-65-17 | 125 | 932.9 |
| 20 | `claude-fable-5-high__t148_c000` | 3 | c148 | 47-78-0 | 125 | 904.2 |
| 21 | `claude-fable-5-high__t111_c000` | 1 | c111 | 32-64-29 | 125 | 901.0 |
| 22 | `claude-fable-5-high__t149_c000` | 3 | c149 | 45-78-2 | 125 | 897.7 |
| 23 | `claude-fable-5-high__t137_c000` | 3 | c137 | 24-80-21 | 125 | 818.3 |
| 24 | `claude-fable-5-high__t144_c000` | 3 | c144 | 32-92-1 | 125 | 803.3 |
| 25 | `claude-fable-5-high__t147_c000` | 3 | c147 | 31-92-2 | 125 | 799.5 |
| 26 | `claude-fable-5-high__t132_c000` | 2 | c132 | 13-102-10 | 125 | 673.2 |
| — | `claude-fable-5-high__t108_c000` | 1 | c108 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `claude-fable-5-high__t114_c000` | 1 | c114 | no games | 0 | — (qualification failed (W1 D0 L2)) |
| — | `claude-fable-5-high__t119_c000` | 2 | c119 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `claude-fable-5-high__t128_c000` | 2 | c128 | no games | 0 | — (qualification failed (W0 D2 L1)) |

## claude-opus-4-8-high

Pool run `g0`, 765 games among 18 rated bots.

| rank | bot | group | slot | W-L-D | games | Elo |
|--:|---|:-:|---|---|--:|--:|
| 1 | `claude-opus-4-8-high__t33_c000` ★ | 3 | c033 | 65-17-3 | 85 | 1225.1 |
| 2 | `claude-opus-4-8-high__t40_c000` | 3 | c040 | 61-24-0 | 85 | 1166.3 |
| 3 | `claude-opus-4-8-high__t44_c000` | 3 | c044 | 59-26-0 | 85 | 1146.7 |
| 4 | `claude-opus-4-8-high__t10_c000` ★ | 1 | c010 | 52-33-0 | 85 | 1082.4 |
| 5 | `claude-opus-4-8-high__t30_c000` | 2 | c030 | 47-36-2 | 85 | 1047.6 |
| 6 | `claude-opus-4-8-high__t09_c000` | 1 | c009 | 44-38-3 | 85 | 1026.3 |
| 7 | `claude-opus-4-8-high__t17_c000` ★ | 2 | c017 | 45-40-0 | 85 | 1022.0 |
| 8 | `claude-opus-4-8-high__t19_c000` | 2 | c019 | 44-41-0 | 85 | 1013.5 |
| 9 | `claude-opus-4-8-high__t46_c000` | 3 | c046 | 43-41-1 | 85 | 1009.3 |
| 10 | `claude-opus-4-8-high__t14_c000` | 1 | c014 | 43-42-0 | 85 | 1005.1 |
| 11 | `claude-opus-4-8-high__t47_c000` | 3 | c047 | 42-43-0 | 85 | 996.6 |
| 12 | `claude-opus-4-8-high__t07_c000` | 1 | c007 | 41-44-0 | 85 | 988.1 |
| 13 | `claude-opus-4-8-high__t29_c000` | 2 | c029 | 39-46-0 | 85 | 971.1 |
| 14 | `claude-opus-4-8-high__t45_c000` | 3 | c045 | 38-47-0 | 85 | 962.5 |
| 15 | `claude-opus-4-8-high__t24_c000` | 2 | c024 | 36-49-0 | 85 | 945.3 |
| 16 | `claude-opus-4-8-high__t26_c000` | 2 | c026 | 22-63-0 | 85 | 813.8 |
| 17 | `claude-opus-4-8-high__t31_c000` | 2 | c031 | 21-64-0 | 85 | 803.1 |
| 18 | `claude-opus-4-8-high__t25_c000` | 2 | c025 | 18-66-1 | 85 | 775.1 |
| — | `claude-opus-4-8-high__t00_c000` | 1 | c000 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `claude-opus-4-8-high__t02_c000` | 1 | c002 | no games | 0 | — (qualification failed (W1 D0 L2)) |
| — | `claude-opus-4-8-high__t03_c000` | 1 | c003 | no games | 0 | — (qualification failed (W1 D1 L1)) |
| — | `claude-opus-4-8-high__t04_c000` | 1 | c004 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `claude-opus-4-8-high__t05_c000` | 1 | c005 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `claude-opus-4-8-high__t13_c000` | 1 | c013 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `claude-opus-4-8-high__t20_c000` | 2 | c020 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `claude-opus-4-8-high__t21_c000` | 2 | c021 | no games | 0 | — (qualification failed (W0 D2 L1)) |
| — | `claude-opus-4-8-high__t35_c000` | 3 | c035 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `claude-opus-4-8-high__t37_c000` | 3 | c037 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `claude-opus-4-8-high__t41_c000` | 3 | c041 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `claude-opus-4-8-high__t43_c000` | 3 | c043 | no games | 0 | — (qualification failed (W0 D0 L3)) |

## claude-sonnet-5-high

Pool run `g4`, 275 games among 11 rated bots.

| rank | bot | group | slot | W-L-D | games | Elo |
|--:|---|:-:|---|---|--:|--:|
| 1 | `claude-sonnet-5-high__t236_c000` | 3 | c236 | 34-13-3 | 50 | 1147.9 |
| 2 | `claude-sonnet-5-high__t220_c000` | 2 | c220 | 29-20-1 | 50 | 1061.9 |
| 3 | `claude-sonnet-5-high__t231_c000` ★ | 2 | c231 | 29-21-0 | 50 | 1055.1 |
| 4 | `claude-sonnet-5-high__t211_c000` | 1 | c211 | 28-22-0 | 50 | 1041.6 |
| 5 | `claude-sonnet-5-high__t232_c000` ★ | 3 | c232 | 28-22-0 | 50 | 1041.6 |
| 6 | `claude-sonnet-5-high__t206_c000` | 1 | c206 | 24-26-0 | 50 | 988.3 |
| 7 | `claude-sonnet-5-high__t215_c000` ★ | 1 | c215 | 24-26-0 | 50 | 988.3 |
| 8 | `claude-sonnet-5-high__t213_c000` | 1 | c213 | 23-26-1 | 50 | 981.6 |
| 9 | `claude-sonnet-5-high__t204_c000` | 1 | c204 | 22-28-0 | 50 | 961.5 |
| 10 | `claude-sonnet-5-high__t214_c000` | 1 | c214 | 21-28-1 | 50 | 954.7 |
| 11 | `claude-sonnet-5-high__t203_c000` | 1 | c203 | 10-40-0 | 50 | 777.4 |
| — | `claude-sonnet-5-high__t201_c000` | 1 | c201 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `claude-sonnet-5-high__t209_c000` | 1 | c209 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `claude-sonnet-5-high__t210_c000` | 1 | c210 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `claude-sonnet-5-high__t217_c000` | 2 | c217 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `claude-sonnet-5-high__t218_c000` | 2 | c218 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `claude-sonnet-5-high__t219_c000` | 2 | c219 | no games | 0 | — (qualification failed (W0 D1 L2)) |
| — | `claude-sonnet-5-high__t221_c000` | 2 | c221 | no games | 0 | — (qualification failed (W1 D0 L2)) |
| — | `claude-sonnet-5-high__t224_c000` | 2 | c224 | no games | 0 | — (qualification failed (W1 D0 L2)) |
| — | `claude-sonnet-5-high__t225_c000` | 2 | c225 | no games | 0 | — (qualification failed (W1 D0 L2)) |
| — | `claude-sonnet-5-high__t228_c000` | 2 | c228 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `claude-sonnet-5-high__t229_c000` | 2 | c229 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `claude-sonnet-5-high__t235_c000` | 3 | c235 | no games | 0 | — (qualification failed (W1 D0 L2)) |
| — | `claude-sonnet-5-high__t238_c000` | 3 | c238 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `claude-sonnet-5-high__t241_c000` | 3 | c241 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `claude-sonnet-5-high__t243_c000` | 3 | c243 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `claude-sonnet-5-high__t244_c000` | 3 | c244 | no games | 0 | — (forfeit:controller) |
| — | `claude-sonnet-5-high__t245_c000` | 3 | c245 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `claude-sonnet-5-high__t246_c000` | 3 | c246 | no games | 0 | — (forfeit:controller) |
| — | `claude-sonnet-5-high__t247_c000` | 3 | c247 | no games | 0 | — (qualification failed (W0 D0 L3)) |

## deepseek-v4-pro-thinking

Pool run `g1`, 15 games among 3 rated bots.

| rank | bot | group | slot | W-L-D | games | Elo |
|--:|---|:-:|---|---|--:|--:|
| 1 | `deepseek-v4-pro-thinking__t56_c000` ★ | 1 | c056 | 10-0-0 | 10 | 1498.8 |
| 2 | `deepseek-v4-pro-thinking__t83_c000` ★ | 2 | c083 | 3-7-0 | 10 | 784.3 |
| 3 | `deepseek-v4-pro-thinking__t85_c000` ★ | 3 | c085 | 2-8-0 | 10 | 717.0 |
| — | `deepseek-v4-pro-thinking__t50_c000` | 1 | c050 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `deepseek-v4-pro-thinking__t51_c000` | 1 | c051 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `deepseek-v4-pro-thinking__t53_c000` | 1 | c053 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `deepseek-v4-pro-thinking__t54_c000` | 1 | c054 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `deepseek-v4-pro-thinking__t60_c000` | 1 | c060 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `deepseek-v4-pro-thinking__t61_c000` | 1 | c061 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `deepseek-v4-pro-thinking__t64_c000` | 1 | c064 | no games | 0 | — (forfeit:controller) |
| — | `deepseek-v4-pro-thinking__t65_c000` | 1 | c065 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `deepseek-v4-pro-thinking__t67_c000` | 1 | c067 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `deepseek-v4-pro-thinking__t68_c000` | 2 | c068 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `deepseek-v4-pro-thinking__t69_c000` | 2 | c069 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `deepseek-v4-pro-thinking__t71_c000` | 2 | c071 | no games | 0 | — (forfeit:controller) |
| — | `deepseek-v4-pro-thinking__t73_c000` | 2 | c073 | no games | 0 | — (qualification failed (W1 D0 L2)) |
| — | `deepseek-v4-pro-thinking__t74_c000` | 2 | c074 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `deepseek-v4-pro-thinking__t77_c000` | 2 | c077 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `deepseek-v4-pro-thinking__t78_c000` | 2 | c078 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `deepseek-v4-pro-thinking__t80_c000` | 2 | c080 | no games | 0 | — (qualification failed (W1 D0 L2)) |
| — | `deepseek-v4-pro-thinking__t81_c000` | 2 | c081 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `deepseek-v4-pro-thinking__t87_c000` | 3 | c087 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `deepseek-v4-pro-thinking__t89_c000` | 3 | c089 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `deepseek-v4-pro-thinking__t90_c000` | 3 | c090 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `deepseek-v4-pro-thinking__t91_c000` | 3 | c091 | no games | 0 | — (forfeit:controller) |
| — | `deepseek-v4-pro-thinking__t92_c000` | 3 | c092 | no games | 0 | — (forfeit:controller) |
| — | `deepseek-v4-pro-thinking__t93_c000` | 3 | c093 | no games | 0 | — (forfeit:controller) |
| — | `deepseek-v4-pro-thinking__t97_c000` | 3 | c097 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `deepseek-v4-pro-thinking__t98_c000` | 3 | c098 | no games | 0 | — (forfeit:controller) |
| — | `deepseek-v4-pro-thinking__t99_c000` | 3 | c099 | no games | 0 | — (qualification failed (W0 D0 L3)) |

## gemini-3-1-pro-high

Pool run `g3`, 600 games among 16 rated bots.

| rank | bot | group | slot | W-L-D | games | Elo |
|--:|---|:-:|---|---|--:|--:|
| 1 | `gemini-3-1-pro-high__t192_c000` ★ | 3 | c192 | 59-14-2 | 75 | 1241.8 |
| 2 | `gemini-3-1-pro-high__t158_c000` | 1 | c158 | 55-18-2 | 75 | 1190.4 |
| 3 | `gemini-3-1-pro-high__t155_c000` ★ | 1 | c155 | 50-22-3 | 75 | 1138.8 |
| 4 | `gemini-3-1-pro-high__t167_c000` ★ | 2 | c167 | 46-28-1 | 75 | 1086.4 |
| 5 | `gemini-3-1-pro-high__t188_c000` | 3 | c188 | 44-29-2 | 75 | 1071.3 |
| 6 | `gemini-3-1-pro-high__t173_c000` | 2 | c173 | 42-33-0 | 75 | 1041.7 |
| 7 | `gemini-3-1-pro-high__t196_c000` | 3 | c196 | 39-35-1 | 75 | 1017.5 |
| 8 | `gemini-3-1-pro-high__t174_c000` | 2 | c174 | 37-37-1 | 75 | 998.2 |
| 9 | `gemini-3-1-pro-high__t189_c000` | 3 | c189 | 34-41-0 | 75 | 964.6 |
| 10 | `gemini-3-1-pro-high__t199_c000` | 3 | c199 | 32-43-0 | 75 | 945.2 |
| 11 | `gemini-3-1-pro-high__t175_c000` | 2 | c175 | 31-43-1 | 75 | 940.3 |
| 12 | `gemini-3-1-pro-high__t183_c000` | 2 | c183 | 30-45-0 | 75 | 925.6 |
| 13 | `gemini-3-1-pro-high__t151_c000` | 1 | c151 | 26-48-1 | 75 | 890.4 |
| 14 | `gemini-3-1-pro-high__t179_c000` | 2 | c179 | 26-49-0 | 75 | 885.2 |
| 15 | `gemini-3-1-pro-high__t193_c000` | 3 | c193 | 21-52-2 | 75 | 842.6 |
| 16 | `gemini-3-1-pro-high__t197_c000` | 3 | c197 | 20-55-0 | 75 | 820.1 |
| — | `gemini-3-1-pro-high__t150_c000` | 1 | c150 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `gemini-3-1-pro-high__t153_c000` | 1 | c153 | no games | 0 | — (forfeit:controller) |
| — | `gemini-3-1-pro-high__t156_c000` | 1 | c156 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `gemini-3-1-pro-high__t160_c000` | 1 | c160 | no games | 0 | — (forfeit:controller) |
| — | `gemini-3-1-pro-high__t161_c000` | 1 | c161 | no games | 0 | — (forfeit:controller) |
| — | `gemini-3-1-pro-high__t163_c000` | 1 | c163 | no games | 0 | — (forfeit:controller) |
| — | `gemini-3-1-pro-high__t165_c000` | 1 | c165 | no games | 0 | — (forfeit:controller) |
| — | `gemini-3-1-pro-high__t166_c000` | 2 | c166 | no games | 0 | — (qualification failed (W1 D0 L2)) |
| — | `gemini-3-1-pro-high__t168_c000` | 2 | c168 | no games | 0 | — (forfeit:controller) |
| — | `gemini-3-1-pro-high__t172_c000` | 2 | c172 | no games | 0 | — (forfeit:controller) |
| — | `gemini-3-1-pro-high__t181_c000` | 2 | c181 | no games | 0 | — (qualification failed (W0 D1 L2)) |
| — | `gemini-3-1-pro-high__t190_c000` | 3 | c190 | no games | 0 | — (forfeit:controller) |
| — | `gemini-3-1-pro-high__t194_c000` | 3 | c194 | no games | 0 | — (forfeit:controller) |
| — | `gemini-3-1-pro-high__t195_c000` | 3 | c195 | no games | 0 | — (forfeit:controller) |

## gemini-3-8-flash-high

Pool run `g2`, 1500 games among 25 rated bots.

| rank | bot | group | slot | W-L-D | games | Elo |
|--:|---|:-:|---|---|--:|--:|
| 1 | `gemini-3-8-flash-high__t122_c000` ★ | 2 | c122 | 86-31-3 | 120 | 1174.2 |
| 2 | `gemini-3-8-flash-high__t139_c000` ★ | 3 | c139 | 84-31-5 | 120 | 1167.1 |
| 3 | `gemini-3-8-flash-high__t128_c000` | 2 | c128 | 73-35-12 | 120 | 1116.4 |
| 4 | `gemini-3-8-flash-high__t131_c000` | 3 | c131 | 73-43-4 | 120 | 1091.0 |
| 5 | `gemini-3-8-flash-high__t113_c000` ★ | 1 | c113 | 72-46-2 | 120 | 1078.6 |
| 6 | `gemini-3-8-flash-high__t130_c000` | 3 | c130 | 70-44-6 | 120 | 1078.6 |
| 7 | `gemini-3-8-flash-high__t118_c000` | 2 | c118 | 65-52-3 | 120 | 1039.3 |
| 8 | `gemini-3-8-flash-high__t127_c000` | 2 | c127 | 66-53-1 | 120 | 1039.3 |
| 9 | `gemini-3-8-flash-high__t119_c000` | 2 | c119 | 66-54-0 | 120 | 1036.3 |
| 10 | `gemini-3-8-flash-high__t107_c000` | 1 | c107 | 63-54-3 | 120 | 1027.4 |
| 11 | `gemini-3-8-flash-high__t102_c000` | 1 | c102 | 62-56-2 | 120 | 1018.5 |
| 12 | `gemini-3-8-flash-high__t106_c000` | 1 | c106 | 60-54-6 | 120 | 1018.5 |
| 13 | `gemini-3-8-flash-high__t114_c000` | 2 | c114 | 59-54-7 | 120 | 1015.5 |
| 14 | `gemini-3-8-flash-high__t135_c000` | 3 | c135 | 53-63-4 | 120 | 971.1 |
| 15 | `gemini-3-8-flash-high__t100_c000` | 1 | c100 | 53-64-3 | 120 | 968.1 |
| 16 | `gemini-3-8-flash-high__t116_c000` | 2 | c116 | 49-60-11 | 120 | 968.1 |
| 17 | `gemini-3-8-flash-high__t145_c000` | 3 | c145 | 52-63-5 | 120 | 968.1 |
| 18 | `gemini-3-8-flash-high__t147_c000` | 3 | c147 | 54-65-1 | 120 | 968.1 |
| 19 | `gemini-3-8-flash-high__t123_c000` | 2 | c123 | 52-67-1 | 120 | 956.2 |
| 20 | `gemini-3-8-flash-high__t142_c000` | 3 | c142 | 49-66-5 | 120 | 950.2 |
| 21 | `gemini-3-8-flash-high__t137_c000` | 3 | c137 | 47-70-3 | 120 | 931.9 |
| 22 | `gemini-3-8-flash-high__t129_c000` | 2 | c129 | 46-70-4 | 120 | 928.9 |
| 23 | `gemini-3-8-flash-high__t125_c000` | 2 | c125 | 40-79-1 | 120 | 881.5 |
| 24 | `gemini-3-8-flash-high__t105_c000` | 1 | c105 | 33-78-9 | 120 | 861.6 |
| 25 | `gemini-3-8-flash-high__t108_c000` | 1 | c108 | 22-97-1 | 120 | 745.8 |
| — | `gemini-3-8-flash-high__t101_c000` | 1 | c101 | no games | 0 | — (qualification failed (W1 D0 L2)) |
| — | `gemini-3-8-flash-high__t104_c000` | 1 | c104 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `gemini-3-8-flash-high__t109_c000` | 1 | c109 | no games | 0 | — (forfeit:controller) |
| — | `gemini-3-8-flash-high__t136_c000` | 3 | c136 | no games | 0 | — (qualification failed (W1 D0 L2)) |
| — | `gemini-3-8-flash-high__t141_c000` | 3 | c141 | no games | 0 | — (forfeit:controller) |

## glm-5.2-high

Pool run `g1`, 180 games among 9 rated bots.

| rank | bot | group | slot | W-L-D | games | Elo |
|--:|---|:-:|---|---|--:|--:|
| 1 | `glm-5.2-high__t69_c000` ★ | 1 | c069 | 25-12-3 | 40 | 1111.1 |
| 2 | `glm-5.2-high__t99_c000` ★ | 3 | c099 | 26-13-1 | 40 | 1111.1 |
| 3 | `glm-5.2-high__t62_c000` | 1 | c062 | 23-17-0 | 40 | 1051.4 |
| 4 | `glm-5.2-high__t78_c000` ★ | 2 | c078 | 22-18-0 | 40 | 1034.9 |
| 5 | `glm-5.2-high__t51_c000` | 1 | c051 | 20-19-1 | 40 | 1010.2 |
| 6 | `glm-5.2-high__t58_c000` | 1 | c058 | 18-21-1 | 40 | 977.4 |
| 7 | `glm-5.2-high__t55_c000` | 1 | c055 | 18-22-0 | 40 | 969.1 |
| 8 | `glm-5.2-high__t84_c000` | 2 | c084 | 17-23-0 | 40 | 952.5 |
| 9 | `glm-5.2-high__t87_c000` | 3 | c087 | 8-32-0 | 40 | 782.3 |
| — | `glm-5.2-high__t52_c000` | 1 | c052 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `glm-5.2-high__t54_c000` | 1 | c054 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `glm-5.2-high__t59_c000` | 1 | c059 | no games | 0 | — (forfeit:controller) |
| — | `glm-5.2-high__t60_c000` | 1 | c060 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `glm-5.2-high__t67_c000` | 1 | c067 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `glm-5.2-high__t70_c000` | 2 | c070 | no games | 0 | — (qualification failed (W1 D1 L1)) |
| — | `glm-5.2-high__t74_c000` | 2 | c074 | no games | 0 | — (forfeit:controller) |
| — | `glm-5.2-high__t75_c000` | 2 | c075 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `glm-5.2-high__t76_c000` | 2 | c076 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `glm-5.2-high__t77_c000` | 2 | c077 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `glm-5.2-high__t79_c000` | 2 | c079 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `glm-5.2-high__t83_c000` | 2 | c083 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `glm-5.2-high__t85_c000` | 2 | c085 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `glm-5.2-high__t86_c000` | 3 | c086 | no games | 0 | — (forfeit:controller) |
| — | `glm-5.2-high__t89_c000` | 3 | c089 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `glm-5.2-high__t90_c000` | 3 | c090 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `glm-5.2-high__t92_c000` | 3 | c092 | no games | 0 | — (qualification failed (W0 D2 L1)) |
| — | `glm-5.2-high__t93_c000` | 3 | c093 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `glm-5.2-high__t94_c000` | 3 | c094 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `glm-5.2-high__t95_c000` | 3 | c095 | no games | 0 | — (forfeit:controller) |
| — | `glm-5.2-high__t98_c000` | 3 | c098 | no games | 0 | — (qualification failed (W1 D0 L2)) |

## glm-5.3-high

Pool run `g3`, 0 games among 0 rated bots.

| rank | bot | group | slot | W-L-D | games | Elo |
|--:|---|:-:|---|---|--:|--:|
| — | `glm-5.3-high__t150_c000` | 1 | c150 | no games | 0 | — (forfeit:controller) |
| — | `glm-5.3-high__t151_c000` | 1 | c151 | no games | 0 | — (forfeit:controller) |
| — | `glm-5.3-high__t152_c000` | 1 | c152 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `glm-5.3-high__t153_c000` | 1 | c153 | no games | 0 | — (forfeit:controller) |
| — | `glm-5.3-high__t155_c000` | 1 | c155 | no games | 0 | — (forfeit:controller) |
| — | `glm-5.3-high__t156_c000` | 1 | c156 | no games | 0 | — (forfeit:controller) |
| — | `glm-5.3-high__t158_c000` | 1 | c158 | no games | 0 | — (forfeit:controller) |
| — | `glm-5.3-high__t162_c000` | 1 | c162 | no games | 0 | — (forfeit:controller) |
| — | `glm-5.3-high__t163_c000` | 1 | c163 | no games | 0 | — (forfeit:controller) |
| — | `glm-5.3-high__t165_c000` | 1 | c165 | no games | 0 | — (forfeit:controller) |
| — | `glm-5.3-high__t166_c000` | 2 | c166 | no games | 0 | — (forfeit:controller) |
| — | `glm-5.3-high__t167_c000` | 2 | c167 | no games | 0 | — (forfeit:controller) |
| — | `glm-5.3-high__t168_c000` | 2 | c168 | no games | 0 | — (forfeit:controller) |
| — | `glm-5.3-high__t171_c000` | 2 | c171 | no games | 0 | — (forfeit:controller) |
| — | `glm-5.3-high__t173_c000` | 2 | c173 | no games | 0 | — (forfeit:controller) |
| — | `glm-5.3-high__t174_c000` | 2 | c174 | no games | 0 | — (forfeit:controller) |
| — | `glm-5.3-high__t176_c000` | 2 | c176 | no games | 0 | — (forfeit:controller) |
| — | `glm-5.3-high__t177_c000` | 2 | c177 | no games | 0 | — (forfeit:controller) |
| — | `glm-5.3-high__t178_c000` | 2 | c178 | no games | 0 | — (forfeit:controller) |
| — | `glm-5.3-high__t179_c000` | 2 | c179 | no games | 0 | — (forfeit:controller) |
| — | `glm-5.3-high__t182_c000` | 3 | c182 | no games | 0 | — (forfeit:controller) |
| — | `glm-5.3-high__t183_c000` | 3 | c183 | no games | 0 | — (forfeit:controller) |
| — | `glm-5.3-high__t185_c000` | 3 | c185 | no games | 0 | — (forfeit:controller) |
| — | `glm-5.3-high__t187_c000` | 3 | c187 | no games | 0 | — (forfeit:controller) |
| — | `glm-5.3-high__t188_c000` | 3 | c188 | no games | 0 | — (forfeit:controller) |
| — | `glm-5.3-high__t189_c000` | 3 | c189 | no games | 0 | — (forfeit:controller) |
| — | `glm-5.3-high__t190_c000` | 3 | c190 | no games | 0 | — (forfeit:controller) |
| — | `glm-5.3-high__t192_c000` | 3 | c192 | no games | 0 | — (forfeit:controller) |
| — | `glm-5.3-high__t196_c000` | 3 | c196 | no games | 0 | — (forfeit:controller) |
| — | `glm-5.3-high__t199_c000` | 3 | c199 | no games | 0 | — (forfeit:controller) |

## gpt-5.3-codex-high

Pool run `g2`, 330 games among 12 rated bots.

| rank | bot | group | slot | W-L-D | games | Elo |
|--:|---|:-:|---|---|--:|--:|
| 1 | `gpt-5.3-codex-high__t143_c000` ★ | 3 | c143 | 37-18-0 | 55 | 1117.8 |
| 2 | `gpt-5.3-codex-high__t142_c000` | 3 | c142 | 36-19-0 | 55 | 1104.7 |
| 3 | `gpt-5.3-codex-high__t113_c000` ★ | 1 | c113 | 33-20-2 | 55 | 1079.2 |
| 4 | `gpt-5.3-codex-high__t138_c000` | 3 | c138 | 28-27-0 | 55 | 1006.0 |
| 5 | `gpt-5.3-codex-high__t147_c000` | 3 | c147 | 28-27-0 | 55 | 1006.0 |
| 6 | `gpt-5.3-codex-high__t119_c000` ★ | 2 | c119 | 26-28-1 | 55 | 988.0 |
| 7 | `gpt-5.3-codex-high__t139_c000` | 3 | c139 | 26-28-1 | 55 | 988.0 |
| 8 | `gpt-5.3-codex-high__t121_c000` | 2 | c121 | 24-28-3 | 55 | 976.0 |
| 9 | `gpt-5.3-codex-high__t103_c000` | 1 | c103 | 24-29-2 | 55 | 969.9 |
| 10 | `gpt-5.3-codex-high__t108_c000` | 1 | c108 | 23-28-4 | 55 | 969.9 |
| 11 | `gpt-5.3-codex-high__t105_c000` | 1 | c105 | 21-31-3 | 55 | 939.5 |
| 12 | `gpt-5.3-codex-high__t128_c000` | 2 | c128 | 16-39-0 | 55 | 855.0 |
| — | `gpt-5.3-codex-high__t100_c000` | 1 | c100 | no games | 0 | — (forfeit:controller) |
| — | `gpt-5.3-codex-high__t107_c000` | 1 | c107 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `gpt-5.3-codex-high__t110_c000` | 1 | c110 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `gpt-5.3-codex-high__t111_c000` | 1 | c111 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `gpt-5.3-codex-high__t112_c000` | 1 | c112 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `gpt-5.3-codex-high__t115_c000` | 1 | c115 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `gpt-5.3-codex-high__t118_c000` | 2 | c118 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `gpt-5.3-codex-high__t120_c000` | 2 | c120 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `gpt-5.3-codex-high__t122_c000` | 2 | c122 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `gpt-5.3-codex-high__t124_c000` | 2 | c124 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `gpt-5.3-codex-high__t126_c000` | 2 | c126 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `gpt-5.3-codex-high__t127_c000` | 2 | c127 | no games | 0 | — (qualification failed (W0 D1 L2)) |
| — | `gpt-5.3-codex-high__t131_c000` | 2 | c131 | no games | 0 | — (qualification failed (W0 D1 L2)) |
| — | `gpt-5.3-codex-high__t134_c000` | 3 | c134 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `gpt-5.3-codex-high__t136_c000` | 3 | c136 | no games | 0 | — (qualification failed (W0 D2 L1)) |
| — | `gpt-5.3-codex-high__t145_c000` | 3 | c145 | no games | 0 | — (qualification failed (W1 D0 L2)) |
| — | `gpt-5.3-codex-high__t146_c000` | 3 | c146 | no games | 0 | — (qualification failed (W0 D2 L1)) |
| — | `gpt-5.3-codex-high__t149_c000` | 3 | c149 | no games | 0 | — (qualification failed (W0 D0 L3)) |

## gpt-5.4

Pool run `g4`, 765 games among 18 rated bots.

| rank | bot | group | slot | W-L-D | games | Elo |
|--:|---|:-:|---|---|--:|--:|
| 1 | `gpt-5.4__t246_c000` ★ | 3 | c246 | 80-3-2 | 85 | 1537.4 |
| 2 | `gpt-5.4__t247_c000` | 3 | c247 | 66-17-2 | 85 | 1251.9 |
| 3 | `gpt-5.4__t210_c000` | 1 | c210 | 62-23-0 | 85 | 1188.3 |
| 4 | `gpt-5.4__t242_c000` | 3 | c242 | 52-21-12 | 85 | 1143.1 |
| 5 | `gpt-5.4__t222_c000` | 2 | c222 | 46-25-14 | 85 | 1091.0 |
| 6 | `gpt-5.4__t234_c000` | 3 | c234 | 41-32-12 | 85 | 1032.5 |
| 7 | `gpt-5.4__t227_c000` ★ | 2 | c227 | 33-26-26 | 85 | 1023.0 |
| 8 | `gpt-5.4__t219_c000` | 1 | c219 | 33-35-17 | 85 | 980.8 |
| 9 | `gpt-5.4__t243_c000` | 3 | c243 | 38-40-7 | 85 | 980.8 |
| 10 | `gpt-5.4__t216_c000` ★ | 1 | c216 | 39-43-3 | 85 | 971.5 |
| 11 | `gpt-5.4__t213_c000` | 1 | c213 | 30-36-19 | 85 | 962.2 |
| 12 | `gpt-5.4__t233_c000` | 2 | c233 | 30-43-12 | 85 | 929.4 |
| 13 | `gpt-5.4__t230_c000` | 2 | c230 | 32-49-4 | 85 | 910.5 |
| 14 | `gpt-5.4__t236_c000` | 3 | c236 | 32-52-1 | 85 | 896.2 |
| 15 | `gpt-5.4__t218_c000` | 1 | c218 | 26-59-0 | 85 | 831.4 |
| 16 | `gpt-5.4__t244_c000` | 3 | c244 | 25-60-0 | 85 | 820.9 |
| 17 | `gpt-5.4__t228_c000` | 2 | c228 | 17-56-12 | 85 | 799.4 |
| 18 | `gpt-5.4__t226_c000` | 2 | c226 | 10-72-3 | 85 | 649.6 |
| — | `gpt-5.4__t200_c000` | 1 | c200 | no games | 0 | — (forfeit:controller) |
| — | `gpt-5.4__t201_c000` | 1 | c201 | no games | 0 | — (forfeit:controller) |
| — | `gpt-5.4__t202_c000` | 1 | c202 | no games | 0 | — (qualification failed (W1 D0 L2)) |
| — | `gpt-5.4__t205_c000` | 1 | c205 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `gpt-5.4__t211_c000` | 1 | c211 | no games | 0 | — (qualification failed (W0 D1 L2)) |
| — | `gpt-5.4__t220_c000` | 2 | c220 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `gpt-5.4__t224_c000` | 2 | c224 | no games | 0 | — (forfeit:controller) |
| — | `gpt-5.4__t225_c000` | 2 | c225 | no games | 0 | — (qualification failed (W0 D2 L1)) |
| — | `gpt-5.4__t232_c000` | 2 | c232 | no games | 0 | — (qualification failed (W0 D2 L1)) |
| — | `gpt-5.4__t237_c000` | 3 | c237 | no games | 0 | — (qualification failed (W1 D0 L2)) |
| — | `gpt-5.4__t239_c000` | 3 | c239 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `gpt-5.4__t248_c000` | 3 | c248 | no games | 0 | — (qualification failed (W1 D0 L2)) |

## gpt-5.5

Pool run `g3`, 765 games among 18 rated bots.

| rank | bot | group | slot | W-L-D | games | Elo |
|--:|---|:-:|---|---|--:|--:|
| 1 | `gpt-5.5__t152_c000` | 1 | c152 | 55-27-3 | 85 | 1117.8 |
| 2 | `gpt-5.5__t192_c000` ★ | 3 | c192 | 51-24-10 | 85 | 1113.4 |
| 3 | `gpt-5.5__t166_c000` ★ | 2 | c166 | 51-28-6 | 85 | 1095.9 |
| 4 | `gpt-5.5__t185_c000` | 3 | c185 | 49-30-6 | 85 | 1078.8 |
| 5 | `gpt-5.5__t154_c000` | 1 | c154 | 50-32-3 | 85 | 1074.6 |
| 6 | `gpt-5.5__t197_c000` | 3 | c197 | 44-30-11 | 85 | 1057.8 |
| 7 | `gpt-5.5__t196_c000` | 3 | c196 | 46-37-2 | 85 | 1037.2 |
| 8 | `gpt-5.5__t162_c000` ★ | 1 | c162 | 42-38-5 | 85 | 1016.8 |
| 9 | `gpt-5.5__t193_c000` | 3 | c193 | 44-40-1 | 85 | 1016.8 |
| 10 | `gpt-5.5__t189_c000` | 3 | c189 | 40-39-6 | 85 | 1004.6 |
| 11 | `gpt-5.5__t151_c000` | 1 | c151 | 41-42-2 | 85 | 996.5 |
| 12 | `gpt-5.5__t150_c000` | 1 | c150 | 41-43-1 | 85 | 992.4 |
| 13 | `gpt-5.5__t160_c000` | 1 | c160 | 29-45-11 | 85 | 934.8 |
| 14 | `gpt-5.5__t187_c000` | 3 | c187 | 30-47-8 | 85 | 930.6 |
| 15 | `gpt-5.5__t182_c000` | 2 | c182 | 31-53-1 | 85 | 909.3 |
| 16 | `gpt-5.5__t194_c000` | 3 | c194 | 28-51-6 | 85 | 905.0 |
| 17 | `gpt-5.5__t170_c000` | 2 | c170 | 26-51-8 | 85 | 896.3 |
| 18 | `gpt-5.5__t179_c000` | 2 | c179 | 21-62-2 | 85 | 821.2 |
| — | `gpt-5.5__t156_c000` | 1 | c156 | no games | 0 | — (qualification failed (W1 D0 L2)) |
| — | `gpt-5.5__t157_c000` | 1 | c157 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `gpt-5.5__t158_c000` | 1 | c158 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `gpt-5.5__t165_c000` | 1 | c165 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `gpt-5.5__t168_c000` | 2 | c168 | no games | 0 | — (qualification failed (W1 D1 L1)) |
| — | `gpt-5.5__t169_c000` | 2 | c169 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `gpt-5.5__t172_c000` | 2 | c172 | no games | 0 | — (qualification failed (W1 D1 L1)) |
| — | `gpt-5.5__t176_c000` | 2 | c176 | no games | 0 | — (qualification failed (W1 D0 L2)) |
| — | `gpt-5.5__t181_c000` | 2 | c181 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `gpt-5.5__t184_c000` | 2 | c184 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `gpt-5.5__t188_c000` | 3 | c188 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `gpt-5.5__t191_c000` | 3 | c191 | no games | 0 | — (qualification failed (W1 D1 L1)) |

## gpt-5.6-luna

Pool run `g2`, 30 games among 4 rated bots.

| rank | bot | group | slot | W-L-D | games | Elo |
|--:|---|:-:|---|---|--:|--:|
| 1 | `gpt-5.6-luna__t117_c000` ★ | 1 | c117 | 12-3-0 | 15 | 1191.1 |
| 2 | `gpt-5.6-luna__t128_c000` ★ | 2 | c128 | 9-6-0 | 15 | 1060.3 |
| 3 | `gpt-5.6-luna__t133_c000` | 2 | c133 | 6-9-0 | 15 | 939.7 |
| 4 | `gpt-5.6-luna__t146_c000` ★ | 3 | c146 | 3-12-0 | 15 | 808.9 |
| — | `gpt-5.6-luna__t103_c000` | 1 | c103 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `gpt-5.6-luna__t104_c000` | 1 | c104 | no games | 0 | — (forfeit:controller) |
| — | `gpt-5.6-luna__t106_c000` | 1 | c106 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `gpt-5.6-luna__t113_c000` | 1 | c113 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `gpt-5.6-luna__t114_c000` | 1 | c114 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `gpt-5.6-luna__t118_c000` | 1 | c118 | no games | 0 | — (qualification failed (W0 D1 L2)) |
| — | `gpt-5.6-luna__t119_c000` | 1 | c119 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `gpt-5.6-luna__t120_c000` | 1 | c120 | no games | 0 | — (forfeit:controller) |
| — | `gpt-5.6-luna__t121_c000` | 1 | c121 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `gpt-5.6-luna__t122_c000` | 2 | c122 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `gpt-5.6-luna__t123_c000` | 2 | c123 | no games | 0 | — (qualification failed (W0 D1 L2)) |
| — | `gpt-5.6-luna__t124_c000` | 2 | c124 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `gpt-5.6-luna__t129_c000` | 2 | c129 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `gpt-5.6-luna__t130_c000` | 2 | c130 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `gpt-5.6-luna__t131_c000` | 2 | c131 | no games | 0 | — (qualification failed (W0 D2 L1)) |
| — | `gpt-5.6-luna__t132_c000` | 2 | c132 | no games | 0 | — (forfeit:controller) |
| — | `gpt-5.6-luna__t134_c000` | 2 | c134 | no games | 0 | — (qualification failed (W0 D2 L1)) |
| — | `gpt-5.6-luna__t135_c000` | 3 | c135 | no games | 0 | — (forfeit:controller) |
| — | `gpt-5.6-luna__t136_c000` | 3 | c136 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `gpt-5.6-luna__t138_c000` | 3 | c138 | no games | 0 | — (forfeit:controller) |
| — | `gpt-5.6-luna__t140_c000` | 3 | c140 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `gpt-5.6-luna__t142_c000` | 3 | c142 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `gpt-5.6-luna__t143_c000` | 3 | c143 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `gpt-5.6-luna__t144_c000` | 3 | c144 | no games | 0 | — (qualification failed (W0 D2 L1)) |
| — | `gpt-5.6-luna__t145_c000` | 3 | c145 | no games | 0 | — (qualification failed (W0 D1 L2)) |
| — | `gpt-5.6-luna__t147_c000` | 3 | c147 | no games | 0 | — (qualification failed (W0 D0 L3)) |

## gpt-5.6-sol

Pool run `g0`, 1380 games among 24 rated bots.

| rank | bot | group | slot | W-L-D | games | Elo |
|--:|---|:-:|---|---|--:|--:|
| 1 | `gpt-5.6-sol__t30_c000` ★ | 2 | c030 | 95-13-7 | 115 | 1346.1 |
| 2 | `gpt-5.6-sol__t00_c000` ★ | 1 | c000 | 80-29-6 | 115 | 1197.8 |
| 3 | `gpt-5.6-sol__t44_c000` ★ | 3 | c044 | 83-32-0 | 115 | 1197.8 |
| 4 | `gpt-5.6-sol__t23_c000` | 2 | c023 | 75-33-7 | 115 | 1162.5 |
| 5 | `gpt-5.6-sol__t46_c000` | 3 | c046 | 72-31-12 | 115 | 1158.6 |
| 6 | `gpt-5.6-sol__t16_c000` | 1 | c016 | 72-36-7 | 115 | 1139.9 |
| 7 | `gpt-5.6-sol__t33_c000` | 3 | c033 | 71-38-6 | 115 | 1128.8 |
| 8 | `gpt-5.6-sol__t41_c000` | 3 | c041 | 71-40-4 | 115 | 1121.5 |
| 9 | `gpt-5.6-sol__t36_c000` | 3 | c036 | 58-42-15 | 115 | 1067.9 |
| 10 | `gpt-5.6-sol__t15_c000` | 1 | c015 | 62-51-2 | 115 | 1050.3 |
| 11 | `gpt-5.6-sol__t24_c000` | 2 | c024 | 46-43-26 | 115 | 1022.3 |
| 12 | `gpt-5.6-sol__t42_c000` | 3 | c042 | 52-49-14 | 115 | 1022.3 |
| 13 | `gpt-5.6-sol__t27_c000` | 2 | c027 | 52-51-12 | 115 | 1015.3 |
| 14 | `gpt-5.6-sol__t12_c000` | 1 | c012 | 54-54-7 | 115 | 1011.8 |
| 15 | `gpt-5.6-sol__t20_c000` | 2 | c020 | 53-53-9 | 115 | 1011.8 |
| 16 | `gpt-5.6-sol__t43_c000` | 3 | c043 | 48-51-16 | 115 | 1001.2 |
| 17 | `gpt-5.6-sol__t48_c000` | 3 | c048 | 50-57-8 | 115 | 987.0 |
| 18 | `gpt-5.6-sol__t29_c000` | 2 | c029 | 49-59-7 | 115 | 976.3 |
| 19 | `gpt-5.6-sol__t07_c000` | 1 | c007 | 39-70-6 | 115 | 898.3 |
| 20 | `gpt-5.6-sol__t26_c000` | 2 | c026 | 36-72-7 | 115 | 878.5 |
| 21 | `gpt-5.6-sol__t19_c000` | 2 | c019 | 30-76-9 | 115 | 837.0 |
| 22 | `gpt-5.6-sol__t05_c000` | 1 | c005 | 12-97-6 | 115 | 624.5 |
| 23 | `gpt-5.6-sol__t22_c000` | 2 | c022 | 12-99-4 | 115 | 609.6 |
| 24 | `gpt-5.6-sol__t39_c000` | 3 | c039 | 6-102-7 | 115 | 533.0 |
| — | `gpt-5.6-sol__t01_c000` | 1 | c001 | no games | 0 | — (forfeit:controller) |
| — | `gpt-5.6-sol__t03_c000` | 1 | c003 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `gpt-5.6-sol__t13_c000` | 1 | c013 | no games | 0 | — (qualification failed (W1 D1 L1)) |
| — | `gpt-5.6-sol__t18_c000` | 1 | c018 | no games | 0 | — (forfeit:controller) |
| — | `gpt-5.6-sol__t31_c000` | 2 | c031 | no games | 0 | — (qualification failed (W0 D1 L2)) |
| — | `gpt-5.6-sol__t38_c000` | 3 | c038 | no games | 0 | — (qualification failed (W0 D2 L1)) |

## gpt-5.6-terra

Pool run `g2`, 855 games among 19 rated bots.

| rank | bot | group | slot | W-L-D | games | Elo |
|--:|---|:-:|---|---|--:|--:|
| 1 | `gpt-5.6-terra__t101_c000` | 1 | c101 | 57-25-8 | 90 | 1133.6 |
| 2 | `gpt-5.6-terra__t129_c000` | 2 | c129 | 58-27-5 | 90 | 1129.2 |
| 3 | `gpt-5.6-terra__t117_c000` ★ | 2 | c117 | 51-25-14 | 90 | 1107.7 |
| 4 | `gpt-5.6-terra__t116_c000` | 1 | c116 | 55-30-5 | 90 | 1103.5 |
| 5 | `gpt-5.6-terra__t104_c000` ★ | 1 | c104 | 50-27-13 | 90 | 1095.1 |
| 6 | `gpt-5.6-terra__t149_c000` ★ | 3 | c149 | 50-32-8 | 90 | 1074.5 |
| 7 | `gpt-5.6-terra__t134_c000` | 3 | c134 | 49-32-9 | 90 | 1070.4 |
| 8 | `gpt-5.6-terra__t146_c000` | 3 | c146 | 44-33-13 | 90 | 1046.2 |
| 9 | `gpt-5.6-terra__t127_c000` | 2 | c127 | 49-41-0 | 90 | 1034.2 |
| 10 | `gpt-5.6-terra__t124_c000` | 2 | c124 | 47-40-3 | 90 | 1030.2 |
| 11 | `gpt-5.6-terra__t132_c000` | 3 | c132 | 43-38-9 | 90 | 1022.3 |
| 12 | `gpt-5.6-terra__t143_c000` | 3 | c143 | 42-46-2 | 90 | 986.5 |
| 13 | `gpt-5.6-terra__t102_c000` | 1 | c102 | 29-40-21 | 90 | 958.4 |
| 14 | `gpt-5.6-terra__t115_c000` | 1 | c115 | 34-45-11 | 90 | 958.4 |
| 15 | `gpt-5.6-terra__t112_c000` | 1 | c112 | 33-50-7 | 90 | 934.0 |
| 16 | `gpt-5.6-terra__t120_c000` | 2 | c120 | 27-52-11 | 90 | 900.4 |
| 17 | `gpt-5.6-terra__t130_c000` | 2 | c130 | 27-61-2 | 90 | 860.6 |
| 18 | `gpt-5.6-terra__t140_c000` | 3 | c140 | 20-65-5 | 90 | 807.6 |
| 19 | `gpt-5.6-terra__t108_c000` | 1 | c108 | 15-71-4 | 90 | 747.0 |
| — | `gpt-5.6-terra__t106_c000` | 1 | c106 | no games | 0 | — (qualification failed (W0 D2 L1)) |
| — | `gpt-5.6-terra__t107_c000` | 1 | c107 | no games | 0 | — (qualification failed (W0 D1 L2)) |
| — | `gpt-5.6-terra__t113_c000` | 1 | c113 | no games | 0 | — (qualification failed (W0 D1 L2)) |
| — | `gpt-5.6-terra__t118_c000` | 2 | c118 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `gpt-5.6-terra__t123_c000` | 2 | c123 | no games | 0 | — (qualification failed (W1 D0 L2)) |
| — | `gpt-5.6-terra__t125_c000` | 2 | c125 | no games | 0 | — (forfeit:controller) |
| — | `gpt-5.6-terra__t126_c000` | 2 | c126 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `gpt-5.6-terra__t133_c000` | 3 | c133 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `gpt-5.6-terra__t135_c000` | 3 | c135 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `gpt-5.6-terra__t141_c000` | 3 | c141 | no games | 0 | — (qualification failed (W0 D1 L2)) |
| — | `gpt-5.6-terra__t142_c000` | 3 | c142 | no games | 0 | — (forfeit:controller) |

## gpt-6-astra

Pool run `g4`, 390 games among 13 rated bots.

| rank | bot | group | slot | W-L-D | games | Elo |
|--:|---|:-:|---|---|--:|--:|
| 1 | `gpt-6-astra__t244_c000` ★ | 3 | c244 | 47-7-6 | 60 | 1299.1 |
| 2 | `gpt-6-astra__t238_c000` | 3 | c238 | 45-15-0 | 60 | 1213.2 |
| 3 | `gpt-6-astra__t236_c000` | 2 | c236 | 37-19-4 | 60 | 1126.0 |
| 4 | `gpt-6-astra__t224_c000` ★ | 2 | c224 | 34-19-7 | 60 | 1105.6 |
| 5 | `gpt-6-astra__t221_c000` ★ | 1 | c221 | 36-23-1 | 60 | 1092.2 |
| 6 | `gpt-6-astra__t204_c000` | 1 | c204 | 31-24-5 | 60 | 1052.6 |
| 7 | `gpt-6-astra__t220_c000` | 1 | c220 | 31-24-5 | 60 | 1052.6 |
| 8 | `gpt-6-astra__t243_c000` | 3 | c243 | 27-29-4 | 60 | 993.9 |
| 9 | `gpt-6-astra__t229_c000` | 2 | c229 | 27-31-2 | 60 | 980.7 |
| 10 | `gpt-6-astra__t247_c000` | 3 | c247 | 18-36-6 | 60 | 885.1 |
| 11 | `gpt-6-astra__t213_c000` | 1 | c213 | 18-42-0 | 60 | 840.7 |
| 12 | `gpt-6-astra__t215_c000` | 1 | c215 | 13-46-1 | 60 | 766.8 |
| 13 | `gpt-6-astra__t245_c000` | 3 | c245 | 5-54-1 | 60 | 591.4 |
| — | `gpt-6-astra__t202_c000` | 1 | c202 | no games | 0 | — (qualification failed (W0 D1 L2)) |
| — | `gpt-6-astra__t205_c000` | 1 | c205 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `gpt-6-astra__t207_c000` | 1 | c207 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `gpt-6-astra__t210_c000` | 1 | c210 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `gpt-6-astra__t212_c000` | 1 | c212 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `gpt-6-astra__t222_c000` | 2 | c222 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `gpt-6-astra__t223_c000` | 2 | c223 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `gpt-6-astra__t226_c000` | 2 | c226 | no games | 0 | — (qualification failed (W1 D0 L2)) |
| — | `gpt-6-astra__t227_c000` | 2 | c227 | no games | 0 | — (qualification failed (W1 D0 L2)) |
| — | `gpt-6-astra__t228_c000` | 2 | c228 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `gpt-6-astra__t230_c000` | 2 | c230 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `gpt-6-astra__t233_c000` | 2 | c233 | no games | 0 | — (qualification failed (W1 D0 L2)) |
| — | `gpt-6-astra__t237_c000` | 3 | c237 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `gpt-6-astra__t239_c000` | 3 | c239 | no games | 0 | — (qualification failed (W0 D1 L2)) |
| — | `gpt-6-astra__t241_c000` | 3 | c241 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `gpt-6-astra__t242_c000` | 3 | c242 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `gpt-6-astra__t246_c000` | 3 | c246 | no games | 0 | — (qualification failed (W1 D0 L2)) |

## grok-4.20-reasoning

Pool run `g0`, 0 games among 0 rated bots.

| rank | bot | group | slot | W-L-D | games | Elo |
|--:|---|:-:|---|---|--:|--:|
| — | `grok-4.20-reasoning__t01_c000` | 1 | c001 | no games | 0 | — (forfeit:controller) |
| — | `grok-4.20-reasoning__t03_c000` | 1 | c003 | no games | 0 | — (forfeit:controller) |
| — | `grok-4.20-reasoning__t04_c000` | 1 | c004 | no games | 0 | — (forfeit:controller) |
| — | `grok-4.20-reasoning__t05_c000` | 1 | c005 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `grok-4.20-reasoning__t06_c000` | 1 | c006 | no games | 0 | — (forfeit:controller) |
| — | `grok-4.20-reasoning__t07_c000` | 1 | c007 | no games | 0 | — (forfeit:controller) |
| — | `grok-4.20-reasoning__t11_c000` | 1 | c011 | no games | 0 | — (forfeit:controller) |
| — | `grok-4.20-reasoning__t13_c000` | 1 | c013 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `grok-4.20-reasoning__t14_c000` | 1 | c014 | no games | 0 | — (qualification failed (W0 D1 L2)) |
| — | `grok-4.20-reasoning__t15_c000` | 1 | c015 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `grok-4.20-reasoning__t16_c000` | 2 | c016 | no games | 0 | — (forfeit:controller) |
| — | `grok-4.20-reasoning__t17_c000` | 2 | c017 | no games | 0 | — (forfeit:controller) |
| — | `grok-4.20-reasoning__t18_c000` | 2 | c018 | no games | 0 | — (forfeit:controller) |
| — | `grok-4.20-reasoning__t19_c000` | 2 | c019 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `grok-4.20-reasoning__t21_c000` | 2 | c021 | no games | 0 | — (forfeit:controller) |
| — | `grok-4.20-reasoning__t22_c000` | 2 | c022 | no games | 0 | — (forfeit:controller) |
| — | `grok-4.20-reasoning__t25_c000` | 2 | c025 | no games | 0 | — (forfeit:controller) |
| — | `grok-4.20-reasoning__t26_c000` | 2 | c026 | no games | 0 | — (forfeit:controller) |
| — | `grok-4.20-reasoning__t29_c000` | 2 | c029 | no games | 0 | — (forfeit:controller) |
| — | `grok-4.20-reasoning__t31_c000` | 2 | c031 | no games | 0 | — (forfeit:controller) |
| — | `grok-4.20-reasoning__t32_c000` | 3 | c032 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `grok-4.20-reasoning__t37_c000` | 3 | c037 | no games | 0 | — (forfeit:controller) |
| — | `grok-4.20-reasoning__t38_c000` | 3 | c038 | no games | 0 | — (eligible) |
| — | `grok-4.20-reasoning__t40_c000` | 3 | c040 | no games | 0 | — (forfeit:controller) |
| — | `grok-4.20-reasoning__t41_c000` | 3 | c041 | no games | 0 | — (forfeit:controller) |
| — | `grok-4.20-reasoning__t42_c000` | 3 | c042 | no games | 0 | — (forfeit:controller) |
| — | `grok-4.20-reasoning__t43_c000` | 3 | c043 | no games | 0 | — (forfeit:controller) |
| — | `grok-4.20-reasoning__t45_c000` | 3 | c045 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `grok-4.20-reasoning__t46_c000` | 3 | c046 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `grok-4.20-reasoning__t49_c000` | 3 | c049 | no games | 0 | — (forfeit:controller) |

## grok-4.5-high

Pool run `g2`, 0 games among 0 rated bots.

| rank | bot | group | slot | W-L-D | games | Elo |
|--:|---|:-:|---|---|--:|--:|
| — | `grok-4.5-high__t101_c000` | 1 | c101 | no games | 0 | — (forfeit:controller) |
| — | `grok-4.5-high__t105_c000` | 1 | c105 | no games | 0 | — (forfeit:controller) |
| — | `grok-4.5-high__t106_c000` | 1 | c106 | no games | 0 | — (forfeit:controller) |
| — | `grok-4.5-high__t107_c000` | 1 | c107 | no games | 0 | — (forfeit:controller) |
| — | `grok-4.5-high__t108_c000` | 1 | c108 | no games | 0 | — (forfeit:controller) |
| — | `grok-4.5-high__t110_c000` | 1 | c110 | no games | 0 | — (forfeit:controller) |
| — | `grok-4.5-high__t113_c000` | 1 | c113 | no games | 0 | — (forfeit:controller) |
| — | `grok-4.5-high__t114_c000` | 1 | c114 | no games | 0 | — (qualification failed (W1 D0 L2)) |
| — | `grok-4.5-high__t115_c000` | 1 | c115 | no games | 0 | — (eligible) |
| — | `grok-4.5-high__t116_c000` | 1 | c116 | no games | 0 | — (forfeit:controller) |
| — | `grok-4.5-high__t117_c000` | 2 | c117 | no games | 0 | — (qualification failed (W0 D1 L2)) |
| — | `grok-4.5-high__t118_c000` | 2 | c118 | no games | 0 | — (forfeit:controller) |
| — | `grok-4.5-high__t119_c000` | 2 | c119 | no games | 0 | — (forfeit:controller) |
| — | `grok-4.5-high__t122_c000` | 2 | c122 | no games | 0 | — (forfeit:controller) |
| — | `grok-4.5-high__t123_c000` | 2 | c123 | no games | 0 | — (forfeit:controller) |
| — | `grok-4.5-high__t127_c000` | 2 | c127 | no games | 0 | — (forfeit:controller) |
| — | `grok-4.5-high__t128_c000` | 2 | c128 | no games | 0 | — (forfeit:controller) |
| — | `grok-4.5-high__t129_c000` | 2 | c129 | no games | 0 | — (forfeit:controller) |
| — | `grok-4.5-high__t131_c000` | 2 | c131 | no games | 0 | — (forfeit:controller) |
| — | `grok-4.5-high__t132_c000` | 2 | c132 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `grok-4.5-high__t133_c000` | 3 | c133 | no games | 0 | — (forfeit:controller) |
| — | `grok-4.5-high__t136_c000` | 3 | c136 | no games | 0 | — (forfeit:controller) |
| — | `grok-4.5-high__t137_c000` | 3 | c137 | no games | 0 | — (forfeit:controller) |
| — | `grok-4.5-high__t138_c000` | 3 | c138 | no games | 0 | — (forfeit:controller) |
| — | `grok-4.5-high__t139_c000` | 3 | c139 | no games | 0 | — (forfeit:controller) |
| — | `grok-4.5-high__t142_c000` | 3 | c142 | no games | 0 | — (forfeit:controller) |
| — | `grok-4.5-high__t145_c000` | 3 | c145 | no games | 0 | — (forfeit:controller) |
| — | `grok-4.5-high__t146_c000` | 3 | c146 | no games | 0 | — (forfeit:controller) |
| — | `grok-4.5-high__t148_c000` | 3 | c148 | no games | 0 | — (forfeit:controller) |
| — | `grok-4.5-high__t149_c000` | 3 | c149 | no games | 0 | — (qualification failed (W1 D0 L2)) |

## grok-4.6-high

Pool run `g4`, 1155 games among 22 rated bots.

| rank | bot | group | slot | W-L-D | games | Elo |
|--:|---|:-:|---|---|--:|--:|
| 1 | `grok-4.6-high__t213_c000` ★ | 1 | c213 | 83-21-1 | 105 | 1261.1 |
| 2 | `grok-4.6-high__t240_c000` ★ | 3 | c240 | 78-24-3 | 105 | 1221.8 |
| 3 | `grok-4.6-high__t229_c000` | 2 | c229 | 78-26-1 | 105 | 1212.5 |
| 4 | `grok-4.6-high__t221_c000` | 2 | c221 | 71-30-4 | 105 | 1164.2 |
| 5 | `grok-4.6-high__t203_c000` | 1 | c203 | 64-26-15 | 105 | 1151.7 |
| 6 | `grok-4.6-high__t223_c000` | 2 | c223 | 68-37-0 | 105 | 1123.3 |
| 7 | `grok-4.6-high__t219_c000` ★ | 2 | c219 | 64-38-3 | 105 | 1103.6 |
| 8 | `grok-4.6-high__t209_c000` | 1 | c209 | 59-36-10 | 105 | 1092.0 |
| 9 | `grok-4.6-high__t226_c000` | 2 | c226 | 57-35-13 | 105 | 1088.1 |
| 10 | `grok-4.6-high__t243_c000` | 3 | c243 | 57-47-1 | 105 | 1042.5 |
| 11 | `grok-4.6-high__t239_c000` | 3 | c239 | 53-48-4 | 105 | 1023.7 |
| 12 | `grok-4.6-high__t200_c000` | 1 | c200 | 50-46-9 | 105 | 1020.0 |
| 13 | `grok-4.6-high__t216_c000` | 1 | c216 | 42-62-1 | 105 | 929.0 |
| 14 | `grok-4.6-high__t201_c000` | 1 | c201 | 38-61-6 | 105 | 917.2 |
| 15 | `grok-4.6-high__t248_c000` | 3 | c248 | 39-63-3 | 105 | 913.3 |
| 16 | `grok-4.6-high__t227_c000` | 2 | c227 | 35-60-10 | 105 | 909.3 |
| 17 | `grok-4.6-high__t233_c000` | 2 | c233 | 37-62-6 | 105 | 909.3 |
| 18 | `grok-4.6-high__t238_c000` | 3 | c238 | 37-68-0 | 105 | 885.2 |
| 19 | `grok-4.6-high__t204_c000` | 1 | c204 | 30-65-10 | 105 | 868.7 |
| 20 | `grok-4.6-high__t234_c000` | 3 | c234 | 33-68-4 | 105 | 868.7 |
| 21 | `grok-4.6-high__t202_c000` | 1 | c202 | 21-82-2 | 105 | 747.2 |
| 22 | `grok-4.6-high__t236_c000` | 3 | c236 | 8-97-0 | 105 | 547.4 |
| — | `grok-4.6-high__t205_c000` | 1 | c205 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `grok-4.6-high__t215_c000` | 1 | c215 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `grok-4.6-high__t225_c000` | 2 | c225 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `grok-4.6-high__t231_c000` | 2 | c231 | no games | 0 | — (forfeit:controller) |
| — | `grok-4.6-high__t232_c000` | 2 | c232 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `grok-4.6-high__t237_c000` | 3 | c237 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `grok-4.6-high__t242_c000` | 3 | c242 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `grok-4.6-high__t246_c000` | 3 | c246 | no games | 0 | — (qualification failed (W1 D1 L1)) |

## kimi-k3-high

Pool run `g0`, 180 games among 9 rated bots.

| rank | bot | group | slot | W-L-D | games | Elo |
|--:|---|:-:|---|---|--:|--:|
| 1 | `kimi-k3-high__t23_c000` ★ | 2 | c023 | 36-4-0 | 40 | 1382.4 |
| 2 | `kimi-k3-high__t45_c000` ★ | 3 | c045 | 33-7-0 | 40 | 1282.3 |
| 3 | `kimi-k3-high__t16_c000` | 1 | c016 | 18-17-5 | 40 | 997.2 |
| 4 | `kimi-k3-high__t20_c000` | 2 | c020 | 15-18-7 | 40 | 959.0 |
| 5 | `kimi-k3-high__t22_c000` | 2 | c022 | 17-22-1 | 40 | 940.0 |
| 6 | `kimi-k3-high__t37_c000` | 3 | c037 | 16-21-3 | 40 | 940.0 |
| 7 | `kimi-k3-high__t38_c000` | 3 | c038 | 16-22-2 | 40 | 930.5 |
| 8 | `kimi-k3-high__t07_c000` ★ | 1 | c007 | 10-23-7 | 40 | 862.8 |
| 9 | `kimi-k3-high__t42_c000` | 3 | c042 | 4-31-5 | 40 | 705.7 |
| — | `kimi-k3-high__t01_c000` | 1 | c001 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `kimi-k3-high__t05_c000` | 1 | c005 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `kimi-k3-high__t08_c000` | 1 | c008 | no games | 0 | — (qualification failed (W1 D0 L2)) |
| — | `kimi-k3-high__t09_c000` | 1 | c009 | no games | 0 | — (qualification failed (W0 D1 L2)) |
| — | `kimi-k3-high__t13_c000` | 1 | c013 | no games | 0 | — (qualification failed (W1 D0 L2)) |
| — | `kimi-k3-high__t14_c000` | 1 | c014 | no games | 0 | — (forfeit:controller) |
| — | `kimi-k3-high__t15_c000` | 1 | c015 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `kimi-k3-high__t19_c000` | 1 | c019 | no games | 0 | — (qualification failed (W0 D1 L2)) |
| — | `kimi-k3-high__t21_c000` | 2 | c021 | no games | 0 | — (forfeit:controller) |
| — | `kimi-k3-high__t25_c000` | 2 | c025 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `kimi-k3-high__t26_c000` | 2 | c026 | no games | 0 | — (qualification failed (W1 D0 L2)) |
| — | `kimi-k3-high__t27_c000` | 2 | c027 | no games | 0 | — (qualification failed (W1 D0 L2)) |
| — | `kimi-k3-high__t32_c000` | 2 | c032 | no games | 0 | — (qualification failed (W0 D2 L1)) |
| — | `kimi-k3-high__t33_c000` | 2 | c033 | no games | 0 | — (qualification failed (W0 D1 L2)) |
| — | `kimi-k3-high__t34_c000` | 2 | c034 | no games | 0 | — (qualification failed (W1 D0 L2)) |
| — | `kimi-k3-high__t39_c000` | 3 | c039 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `kimi-k3-high__t43_c000` | 3 | c043 | no games | 0 | — (forfeit:controller) |
| — | `kimi-k3-high__t44_c000` | 3 | c044 | no games | 0 | — (qualification failed (W1 D0 L2)) |
| — | `kimi-k3-high__t46_c000` | 3 | c046 | no games | 0 | — (forfeit:controller) |
| — | `kimi-k3-high__t47_c000` | 3 | c047 | no games | 0 | — (forfeit:controller) |
| — | `kimi-k3-high__t49_c000` | 3 | c049 | no games | 0 | — (qualification failed (W0 D0 L3)) |

## qwen3.8-2.4t-a95b-thinking

Pool run `g3`, 1050 games among 21 rated bots.

| rank | bot | group | slot | W-L-D | games | Elo |
|--:|---|:-:|---|---|--:|--:|
| 1 | `qwen3.8-2.4t-a95b-thinking__t155_c000` ★ | 1 | c155 | 84-13-3 | 100 | 1335.3 |
| 2 | `qwen3.8-2.4t-a95b-thinking__t164_c000` ★ | 2 | c164 | 81-16-3 | 100 | 1295.9 |
| 3 | `qwen3.8-2.4t-a95b-thinking__t157_c000` | 1 | c157 | 78-21-1 | 100 | 1249.3 |
| 4 | `qwen3.8-2.4t-a95b-thinking__t196_c000` | 3 | c196 | 72-20-8 | 100 | 1222.6 |
| 5 | `qwen3.8-2.4t-a95b-thinking__t178_c000` | 2 | c178 | 62-37-1 | 100 | 1098.1 |
| 6 | `qwen3.8-2.4t-a95b-thinking__t167_c000` | 2 | c167 | 53-40-7 | 100 | 1048.8 |
| 7 | `qwen3.8-2.4t-a95b-thinking__t190_c000` | 3 | c190 | 54-43-3 | 100 | 1040.7 |
| 8 | `qwen3.8-2.4t-a95b-thinking__t152_c000` | 1 | c152 | 52-43-5 | 100 | 1032.7 |
| 9 | `qwen3.8-2.4t-a95b-thinking__t181_c000` | 3 | c181 | 44-43-13 | 100 | 1001.0 |
| 10 | `qwen3.8-2.4t-a95b-thinking__t192_c000` ★ | 3 | c192 | 50-49-1 | 100 | 1001.0 |
| 11 | `qwen3.8-2.4t-a95b-thinking__t158_c000` | 1 | c158 | 48-49-3 | 100 | 993.1 |
| 12 | `qwen3.8-2.4t-a95b-thinking__t159_c000` | 1 | c159 | 44-50-6 | 100 | 973.3 |
| 13 | `qwen3.8-2.4t-a95b-thinking__t183_c000` | 3 | c183 | 38-46-16 | 100 | 965.4 |
| 14 | `qwen3.8-2.4t-a95b-thinking__t198_c000` | 3 | c198 | 39-51-10 | 100 | 949.6 |
| 15 | `qwen3.8-2.4t-a95b-thinking__t171_c000` | 2 | c171 | 37-57-6 | 100 | 917.5 |
| 16 | `qwen3.8-2.4t-a95b-thinking__t168_c000` | 2 | c168 | 36-59-5 | 100 | 905.3 |
| 17 | `qwen3.8-2.4t-a95b-thinking__t179_c000` | 2 | c179 | 34-60-6 | 100 | 892.9 |
| 18 | `qwen3.8-2.4t-a95b-thinking__t165_c000` | 2 | c165 | 32-68-0 | 100 | 850.5 |
| 19 | `qwen3.8-2.4t-a95b-thinking__t187_c000` | 3 | c187 | 27-70-3 | 100 | 819.2 |
| 20 | `qwen3.8-2.4t-a95b-thinking__t173_c000` | 2 | c173 | 15-75-10 | 100 | 734.0 |
| 21 | `qwen3.8-2.4t-a95b-thinking__t182_c000` | 3 | c182 | 15-85-0 | 100 | 673.9 |
| — | `qwen3.8-2.4t-a95b-thinking__t151_c000` | 1 | c151 | no games | 0 | — (qualification failed (W0 D2 L1)) |
| — | `qwen3.8-2.4t-a95b-thinking__t153_c000` | 1 | c153 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `qwen3.8-2.4t-a95b-thinking__t154_c000` | 1 | c154 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `qwen3.8-2.4t-a95b-thinking__t162_c000` | 1 | c162 | no games | 0 | — (qualification failed (W0 D1 L2)) |
| — | `qwen3.8-2.4t-a95b-thinking__t163_c000` | 1 | c163 | no games | 0 | — (qualification failed (W0 D1 L2)) |
| — | `qwen3.8-2.4t-a95b-thinking__t174_c000` | 2 | c174 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `qwen3.8-2.4t-a95b-thinking__t180_c000` | 2 | c180 | no games | 0 | — (forfeit:controller) |
| — | `qwen3.8-2.4t-a95b-thinking__t185_c000` | 3 | c185 | no games | 0 | — (qualification failed (W0 D0 L3)) |
| — | `qwen3.8-2.4t-a95b-thinking__t188_c000` | 3 | c188 | no games | 0 | — (qualification failed (W0 D2 L1)) |
