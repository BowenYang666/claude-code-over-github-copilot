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
import re
import tiktoken


# Claude Code sends dated model ids for some defaults / the small-fast model,
# e.g. "claude-haiku-4-5-20251001". GitHub Copilot only knows the undated id
# ("claude-haiku-4.5"). Strip any trailing -YYYYMMDD so the request matches the
# undated config entry. Generic by design: future dates need no config change.
_DATE_SUFFIX_RE = re.compile(r"-\d{8}$")


def _strip_date_suffix(model: str) -> str:
    if not isinstance(model, str):
        return model
    return _DATE_SUFFIX_RE.sub("", model)

# GitHub Copilot's per-model input limits (verified via
# scripts/check_copilot_models.py against the live /models endpoint).
# As of mid-2026, base Opus 4.6/4.7/4.8 and Sonnet 4.6 all have 1M context.
DEFAULT_MAX_INPUT = 168000
MODEL_MAX_INPUT = {
    # 1M-context models (base models, not -1m variants)
    "claude-opus-4-6": 1_000_000,
    "claude-opus-4.6": 1_000_000,
    "claude-opus-4-7": 1_000_000,
    "claude-opus-4.7": 1_000_000,
    "claude-opus-4-8": 1_000_000,
    "claude-opus-4.8": 1_000_000,
    "claude-sonnet-4-6": 1_000_000,
    "claude-sonnet-4.6": 1_000_000,
    # Legacy -1m suffixed variants
    "claude-opus-4-6-1m": 1_000_000,
    "claude-opus-4.6-1m": 1_000_000,
    "claude-opus-4-7-1m": 1_000_000,
    "claude-opus-4.7-1m": 1_000_000,
    "claude-opus-4-7-1m-internal": 1_000_000,
    "claude-opus-4.7-1m-internal": 1_000_000,
}


def _has_1m_beta(data: dict, headers: dict | None = None, query: str = "") -> bool:
    """Detect if request opts into Anthropic's 1M context beta."""
    def _check(s):
        if not isinstance(s, str):
            return False
        s = s.lower()
        return "context-1m" in s or "1m-2025" in s

    if isinstance(data, dict):
        betas = data.get("betas") or data.get("anthropic_beta")
        if isinstance(betas, str) and _check(betas):
            return True
        if isinstance(betas, list):
            for b in betas:
                if _check(b):
                    return True
    if headers:
        # ASGI header keys are lowercase
        hv = headers.get("anthropic-beta", "")
        if _check(hv):
            return True
    if _check(query):
        return True
    return False


def _limit_for_model(model: str, data: dict | None = None,
                    headers: dict | None = None, query: str = "") -> int:
    if _has_1m_beta(data or {}, headers, query):
        return 1_000_000
    if not model:
        return DEFAULT_MAX_INPUT
    m = model.lower()
    if m in MODEL_MAX_INPUT:
        return MODEL_MAX_INPUT[m]
    # Heuristic: any model id containing "-1m" gets the 1M cap
    if "-1m" in m or "_1m" in m:
        return 1_000_000
    return DEFAULT_MAX_INPUT

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


def print_token_bar(input_tokens: int, model: str = "?", data: dict | None = None,
                    headers: dict | None = None, query: str = ""):
    limit = _limit_for_model(model, data, headers, query)
    remaining = limit - input_tokens
    pct = (input_tokens / limit) * 100

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
        f"input: ~{input_tokens:,} / {limit:,} | "
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

        # Handle count_tokens ourselves to avoid LiteLLM's bug with
        # Anthropic-format `type: "image"` content blocks.
        if "count_tokens" in path:
            await self._handle_count_tokens(scope, receive, send)
            return

        if "/v1/messages" not in path:
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
        data = {}
        headers = {
            k.decode("latin-1").lower(): v.decode("latin-1")
            for k, v in scope.get("headers", [])
        }
        query = scope.get("query_string", b"").decode("latin-1", "ignore")
        try:
            data = json.loads(body) if body else {}

            model_in = data.get("model", "")
            new_model = model_in

            # 1) Generic: strip dated suffix (claude-haiku-4-5-20251001 ->
            #    claude-haiku-4-5) so it matches the undated config entry.
            new_model = _strip_date_suffix(new_model)

            # 2) Historical: when only -1m variants supported 1M context, we
            #    rewrote base model -> -1m variant on beta opt-in. As of
            #    mid-2026 Copilot's base Opus 4.6/4.7/4.8 and Sonnet 4.6 all
            #    have 1M context natively, so this map is intentionally empty.
            #    Re-add entries here if upstream regresses (verify with
            #    scripts/check_copilot_models.py first).
            MODEL_1M_MAP = {}
            if (
                isinstance(new_model, str)
                and new_model.lower() in MODEL_1M_MAP
                and _has_1m_beta(data, headers, query)
            ):
                new_model = MODEL_1M_MAP[new_model.lower()]

            # Apply rewrite (if any) once: update body + Content-Length.
            if isinstance(model_in, str) and new_model != model_in:
                data["model"] = new_model
                body = json.dumps(data).encode("utf-8")
                # Patch Content-Length in scope headers so downstream is happy
                new_headers = []
                for k, v in scope.get("headers", []):
                    if k.lower() == b"content-length":
                        new_headers.append((k, str(len(body)).encode("latin-1")))
                    else:
                        new_headers.append((k, v))
                scope["headers"] = new_headers
                print(
                    f"\033[36m[TokenMonitor] rewriting model "
                    f"{model_in} -> {new_model}\033[0m",
                    flush=True,
                )

            tokens = estimate_input_tokens(data)
            model = data.get("model", "?")
            if tokens > 0:
                print_token_bar(tokens, model, data, headers, query)
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

    async def _handle_count_tokens(self, scope, receive, send):
        """Implement /v1/messages/count_tokens locally with tiktoken.

        LiteLLM's built-in implementation crashes on Anthropic-format image
        content blocks (`type: "image"`). We do it ourselves and return the
        same response shape Anthropic returns.
        """
        body = b""
        more_body = True
        while more_body:
            message = await receive()
            if message["type"] == "http.request":
                body += message.get("body", b"")
                more_body = message.get("more_body", False)
            elif message["type"] == "http.disconnect":
                return

        try:
            data = json.loads(body) if body else {}
            tokens = estimate_input_tokens(data)
        except Exception:
            tokens = 0

        response_body = json.dumps({"input_tokens": tokens}).encode("utf-8")

        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(response_body)).encode()),
            ],
        })
        await send({
            "type": "http.response.body",
            "body": response_body,
        })
