"""
Auto-generate copilot-config.yaml model mappings from GitHub Copilot API.

Fetches the current model list and creates dash->dot mappings for Claude models,
explicit Responses API routes for response-only models, and a wildcard fallback.

Usage: python update_models.py
"""
import json
import re
import os
import urllib.request

EXTRA_HEADERS = '{"Editor-Version": "vscode/1.95.0", "Copilot-Integration-Id": "vscode-chat"}'
ACCESS_TOKEN_FILE = os.path.expanduser("~/.config/litellm/github_copilot/access-token")


def get_chat_token():
    """Exchange the cached GitHub OAuth token for a short-lived Copilot token."""
    with open(ACCESS_TOKEN_FILE, encoding="utf-8") as f:
        access_token = f.read().strip()

    request = urllib.request.Request(
        "https://api.github.com/copilot_internal/v2/token",
        headers={
            "Authorization": f"Bearer {access_token}",
            "User-Agent": "GitHubCopilotChat/0.30.0",
        },
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.load(response)


def fetch_models():
    """Fetch available models from GitHub Copilot API."""
    info = get_chat_token()
    token = info["token"]
    api_base = info["endpoints"]["api"]

    request = urllib.request.Request(
        f"{api_base}/models",
        headers={
            "Authorization": f"Bearer {token}",
            "Editor-Version": "vscode/1.95.0",
            "Copilot-Integration-Id": "vscode-chat",
            "User-Agent": "GitHubCopilotChat/0.30.0",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        data = json.load(response)
    return [
        m
        for m in data.get("data", [])
        if m.get("capabilities", {}).get("type") == "chat"
    ]


def needs_dash_mapping(model_id):
    """Check if a model ID has a dot-version that Claude Code would send with dashes."""
    return bool(re.match(r"^(claude-\w+)-(\d+)\.(\d+)(.*)$", model_id))


def dash_version(model_id):
    """Convert claude-opus-4.7 -> claude-opus-4-7"""
    m = re.match(r"^(claude-\w+)-(\d+)\.(\d+)(.*)$", model_id)
    if m:
        base, major, minor, suffix = m.groups()
        return f"{base}-{major}-{minor}{suffix}"
    return None


def generate_config(models):
    """Generate copilot-config.yaml content."""
    model_ids = [model["id"] for model in models]
    lines = [
        "# GitHub Copilot uses dots in version numbers (claude-opus-4.7)",
        "# but Claude Code uses dashes (claude-opus-4-7).",
        "# We map dash-versions to dot-versions, and use wildcard for everything else.",
        "#",
        "# Run `python update_models.py` or `.\\run.ps1 update-models` to refresh.",
        "#",
        f"# Last updated with {len(models)} chat models.",
        "",
        "model_list:",
        "  # === Auto-compatible mappings (dash -> dot conversion) ===",
    ]

    for mid in sorted(model_ids):
        if needs_dash_mapping(mid):
            dv = dash_version(mid)
            lines.extend([
                f"  - model_name: {dv}",
                f"    litellm_params:",
                f"      model: github_copilot/{mid}",
                f"      extra_headers: {EXTRA_HEADERS}",
            ])

    responses_only = sorted(
        [
            model for model in models
            if "/responses" in model.get("supported_endpoints", [])
            and "/chat/completions" not in model.get("supported_endpoints", [])
        ],
        key=lambda model: model["id"],
    )
    if responses_only:
        lines.extend(["", "  # === Responses API-only models ==="])
        for model in responses_only:
            mid = model["id"]
            lines.extend([
                f"  - model_name: {mid}",
                "    model_info:",
                "      mode: responses",
                "    litellm_params:",
                f"      model: github_copilot/{mid}",
            ])

    lines.extend([
        "",
        "  # === Wildcard fallback: forwards any other model name as-is ===",
        '  - model_name: "*"',
        "    litellm_params:",
        '      model: "github_copilot/*"',
        f"      extra_headers: {EXTRA_HEADERS}",
        "",
        "litellm_settings:",
        "  drop_params: true",
        "",
    ])

    return "\n".join(lines)


def main():
    if not os.path.exists(ACCESS_TOKEN_FILE):
        print(f"[ERROR] {ACCESS_TOKEN_FILE} not found. Start the proxy once first to authenticate.")
        return

    print("Fetching models from GitHub Copilot API...")
    models = fetch_models()
    print(f"Found {len(models)} chat models")

    claude_mappings = [m["id"] for m in models if needs_dash_mapping(m["id"])]
    responses_only = [
        m["id"] for m in models
        if "/responses" in m.get("supported_endpoints", [])
        and "/chat/completions" not in m.get("supported_endpoints", [])
    ]
    print(f"Models needing dash->dot mapping: {len(claude_mappings)}")
    for m in sorted(claude_mappings):
        print(f"  {dash_version(m):30s} -> {m}")
    print(f"Responses API-only models: {len(responses_only)}")
    for model_id in sorted(responses_only):
        print(f"  {model_id}")

    config = generate_config(models)

    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "copilot-config.yaml")
    with open(config_path, "w") as f:
        f.write(config)

    print(f"\n[OK] Updated {config_path}")


if __name__ == "__main__":
    main()
