<#
.SYNOPSIS
    Start V2RayN and then launch the Claude Code proxy.
.DESCRIPTION
    1. Starts V2RayN (if not already running)
    2. Waits 5 seconds for the VPN to initialize
    3. Launches the LiteLLM proxy via run.ps1
.EXAMPLE
    .\start-all.ps1
#>

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

# Load V2RAY_PATH from .env if present (so the path isn't hardcoded per-machine)
$v2rayPath = $null
if (Test-Path ".env") {
    Get-Content ".env" | ForEach-Object {
        if ($_ -match '^\s*V2RAY_PATH\s*=\s*"?([^"#\r\n]+?)"?\s*$') {
            $v2rayPath = $Matches[1].Trim()
        }
    }
}
if (-not $v2rayPath) {
    # Fallback default; override by setting V2RAY_PATH in .env
    $v2rayPath = "D:\doc\vpn\v2rayN-windows-64\v2rayN.exe"
}

# Step 1: Start V2RayN if not already running
if (Get-Process -Name "v2rayN" -ErrorAction SilentlyContinue) {
    Write-Host "[OK] V2RayN is already running" -ForegroundColor Green
} else {
    if (Test-Path $v2rayPath) {
        Write-Host "Starting V2RayN..." -ForegroundColor Yellow
        Start-Process -FilePath $v2rayPath
        Write-Host "[OK] V2RayN started" -ForegroundColor Green
    } else {
        Write-Host "[ERROR] V2RayN not found at $v2rayPath" -ForegroundColor Red
        exit 1
    }
}

# Step 2: Wait for VPN to initialize
Write-Host "Waiting 5 seconds for VPN to initialize..." -ForegroundColor Yellow
Start-Sleep -Seconds 5

# Step 3: Start the proxy
Write-Host "Starting Claude Code proxy..." -ForegroundColor Cyan
& .\run.ps1
