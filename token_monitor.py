"""
Token usage monitor for LiteLLM proxy.
Counts input tokens of /v1/messages requests using tiktoken (o200k_base).

Strategy: intercept the REQUEST body (always complete JSON), count tokens
locally, then re-inject the body for downstream processing. This avoids the
SSE streaming-response complications of the previous response-side approach.

Note: tiktoken is OpenAI's tokenizer. Claude uses a different tokenizer, so
the count is approximate (typically within ±5% for English/code, may overshoot
by 10-20% for heavy Chinese text). Good enough for a "remaining context" gauge.
"""

import json
import tiktoken

# GitHub Copilot enforces 128K input token limit for all models
COPILOT_MAX_INPUT = 128000

# Use o200k_base (GPT-4o tokenizer) - friendlier to Chinese than cl100k_base
_encoder = tiktoken.get_encoding("o200k_base")


def _count_tokens(text: str) -> int:
    if not text:
        return 0
    try:
        return len(_encoder.encode(text, disallowed_special=()))
    except Exception:
        # Fallback: rough char-based estimate
        return len(text) // 3


def estimate_input_tokens(data: dict) -> int:
    """Estimate total input tokens from an Anthropic /v1/messages request body."""
    total = 0

    # System prompt (can be string or list of content blocks)
    system = data.get("system")
    if isinstance(system, str):
        total += _count_tokens(system)
    elif isinstance(system, list):
        for block in system:
            if isinstance(block, dict):
                total += _count_tokens(block.get("text", ""))

    # Messages
    for msg in data.get("messages", []):
        content = msg.get("content")
        if isinstance(content, str):
            total += _count_tokens(content)
        elif isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type")
                if btype == "text":
                    total += _count_tokens(block.get("text", ""))
                elif btype == "tool_use":
                    total += _count_tokens(json.dumps(block.get("input", {})))
                    total += _count_tokens(block.get("name", ""))
                elif btype == "tool_result":
                    tc = block.get("content")
                    if isinstance(tc, str):
                        total += _count_tokens(tc)
                    elif isinstance(tc, list):
                        for sub in tc:
                            if isinstance(sub, dict):
                                total += _count_tokens(sub.get("text", ""))
                elif btype == "image":
                    # Rough estimate for images: Claude charges ~1500 tokens per image
                    total += 1500

    # Tools (function definitions)
    for tool in data.get("tools", []) or []:
        total += _count_tokens(json.dumps(tool))

    # Add small overhead for message structure (role markers etc.)
    total += len(data.get("messages", [])) * 4
    return total


def print_token_bar(input_tokens: int, model: str = "?"):
    remaining = COPILOT_MAX_INPUT - input_tokens
    pct = (input_tokens / COPILOT_MAX_INPUT) * 100

    if pct >= 90:
        color, icon = "\033[1;31m", "🔴"
    elif pct >= 75:
        color, icon = "\033[31m", "🟠"
    elif pct >= 50:
        color, icon = "\033[33m", "🟡"
    else:
        color, icon = "\033[32m", "🟢"
    reset = "\033[0m"

    bar_len = 30
    filled = min(bar_len, int(bar_len * pct / 100))
    bar = "█" * filled + "░" * (bar_len - filled)

    print(flush=True)
    print(
        f"{color}{icon} [{bar}] {pct:.0f}% | "
        f"input: ~{input_tokens:,} / {COPILOT_MAX_INPUT:,} | "
        f"remaining: ~{remaining:,} | "
        f"model: {model}{reset}",
        flush=True,
    )
    if pct >= 80:
        print(
            f"{color}   ⚠️  Context filling up — run /compact in Claude Code soon{reset}",
            flush=True,
        )


def install_monitor(app):
    """Install request-side token monitor as pure ASGI middleware.

    BaseHTTPMiddleware (@app.middleware('http')) has a known issue where
    body re-injection via request._receive doesn't reach call_next's inner
    app. Pure ASGI middleware avoids that by replacing the receive callable
    directly.
    """

    app.add_middleware(_TokenMonitorASGIMiddleware)
    print(
        "\033[36m[TokenMonitor] Request-side ASGI middleware installed "
        "(tiktoken o200k_base)\033[0m",
        flush=True,
    )


class _TokenMonitorASGIMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if "/v1/messages" not in path or "count_tokens" in path:
            await self.app(scope, receive, send)
            return

        # Buffer the entire request body
        body = b""
        more_body = True
        while more_body:
            message = await receive()
            if message["type"] == "http.request":
                body += message.get("body", b"")
                more_body = message.get("more_body", False)
            elif message["type"] == "http.disconnect":
                # Client disconnected before body fully received
                await self.app(scope, receive, send)
                return

        # Estimate tokens (best-effort)
        try:
            data = json.loads(body) if body else {}
            tokens = estimate_input_tokens(data)
            model = data.get("model", "?")
            if tokens > 0:
                print_token_bar(tokens, model)
        except Exception as e:
            print(f"\033[33m[TokenMonitor] estimate failed: {e}\033[0m", flush=True)

        # Replay the body to downstream via a new receive() function
        body_consumed = False

        async def replay_receive():
            nonlocal body_consumed
            if not body_consumed:
                body_consumed = True
                return {"type": "http.request", "body": body, "more_body": False}
            # After body is consumed, forward whatever the real client sends
            # (typically http.disconnect when the request finishes)
            return await receive()

        await self.app(scope, replay_receive, send)
