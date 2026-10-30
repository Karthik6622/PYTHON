"""NVIDIA's OpenAI-compatible chat API (nvidia/nemotron-3-ultra-550b-a55b by default).

Streaming, tool calls, retry with backoff, timeouts, friendly errors and context-window management. The endpoint and model
come from configuration; the API key is read per request and never logged.
"""

from __future__ import annotations

import asyncio
import json
import random
import ssl
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

import httpx

from ..config import settings
from ..security import redact

SYSTEM_PROMPT = (
    "You are the primary software engineering agent inside Nemotron AI Code Studio.\n"
    "You can inspect repositories, understand software architecture, search code, read files, modify files, create files, "
    "run approved development commands, analyze errors, run tests, and interact with Git tools.\n"
    "Never claim you inspected a file unless the application provided its contents.\n"
    "Never invent repository contents.\n"
    "Before editing code:\n"
    "1. Analyze the user's request.\n"
    "2. Inspect the relevant repository structure.\n"
    "3. Search for relevant implementations.\n"
    "4. Read the required files.\n"
    "5. Understand dependencies.\n"
    "6. Build a short implementation plan.\n"
    "7. Make the smallest correct changes.\n"
    "8. Validate those changes.\n"
    "9. Clearly report the modified files.\n"
    "Never push repository changes without explicit authorization."
)

RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}


class NvidiaError(Exception):
    def __init__(self, message: str, status: int = 502, retryable: bool = False) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.retryable = retryable


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    raw_arguments: str = ""
    error: str = ""

    def as_message_entry(self) -> dict[str, Any]:
        return {"id": self.id, "type": "function", "function": {"name": self.name, "arguments": self.raw_arguments or json.dumps(self.arguments)}}


@dataclass
class ChatResult:
    content: str = ""
    reasoning: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = ""
    usage: dict[str, Any] = field(default_factory=dict)


# ------------------------------------------------------------------ token and context management
def estimate_tokens(value: Any) -> int:
    if isinstance(value, str):
        return len(value) // 4 + 1
    return len(json.dumps(value, ensure_ascii=False, default=str)) // 4 + 1


def messages_tokens(messages: list[dict[str, Any]]) -> int:
    return sum(estimate_tokens(m) + 4 for m in messages)


