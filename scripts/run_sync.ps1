# Quant_Bot Automated Daily Sync Runner
param(
    [int]$WaitSeconds = 120,
    [switch]$Force
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDir
$pythonExe = Join-Path $projectRoot "venv\Scripts\python.exe"
$syncScript = Join-Path $scriptDir "daily_sync.py"

# Wait specified seconds (default 2 minutes) for network/Wi-Fi to stabilize
if ($WaitSeconds -gt 0) {
    Start-Sleep -Seconds $WaitSeconds
}

$argsList = @($syncScript)
if ($Force) {
    $argsList += "--force"
}

# Run python script quietly
Start-Process -FilePath $pythonExe -ArgumentList $argsList -WorkingDirectory $projectRoot -Wait -WindowStyle Hidden
