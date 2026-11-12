# Copyright 2026 CareMatch Contributors
# Licensed under the Apache License, Version 2.0.

"""Domain unit tests covering CareMatch geospatial lookups, surgeons, plans, and root facades."""

from __future__ import annotations

from memory import AGENT_SYSTEM_PROMPT, get_compacted_context_window
from tools import (
    ToolInterfaceRegistry,
    compare_medicare_advantage_plans,
    compare_procedure_outcomes,
    execute_validated_tool,
    find_surgeons_and_specialists,
    search_hospitals_by_location,
)


def test_root_tool_registry_and_dispatcher() -> None:
    assert len(ToolInterfaceRegistry.list_tools()) == 9
    assert ToolInterfaceRegistry.get_schema("search_hospitals_by_location") is not None

    out = execute_validated_tool(
        "search_hospitals_by_location",
        {"location": "30309", "radius_miles": 25, "min_stars": 4},
    )
    assert out["status"] == "success"
    hospital_names = [h["name"] for h in out["hospitals"]]
    assert "Piedmont Atlanta Hospital" in hospital_names
    assert "Emory University Hospital" in hospital_names


def test_root_memory_compaction_facade() -> None:
    assert "CareMatch" in AGENT_SYSTEM_PROMPT
    ctx = get_compacted_context_window("unit_facade_session")
    assert ctx["system_prompt_included"] is True
    assert ctx["messages"][0]["role"] == "system"


def test_procedure_and_surgeon_matching_across_metros() -> None:
    cabg_dallas = compare_procedure_outcomes("cabg", "75201")
    assert cabg_dallas["status"] == "success"
    assert cabg_dallas["total_hospitals"] >= 2

    surgeons_stl = find_surgeons_and_specialists("orthopedic", "63010")
    assert surgeons_stl["status"] == "success"
    assert len(surgeons_stl["specialists"]) >= 2
    assert all("npiregistry.cms.hhs.gov" in s["nppes_lookup_url"] for s in surgeons_stl["specialists"])


def test_medicare_plan_filtering() -> None:
    or_plans = compare_medicare_advantage_plans(state="OR", min_stars=4.0)
    assert or_plans["status"] == "success"
    carriers = {p["carrier"] for p in or_plans["plans"]}
    assert "Kaiser Permanente" in carriers

    by_zip_ny = search_hospitals_by_location("07030", radius_miles=20, min_stars=4)
    assert by_zip_ny["status"] == "success"
    assert any("Hospital for Special Surgery" in h["name"] for h in by_zip_ny["hospitals"])
