<#
.SYNOPSIS
    Claude Code over GitHub Copilot - Windows Setup & Management Script
.DESCRIPTION
    PowerShell equivalent of the Makefile for Windows users.
.PARAMETER Command
    The command to execute: help, setup, install-claude, start, stop, test,
    claude-enable, claude-disable, claude-status, list-models, list-models-enabled
.EXAMPLE
    .\run.ps1 setup
    .\run.ps1 start
    .\run.ps1 claude-enable
#>

param(
    [Parameter(Position = 0)]
    [ValidateSet(
        "help", "setup", "install-claude", "start", "stop", "test",
        "claude-enable", "claude-disable", "claude-status",
        "list-models", "list-models-enabled"
    )]
    [string]$Command = "help"
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

function Show-Help {
    Write-Host "Available commands:" -ForegroundColor Cyan
    Write-Host "  .\run.ps1 setup              - Set up virtual environment and dependencies"
    Write-Host "  .\run.ps1 install-claude      - Install Claude Code desktop application"
    Write-Host "  .\run.ps1 start              - Start LiteLLM proxy server"
    Write-Host "  .\run.ps1 stop               - Stop running processes"
    Write-Host "  .\run.ps1 test               - Test the proxy connection"
    Write-Host "  .\run.ps1 claude-enable       - Configure Claude Code to use local proxy"
    Write-Host "  .\run.ps1 claude-disable      - Restore Claude Code to default settings"
    Write-Host "  .\run.ps1 claude-status       - Show current Claude Code configuration"
    Write-Host "  .\run.ps1 list-models         - List all GitHub Copilot models"
    Write-Host "  .\run.ps1 list-models-enabled - List only enabled GitHub Copilot models"
}

function Invoke-Setup {
    Write-Host "Setting up environment..." -ForegroundColor Yellow

    # Create virtual environment
    if (-not (Test-Path "venv")) {
        Write-Host "Creating Python virtual environment..."
        python -m venv venv
    } else {
        Write-Host "[OK] Virtual environment already exists" -ForegroundColor Green
    }

    # Install dependencies
    Write-Host "Installing dependencies..."
    & .\venv\Scripts\pip.exe install -r requirements.txt

    # Generate .env if needed
    if (-not (Test-Path ".env")) {
        Write-Host "Generating .env file..."
        & .\venv\Scripts\python.exe generate_env.py
    } else {
        Write-Host "[OK] .env file already exists, skipping generation" -ForegroundColor Green
    }

    Write-Host "[OK] Setup complete" -ForegroundColor Green
}

function Install-Claude {
    Write-Host "Installing Claude Code desktop application..." -ForegroundColor Yellow

    if (Get-Command npm -ErrorAction SilentlyContinue) {
        Write-Host "Installing Claude Code via npm..."
        npm install -g @anthropic-ai/claude-code
        Write-Host "[OK] Claude Code installed successfully" -ForegroundColor Green
        Write-Host "Tip: You can now run '.\run.ps1 claude-enable' to configure it" -ForegroundColor Cyan
    } else {
        Write-Host "[ERROR] npm not found. Please install Node.js and npm first:" -ForegroundColor Red
        Write-Host "  https://nodejs.org/"
        Write-Host "  Then run: npm install -g @anthropic-ai/claude-code"
    }
}

function Start-Proxy {
    Write-Host "Starting LiteLLM proxy..." -ForegroundColor Yellow

    if (-not (Test-Path "venv")) {
        Write-Host "[ERROR] Virtual environment not found. Run '.\run.ps1 setup' first." -ForegroundColor Red
        return
    }

    if (-not (Test-Path ".env")) {
        Write-Host "[ERROR] .env file not found. Run '.\run.ps1 setup' first." -ForegroundColor Red
        return
    }

    # Fix proxy for httpx/LiteLLM on Windows.
    # httpx reads the Windows system proxy from the registry but may fail with
    # SSL errors during HTTPS CONNECT. Explicitly setting HTTPS_PROXY and
    # HTTP_PROXY via environment variables resolves this.
    if (-not $env:HTTPS_PROXY -and -not $env:HTTP_PROXY) {
        try {
            $regProxy = Get-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' -ErrorAction Stop
            if ($regProxy.ProxyEnable -eq 1 -and $regProxy.ProxyServer) {
                $proxyUrl = "http://$($regProxy.ProxyServer)"
                $env:HTTPS_PROXY = $proxyUrl
                $env:HTTP_PROXY = $proxyUrl
                Write-Host "[INFO] Detected system proxy ($($regProxy.ProxyServer)). Set HTTPS_PROXY=$proxyUrl" -ForegroundColor Yellow
            }
        } catch {
            # No registry proxy, nothing to do
        }
    }

    # Load .env variables into the current session
    Get-Content ".env" | ForEach-Object {
        if ($_ -match "^\s*([^#][^=]+?)\s*=\s*(.+)\s*$") {
            [System.Environment]::SetEnvironmentVariable($Matches[1], $Matches[2], "Process")
        }
    }

    Write-Host "Proxy will start on http://localhost:4444"
    Write-Host "Press Ctrl+C to stop the proxy" -ForegroundColor Cyan
    & .\venv\Scripts\litellm.exe --config copilot-config.yaml --port 4444
}

function Stop-Proxy {
    Write-Host "Stopping processes..." -ForegroundColor Yellow
    $procs = Get-Process -Name "litellm" -ErrorAction SilentlyContinue
    if ($procs) {
        $procs | Stop-Process -Force
        Write-Host "[OK] Processes stopped" -ForegroundColor Green
    } else {
        # Also try to find python processes running litellm
        $pyProcs = Get-Process -Name "python", "python3" -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -like "*litellm*" }
        if ($pyProcs) {
            $pyProcs | Stop-Process -Force
            Write-Host "[OK] Processes stopped" -ForegroundColor Green
        } else {
            Write-Host "No LiteLLM processes found" -ForegroundColor Yellow
        }
    }
}

