# Re-pull the borrowed engine pieces from the trusty-lab container (CT 203 on pve):
# strategy contract, runner, inspector, every strategy file, and the CSV history the
# strategies reference. Run after the lab adopts or authors something new.
#
#   powershell -File host\sync_engine.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$stage = Join-Path $env:TEMP "edgestack_engine_sync"
New-Item -ItemType Directory -Force $stage | Out-Null

$remote = @'
cd /opt/trustyrusty
# Only the submitted strategy's lineage and the benchmark are public; the
# operator's own strategies stay in the container (engine/BORROWED.md).
PUB=$(ls python_strategies/strategies/edgestack*.py python_strategies/strategies/bench_spy_hold.py 2>/dev/null)
SYMS=$(grep -ohE "[\"'][A-Z]{2,6}[\"']" $PUB 2>/dev/null | tr -d "\"'" | sort -u)
FILES=""
for s in $SYMS; do [ -f data/historical/$s.csv ] && FILES="$FILES data/historical/$s.csv"; done
tar czf /tmp/engine_sync.tgz bridge/__init__.py bridge/strategy_interface.py python_strategies/inspect_strategy.py $PUB
'@
$remote = $remote -replace "`r", ""
ssh pve "pct exec 203 -- bash -c '$($remote -replace "'", "'\''")' ; pct pull 203 /tmp/engine_sync.tgz /tmp/engine_sync.tgz"
scp -q pve:/tmp/engine_sync.tgz (Join-Path $stage "engine_sync.tgz")
Push-Location $stage
try {
    if (Test-Path "x") { Remove-Item -Recurse -Force "x" }
    New-Item -ItemType Directory -Force "x" | Out-Null
    tar xzf engine_sync.tgz -C x
    Copy-Item x\bridge\*.py (Join-Path $root "engine\bridge") -Force
    Copy-Item x\python_strategies\inspect_strategy.py (Join-Path $root "engine") -Force
    Copy-Item x\python_strategies\strategies\*.py (Join-Path $root "engine\strategies") -Force  # allowlisted above
    Copy-Item x\data\historical\*.csv (Join-Path $root "engine\data") -Force
} finally { Pop-Location }
# run_backtest.py is NOT overwritten: it carries the final_weights addition (engine/BORROWED.md).
Write-Host "engine synced: $((Get-ChildItem (Join-Path $root 'engine\strategies') -Filter *.py).Count) strategies, $((Get-ChildItem (Join-Path $root 'engine\data') -Filter *.csv).Count) csv"
