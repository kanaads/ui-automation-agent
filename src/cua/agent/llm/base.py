"""The provider-agnostic LLM boundary the discovery loop (cua.agent
.discover) talks to. Deliberately the narrowest possible surface -- one
method, plain text in, plain text out -- so every provider (Groq,
NVIDIA NIM, AWS Bedrock) can implement it without the loop caring about
tool-calling schemas, response formats, or SDK-specific message shapes
that differ across them. The discovery loop is what imposes structure
(asking for a strict JSON decision back, per turn) on top of this; the
client itself does nothing but relay a conversation.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class LLMMessage:
    role: Literal["system", "user", "assistant"]
    content: str


class LLMClient(ABC):
    @abstractmethod
    def complete(self, messages: Sequence[LLMMessage]) -> str:
        """Sends the whole conversation so far and returns the
        assistant's next reply as plain text. Never raises for what the
        model said (there's no such thing as an invalid reply at this
        layer); an HTTP/API-level failure propagates as whatever the
        underlying transport raises."""