function Test-Proxy {
    Write-Host "Testing proxy connection..." -ForegroundColor Yellow

    if (-not (Test-Path ".env")) {
        Write-Host "[ERROR] .env file not found. Run '.\run.ps1 setup' first." -ForegroundColor Red
        return
    }

    $masterKey = (Get-Content ".env" | Where-Object { $_ -match "^LITELLM_MASTER_KEY=" }) -replace "^LITELLM_MASTER_KEY=", "" -replace '"', ''

    $body = @{
        model    = "gpt-4"
        messages = @(@{ role = "user"; content = "Hello" })
    } | ConvertTo-Json -Depth 3

    try {
        $response = Invoke-RestMethod -Uri "http://localhost:4444/chat/completions" `
            -Method Post `
            -ContentType "application/json" `
            -Headers @{ Authorization = "Bearer $masterKey" } `
            -Body $body

        Write-Host ($response | ConvertTo-Json -Depth 5)
        Write-Host "[OK] Test completed successfully!" -ForegroundColor Green
    } catch {
        Write-Host "[ERROR] Test failed: $_" -ForegroundColor Red
        Write-Host "Make sure the proxy is running (.\run.ps1 start)" -ForegroundColor Yellow
    }
}

function Enable-ClaudeProxy {
    Write-Host "Configuring Claude Code to use local proxy..." -ForegroundColor Yellow

    if (-not (Test-Path ".env")) {
        Write-Host "[ERROR] .env file not found. Run '.\run.ps1 setup' first." -ForegroundColor Red
        return
    }

    $masterKey = (Get-Content ".env" | Where-Object { $_ -match "^LITELLM_MASTER_KEY=" }) -replace "^LITELLM_MASTER_KEY=", "" -replace '"', ''

    if ([string]::IsNullOrWhiteSpace($masterKey)) {
        Write-Host "[ERROR] LITELLM_MASTER_KEY not found in .env" -ForegroundColor Red
        return
    }

    $settingsFile = Join-Path $env:USERPROFILE ".claude\settings.json"

    # Backup existing settings
    if (Test-Path $settingsFile) {
        $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
        $backupFile = "$settingsFile.backup.$timestamp"
        Copy-Item $settingsFile $backupFile
        Write-Host "Backed up existing settings to $backupFile"
    }

    & .\venv\Scripts\python.exe scripts\claude_enable.py $masterKey
    Write-Host "[OK] Claude Code configured to use local proxy" -ForegroundColor Green
    Write-Host "Tip: Make sure to run '.\run.ps1 start' to start the LiteLLM proxy server" -ForegroundColor Cyan
}

function Disable-ClaudeProxy {
    Write-Host "Restoring Claude Code to default settings..." -ForegroundColor Yellow

    $settingsFile = Join-Path $env:USERPROFILE ".claude\settings.json"

    # Backup current proxy settings
    if (Test-Path $settingsFile) {
        $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
        $backupFile = "$settingsFile.proxy_backup.$timestamp"
        Copy-Item $settingsFile $backupFile
        Write-Host "Backed up proxy settings to $backupFile"
    }

    # Try to restore from latest backup
    $backups = Get-ChildItem -Path (Join-Path $env:USERPROFILE ".claude") -Filter "settings.json.backup.*" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending

    if ($backups) {
        $latestBackup = $backups[0].FullName
        Copy-Item $latestBackup $settingsFile
        Write-Host "[OK] Restored settings from $latestBackup" -ForegroundColor Green
    } else {
        python scripts\claude_disable.py
    }
}

function Show-ClaudeStatus {
    Write-Host "Current Claude Code configuration:" -ForegroundColor Cyan
    Write-Host "=================================="

    $settingsFile = Join-Path $env:USERPROFILE ".claude\settings.json"

    if (Test-Path $settingsFile) {
        Write-Host "Settings file: $settingsFile"
        Write-Host ""
        $content = Get-Content $settingsFile -Raw
        try {
            $content | ConvertFrom-Json | ConvertTo-Json -Depth 5
        } catch {
            Write-Host $content
        }
        Write-Host ""

        if ($content -match "localhost:4444") {
            Write-Host "Status: Using local proxy" -ForegroundColor Yellow
            try {
                $health = Invoke-RestMethod -Uri "http://localhost:4444/health" -TimeoutSec 3 -ErrorAction Stop
                Write-Host "[OK] Proxy server: Running" -ForegroundColor Green
            } catch {
                Write-Host "[ERROR] Proxy server: Not running (run '.\run.ps1 start')" -ForegroundColor Red
            }
        } else {
            Write-Host "Status: Using default Anthropic servers" -ForegroundColor Cyan
        }
    } else {
        Write-Host "No settings file found - using Claude Code defaults"
        Write-Host "Status: Using default Anthropic servers" -ForegroundColor Cyan
    }
}

# Main dispatch
switch ($Command) {
    "help"                  { Show-Help }
    "setup"                 { Invoke-Setup }
    "install-claude"        { Install-Claude }
    "start"                 { Start-Proxy }
    "stop"                  { Stop-Proxy }
    "test"                  { Test-Proxy }
    "claude-enable"         { Enable-ClaudeProxy }
    "claude-disable"        { Disable-ClaudeProxy }
    "claude-status"         { Show-ClaudeStatus }
    "list-models"           { & .\list-copilot-models.ps1 }
    "list-models-enabled"   { & .\list-copilot-models.ps1 -EnabledOnly }
    default                 { Show-Help }
}