def _units(messages: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Group an assistant tool-call message with its tool results so they are kept or dropped together."""
    units: list[list[dict[str, Any]]] = []
    for message in messages:
        if message.get("role") == "tool" and units:
            units[-1].append(message)
        else:
            units.append([message])
    return units


def fit_messages(messages: list[dict[str, Any]], limit: int | None = None, reserve: int = 6000) -> list[dict[str, Any]]:
    """Keeps the conversation inside the context window.

    1. shorten old tool results, 2. drop the oldest turns (never the system prompt or the latest user request).
    """
    budget = (limit or settings.context_window_tokens) - reserve
    result = [dict(m) for m in messages]
    if messages_tokens(result) <= budget:
        return result
    protect = max(0, len(result) - 8)
    for index in range(protect):
        message = result[index]
        if message.get("role") == "tool" and isinstance(message.get("content"), str) and len(message["content"]) > 800:
            message["content"] = message["content"][:800] + "\n[older tool output shortened to save context]"
    if messages_tokens(result) <= budget:
        return result
    system = [m for m in result if m.get("role") == "system"]
    rest = [m for m in result if m.get("role") != "system"]
    units = _units(rest)
    last_user = max((i for i, unit in enumerate(units) if unit[0].get("role") == "user"), default=0)
    while len(units) > 1 and messages_tokens(system + [m for unit in units for m in unit]) > budget:
        drop = next((i for i in range(len(units)) if i != last_user and i < len(units) - 1), None)
        if drop is None:
            break
        units.pop(drop)
        if drop < last_user:
            last_user -= 1
    flat = [m for unit in units for m in unit]
    if messages_tokens(system + flat) > budget and flat:
        for message in flat:  # last resort: shorten the biggest remaining message
            if isinstance(message.get("content"), str) and len(message["content"]) > 20_000:
                message["content"] = message["content"][:20_000] + "\n[truncated to fit the context window]"
    return system + flat


# ------------------------------------------------------------------ parsing
def parse_tool_arguments(raw: str) -> tuple[dict[str, Any], str]:
    text = (raw or "").strip()
    if not text:
        return {}, ""
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    try:
        value = json.loads(text)
    except ValueError as exc:
        return {}, f"The tool arguments were not valid JSON ({exc.__class__.__name__}). Send a single valid JSON object."
    if not isinstance(value, dict):
        return {}, "The tool arguments must be a JSON object."
    return value, ""


def _friendly_error(status: int, body: str) -> NvidiaError:
    detail = ""
    try:
        data = json.loads(body)
        err = data.get("error", data) if isinstance(data, dict) else {}
        detail = err.get("message") or err.get("detail") or "" if isinstance(err, dict) else str(err)
        if not detail and isinstance(data, dict):
            detail = str(data.get("detail") or "")
    except ValueError:
        detail = body.strip()[:300]
    detail = redact(" ".join(str(detail).split()))[:400]
    if status == 401:
        return NvidiaError("NVIDIA rejected the API key. Check NVIDIA_API_KEY in Settings.", 401)
    if status == 403:
        return NvidiaError("The NVIDIA API key does not have access to this model." + (f" ({detail})" if detail else ""), 403)
    if status == 404:
        return NvidiaError(f"NVIDIA could not find the model '{settings.nvidia_model}'. Check NVIDIA_MODEL.", 404)
    if status == 413 or (status == 400 and "context" in detail.lower()):
        return NvidiaError("The request is too large for the model's context window. Start a new chat or ask about fewer files." + (f" ({detail})" if detail else ""), 400)
    if status == 429:
        return NvidiaError("NVIDIA's rate limit was reached. Wait a moment and try again.", 429, True)
    if status >= 500 or status in RETRYABLE_STATUS:
        return NvidiaError(f"NVIDIA's service had a problem ({status})." + (f" {detail}" if detail else ""), 502, True)
    return NvidiaError(f"NVIDIA rejected the request ({status}). {detail}".strip(), 400)


class NvidiaService:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None, sleep: Any = asyncio.sleep) -> None:
        self._transport = transport
        self._sleep = sleep

    # ---------------------------------------------------------------- status
    def status(self) -> dict[str, Any]:
        return {"configured": bool(settings.nvidia_api_key), "model": settings.nvidia_model, "base_url": settings.nvidia_base_url}

    def _client(self) -> httpx.AsyncClient:
        timeout = httpx.Timeout(connect=15.0, read=settings.nvidia_timeout_seconds, write=30.0, pool=15.0)
        kwargs: dict[str, Any] = {"timeout": timeout}
        if self._transport is not None:
            kwargs["transport"] = self._transport
        else:
            kwargs["verify"] = ssl.create_default_context()
        return httpx.AsyncClient(**kwargs)

    # ---------------------------------------------------------------- core streaming call
    async def stream_chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> AsyncIterator[dict[str, Any]]:
        """Yields {"type": "content"|"reasoning", "text"} while streaming, then {"type": "done", "result": ChatResult}."""
        key = settings.nvidia_api_key
        if not key:
            raise NvidiaError("No NVIDIA API key is configured. Add NVIDIA_API_KEY to .env or enter it in Settings.", 400)
        body: dict[str, Any] = {
            "model": settings.nvidia_model, "messages": fit_messages(messages), "stream": True,
            "temperature": temperature, "max_tokens": max_tokens,
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        body.update(settings.nvidia_extra_body)
        headers = {"Authorization": f"Bearer {key}", "Accept": "text/event-stream", "Content-Type": "application/json"}
        url = f"{settings.nvidia_base_url}/chat/completions"
        attempts = settings.nvidia_max_retries + 1
        async with self._client() as client:
            for attempt in range(attempts):
                started = False
                try:
                    async with client.stream("POST", url, headers=headers, json=body) as response:
                        if response.status_code != 200:
                            raw = (await response.aread()).decode("utf-8", errors="replace")
                            error = _friendly_error(response.status_code, raw)
                            error.retry_after = _retry_after(response.headers.get("retry-after"))  # type: ignore[attr-defined]
                            raise error
                        result = ChatResult()
                        partial: dict[int, dict[str, str]] = {}
                        async for line in response.aiter_lines():
                            line = line.strip()
                            if not line.startswith("data:"):
                                continue
                            payload = line[5:].strip()
                            if payload == "[DONE]":
                                break
                            try:
                                chunk = json.loads(payload)
                            except ValueError:
                                continue
                            if chunk.get("usage"):
                                result.usage = chunk["usage"]
                            if isinstance(chunk.get("error"), dict):
                                raise NvidiaError(redact(str(chunk["error"].get("message", "The model returned an error."))), 502)
                            for choice in chunk.get("choices") or []:
                                delta = choice.get("delta") or {}
                                if choice.get("finish_reason"):
                                    result.finish_reason = choice["finish_reason"]
                                text = delta.get("content")
                                if text:
                                    started = True
                                    result.content += text
                                    yield {"type": "content", "text": text}
                                thought = delta.get("reasoning_content") or delta.get("reasoning")
                                if thought:
                                    started = True
                                    result.reasoning += thought
                                    yield {"type": "reasoning", "text": thought}
                                for part in delta.get("tool_calls") or []:
                                    started = True
                                    slot = partial.setdefault(part.get("index", 0), {"id": "", "name": "", "args": ""})
                                    slot["id"] = part.get("id") or slot["id"]
                                    function = part.get("function") or {}
                                    slot["name"] += function.get("name") or ""
                                    slot["args"] += function.get("arguments") or ""
                        for position, slot in sorted(partial.items()):
                            if not slot["name"]:
                                continue
                            arguments, problem = parse_tool_arguments(slot["args"])
                            result.tool_calls.append(ToolCall(slot["id"] or f"call_{position}", slot["name"], arguments, slot["args"], problem))
                        yield {"type": "done", "result": result}
                        return
                except NvidiaError as error:
                    if not error.retryable or started or attempt >= attempts - 1:
                        raise
                    await self._sleep(getattr(error, "retry_after", None) or _backoff(attempt))
                except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout) as exc:
                    if started or attempt >= attempts - 1:
                        raise NvidiaError("Could not reach the NVIDIA API. Check your network connection and NVIDIA_BASE_URL.", 502) from exc
                    await self._sleep(_backoff(attempt))
                except httpx.TimeoutException as exc:
                    if started or attempt >= attempts - 1:
                        raise NvidiaError("The NVIDIA API took too long to answer. Try again, or raise NVIDIA_TIMEOUT_SECONDS.", 504) from exc
                    await self._sleep(_backoff(attempt))
                except (httpx.ReadError, httpx.RemoteProtocolError) as exc:
                    if started or attempt >= attempts - 1:
                        raise NvidiaError("The connection to the NVIDIA API was interrupted.", 502) from exc
                    await self._sleep(_backoff(attempt))

    # ---------------------------------------------------------------- public helpers
    async def chat(self, messages: list[dict[str, Any]], *, temperature: float = 0.2, max_tokens: int = 4096) -> ChatResult:
        result = ChatResult()
        async for event in self.stream_chat(messages, temperature=temperature, max_tokens=max_tokens):
            if event["type"] == "done":
                result = event["result"]
        return result

    def agent_chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]], *, temperature: float = 0.1, max_tokens: int = 6000) -> AsyncIterator[dict[str, Any]]:
        """One agent turn: streams text and returns structured tool calls in the final event."""
        return self.stream_chat(messages, tools=tools, temperature=temperature, max_tokens=max_tokens)

    async def generate_code(self, instruction: str, language: str = "", context: str = "") -> str:
        prompt = f"Write {language + ' ' if language else ''}code for the following request. Reply with the code only.\n\n{instruction}"
        if context:
            prompt += f"\n\nRelevant context:\n{context}"
        result = await self.chat([{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}], temperature=0.1)
        return result.content.strip()

    async def analyze_code(self, code: str, question: str = "Explain what this code does and point out problems.") -> str:
        prompt = f"{question}\n\n```\n{code[:60_000]}\n```"
        result = await self.chat([{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}], temperature=0.1)
        return result.content.strip()

    async def ping(self) -> dict[str, Any]:
        """Cheap configuration check used by the top-bar status indicator."""
        info = self.status()
        if not info["configured"]:
            return {**info, "ok": False, "message": "No NVIDIA API key configured."}
        try:
            await self.chat([{"role": "user", "content": "Reply with the single word ok."}], max_tokens=8)
        except NvidiaError as exc:
            return {**info, "ok": False, "message": exc.message}
        return {**info, "ok": True, "message": "Connected."}


def _backoff(attempt: int) -> float:
    return min(20.0, (2 ** attempt)) + random.uniform(0, 0.5)


def _retry_after(value: str | None) -> float | None:
    try:
        return min(30.0, float(value)) if value else None
    except ValueError:
        return None
