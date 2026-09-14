"""The coaching agent: one Claude conversation driven by the SDK tool runner.

Each `send()` call appends the user's message, streams the reply (printing text
as it arrives), runs any tools the model calls, and mirrors the full exchange
into `self.messages` so the next turn continues the same conversation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import anthropic

from . import config
from .db import Database
from .prompt import build_system
from .tools import ALL_TOOLS, today

REFUSAL_TEXT = (
    "[The model declined to answer that request. Try rephrasing, or ask a different question.]"
)


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    requests: int = 0

    def add(self, usage: Any) -> None:
        self.requests += 1
        self.input_tokens += getattr(usage, "input_tokens", 0) or 0
        self.output_tokens += getattr(usage, "output_tokens", 0) or 0
        self.cache_read_tokens += getattr(usage, "cache_read_input_tokens", 0) or 0
        self.cache_write_tokens += getattr(usage, "cache_creation_input_tokens", 0) or 0


@dataclass
class Coach:
    client: anthropic.Anthropic
    db: Database
    manual: str | None = None
    extra_instructions: str = ""
    on_text: Callable[[str], None] = lambda s: print(s, end="", flush=True)
    on_tool: Callable[[str], None] | None = None
    max_iterations: int = 12
    messages: list[dict[str, Any]] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)

    @staticmethod
    def fallback_params() -> dict[str, Any]:
        if config.use_fallback(config.MODEL):
            return {"betas": [config.FALLBACK_BETA], "fallbacks": "default"}
        return {}

    def send(self, user_text: str) -> str:
        """Send one user turn and return the assistant's final text."""
        self.messages.append({"role": "user", "content": user_text})

        runner = self.client.beta.messages.tool_runner(
            model=config.MODEL,
            max_tokens=config.MAX_TOKENS,
            system=build_system(self.db, today(), self.manual, self.extra_instructions),
            tools=ALL_TOOLS,
            messages=self.messages,
            thinking={"type": "adaptive"},
            output_config={"effort": config.EFFORT},
            cache_control={"type": "ephemeral"},
            stream=True,
            max_iterations=self.max_iterations,
            **self.fallback_params(),
        )

        final_text: list[str] = []
        last = None
        for stream in runner:
            for text in stream.text_stream:
                self.on_text(text)
                final_text.append(text)
            message = stream.get_final_message()
            last = message
            self.usage.add(message.usage)

            # Mirror the exchange so the next send() continues this conversation.
            self.messages.append(message.to_param())
            tool_response = runner.generate_tool_call_response()  # cached: tools run once
            if tool_response is not None:
                if self.on_tool:
                    for block in message.content:
                        if block.type == "tool_use":
                            self.on_tool(block.name)
                self.messages.append(tool_response)

        if last is not None and last.stop_reason == "refusal":
            self.on_text(REFUSAL_TEXT)
            final_text.append(REFUSAL_TEXT)
        elif last is not None and last.stop_reason == "max_tokens":
            note = "\n[Reply was cut off at the token limit.]"
            self.on_text(note)
            final_text.append(note)

        self.on_text("\n")
        return "".join(final_text)
