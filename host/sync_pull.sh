#!/bin/bash
# Runs INSIDE the lab container (root), read-only: stages the publishable
# strategy files and the price histories they reference into one tarball.
# Publishable = the submitted strategy's lineage, the benchmark, and every
# agent-authored family (protocol/families.json) - the operator's own
# strategies never leave the container (engine/BORROWED.md).
set -eu
cd /opt/trustyrusty
S=python_strategies/strategies
PUB="$(ls $S/edgestack*.py $S/bench_spy_hold.py 2>/dev/null || true)"
for root in $(python3 -c 'import json;print(" ".join(f["root"] for f in json.load(open("/opt/agent-lab/protocol/families.json"))["families"]))' 2>/dev/null); do
  PUB="$PUB $(ls $S/${root}_c*.py 2>/dev/null || true)"
done
SYMS="$(grep -ohE '["'"'"'][A-Z0-9]{2,6}["'"'"']' $PUB 2>/dev/null | tr -d '"'"'"'"' | sort -u || true)"
FILES=""
for s in $SYMS; do [ -f "data/historical/$s.csv" ] && FILES="$FILES data/historical/$s.csv"; done
tar czf /tmp/engine_sync.tgz bridge/__init__.py bridge/strategy_interface.py python_strategies/inspect_strategy.py $PUB $FILES
echo "staged: $(echo $PUB | wc -w) strategies, $(echo $FILES | wc -w) histories"
