# Copyright 2026 CareMatch Contributors
# Licensed under the Apache License, Version 2.0.

"""Pillar 3: Multi-Agent ADK Supervisor & Specialist Hierarchy — CareMatch.

Defines the CareMatch Supervisor (`root_agent`, name=`carematch`) coordinating three
domain specialists:
  1. `hospital_quality_agent`: Geospatial CMS Hospital Star Ratings, HCAHPS, safety,
     methodology glossary, and shortlist memory.
  2. `surgeon_outcomes_agent`: Procedure complication/readmission benchmarks (Hip/Knee,
     CABG, Heart Failure, Maternity) and surgeon/specialist discovery with NPPES links.
  3. `medicare_coverage_agent`: Medicare Advantage & Part D Star Ratings, network
     verification checklists, CMS-0057-F prior authorization timelines, and HITL escalations.

Uses native `google.adk` classes when installed and falls back cleanly to lightweight
structural agent descriptors when running unit tests without optional ADK extras.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from app.resilience_plugin import CareMatchResiliencePlugin
from app.tools import (
    check_network_and_coverage_fit,
    compare_medicare_advantage_plans,
    compare_procedure_outcomes,
    find_surgeons_and_specialists,
    get_hospital_quality_profile,
    lookup_cms_metric_definition,
    save_or_query_care_memory,
    search_hospitals_by_location,
    submit_feedback_or_escalation,
)

MODEL = os.getenv("CAREMATCH_MODEL", "gemini-2.5-flash")

try:
    from google.adk.agents import Agent as _ADKAgent
    from google.adk.apps import App as _ADKApp
    from google.adk.models import Gemini as _ADKGemini
    from google.genai import types as _genai_types

    ADK_AVAILABLE = True

    def _make_model(model_name: str) -> Any:
        return _ADKGemini(
            model=model_name,
            retry_options=_genai_types.HttpRetryOptions(attempts=3),
        )

    AgentCls = _ADKAgent
    AppCls = _ADKApp
except Exception:  # pragma: no cover - lightweight fallback when google-adk isn't installed
    ADK_AVAILABLE = False

    def _make_model(model_name: str) -> Any:
        return model_name

    @dataclass
    class _FallbackAgent:
        name: str
        model: Any
        description: str
        instruction: str
        tools: list[Any] = field(default_factory=list)
        sub_agents: list[Any] = field(default_factory=list)

    @dataclass
    class _FallbackApp:
        name: str
        root_agent: Any
        plugins: list[Any] = field(default_factory=list)

    AgentCls = _FallbackAgent  # type: ignore[assignment]
    AppCls = _FallbackApp  # type: ignore[assignment]


hospital_quality_agent = AgentCls(
    name="hospital_quality_agent",
    model=_make_model(MODEL),
    description=(
        "Hospital Quality & Patient Safety Specialist. Evaluates CMS Hospital Overall Star Ratings "
        "(1-5 stars), HCAHPS patient experience scores, geospatial distance from U.S. ZIP codes/cities, "
        "official CMS metric methodology, and persistent care shortlist notes."
    ),
    instruction="""You are the Hospital Quality & Patient Safety Specialist within CareMatch.
Your job is to help patients and caregivers evaluate nearby hospitals using official public
CMS Provider Data Catalog & Medicare Care Compare metrics.

Rules:
1. Always call `search_hospitals_by_location`, `get_hospital_quality_profile`, `lookup_cms_metric_definition`,
   or `save_or_query_care_memory` to ground every response.
