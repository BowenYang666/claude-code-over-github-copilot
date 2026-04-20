"""
Auto-generate copilot-config.yaml model mappings from GitHub Copilot API.

Fetches the current model list and creates dash->dot mappings for Claude models,
plus a wildcard fallback for everything else.

Usage: python update_models.py
"""
import json
import re
import os

EXTRA_HEADERS = '{"Editor-Version": "vscode/1.85.1", "Copilot-Integration-Id": "vscode-chat"}'
API_KEY_FILE = os.path.expanduser("~/.config/litellm/github_copilot/api-key.json")


def fetch_models():
    """Fetch available models from GitHub Copilot API."""
    import httpx

    with open(API_KEY_FILE) as f:
        info = json.load(f)

    token = info["token"]
    api_base = info["endpoints"]["api"]

    r = httpx.get(
        f"{api_base}/models",
        headers={
            "Authorization": f"Bearer {token}",
            "Editor-Version": "vscode/1.85.1",
            "Copilot-Integration-Id": "vscode-chat",
        },
        timeout=15,
    )
    data = r.json()
    return [
        m["id"]
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

    for mid in sorted(models):
        if needs_dash_mapping(mid):
            dv = dash_version(mid)
            lines.extend([
                f"  - model_name: {dv}",
                f"    litellm_params:",
                f"      model: github_copilot/{mid}",
                f"      extra_headers: {EXTRA_HEADERS}",
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
    if not os.path.exists(API_KEY_FILE):
        print(f"[ERROR] {API_KEY_FILE} not found. Start the proxy once first to authenticate.")
        return

    print("Fetching models from GitHub Copilot API...")
    models = fetch_models()
    print(f"Found {len(models)} chat models")

    claude_mappings = [m for m in models if needs_dash_mapping(m)]
    print(f"Models needing dash->dot mapping: {len(claude_mappings)}")
    for m in sorted(claude_mappings):
        print(f"  {dash_version(m):30s} -> {m}")

    config = generate_config(models)

    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "copilot-config.yaml")
    with open(config_path, "w") as f:
        f.write(config)

    print(f"\n[OK] Updated {config_path}")


if __name__ == "__main__":
    main()
