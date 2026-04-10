<#
.SYNOPSIS
    List available GitHub Copilot models in copilot-config.yaml format.
.PARAMETER EnabledOnly
    If specified, only show enabled models.
.EXAMPLE
    .\list-copilot-models.ps1
    .\list-copilot-models.ps1 -EnabledOnly
#>

param(
    [switch]$EnabledOnly
)

$ErrorActionPreference = "Stop"

# Locate the GitHub Copilot token
$tokenPaths = @(
    (Join-Path $env:USERPROFILE ".config\litellm\github_copilot\access-token"),
    (Join-Path $env:LOCALAPPDATA "litellm\github_copilot\access-token")
)

$tokenFile = $tokenPaths | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $tokenFile) {
    Write-Host "[ERROR] GitHub Copilot token not found." -ForegroundColor Red
    Write-Host "Searched paths:"
    $tokenPaths | ForEach-Object { Write-Host "  $_" }
    Write-Host "Run '.\run.ps1 start' first to authenticate with GitHub"
    exit 1
}

$token = (Get-Content $tokenFile -Raw).Trim()

Write-Host "# GitHub Copilot Models Available"
Write-Host "# Generated on $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host "# Usage: Copy the desired models to your copilot-config.yaml"
Write-Host ""

if ($EnabledOnly) {
    Write-Host "# Showing only enabled models"
} else {
    Write-Host "# Showing all models (enabled and unconfigured)"
}

Write-Host ""
Write-Host "model_list:"

try {
    $response = Invoke-RestMethod -Uri "https://api.githubcopilot.com/models" `
        -Headers @{ Authorization = "Bearer $token" } `
        -TimeoutSec 30

    $chatModels = $response.data | Where-Object { $_.capabilities.type -eq "chat" }

    if ($EnabledOnly) {
        $chatModels = $chatModels | Where-Object {
            $null -eq $_.policy -or $_.policy.state -eq "enabled"
        }
    }

    foreach ($model in $chatModels) {
        $state = if ($model.policy.state) { $model.policy.state } else { "enabled" }
        $maxOutput = $model.capabilities.limits.max_output_tokens
        $maxContext = $model.capabilities.limits.max_context_window_tokens

        Write-Host "  - model_name: $($model.id)"
        Write-Host "    litellm_params:"
        Write-Host "      model: github_copilot/$($model.id)"
        Write-Host '      extra_headers: {"Editor-Version": "vscode/1.85.1", "Copilot-Integration-Id": "vscode-chat"}'
        Write-Host "    # $($model.name) ($($model.vendor)) - $state"
        Write-Host "    # Max tokens: $maxOutput, Context: $maxContext"
        Write-Host ""
    }
} catch {
    Write-Host "[ERROR] Failed to fetch models: $_" -ForegroundColor Red
    Write-Host "Make sure the proxy has been started at least once to complete GitHub authentication." -ForegroundColor Yellow
}
