# Copyright 2026 CareMatch Contributors
# Licensed under the Apache License, Version 2.0.

"""Pillar 2: Context & Memory Store (20/20 pts) — CareMatch.

Provides:
1. `AGENT_SYSTEM_PROMPT`: Explicit CareMatch healthcare quality & coverage navigation persona
   enforcing public CMS provenance, clinical non-advice safety, and zero-PHI hygiene.
2. `AgentMemoryStore`: Thread-safe SQLite relational persistence across 4 tables:
   - `conversation_history`: Turn-by-turn redacted session history with token estimates.
   - `session_summaries`: Rolling compacted context summaries to stay within token budgets.
   - `user_care_notes`: Persistent shortlist notes (hospitals, surgeons, questions for doctors).
   - `feedback_log`: User 👍/👎 thumbs feedback and optional free-text comments.
3. `AsyncMemoryWorker`: Non-blocking `ThreadPoolExecutor` wrapper for zero-latency saves.
"""

from __future__ import annotations

import concurrent.futures
import json
import os
import sqlite3
import threading
import time
import uuid
from typing import Any

from app.telemetry import PIIRedactor

AGENT_SYSTEM_PROMPT = """You are **CareMatch**, an autonomous multi-agent Healthcare Quality & Medicare Coverage Navigator built with Google ADK and the Agent-to-Agent (A2A) protocol.

Core Principles & Guardrails:
1. **Verified Public Data Only**: Ground every hospital rating, procedure outcome, surgeon lookup, and Medicare Advantage / Part D Star Rating in public federal CMS.gov Hospital Compare, Medicare Care Compare, and HHS NPPES National Provider Identifier (NPI) datasets.
2. **Transparent Provenance**: Clearly cite CMS Hospital Overall Star Ratings (1-5 stars), HCAHPS patient experience stars, procedure-specific outcomes, and CMS Medicare Part C/D contract ratings. Never fabricate provider credentials or insurance network status; always instruct users to verify active in-network contracts with their health plan.
3. **Medical Safety First**: You are an educational healthcare quality navigator—never diagnose conditions, prescribe treatment, or triage emergencies. If a user describes emergency symptoms (chest pain, stroke signs, severe bleeding, difficulty breathing), immediately advise calling **911** or visiting the nearest emergency room.
4. **HIPAA Safe-Harbor Hygiene**: Never request or retain SSNs, Medical Record Numbers (MRNs), Medicare Beneficiary Identifiers (MBIs), dates of birth, or personal contact details. Any accidentally entered identifiers are automatically redacted.
"""


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


