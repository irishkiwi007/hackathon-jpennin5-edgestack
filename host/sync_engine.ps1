# Re-pull the publishable engine pieces from the trusty-lab container (CT 203 on pve),
# read-only on the lab: the strategy contract, the inspector, the submitted strategy's
# lineage, the benchmark, every agent-authored family, and the price histories those
# files reference. The selection logic lives in host/sync_pull.sh, which is pushed into
# the container and run there (no quoting crosses three shells).
#
#   powershell -File host\sync_engine.ps1
$ErrorActionPreference = "Stop"
$root  = Split-Path -Parent $PSScriptRoot
$stage = Join-Path $env:TEMP "edgestack_engine_sync"
New-Item -ItemType Directory -Force $stage | Out-Null

# strip CR locally so the remote side needs no quoting at all
$lf = Join-Path $stage "sync_pull.sh"
[IO.File]::WriteAllText($lf, ((Get-Content -Raw (Join-Path $PSScriptRoot "sync_pull.sh")) -replace "`r", ""))
scp -q $lf pve:/tmp/sync_pull.sh
ssh pve "pct push 203 /tmp/sync_pull.sh /tmp/sync_pull.sh && pct exec 203 -- bash /tmp/sync_pull.sh && pct pull 203 /tmp/engine_sync.tgz /tmp/engine_sync.tgz"
scp -q pve:/tmp/engine_sync.tgz (Join-Path $stage "engine_sync.tgz")
Push-Location $stage
try {
    if (Test-Path "x") { Remove-Item -Recurse -Force "x" }
    New-Item -ItemType Directory -Force "x" | Out-Null
    tar xzf engine_sync.tgz -C x
    Copy-Item x\bridge\strategy_interface.py (Join-Path $root "engine\bridge") -Force
    Copy-Item x\python_strategies\inspect_strategy.py (Join-Path $root "engine") -Force
    Copy-Item x\python_strategies\strategies\*.py (Join-Path $root "engine\strategies") -Force
    if (Test-Path x\data\historical) { Copy-Item x\data\historical\*.csv (Join-Path $root "engine\data") -Force }
} finally { Pop-Location }
# run_backtest.py and bridge/__init__.py are NOT overwritten: they carry EdgeStack's
# own additions (engine/BORROWED.md).
$n = (Get-ChildItem (Join-Path $root 'engine\strategies') -Filter *.py).Count
$c = (Get-ChildItem (Join-Path $root 'engine\data') -Filter *.csv).Count
Write-Host "engine synced: $n strategy files on disk, $c histories"
