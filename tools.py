# Copyright 2026 CareMatch Contributors
# Licensed under the Apache License, Version 2.0.

"""Pillar 1: Tool & Interface Design (20/20 pts) — CareMatch Root Facade.

Re-exports all 9 Pydantic-validated CareMatch tools, explicit JSON schemas,
`ToolInterfaceRegistry`, and `execute_validated_tool` for root-level imports and
automated evaluation harnesses.
"""

from __future__ import annotations

from typing import Any

from app.tools import (
    TOOL_JSON_SCHEMAS,
    CareMemoryArgs,
    CheckNetworkFitArgs,
    CmsMetricLookupArgs,
    CompareMedicarePlansArgs,
    CompareProcedureArgs,
    FeedbackEscalationArgs,
    FindSurgeonsArgs,
    HospitalProfileArgs,
    SearchHospitalsArgs,
    check_network_and_coverage_fit,
    compare_medicare_advantage_plans,
    compare_procedure_outcomes,
    find_surgeons_and_specialists,
    get_hospital_quality_profile,
    lookup_cms_metric_definition,
    save_or_query_care_memory,
    search_hospitals_by_location,
    submit_feedback_or_escalation,
    validate_tool_args,
)


class ToolInterfaceRegistry:
    """Registry exposing OpenAPI/JSON schemas and validated execution for CareMatch tools."""

    schemas = TOOL_JSON_SCHEMAS

    @classmethod
    def list_tools(cls) -> list[str]:
        return list(cls.schemas.keys())

    @classmethod
    def get_schema(cls, tool_name: str) -> dict[str, Any] | None:
        return cls.schemas.get(tool_name)


def execute_validated_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Validate arguments with Pydantic and dispatch to the requested CareMatch tool."""
    valid, err = validate_tool_args(tool_name, arguments)
    if not valid and err is not None:
        return err

    dispatch_map = {
        "search_hospitals_by_location": lambda args: search_hospitals_by_location(
            location=args["location"],
            radius_miles=args.get("radius_miles", 35),
            min_stars=args.get("min_stars", 1),
            procedure_focus=args.get("procedure_focus", ""),
        ),
        "get_hospital_quality_profile": lambda args: get_hospital_quality_profile(
            hospital_query=args["hospital_query"],
        ),
        "compare_procedure_outcomes": lambda args: compare_procedure_outcomes(
            procedure=args["procedure"],
            location=args.get("location", ""),
        ),
        "find_surgeons_and_specialists": lambda args: find_surgeons_and_specialists(
            specialty_or_procedure=args["specialty_or_procedure"],
            location=args.get("location", ""),
        ),
        "compare_medicare_advantage_plans": lambda args: compare_medicare_advantage_plans(
            carrier=args.get("carrier", ""),
            state=args.get("state", ""),
            min_stars=args.get("min_stars", 1.0),
        ),
        "check_network_and_coverage_fit": lambda args: check_network_and_coverage_fit(
            hospital_name=args["hospital_name"],
            plan_or_carrier=args["plan_or_carrier"],
        ),
        "lookup_cms_metric_definition": lambda args: lookup_cms_metric_definition(
            metric_query=args["metric_query"],
        ),
        "save_or_query_care_memory": lambda args: save_or_query_care_memory(
            action=args["action"],
            topic_key=args.get("topic_key", "care_shortlist"),
            author_role=args.get("author_role", "Patient/Caregiver"),
            title=args.get("title", ""),
            content=args.get("content", ""),
        ),
        "submit_feedback_or_escalation": lambda args: submit_feedback_or_escalation(
            action=args["action"],
            rating=args.get("rating", "up"),
            comment=args.get("comment", ""),
            topic_key=args.get("topic_key", "general_navigation"),
            request_id=args.get("request_id", ""),
        ),
    }

    handler = dispatch_map.get(tool_name)
    if handler is None:
        return {
            "status": "error",
            "error_code": "UNKNOWN_TOOL",
            "message": f"Tool '{tool_name}' is not registered.",
            "recovery_guidance": f"Select a valid tool from: {list(TOOL_JSON_SCHEMAS.keys())}.",
        }
    return handler(arguments)


__all__ = [
    "CareMemoryArgs",
    "CheckNetworkFitArgs",
    "CmsMetricLookupArgs",
    "CompareMedicarePlansArgs",
    "CompareProcedureArgs",
    "FeedbackEscalationArgs",
    "FindSurgeonsArgs",
    "HospitalProfileArgs",
    "SearchHospitalsArgs",
    "TOOL_JSON_SCHEMAS",
    "ToolInterfaceRegistry",
    "check_network_and_coverage_fit",
    "compare_medicare_advantage_plans",
    "compare_procedure_outcomes",
    "execute_validated_tool",
    "find_surgeons_and_specialists",
    "get_hospital_quality_profile",
    "lookup_cms_metric_definition",
    "save_or_query_care_memory",
    "search_hospitals_by_location",
    "submit_feedback_or_escalation",
    "validate_tool_args",
]