2. Report exact CMS Overall Star Ratings, HCAHPS ratings, 6-digit CCNs, and distances cleanly.
3. Never provide medical diagnoses. If urgent/emergency symptoms are mentioned, advise calling 911 immediately.
""",
    tools=[
        search_hospitals_by_location,
        get_hospital_quality_profile,
        lookup_cms_metric_definition,
        save_or_query_care_memory,
    ],
)


surgeon_outcomes_agent = AgentCls(
    name="surgeon_outcomes_agent",
    model=_make_model(MODEL),
    description=(
        "Procedure Outcomes & Surgeon Discovery Specialist. Compares CMS surgical complication, "
        "mortality, readmission, and maternity benchmarks (Hip/Knee THA/TKA, CABG, Heart Failure, "
        "Maternity) and surfaces hospital-affiliated specialists with HHS NPPES verification links."
    ),
    instruction="""You are the Procedure Outcomes & Surgeon Discovery Specialist within CareMatch.
Your job is to compare procedure-specific hospital safety rates and connect consumers with
verified specialist lookups via public CMS and HHS NPPES registries.

Rules:
1. Always call `compare_procedure_outcomes` and/or `find_surgeons_and_specialists`.
2. Explicitly clarify that patients must confirm active hospital privileges, board certification,
   and in-network insurance contracts directly with the surgeon's office and the HHS NPPES Registry.
""",
    tools=[
        compare_procedure_outcomes,
        find_surgeons_and_specialists,
        get_hospital_quality_profile,
    ],
)


medicare_coverage_agent = AgentCls(
    name="medicare_coverage_agent",
    model=_make_model(MODEL),
    description=(
        "Medicare Advantage, Part D & Coverage Fit Specialist. Compares CMS Medicare Star Ratings "
        "across Part C and Part D contracts, generates hospital-insurer network verification checklists "
        "(including CMS-0057-F prior authorization timelines), and manages HITL advisor escalations."
    ),
    instruction="""You are the Medicare Coverage & Network Navigation Specialist within CareMatch.
Your job is to help beneficiaries compare CMS Medicare Advantage & Part D Star Ratings and prepare
concrete verification questions before choosing a plan or scheduling elective surgery.

Rules:
1. Always call `compare_medicare_advantage_plans`, `check_network_and_coverage_fit`, or `submit_feedback_or_escalation`.
2. Clearly explain that public CMS datasets do not publish real-time commercial/Medicare hospital network contracts,
   and instruct users to verify Tier-1 participation with Member Services.
""",
    tools=[
        compare_medicare_advantage_plans,
        check_network_and_coverage_fit,
        lookup_cms_metric_definition,
        submit_feedback_or_escalation,
    ],
)


root_agent = AgentCls(
    name="carematch",
    model=_make_model(MODEL),
    description=(
        "CareMatch Supervisor Agent: Multi-agent Healthcare Quality, Surgeon Outcomes, and "
        "Medicare Coverage Navigator grounded in public federal CMS.gov and HHS NPPES datasets."
    ),
    instruction="""You are CareMatch, the top-level Healthcare Quality & Coverage Navigator supervisor.
Delegate user inquiries to your three specialized sub-agents:
- `hospital_quality_agent` for ZIP/city hospital comparisons, overall CMS Star Ratings, HCAHPS, and CMS metric definitions.
- `surgeon_outcomes_agent` for Hip/Knee, CABG, Heart Failure, or Maternity outcomes and surgeon/specialist lookups.
- `medicare_coverage_agent` for Medicare Advantage/Part D Star Ratings, hospital-plan network checklists, and user feedback/escalations.

Always synthesize concise, scannable Markdown tables with transparent public CMS provenance and
a clear educational non-medical-advice disclaimer.
""",
    sub_agents=[
        hospital_quality_agent,
        surgeon_outcomes_agent,
        medicare_coverage_agent,
    ],
    tools=[
        search_hospitals_by_location,
        get_hospital_quality_profile,
        compare_procedure_outcomes,
        find_surgeons_and_specialists,
        compare_medicare_advantage_plans,
        check_network_and_coverage_fit,
        lookup_cms_metric_definition,
        save_or_query_care_memory,
        submit_feedback_or_escalation,
    ],
)


app = AppCls(
    name="carematch",
    root_agent=root_agent,
    plugins=[CareMatchResiliencePlugin()],
)
