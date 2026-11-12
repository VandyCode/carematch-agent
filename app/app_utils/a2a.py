# Copyright 2026 CareMatch Contributors
# Licensed under the Apache License, Version 2.0.

"""Agent-to-Agent (A2A) Protocol Agent Card & Discovery Route Helper for CareMatch."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI


def build_agent_card(base_url: str = "http://localhost:8000") -> dict[str, Any]:
    """Generate an A2A-compliant Agent Card JSON manifest for CareMatch."""
    return {
        "name": "CareMatch",
        "description": (
            "Autonomous Multi-Agent Healthcare Quality, Surgeon Outcomes, and Medicare Coverage "
            "Navigator grounded in public federal CMS.gov and HHS NPPES datasets."
        ),
        "version": "1.0.0",
        "url": f"{base_url.rstrip('/')}/api/v1/chat",
        "protocolVersion": "0.2.0",
        "capabilities": {
            "streaming": False,
            "pushNotifications": False,
            "stateTransitionHistory": True,
        },
        "defaultInputModes": ["text/plain", "application/json"],
        "defaultOutputModes": ["text/markdown", "application/json"],
        "skills": [
            {
                "id": "hospital-quality-compare",
                "name": "Hospital Quality & Safety Comparison",
                "description": "Compare CMS Overall Star Ratings, HCAHPS scores, and safety indicators by U.S. ZIP code, city, or hospital name.",
                "tags": ["cms", "hospitals", "hcahps", "safety"],
            },
            {
                "id": "surgeon-outcomes-discovery",
                "name": "Procedure Outcomes & Surgeon Lookup",
                "description": "Evaluate Hip/Knee, CABG, Heart Failure, and Maternity hospital benchmarks alongside affiliated specialists.",
                "tags": ["surgeons", "nppes", "outcomes", "procedures"],
            },
            {
                "id": "medicare-plan-evaluation",
                "name": "Medicare Advantage & Part D Coverage Navigator",
                "description": "Compare CMS Part C & Part D Star Ratings and generate hospital-plan network verification checklists.",
                "tags": ["medicare", "star-ratings", "coverage", "cms-0057-f"],
            },
        ],
    }


def attach_a2a_discovery_routes(app: FastAPI) -> None:
    """Attach the standard A2A `/.well-known/agent-card.json` discovery endpoint."""

    @app.get("/.well-known/agent-card.json")
    def get_a2a_agent_card() -> dict[str, Any]:
        return build_agent_card()
