"""
Conversation History Manager
==============================
Maintains a sliding window of the last N conversation turns (default: 5).
Implemented as a collections.deque with maxlen. Each turn stored as
{role: "user" | "assistant", content: "..."} to match Gemini API format.
History is serialisable for logging.

Reference: PRD Section 6.1 (memory.py), Section 13 (Conversation Memory Strategy)
"""

from __future__ import annotations

import collections
from typing import Any, Dict, List

from backend.config import settings


class ConversationMemory:
    """
    Per-session sliding window conversation history.

    Lifecycle (PRD Section 13.2):
      - Session created   → Empty deque initialised
      - User sends question → User message appended
      - LLM responds       → Assistant message appended
      - Deque full         → Oldest pair automatically dropped
      - Session cleared    → Deque replaced with empty deque

    Each message is stored as:
      {"role": "user" | "assistant", "content": "..."}

    This format matches the Gemini API's message format directly,
    so history can be passed without transformation.
    """

    def __init__(self, window_size: int | None = None) -> None:
        """
        Args:
            window_size: Number of conversation turns to retain.
                         Each turn = 1 user message + 1 assistant message.
                         Default from config: 5 turns = 10 messages.
        """
        self._window_size = window_size or settings.conversation_window_size
        # maxlen = turns × 2 (user + assistant per turn)
        self._messages: collections.deque[Dict[str, str]] = collections.deque(
            maxlen=self._window_size * 2
        )

    @property
    def window_size(self) -> int:
        """Number of conversation turns retained."""
        return self._window_size

    def add_user_message(self, content: str) -> None:
        """Append a user message to the history."""
        self._messages.append({"role": "user", "content": content})

    def add_assistant_message(self, content: str) -> None:
        """Append an assistant message to the history."""
        self._messages.append({"role": "assistant", "content": content})

    def add_turn(self, user_content: str, assistant_content: str) -> None:
        """
        Convenience method to add a complete turn (user + assistant).
        If the deque is full, the oldest turn is automatically discarded.
        """
        self.add_user_message(user_content)
        self.add_assistant_message(assistant_content)

    def get_history(self) -> List[Dict[str, str]]:
        """
        Return the conversation history as a list of dicts.
        Serialisable for logging and prompt construction.
        """
        return list(self._messages)

    def clear(self) -> None:
        """Reset the conversation history (PRD Section 13.2: session cleared)."""
        self._messages.clear()

    @property
    def turn_count(self) -> int:
        """Number of complete turns currently in memory."""
        return len(self._messages) // 2

    @property
    def message_count(self) -> int:
        """Total number of individual messages in memory."""
        return len(self._messages)

    def __len__(self) -> int:
        return len(self._messages)

    def __repr__(self) -> str:
        return (
            f"ConversationMemory(turns={self.turn_count}/{self._window_size}, "
            f"messages={self.message_count})"
        )
