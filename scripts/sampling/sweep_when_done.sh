#!/bin/bash
# usage: sweep_when_done.sh <name> "<log1> <log2> ..." "<model substrings>" <per-model> [deadline-min]
name=$1; logs=$2; models=$3; per=$4; dl=${5:-0}
cd <arena-checkout>/.claude/worktrees/upload-main
for l in $logs; do until grep -q "generation stage finished\|ALL DONE" "$l" 2>/dev/null; do sleep 30; done; done
echo "$(date -u +%H:%M:%SZ) $name: predecessors finished; sweeping remaining slots for: $models"
nohup ~/miniconda3/envs/arena/bin/python scripts/sampling/run_pool.py --root LOGS-SH250/20260918 --n-samples 250 --per-model $per --qual-workers 0 --status-every 30 --gen-deadline-min $dl --stop-scope instance --skip-recent-min 0 --models $models --retry-failed --status-name STATUS-$name.md > LOGS-SH250-20260918-$name.pool.log 2>&1 &
echo $! > LOGS-SH250-20260918-$name.pid
until grep -q "^\[pool\] [0-9]* models" LOGS-SH250-20260918-$name.pool.log 2>/dev/null; do sleep 2; done
grep "^\[pool\] [0-9]* models" LOGS-SH250-20260918-$name.pool.log | cut -c1-160
