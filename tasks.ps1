param(
    [Parameter(Position = 0)]
    [string] $Target = "help"
)

$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RootDir

function Get-RepoPython {
    $candidates = @(
        (Join-Path $RootDir ".venv\Scripts\python.exe"),
        (Join-Path $RootDir ".venv\python.exe")
    )
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        return "py"
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        return $python.Source
    }

    throw "Could not locate a Python interpreter for repo tasks."
}

function Invoke-RepoPython {
    param(
        [Parameter(Mandatory = $true)]
        [string[]] $Arguments,

        [switch] $RunE2E
    )

    $python = Get-RepoPython
    $env:PYTHONPATH = if ($env:PYTHONPATH) { "$RootDir\src;$env:PYTHONPATH" } else { "$RootDir\src" }
    if ($RunE2E) {
        $env:RUN_E2E = "1"
    }

    if ($python -eq "py") {
        & py -3 @Arguments
    } else {
        & $python @Arguments
    }
    $code = $LASTEXITCODE

    if ($RunE2E) {
        Remove-Item Env:RUN_E2E -ErrorAction SilentlyContinue
    }

    if ($code -ne 0) {
        exit $code
    }
}

function Get-AuthHeaders {
    $headers = @{ "Content-Type" = "application/json" }
    if ($env:API_BEARER_TOKEN) {
        $headers["Authorization"] = "Bearer $($env:API_BEARER_TOKEN)"
    }
    return $headers
}

switch ($Target) {
    "help" {
        @'
Available targets:
  .\tasks.ps1 preflight              # Validate local prerequisites and config
  .\tasks.ps1 start                  # Start Neo4j + API/web GUI
  .\tasks.ps1 status                 # Check API/version/health/diagnostics
  .\tasks.ps1 diagnostics            # Show diagnostics summary
  .\tasks.ps1 test                   # Run non-e2e pytest tests (safe default)
  .\tasks.ps1 test-unit              # Run non-e2e pytest tests
  .\tasks.ps1 test-e2e               # Run live e2e tests (requires RUN_E2E=1)
  .\tasks.ps1 smoke                  # Hit health/query/diagnostics endpoints
  .\tasks.ps1 sync-example           # Example sync trigger via API
  .\tasks.ps1 ingest-preview-example # Example ingest preview trigger via API
'@ | Write-Output
    }
    "preflight" {
        & (Join-Path $RootDir "scripts\run_ra_from_repo.ps1") preflight
        exit $LASTEXITCODE
    }
    "start" {
        & (Join-Path $RootDir "scripts\run_ra_from_repo.ps1") start
        exit $LASTEXITCODE
    }
    "status" {
        & (Join-Path $RootDir "scripts\run_ra_from_repo.ps1") status
        exit $LASTEXITCODE
    }
    "diagnostics" {
        & (Join-Path $RootDir "scripts\run_ra_from_repo.ps1") diagnostics
        exit $LASTEXITCODE
    }
    "test" {
        Invoke-RepoPython -Arguments @("-m", "pytest", "-m", "not e2e")
    }
    "test-unit" {
        Invoke-RepoPython -Arguments @("-m", "pytest", "-m", "not e2e")
    }
    "test-e2e" {
        Invoke-RepoPython -Arguments @("-m", "pytest", "-m", "e2e") -RunE2E
    }
    "smoke" {
        & (Join-Path $RootDir "scripts\smoke_repo_workflow.ps1")
        exit $LASTEXITCODE
    }
    "sync-example" {
        $headers = Get-AuthHeaders
        $body = @{
            dry_run = $true
            source_mode = "zotero_db"
            run_ingest = $false
        } | ConvertTo-Json -Depth 5
        $response = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8001/api/sync" -Headers $headers -Body $body
        $response | ConvertTo-Json -Depth 10
    }
    "ingest-preview-example" {
        $headers = Get-AuthHeaders
        $body = @{
            mode = "batch"
            partial_count = 3
            override_existing = $false
        } | ConvertTo-Json -Depth 5
        $response = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8001/api/ingest/preview" -Headers $headers -Body $body
        $response | ConvertTo-Json -Depth 10
    }
    default {
        Write-Error "Unknown target: $Target"
        exit 1
    }
}
