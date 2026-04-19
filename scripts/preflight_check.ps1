$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $RootDir

& (Join-Path $RootDir "scripts\run_ra_from_repo.ps1") preflight --port ($(if ($args.Count -gt 0) { $args[0] } else { if ($env:PORT) { $env:PORT } else { 8000 } }))
exit $LASTEXITCODE
