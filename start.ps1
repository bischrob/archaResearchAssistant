$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RootDir

& (Join-Path $RootDir "scripts\run_ra_from_repo.ps1") start --foreground @args
exit $LASTEXITCODE
