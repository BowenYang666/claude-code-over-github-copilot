"""
Start LiteLLM proxy with token monitor middleware.
Replaces direct `litellm` CLI invocation so we can inject our FastAPI middleware.
"""

import sys
from token_monitor import install_monitor
from litellm.proxy.proxy_server import app

# Install request-side token monitor middleware before server starts
install_monitor(app)

# Hand off to LiteLLM's CLI
from litellm.proxy.proxy_cli import run_server

sys.argv = [
    "litellm",
    "--config", "copilot-config.yaml",
    "--port", "4444",
]
run_server()
