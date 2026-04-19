$ErrorActionPreference = "Stop"

$BaseUrl = if ($env:BASE_URL) { $env:BASE_URL } else { "http://127.0.0.1:8001" }
$TimeoutSeconds = if ($env:TIMEOUT_SECONDS) { [int]$env:TIMEOUT_SECONDS } else { 30 }
$PollInterval = if ($env:POLL_INTERVAL) { [int]$env:POLL_INTERVAL } else { 1 }
$RunDiagnostics = if ($env:RUN_DIAGNOSTICS) { $env:RUN_DIAGNOSTICS -ne "0" } else { $true }
$Token = if ($env:API_BEARER_TOKEN_SMOKE) { $env:API_BEARER_TOKEN_SMOKE } else { $env:API_BEARER_TOKEN }

function Get-Headers {
    $headers = @{ "Content-Type" = "application/json" }
    if ($Token) {
        $headers["Authorization"] = "Bearer $Token"
    }
    return $headers
}

function Write-Ok([string] $Message) {
    Write-Output "[OK] $Message"
}

function Invoke-JsonRequest {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Method,

        [Parameter(Mandatory = $true)]
        [string] $Uri,

        [string] $Body
    )

    $params = @{
        Method = $Method
        Uri = $Uri
        Headers = (Get-Headers)
    }
    if ($Body) {
        $params["Body"] = $Body
    }
    return Invoke-RestMethod @params
}

$health = Invoke-JsonRequest -Method Get -Uri "$BaseUrl/api/health"
if (-not $health.PSObject.Properties["status"]) {
    throw "Health payload missing expected shape."
}
Write-Ok "Health endpoint reachable"

$queryBody = @{
    query = "smoke test query"
    limit = 1
    limit_scope = "chunks"
    chunks_per_paper = 1
} | ConvertTo-Json -Depth 5

$start = Invoke-JsonRequest -Method Post -Uri "$BaseUrl/api/query" -Body $queryBody
if ($start.status -notin @("running", "completed", "idle")) {
    throw "Query start payload invalid."
}
Write-Ok "Query start accepted"

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
$terminal = $null
while ((Get-Date) -lt $deadline) {
    $status = Invoke-JsonRequest -Method Get -Uri "$BaseUrl/api/query/status"
    if ($status.status -in @("completed", "failed", "cancelled", "idle")) {
        $terminal = $status.status
        break
    }
    Start-Sleep -Seconds $PollInterval
}

if (-not $terminal) {
    throw "Timed out waiting for /api/query/status terminal state."
}
Write-Ok "Query reached terminal state: $terminal"
if ($terminal -in @("failed", "cancelled")) {
    throw "Query terminal state indicates failure: $terminal"
}

if ($RunDiagnostics) {
    $diag = Invoke-JsonRequest -Method Get -Uri "$BaseUrl/api/diagnostics"
    if (-not $diag.PSObject.Properties["ok"] -or -not $diag.PSObject.Properties["checks"]) {
        throw "Diagnostics payload missing expected keys."
    }
    Write-Ok "Diagnostics endpoint reachable"
}

Write-Output "Smoke workflow passed."
