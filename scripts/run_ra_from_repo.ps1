$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $RootDir

$PythonCandidates = @(
    (Join-Path $RootDir ".venv\Scripts\python.exe"),
    (Join-Path $RootDir ".venv\python.exe")
)

$PythonBin = $null
foreach ($Candidate in $PythonCandidates) {
    if (Test-Path $Candidate) {
        $PythonBin = $Candidate
        break
    }
}
if (-not $PythonBin) {
    $PyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($PyLauncher) {
        $PythonBin = "py"
    } else {
        $PythonCommand = Get-Command python -ErrorAction SilentlyContinue
        if ($PythonCommand) {
            $PythonBin = $PythonCommand.Source
        }
    }
}

if (-not $PythonBin) {
    throw "Could not locate a usable Python interpreter for archaResearch Assistant."
}

$env:PYTHONPATH = if ($env:PYTHONPATH) { "$RootDir\src;$env:PYTHONPATH" } else { "$RootDir\src" }
if (-not $env:RA_BASE_URL) {
    $env:RA_BASE_URL = "http://127.0.0.1:8001"
}

if ($PythonBin -eq "py") {
    & py -3 -m rag.cli @args
} else {
    & $PythonBin -m rag.cli @args
}
exit $LASTEXITCODE
