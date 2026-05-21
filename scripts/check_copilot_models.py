"""List Claude models currently available on your GitHub Copilot account.

Uses your cached Copilot access token to query the live /models endpoint
(automatically picks the right endpoint for free vs. enterprise accounts).

Usage:
    python scripts/check_copilot_models.py            # list claude models
    python scripts/check_copilot_models.py --all      # list every chat model
"""
import json
import os
import sys
import urllib.request

TOKEN_PATH = os.path.expandvars(r"%USERPROFILE%\.config\litellm\github_copilot\access-token")


def get_chat_token():
    token = open(TOKEN_PATH, encoding="utf-8").read().strip()
    req = urllib.request.Request(
        "https://api.github.com/copilot_internal/v2/token",
        headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": "GitHubCopilotChat/0.30.0",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)


def list_models(filter_claude: bool = True):
    resp = get_chat_token()
    api_base = resp["endpoints"]["api"]
    chat_token = resp["token"]

    req = urllib.request.Request(
        f"{api_base}/models",
        headers={
            "Authorization": f"Bearer {chat_token}",
            "Editor-Version": "vscode/1.95.0",
            "Copilot-Integration-Id": "vscode-chat",
            "User-Agent": "GitHubCopilotChat/0.30.0",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        models = json.load(r)

    print(f"endpoint: {api_base}")
    print(f"sku:      {resp.get('sku')}")
    print()
    print(f"{'model id':42s} {'ctx':>9} {'out':>7} policy")
    print("-" * 75)
    for m in models.get("data", []):
        cap = m.get("capabilities", {})
        if cap.get("type") != "chat":
            continue
        mid = m.get("id", "?")
        if filter_claude and "claude" not in mid.lower():
            continue
        lim = cap.get("limits", {})
        pol = (m.get("policy") or {}).get("state", "enabled")
        print(
            f"  {mid:40s} {lim.get('max_context_window_tokens', '?'):>9} "
            f"{lim.get('max_output_tokens', '?'):>7} {pol}"
        )


if __name__ == "__main__":
    list_models(filter_claude="--all" not in sys.argv)
