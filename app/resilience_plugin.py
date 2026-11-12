# Copyright 2026 CareMatch Contributors
# Licensed under the Apache License, Version 2.0.

"""Deterministic Resilience Plugin, Tool Planner & Markdown Formatter for CareMatch.

Ensures CareMatch always returns accurate, grounded public CMS hospital comparisons,
surgeon rosters, and Medicare Advantage Star Ratings even when live LLM API keys are
not configured (local testing, CI, air-gapped demos, or API rate limits).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.cms_data import HOSPITALS_DB, STATE_NAMES, ZIP_CENTROIDS

try:
    from google.adk.plugins import BasePlugin as _BasePlugin
except Exception:  # pragma: no cover - optional ADK dependency fallback
    class _BasePlugin:  # type: ignore[no-redef]
        def __init__(self, name: str = "carematch_resilience") -> None:
            self.name = name


@dataclass
class _PlannedFunctionCall:
    name: str
    args: dict[str, Any]


@dataclass
class _PlannedPart:
    function_call: _PlannedFunctionCall


def _extract_location(prompt: str) -> str:
    zip_m = re.search(r"\b(\d{5})\b", prompt)
    if zip_m:
        return zip_m.group(1)

    p_low = prompt.lower()
    for _, (_, _, city, _) in ZIP_CENTROIDS.items():
        if city.lower() in p_low:
            return city

    for h in HOSPITALS_DB:
        if h["city"].lower() in p_low:
            return h["city"]

    for code, full_name in STATE_NAMES.items():
        if full_name.lower() in p_low or re.search(rf"\b{code}\b", prompt):
            return code
    return ""


def _extract_hospital(prompt: str) -> str:
    p_low = prompt.lower()
    for h in HOSPITALS_DB:
        if h["name"].lower() in p_low:
            return h["name"]
    aliases = {
        "ohsu": "OHSU Hospital (Marquam Hill)",
        "hillsboro": "OHSU Hillsboro Medical Center",
        "st. vincent": "Providence St. Vincent Medical Center",
        "barnes": "Barnes-Jewish Hospital",
        "mercy": "Mercy Hospital South",
        "missouri baptist": "Missouri Baptist Medical Center",
        "emory": "Emory University Hospital",
        "piedmont": "Piedmont Atlanta Hospital",
        "northside": "Northside Hospital Atlanta",
        "ut southwestern": "UT Southwestern William P. Clements Jr. University Hospital",
        "clements": "UT Southwestern William P. Clements Jr. University Hospital",
        "baylor": "Baylor University Medical Center",
        "northwestern": "Northwestern Memorial Hospital",
        "rush": "Rush University Medical Center",
        "uchealth": "UCHealth University of Colorado Hospital",
        "hss": "Hospital for Special Surgery (HSS)",
        "special surgery": "Hospital for Special Surgery (HSS)",
        "cleveland clinic": "Cleveland Clinic",
        "penn": "Hospital of the University of Pennsylvania (HUP)",
        "mayo": "Mayo Clinic Hospital — Rochester",
        "mass general": "Massachusetts General Hospital",
        "ucsf": "UCSF Medical Center (Parnassus)",
        "cedars": "Cedars-Sinai Medical Center",
        "tampa general": "Tampa General Hospital",
    }
    for alias, canonical in aliases.items():
        if alias in p_low:
            return canonical
    return ""


def _extract_procedure(prompt: str) -> str:
    p_low = prompt.lower()
    if any(k in p_low for k in ("hip", "knee", "joint", "arthroplasty", "ortho")):
        return "hip_knee"
    if any(k in p_low for k in ("cabg", "bypass", "heart surgery", "valve", "cardiac surgery")):
        return "cabg"
    if any(k in p_low for k in ("heart failure", "readmission", "chf")):
        return "heart_failure"
    if any(k in p_low for k in ("maternity", "birth", "delivery", "c-section", "ob/gyn", "obgyn")):
        return "maternity"
    if "stroke" in p_low:
        return "stroke"
    return ""


def _extract_carrier(prompt: str) -> str:
    p_low = prompt.lower()
    for carrier in (
        "Kaiser",
        "UnitedHealthcare",
        "UHC",
        "Humana",
        "Anthem",
        "Elevance",
        "Aetna",
        "Regence",
        "Independence Blue Cross",
        "Blue Cross",
    ):
        if carrier.lower() in p_low:
            return "UnitedHealthcare" if carrier == "UHC" else carrier
    return ""


def _plan_tool_calls(prompt: str) -> list[_PlannedPart]:
    """Deterministically plan CareMatch tool calls based on user intent."""
    p = (prompt or "").strip()
    p_low = p.lower()
    parts: list[_PlannedPart] = []

    loc = _extract_location(p)
    hosp = _extract_hospital(p)
    proc = _extract_procedure(p)
    carrier = _extract_carrier(p)

    # 1. CMS Methodology / Glossary queries
    if any(
        k in p_low
        for k in ("methodology", "how are star", "what is hcahps", "cms-0057", "comp_hip_knee", "data source", "define ")
    ):
        parts.append(
            _PlannedPart(
                _PlannedFunctionCall("lookup_cms_metric_definition", {"metric_query": p})
            )
        )

    # 2. Network & Coverage Fit check (both hospital & carrier mentioned)
    if hosp and carrier:
        parts.append(
            _PlannedPart(
                _PlannedFunctionCall(
                    "check_network_and_coverage_fit",
                    {"hospital_name": hosp, "plan_or_carrier": carrier},
                )
            )
        )

    # 3. Medicare Advantage / Part D comparison
    if any(
        k in p_low
        for k in ("medicare", "advantage", "part d", "part c", "plan star", "insurance", "ppo", "hmo")
    ) or carrier:
        state_arg = loc if len(loc) == 2 and loc.isalpha() else ""
        parts.append(
            _PlannedPart(
                _PlannedFunctionCall(
                    "compare_medicare_advantage_plans",
                    {"carrier": carrier, "state": state_arg, "min_stars": 1.0},
                )
            )
        )

    # 4. Specific hospital profile
    if hosp:
        parts.append(
            _PlannedPart(
                _PlannedFunctionCall(
                    "get_hospital_quality_profile", {"hospital_query": hosp}
                )
            )
        )

    # 5. Location-based hospital search
    if loc and not hosp:
        parts.append(
            _PlannedPart(
                _PlannedFunctionCall(
                    "search_hospitals_by_location",
                    {
                        "location": loc,
                        "radius_miles": 45,
                        "min_stars": 1,
                        "procedure_focus": proc,
                    },
                )
            )
        )

    # 6. Procedure comparison
    if proc:
        parts.append(
            _PlannedPart(
                _PlannedFunctionCall(
                    "compare_procedure_outcomes",
                    {"procedure": proc, "location": loc},
                )
            )
        )

    # 7. Surgeon / Specialist discovery
    if (
        any(
            k in p_low
            for k in ("surgeon", "doctor", "physician", "specialist", "orthopedic", "cardiologist", "ob/gyn")
        )
        or proc
    ):
        parts.append(
            _PlannedPart(
                _PlannedFunctionCall(
                    "find_surgeons_and_specialists",
                    {
                        "specialty_or_procedure": proc or p,
                        "location": loc or hosp,
                    },
                )
            )
        )

    # 8. Default fallback: show top CMS-rated hospitals near flagship metro or nationwide
    if not parts:
        parts.append(
            _PlannedPart(
                _PlannedFunctionCall(
                    "search_hospitals_by_location",
                    {"location": "63010" if "63010" in p else "97124", "radius_miles": 50},
                )
            )
        )

    return parts


def _stars(val: Any) -> str:
    try:
        n = int(round(float(val)))
        return f"{'★' * n}{'☆' * max(0, 5 - n)} ({val}/5)"
    except (TypeError, ValueError):
        return str(val)


def _format_tool_results_markdown(
    fn_results: list[tuple[str, dict[str, Any]]],
    route_info: dict[str, Any],
    emergency_banner: str = "",
) -> str:
    """Format grounded CMS tool outputs into a concise, scannable Markdown report."""
    sections: list[str] = []
    if emergency_banner:
        sections.append(f"> **EMERGENCY ALERT:** {emergency_banner}\n")

    sections.append(
        f"**CareMatch Navigator** · Specialist: `{route_info.get('routed_specialist', 'hospital_quality_agent')}` "
        f"· Tier: `{route_info.get('tier_id', 'HOSPITAL_QUALITY_COMPARE')}`\n"
    )

    for tool_name, res in fn_results:
        status = res.get("status")
        if status in ("not_found", "error"):
            sections.append(
                f"### No Exact Match ({tool_name})\n"
                f"- **Guidance:** {res.get('recovery_guidance', res.get('message', 'Try broadening your search.'))}\n"
            )
            continue

        if tool_name == "search_hospitals_by_location":
            anchor = res.get("search_anchor", "")
            lines = [
                f"### Top CMS-Rated Hospitals Near {anchor}",
                "| Hospital | City/State | Distance | CMS Overall | HCAHPS | Top Affiliated Specialists |",
                "|---|---|---:|---|---|---|",
            ]
            for h in res.get("hospitals", [])[:8]:
                dist_str = f"{h['distance_miles']} mi" if h.get("distance_miles") is not None else "Regional"
                docs = ", ".join(s["name"] for s in h.get("specialists", [])[:2]) or "Verify via NPPES"
                lines.append(
                    f"| **{h['name']}** (`CCN {h.get('ccn', 'N/A')}`) | {h['city']}, {h['state']} | {dist_str} | "
                    f"{_stars(h['overall_stars'])} | {_stars(h.get('hcahps_stars', 'N/A'))} | {docs} |"
                )
            lines.append(
                f"\n*Source: {res.get('data_source', 'Public CMS Provider Data Catalog')} — [Verify on Medicare Care Compare]({res.get('verify_url', 'https://www.medicare.gov/care-compare/')})*"
            )
            sections.append("\n".join(lines))

        elif tool_name == "get_hospital_quality_profile":
            h = res.get("hospital", {})
            proc_lines = [
                f"- **{k.replace('_', ' ').title()}**: {v.get('rating', '')} ({v.get('rate', v.get('c_section_rate', 'N/A'))})"
                for k, v in h.get("procedures", {}).items()
            ]
            doc_lines = [
                f"- **{s['name']}** — {s['specialty']}"
                for s in h.get("specialists", [])
            ]
            sections.append(
                f"### Hospital Quality Profile: {h.get('name')} (`CCN {h.get('ccn')}`)\n"
                f"- **Location:** {h.get('city')}, {h.get('state')} {h.get('zip')}\n"
                f"- **CMS Overall Star Rating:** {_stars(h.get('overall_stars'))} | **HCAHPS Patient Experience:** {_stars(h.get('hcahps_stars'))}\n"
                f"- **Safety Summary:** {h.get('safety_summary')}\n"
                + ("\n**Procedure Outcomes:**\n" + "\n".join(proc_lines) if proc_lines else "")
                + ("\n\n**Affiliated Surgeons & Specialists:**\n" + "\n".join(doc_lines) if doc_lines else "")
                + f"\n\n*Official CMS Page: {res.get('medicare_care_compare_url')}*"
            )

        elif tool_name == "compare_procedure_outcomes":
            proc = res.get("procedure_category", "").replace("_", " ").upper()
            lines = [
                f"### CMS Procedure Outcomes Comparison: {proc}",
                "| Hospital | Location | CMS Overall | Procedure Benchmark | Rate |",
                "|---|---|---|---|---|",
            ]
            for row in res.get("comparisons", [])[:6]:
                pm = row.get("procedure_metrics", {})
                rate = pm.get("rate", pm.get("c_section_rate", "N/A"))
                lines.append(
                    f"| **{row['hospital_name']}** | {row['city']}, {row['state']} | "
                    f"{_stars(row['overall_stars'])} | {pm.get('rating', 'N/A')} | {rate} |"
                )
            sections.append("\n".join(lines))

        elif tool_name == "find_surgeons_and_specialists":
            lines = [
                f"### Surgeons & Specialists ({res.get('specialty_query')})",
                "| Clinician | Specialty | Affiliated Hospital | Location | CMS Stars |",
                "|---|---|---|---|---|",
            ]
            for sp in res.get("specialists", [])[:8]:
                lines.append(
                    f"| **{sp['clinician_name']}** | {sp['specialty']} | {sp['affiliated_hospital']} | "
                    f"{sp['city']}, {sp['state']} | {_stars(sp['hospital_stars'])} |"
                )
            lines.append(
                "\n*Verify active NPI credentials and surgical privileges via the [HHS NPPES NPI Registry](https://npiregistry.cms.hhs.gov/search) and [Medicare Care Compare](https://www.medicare.gov/care-compare/?providerType=Physician).*"
            )
            sections.append("\n".join(lines))

        elif tool_name == "compare_medicare_advantage_plans":
            lines = [
                "### CMS Medicare Advantage & Part D Star Ratings",
                "| Contract | Carrier | Plan Name | Type | Overall Stars | Part D | Highlights |",
                "|---|---|---|---|---|---|---|",
            ]
            for p in res.get("plans", [])[:8]:
                lines.append(
                    f"| `{p['contract_id']}` | **{p['carrier']}** | {p['plan_name']} | {p['plan_type']} | "
                    f"{_stars(p['overall_stars'])} | {_stars(p['part_d_stars'])} | {p['highlights']} |"
                )
            lines.append(
                "\n*Source: Public CMS Part C & Part D Star Ratings — verify county availability at [Medicare Plan Finder](https://www.medicare.gov/plan-compare/).*"
            )
            sections.append("\n".join(lines))

        elif tool_name == "check_network_and_coverage_fit":
            checklist = "\n".join(f"- {item}" for item in res.get("verification_checklist", []))
            sections.append(
                f"### Network & Prior Authorization Checklist: {res.get('hospital_name')} × {res.get('carrier_query')}\n"
                f"> {res.get('network_disclaimer')}\n\n"
                f"{checklist}"
            )

        elif tool_name == "lookup_cms_metric_definition":
            defs = res.get("definitions", {})
            lines = ["### CMS Quality Metric & Regulatory Definitions"]
            for _, d in defs.items():
                lines.append(
                    f"- **{d['title']}** (*{d['dataset']}*): {d['summary']} ([Reference]({d['reference_url']}))"
                )
            sections.append("\n".join(lines))

    sections.append(
        "\n---\n*Informational comparison based solely on public federal CMS & HHS NPPES data. "
        "CareMatch does not provide medical advice; always consult licensed clinicians and verify in-network coverage with your insurer.*"
    )
    return "\n\n".join(sections)


class CareMatchResiliencePlugin(_BasePlugin):
    """ADK Plugin providing deterministic CMS tool planning and zero-downtime fallback."""

    def __init__(self, name: str = "carematch_resilience") -> None:
        super().__init__(name=name)

    def plan_tools_for_prompt(self, prompt: str) -> list[_PlannedPart]:
        return _plan_tool_calls(prompt)

    def format_results(
        self,
        fn_results: list[tuple[str, dict[str, Any]]],
        route_info: dict[str, Any],
        emergency_banner: str = "",
    ) -> str:
        return _format_tool_results_markdown(
            fn_results, route_info, emergency_banner=emergency_banner
        )
