# Claude Code over GitHub Copilot-model endpoints - Setup Instructions

## Overview

This project allows you to use Claude Code with GitHub Copilot instead of Anthropic's servers. 
We can't send company information to Anthropic, but we already have an agreement with GitHub Copilot for our 
VSCode and IDEA agents.

The architecture uses:
- **Translation Layer**: LiteLLM proxy to translate between Claude Code and GitHub Copilot APIs
- **Local Proxy**: LiteLLM running locally (no external traffic to third parties)
- **GitHub Integration**: Direct connection to GitHub Copilot models we're already authorized to use

**References:**
- [Claude Code LLM Gateway Documentation](https://docs.anthropic.com/en/docs/claude-code/llm-gateway)
- [LiteLLM Quick Start](https://docs.litellm.ai/#quick-start-proxy---cli)
- [LiteLLM GitHub Copilot Provider](https://docs.litellm.ai/docs/providers/github_copilot)

## Quick Start

> **Windows users**: Use `.\run.ps1 <command>` in PowerShell instead of `make <command>`.
> See [Windows Quick Start](#windows-quick-start) below.

### 1. Install Claude Code (if not already installed)
```bash
# Install Claude Code desktop application via npm
make install-claude
```

This command installs Claude Code globally using npm. Requires Node.js and npm to be installed.

### 2. Initial Setup
```bash
# Set up environment, dependencies, and generate API keys
make setup
```

This command:
- Creates a Python virtual environment
- Installs required dependencies
- Generates random UUID-based API keys in `.env` file (only if it doesn't exist)

### 3. Configure Claude Code
```bash
# Configure Claude Code to use the local proxy
make claude-enable
```

This command:
- Backs up your existing Claude Code settings
- Configures Claude Code to use `http://localhost:4444` as the API endpoint
- Sets up model mappings (claude-sonnet-4, claude-opus-4, gpt-4)

### 4. Start the Proxy Server
- **Important**: The first run will trigger GitHub device authentication - follow the prompts in the terminal
```bash
# Start LiteLLM proxy server
make start
```

This will:
- Activate the virtual environment
- Start LiteLLM with the `copilot-config.yaml` configuration

### 5. Test the Connection
```bash
# Test that everything is working
make test
```

### 6. In your project folder, start Claude Code

```bash
# Open Claude Code in your project folder
claude
```

## Windows Quick Start

Windows users can use the PowerShell script `run.ps1` instead of `make`. All commands follow the same workflow.

### Prerequisites
- **Python 3.8+** installed and available in PATH
- **Node.js / npm** (for installing Claude Code)
- **PowerShell 5.1+** (included with Windows 10/11)

### Steps

```powershell
# 1. Install Claude Code (if not already installed)
.\run.ps1 install-claude

# 2. Set up environment, dependencies, and generate API keys
.\run.ps1 setup

# 3. Configure Claude Code to use the local proxy
.\run.ps1 claude-enable

# 4. Start LiteLLM proxy server (first run triggers GitHub device auth)
.\run.ps1 start

# 5. Test the connection (in a new terminal while proxy is running)
.\run.ps1 test

# 6. In your project folder, start Claude Code
claude
```

### Additional Windows Commands

```powershell
.\run.ps1 claude-status       # View current configuration and proxy status
.\run.ps1 claude-disable      # Restore Claude Code to default Anthropic servers
.\run.ps1 stop                # Stop the LiteLLM proxy server
.\run.ps1 list-models         # List all available GitHub Copilot models
.\run.ps1 list-models-enabled # List only enabled models
```

> **Note**: If you get an execution policy error, run:
> `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`

## Model Configuration

The proxy exposes these models to Claude Code. The Windows `claude-enable`
command selects `gpt-5.6-sol[1m]` by default and uses Luna for background
tasks/subagents.

| Claude Code Model | Maps to GitHub Copilot | Role |
|-------------------|------------------------|------|
| `gpt-5.6-sol` | `github_copilot/gpt-5.6-sol` | Primary/powerful |
| `gpt-5.6-terra` | `github_copilot/gpt-5.6-terra` | Versatile |
| `gpt-5.6-luna` | `github_copilot/gpt-5.6-luna` | Fast/background |

GitHub Copilot serves GPT-5.6 only through the OpenAI Responses API. The
explicit `mode: responses` entries in `copilot-config.yaml` are required;
letting GPT-5.6 fall through the wildcard route sends it to
`/chat/completions` and returns HTTP 400.

Claude Code can use a non-Anthropic model through LiteLLM's Anthropic Messages
compatibility endpoint. Run `claude` normally after `claude-enable`, or select
one explicitly with `claude --model gpt-5.6-sol[1m]`. The `[1m]` suffix makes
Claude Code budget and display a 1M context window. Auto-compaction uses the
upstream model's real 922K maximum prompt limit, leaving room before Copilot
rejects an oversized request. Gateway models appear in the
interactive `/model` picker when using Claude Code 2.1.129 or later; older
versions can still use the configured default or the `--model` argument.

## Additional Commands (Linux/macOS)

### Check Status
```bash
# View current Claude Code configuration and proxy status
make claude-status
```

### Restore Original Settings
```bash
# Restore Claude Code to default Anthropic servers
make claude-disable
```

### Stop the Proxy
```bash
# Stop the LiteLLM proxy server
make stop
```

## Troubleshooting

- **Authentication Issues**: The first `make start` (or `.\run.ps1 start`) will prompt for GitHub authentication
- **Connection Problems**: Use `make test` (or `.\run.ps1 test`) to verify the proxy is working
- **Configuration Issues**: Use `make claude-status` (or `.\run.ps1 claude-status`) to check your settings
- **Reset Everything**: Use `make claude-disable` then `make claude-enable` to reconfigure
- **Windows Execution Policy**: If PowerShell blocks the script, run `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`