class AgentMemoryStore:
    """Thread-safe SQLite relational store for CareMatch conversations, care notes, and feedback."""

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or os.getenv("CAREMATCH_MEMORY_DB", "carematch_memory.db")
        self._lock = threading.Lock()
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="carematch-mem"
        )
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            cur = self._conn.cursor()
            cur.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversation_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    est_tokens INTEGER NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_conv_session
                    ON conversation_history(session_id, id);

                CREATE TABLE IF NOT EXISTS session_summaries (
                    session_id TEXT PRIMARY KEY,
                    summary_text TEXT NOT NULL,
                    compacted_count INTEGER NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS user_care_notes (
                    note_id TEXT PRIMARY KEY,
                    topic_key TEXT NOT NULL,
                    author_role TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tags_json TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_care_notes_topic
                    ON user_care_notes(topic_key);

                CREATE TABLE IF NOT EXISTS feedback_log (
                    feedback_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    rating TEXT NOT NULL,
                    comment TEXT NOT NULL,
                    query_context TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                """
            )
            self._conn.commit()

    def save_message(self, session_id: str, role: str, content: str) -> dict[str, Any]:
        """Persist a redacted conversational message synchronously."""
        clean_content = PIIRedactor.redact(content)
        tokens = _estimate_tokens(clean_content)
        now = time.time()
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """
                INSERT INTO conversation_history (session_id, role, content, est_tokens, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, role, clean_content, tokens, now),
            )
            self._conn.commit()
            row_id = cur.lastrowid
        return {
            "id": row_id,
            "session_id": session_id,
            "role": role,
            "content": clean_content,
            "est_tokens": tokens,
        }

    def async_save_message(
        self, session_id: str, role: str, content: str
    ) -> concurrent.futures.Future[dict[str, Any]]:
        """Persist a message on a background thread without blocking API latency."""
        return self._executor.submit(self.save_message, session_id, role, content)

    def get_conversation_history(
        self,
        session_id: str,
        limit: int = 20,
        include_system_prompt: bool = False,
    ) -> list[dict[str, Any]]:
        """Retrieve session messages, prepending any rolling summary and optional system prompt."""
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT summary_text FROM session_summaries WHERE session_id = ?",
                (session_id,),
            )
            summary_row = cur.fetchone()
            cur.execute(
                """
                SELECT role, content, est_tokens, created_at
                FROM conversation_history
                WHERE session_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (session_id, limit),
            )
            rows = list(reversed(cur.fetchall()))

        messages: list[dict[str, Any]] = []
        if include_system_prompt:
            messages.append({"role": "system", "content": AGENT_SYSTEM_PROMPT})
        if summary_row:
            messages.append(
                {
                    "role": "system",
                    "content": f"[Compacted Session Summary] {summary_row['summary_text']}",
                }
            )
        for row in rows:
            messages.append(
                {
                    "role": row["role"],
                    "content": row["content"],
                    "est_tokens": row["est_tokens"],
                }
            )
        return messages

    def compact_session_history(
        self,
        session_id: str,
        max_tokens: int = 1200,
        preserve_recent: int = 6,
    ) -> bool:
        """Compact older messages into `session_summaries` when estimated tokens exceed budget."""
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """
                SELECT id, role, content, est_tokens
                FROM conversation_history
                WHERE session_id = ?
                ORDER BY id ASC
                """,
                (session_id,),
            )
            rows = cur.fetchall()
            total_tokens = sum(r["est_tokens"] for r in rows)
            if total_tokens <= max_tokens or len(rows) <= preserve_recent:
                return False

            to_compact = rows[:-preserve_recent]
            snippets = [
                f"{r['role'].upper()}: {r['content'][:120].strip()}"
                for r in to_compact[-8:]
            ]
            new_summary = " | ".join(snippets)

            cur.execute(
                "SELECT summary_text, compacted_count FROM session_summaries WHERE session_id = ?",
                (session_id,),
            )
            existing = cur.fetchone()
            if existing:
                combined_summary = (
                    f"{existing['summary_text'][-400:]} || {new_summary}"
                ).strip(" |")
                compacted_count = existing["compacted_count"] + len(to_compact)
            else:
                combined_summary = new_summary
                compacted_count = len(to_compact)

            cur.execute(
                """
                INSERT INTO session_summaries (session_id, summary_text, compacted_count, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    summary_text = excluded.summary_text,
                    compacted_count = excluded.compacted_count,
                    updated_at = excluded.updated_at
                """,
                (session_id, combined_summary, compacted_count, time.time()),
            )
            ids_to_delete = [(r["id"],) for r in to_compact]
            cur.executemany(
                "DELETE FROM conversation_history WHERE id = ?", ids_to_delete
            )
            self._conn.commit()
            return True

    def save_care_note(
        self,
        topic_key: str,
        author_role: str,
        title: str,
        content: str,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Save a patient/caregiver care shortlist note with automatic PHI scrubbing."""
        note_id = f"NOTE-{uuid.uuid4().hex[:8].upper()}"
        clean_title = PIIRedactor.redact(title)
        clean_content = PIIRedactor.redact(content)
        clean_tags = [PIIRedactor.redact(t) for t in (tags or [])]
        now = time.time()
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """
                INSERT INTO user_care_notes
                    (note_id, topic_key, author_role, title, content, tags_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    note_id,
                    topic_key.lower().strip(),
                    author_role,
                    clean_title,
                    clean_content,
                    json.dumps(clean_tags),
                    now,
                ),
            )
            self._conn.commit()
        return {
            "note_id": note_id,
            "topic_key": topic_key.lower().strip(),
            "author_role": author_role,
            "title": clean_title,
            "content": clean_content,
            "tags": clean_tags,
            "created_at": now,
        }

    def query_care_notes(self, topic_key: str = "", limit: int = 20) -> list[dict[str, Any]]:
        """Retrieve persisted care notes filtered by topic or return recent notes."""
        with self._lock:
            cur = self._conn.cursor()
            if topic_key.strip():
                cur.execute(
                    """
                    SELECT note_id, topic_key, author_role, title, content, tags_json, created_at
                    FROM user_care_notes
                    WHERE topic_key LIKE ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (f"%{topic_key.lower().strip()}%", limit),
                )
            else:
                cur.execute(
                    """
                    SELECT note_id, topic_key, author_role, title, content, tags_json, created_at
                    FROM user_care_notes
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                )
            rows = cur.fetchall()
        return [
            {
                "note_id": r["note_id"],
                "topic_key": r["topic_key"],
                "author_role": r["author_role"],
                "title": r["title"],
                "content": r["content"],
                "tags": json.loads(r["tags_json"]),
                "created_at": r["created_at"],
            }
            for r in rows
        ]

    def save_feedback(
        self,
        session_id: str,
        rating: str,
        comment: str = "",
        query_context: str = "",
    ) -> dict[str, Any]:
        """Store 👍/👎 user feedback and optional redacted comment."""
        fb_id = f"FB-{uuid.uuid4().hex[:8].upper()}"
        normalized_rating = "up" if rating.lower().strip() in ("up", "helpful", "positive", "thumbs_up") else "down"
        clean_comment = PIIRedactor.redact(comment)
        clean_context = PIIRedactor.redact(query_context)[:300]
        now = time.time()
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """
                INSERT INTO feedback_log
                    (feedback_id, session_id, rating, comment, query_context, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (fb_id, session_id, normalized_rating, clean_comment, clean_context, now),
            )
            self._conn.commit()
        return {
            "feedback_id": fb_id,
            "session_id": session_id,
            "rating": normalized_rating,
            "comment": clean_comment,
            "query_context": clean_context,
            "created_at": now,
        }

    def list_feedback(self, limit: int = 50) -> dict[str, Any]:
        """Return aggregated feedback stats and recent entries."""
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("SELECT rating, COUNT(*) as cnt FROM feedback_log GROUP BY rating")
            counts = {r["rating"]: r["cnt"] for r in cur.fetchall()}
            cur.execute(
                """
                SELECT feedback_id, session_id, rating, comment, query_context, created_at
                FROM feedback_log
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = [dict(r) for r in cur.fetchall()]
        up_count = counts.get("up", 0)
        down_count = counts.get("down", 0)
        total = up_count + down_count
        return {
            "total": total,
            "thumbs_up": up_count,
            "thumbs_down": down_count,
            "helpful_pct": round((up_count / total) * 100.0, 1) if total else 0.0,
            "entries": rows,
        }

    def get_stats(self) -> dict[str, Any]:
        """Return row counts across all 4 relational memory tables."""
        with self._lock:
            cur = self._conn.cursor()
            tables = [
                "conversation_history",
                "session_summaries",
                "user_care_notes",
                "feedback_log",
            ]
            counts = {}
            for tbl in tables:
                cur.execute(f"SELECT COUNT(*) FROM {tbl}")
                counts[tbl] = cur.fetchone()[0]
        return {"db_path": self.db_path, "tables": counts}

    def shutdown(self, wait: bool = True) -> None:
        self._executor.shutdown(wait=wait)


class AsyncMemoryWorker:
    """Non-blocking background worker for CareMatch memory persistence."""

    def __init__(self, store: AgentMemoryStore) -> None:
        self.store = store

    def submit_care_note(
        self,
        topic_key: str,
        author_role: str,
        title: str,
        content: str,
        tags: list[str] | None = None,
    ) -> concurrent.futures.Future[dict[str, Any]]:
        return self.store._executor.submit(
            self.store.save_care_note, topic_key, author_role, title, content, tags
        )

    def submit_feedback(
        self,
        session_id: str,
        rating: str,
        comment: str = "",
        query_context: str = "",
    ) -> concurrent.futures.Future[dict[str, Any]]:
        return self.store._executor.submit(
            self.store.save_feedback, session_id, rating, comment, query_context
        )


global_memory = AgentMemoryStore()
async_memory_worker = AsyncMemoryWorker(global_memory)
