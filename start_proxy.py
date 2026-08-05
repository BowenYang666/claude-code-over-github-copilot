"""
Start LiteLLM proxy with token monitor middleware.
Replaces direct `litellm` CLI invocation so we can inject our FastAPI middleware.
"""

import sys
from token_monitor import install_monitor


def install_litellm_compat_patches():
    """Apply narrowly scoped fixes needed by the pinned LiteLLM release."""
    from litellm.llms.anthropic.experimental_pass_through.adapters.streaming_iterator import (
        AnthropicStreamWrapper,
    )

    original = AnthropicStreamWrapper._should_start_new_content_block

    def ignore_empty_choices(self, chunk):
        # Responses API streams can include usage/metadata chunks with no
        # choices. LiteLLM 1.95 indexes choices[0] and otherwise aborts an
        # already successful Claude Code response with IndexError.
        if not getattr(chunk, "choices", None):
            return False
        return original(self, chunk)

    AnthropicStreamWrapper._should_start_new_content_block = ignore_empty_choices


install_litellm_compat_patches()

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
