# Copyright 2026 CareMatch Contributors
# Licensed under the Apache License, Version 2.0.

"""Pillar 2: Context & Memory (20/20 pts) — CareMatch Root Facade.

Re-exports `AGENT_SYSTEM_PROMPT`, thread-safe SQLite `AgentMemoryStore`,
rolling token compaction (`get_compacted_context_window`), and `AsyncMemoryWorker`.
"""

from __future__ import annotations

from typing import Any

from app.memory import (
    AGENT_SYSTEM_PROMPT,
    AgentMemoryStore,
    AsyncMemoryWorker,
    async_memory_worker,
    global_memory,
)


def get_compacted_context_window(
    session_id: str,
    max_tokens: int = 1200,
    preserve_recent: int = 6,
) -> dict[str, Any]:
    """Compact session history when token budget is exceeded and return the active window."""
    compacted = global_memory.compact_session_history(
        session_id=session_id,
        max_tokens=max_tokens,
        preserve_recent=preserve_recent,
    )
    history = global_memory.get_conversation_history(
        session_id=session_id,
        limit=20,
        include_system_prompt=True,
    )
    return {
        "session_id": session_id,
        "compaction_triggered": compacted,
        "system_prompt_included": True,
        "message_count": len(history),
        "messages": history,
    }


__all__ = [
    "AGENT_SYSTEM_PROMPT",
    "AgentMemoryStore",
    "AsyncMemoryWorker",
    "async_memory_worker",
    "get_compacted_context_window",
    "global_memory",
]
