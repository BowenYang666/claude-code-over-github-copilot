#!/usr/bin/env python3
"""
Script to enable Claude Code proxy configuration.
Usage: claude_enable.py <master_key>
"""
import json
import sys
import os
from pathlib import Path

def main():
    if len(sys.argv) != 2:
        print("Usage: claude_enable.py <master_key>")
        sys.exit(1)

    master_key = sys.argv[1]
    claude_dir = Path(os.environ.get('CLAUDE_CONFIG_DIR') or (Path.home() / '.claude'))
    settings_file = claude_dir / 'settings.json'

    # Create .claude directory if it doesn't exist
    claude_dir.mkdir(exist_ok=True)

    # Load existing settings or create empty dict
    settings = {}
    if settings_file.exists():
        try:
            with open(settings_file, 'r') as f:
                settings = json.load(f)
        except (json.JSONDecodeError, IOError):
            settings = {}

    # Add proxy configuration. GPT-5.6 is exposed by the gateway under its
    # native model id; LiteLLM translates Claude Code's Anthropic requests to
    # the Copilot Responses API.
    settings['env'] = {
        'ANTHROPIC_AUTH_TOKEN': master_key,
        'ANTHROPIC_BASE_URL': 'http://localhost:4444',
        # Claude Code uses the [1m] suffix to advertise and budget an extended
        # context model. The proxy/upstream still receives gpt-5.6-sol.
        'ANTHROPIC_MODEL': 'gpt-5.6-sol[1m]',
        'ANTHROPIC_DEFAULT_OPUS_MODEL': 'gpt-5.6-sol[1m]',
        # Built-in Research/Explore/Plan agents can request the Sonnet alias.
        # Route that alias and all subagents to the balanced Terra model.
        'ANTHROPIC_DEFAULT_SONNET_MODEL': 'gpt-5.6-terra[1m]',
        'CLAUDE_CODE_SUBAGENT_MODEL': 'gpt-5.6-terra[1m]',
        # Keep lightweight background features on Luna.
        'ANTHROPIC_SMALL_FAST_MODEL': 'gpt-5.6-luna',
        'ANTHROPIC_DEFAULT_HAIKU_MODEL': 'gpt-5.6-luna',
        # Copilot reports a 1.05M total context but allows 922K prompt tokens.
        # Compact against the real prompt ceiling instead of waiting for 1M.
        'CLAUDE_CODE_AUTO_COMPACT_WINDOW': '922000',
        'CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY': '1'
    }

    # Keep the persisted model selection consistent with the environment
    # override so /status and resumed sessions also identify the 1M model.
    settings['model'] = 'gpt-5.6-sol[1m]'

    # Add schema if it's a new file
    if '$schema' not in settings:
        settings['$schema'] = 'https://json.schemastore.org/claude-code-settings.json'

    # Save updated settings
    with open(settings_file, 'w') as f:
        json.dump(settings, f, indent=2)

    print('✅ Updated settings while preserving existing configuration')

if __name__ == '__main__':
    main()