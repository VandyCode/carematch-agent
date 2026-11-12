# Copyright 2026 CareMatch Contributors
# Licensed under the Apache License, Version 2.0.

"""Session and artifact service configuration helpers for CareMatch."""

from __future__ import annotations

import os
from typing import Any

SESSION_SERVICE_URI = os.getenv("CAREMATCH_SESSION_URI", "memory://")
ARTIFACT_SERVICE_URI = os.getenv("CAREMATCH_ARTIFACT_URI", "memory://")


def get_session_service() -> Any:
    """Return an ADK InMemorySessionService when google-adk is available."""
    try:
        from google.adk.sessions import InMemorySessionService

        return InMemorySessionService()
    except Exception:
        return None


def get_artifact_service() -> Any:
    """Return an ADK InMemoryArtifactService when google-adk is available."""
    try:
        from google.adk.artifacts import InMemoryArtifactService

        return InMemoryArtifactService()
    except Exception:
        return None
