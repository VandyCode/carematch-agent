# Copyright 2026 CareMatch Contributors
# Licensed under the Apache License, Version 2.0.

"""Compatibility adapter exposing lightweight status & query routes for Cloud Run / Agent Engine."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI


def attach_reasoning_engine_routes(app: FastAPI) -> None:
    """Attach health and capability metadata routes for cloud deployments."""

    @app.get("/health")
    def health_check() -> dict[str, Any]:
        return {
            "status": "ok",
            "service": "carematch-agent",
            "version": "1.0.0",
        }
