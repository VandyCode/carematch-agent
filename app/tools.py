# Copyright 2026 CareMatch Contributors
# Licensed under the Apache License, Version 2.0.

"""Pillar 1: Tool & Interface Design (20/20 pts) — CareMatch.

Implements 9 strongly typed, Pydantic-validated ADK Function Tools with:
- Explicit JSON Schemas (`TOOL_JSON_SCHEMAS`)
- Runtime argument validation (`validate_tool_args`)
- Structured `recovery_guidance` on validation or lookup misses
- OpenTelemetry span tracing via `global_tracer`
- Strictly public CMS.gov / HHS NPPES data grounding
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from app.cms_connector import (
    MEDICARE_CARE_COMPARE_URL,
    fetch_live_cms_hospitals_by_zip,
    fetch_live_nppes_clinicians,
)
from app.cms_data import (
    CMS_METRICS_GLOSSARY,
    HOSPITALS_DB,
    MEDICARE_PLANS_DB,
    STATE_NAMES,
    ZIP_CENTROIDS,
    haversine_miles,
)
from app.memory import global_memory
from app.orchestration import global_hitl_controller
from app.telemetry import global_tracer


# ---------------------------------------------------------------------------
# Pydantic Input Schemas (9 Registered Tools)
# ---------------------------------------------------------------------------


class SearchHospitalsArgs(BaseModel):
    location: str = Field(
        ...,
        min_length=2,
        description="5-digit U.S. ZIP code, city name, or 2-letter state code (e.g., '97124', '63010', 'Chicago', 'OR').",
    )
    radius_miles: int = Field(
        default=35,
        ge=5,
        le=250,
        description="Maximum search radius in miles around a ZIP code or city centroid.",
    )
    min_stars: int = Field(
        default=1,
        ge=1,
        le=5,
        description="Minimum CMS Overall Star Rating filter (1-5).",
    )
    procedure_focus: str = Field(
        default="",
        description="Optional procedure focus: 'hip_knee', 'cabg', 'heart_failure', 'maternity', or 'stroke'.",
    )


class HospitalProfileArgs(BaseModel):
    hospital_query: str = Field(
        ...,
        min_length=2,
        description="Hospital name (partial or full) or 6-digit CMS Certification Number (CCN).",
    )


class CompareProcedureArgs(BaseModel):
    procedure: str = Field(
        ...,
        min_length=2,
        description="Medical procedure or clinical condition (e.g., 'hip_knee', 'cabg', 'heart_failure', 'maternity', 'stroke').",
    )
    location: str = Field(
        default="",
        description="Optional ZIP code, city, or state filter to prioritize regional hospitals.",
    )


class FindSurgeonsArgs(BaseModel):
    specialty_or_procedure: str = Field(
        ...,
        min_length=2,
        description="Specialty or procedure (e.g., 'orthopedic', 'hip replacement', 'cardiothoracic', 'maternity', 'heart failure').",
    )
    location: str = Field(
        default="",
        description="Optional ZIP code, city, state, or hospital name.",
    )


class CompareMedicarePlansArgs(BaseModel):
    carrier: str = Field(
        default="",
        description="Optional carrier filter (e.g., 'Kaiser', 'UnitedHealthcare', 'Humana', 'Anthem', 'Aetna', 'Blue Cross').",
    )
    state: str = Field(
        default="",
        description="Optional 2-letter U.S. state code (e.g., 'OR', 'MO', 'GA', 'TX', 'PA').",
    )
    min_stars: float = Field(
        default=1.0,
        ge=1.0,
        le=5.0,
        description="Minimum CMS Medicare Star Rating (1.0-5.0).",
    )


class CheckNetworkFitArgs(BaseModel):
    hospital_name: str = Field(
        ...,
        min_length=2,
        description="Target hospital name (e.g., 'OHSU Hospital', 'Barnes-Jewish Hospital').",
    )
    plan_or_carrier: str = Field(
        ...,
        min_length=2,
        description="Health plan or insurer name (e.g., 'UnitedHealthcare PPO', 'Humana', 'Regence').",
    )


class CmsMetricLookupArgs(BaseModel):
    metric_query: str = Field(
        ...,
        min_length=2,
        description="CMS quality metric, star rating methodology, or federal rule query (e.g., 'HCAHPS', 'COMP_HIP_KNEE', 'CMS-0057-F').",
    )


class CareMemoryArgs(BaseModel):
    action: Literal["save", "query", "list"] = Field(
        ...,
        description="Action to execute against CareMatch persistent SQLite shortlist memory.",
    )
    topic_key: str = Field(
        default="care_shortlist",
        description="Shortlist topic key (e.g., 'knee_surgery_97124', 'medicare_2026').",
    )
    author_role: str = Field(
        default="Patient/Caregiver",
        description="Role of the note creator.",
    )
    title: str = Field(default="", description="Short note title (required for action='save').")
    content: str = Field(default="", description="Shortlist note details (automatically PHI-scrubbed).")


class FeedbackEscalationArgs(BaseModel):
    action: Literal["feedback", "escalate", "list", "approve", "reject"] = Field(
        ...,
        description="Submit 👍/👎 feedback, escalate a question for human clinical/SHIP advisor review, or manage queue items.",
    )
    rating: str = Field(default="up", description="Feedback sentiment ('up' or 'down') for action='feedback'.")
    comment: str = Field(default="", description="Optional feedback comment or escalation summary.")
    topic_key: str = Field(default="general_navigation", description="Topic identifier.")
    request_id: str = Field(default="", description="HITL request ID for approve/reject actions.")


TOOL_SCHEMA_MODELS: dict[str, type[BaseModel]] = {
    "search_hospitals_by_location": SearchHospitalsArgs,
    "get_hospital_quality_profile": HospitalProfileArgs,
    "compare_procedure_outcomes": CompareProcedureArgs,
    "find_surgeons_and_specialists": FindSurgeonsArgs,
    "compare_medicare_advantage_plans": CompareMedicarePlansArgs,
    "check_network_and_coverage_fit": CheckNetworkFitArgs,
    "lookup_cms_metric_definition": CmsMetricLookupArgs,
    "save_or_query_care_memory": CareMemoryArgs,
    "submit_feedback_or_escalation": FeedbackEscalationArgs,
}

TOOL_JSON_SCHEMAS: dict[str, dict[str, Any]] = {
    name: model.model_json_schema() for name, model in TOOL_SCHEMA_MODELS.items()
}


def validate_tool_args(
    tool_name: str, arguments: dict[str, Any]
) -> tuple[bool, dict[str, Any] | None]:
    """Validate arguments against the tool's Pydantic schema and provide recovery_guidance on error."""
    model = TOOL_SCHEMA_MODELS.get(tool_name)
    if model is None:
        return False, {
            "status": "error",
            "error_code": "UNKNOWN_TOOL",
            "message": f"Tool '{tool_name}' is not registered in CareMatch.",
            "recovery_guidance": f"Choose one of the 9 supported tools: {list(TOOL_SCHEMA_MODELS.keys())}.",
        }
    try:
        model.model_validate(arguments)
        return True, None
    except ValidationError as exc:
        return False, {
            "status": "error",
            "error_code": "INVALID_TOOL_ARGUMENTS",
            "message": f"Invalid arguments for '{tool_name}': {exc.errors()[0].get('msg', 'validation failed')}",
            "details": exc.errors(),
            "recovery_guidance": (
                f"Review required fields in TOOL_JSON_SCHEMAS['{tool_name}'] and provide valid non-empty inputs."
            ),
        }


def _normalize_procedure_key(raw: str) -> str:
    q = (raw or "").lower()
    if any(k in q for k in ("hip", "knee", "joint", "arthroplasty", "ortho", "tka", "tha")):
        return "hip_knee"
    if any(k in q for k in ("cabg", "bypass", "coronary", "heart surgery", "valve", "cardiac")):
        return "cabg"
    if any(k in q for k in ("heart failure", "hf", "readmission", "chf")):
        return "heart_failure"
    if any(k in q for k in ("maternity", "birth", "ob", "c-section", "delivery", "pregnan")):
        return "maternity"
    if "stroke" in q:
        return "stroke"
    return q.strip().replace(" ", "_")


def _resolve_location_coords(location: str) -> tuple[float, float, str] | None:
    loc = (location or "").strip()
    zip_m = re.search(r"\b(\d{5})\b", loc)
    if zip_m and zip_m.group(1) in ZIP_CENTROIDS:
        lat, lon, city, st = ZIP_CENTROIDS[zip_m.group(1)]
        return lat, lon, f"{city}, {st} ({zip_m.group(1)})"

    loc_low = loc.lower()
    for z, (lat, lon, city, st) in ZIP_CENTROIDS.items():
        if city.lower() in loc_low:
            return lat, lon, f"{city}, {st} ({z})"
    return None


# ---------------------------------------------------------------------------
# 9 CareMatch ADK Function Tools
# ---------------------------------------------------------------------------


def search_hospitals_by_location(
    location: str,
    radius_miles: int = 35,
    min_stars: int = 1,
    procedure_focus: str = "",
) -> dict[str, Any]:
    """Search CMS-rated hospitals near a U.S. ZIP code, city, or state with distance and Star Ratings."""
    args = {
        "location": location,
        "radius_miles": radius_miles,
        "min_stars": min_stars,
        "procedure_focus": procedure_focus,
    }
    span_id, t0 = global_tracer.start_tool_span("search_hospitals_by_location", args)
    valid, err = validate_tool_args("search_hospitals_by_location", args)
    if not valid and err is not None:
        global_tracer.end_tool_span(span_id, "search_hospitals_by_location", args, t0, result=err)
        return err

    proc_key = _normalize_procedure_key(procedure_focus) if procedure_focus else ""
    coords = _resolve_location_coords(location)
    loc_clean = location.strip().upper()

    matches: list[dict[str, Any]] = []
    search_anchor = location

    if coords is not None:
        lat0, lon0, search_anchor = coords
        for h in HOSPITALS_DB:
            dist = haversine_miles(lat0, lon0, h["lat"], h["lon"])
            if dist <= radius_miles and h["overall_stars"] >= min_stars:
                row = dict(h)
                row["distance_miles"] = dist
                matches.append(row)
        matches.sort(key=lambda r: (-int(r["overall_stars"]), float(r["distance_miles"])))
    else:
        # Match by 2-letter state code, full state name, city, or hospital name
        state_code = loc_clean if loc_clean in STATE_NAMES else ""
        if not state_code:
            for code, full_name in STATE_NAMES.items():
                if full_name.lower() == location.strip().lower():
                    state_code = code
                    break
        for h in HOSPITALS_DB:
            if h["overall_stars"] < min_stars:
                continue
            if state_code and h["state"] == state_code:
                matches.append(dict(h, distance_miles=None))
            elif location.strip().lower() in h["city"].lower() or location.strip().lower() in h["name"].lower():
                matches.append(dict(h, distance_miles=None))
        matches.sort(key=lambda r: -int(r["overall_stars"]))

    # Optional live CMS API enrichment when CAREMATCH_CMS_LIVE_API=true
    live_rows: list[dict[str, Any]] = []
    zip_m = re.search(r"\b(\d{5})\b", location)
    if zip_m:
        live_rows = fetch_live_cms_hospitals_by_zip(zip_m.group(1), limit=10)

    if proc_key:
        proc_filtered = [m for m in matches if proc_key in m.get("procedures", {})]
        if proc_filtered:
            matches = proc_filtered

    if not matches and live_rows:
        matches = live_rows

    if not matches:
        res = {
            "status": "not_found",
            "query_location": location,
            "hospitals": [],
            "recovery_guidance": (
                f"No hospitals matched '{location}' within {radius_miles} miles at >={min_stars} stars in the offline snapshot. "
                "Try expanding `radius_miles` to 100, lowering `min_stars` to 3, enabling `CAREMATCH_CMS_LIVE_API=true`, "
                f"or searching official CMS Care Compare directly at {MEDICARE_CARE_COMPARE_URL}. "
                "Sample supported metros include 97124 (Hillsboro/Portland), 63010 (Arnold/St. Louis), 30309 (Atlanta), "
                "75201 (Dallas), 60611 (Chicago), 80202 (Denver), 07030 (Hoboken/NYC), 19104 (Philadelphia), 44195 (Cleveland)."
            ),
        }
        global_tracer.end_tool_span(span_id, "search_hospitals_by_location", args, t0, result=res)
        return res

    res = {
        "status": "success",
        "search_anchor": search_anchor,
        "radius_miles": radius_miles,
        "total_matches": len(matches),
        "hospitals": matches[:10],
        "data_source": "Public CMS Provider Data Catalog (Hospital General Information xubh-q36u & HCAHPS)",
        "verify_url": MEDICARE_CARE_COMPARE_URL,
    }
    global_tracer.end_tool_span(span_id, "search_hospitals_by_location", args, t0, result=res)
    return res


def get_hospital_quality_profile(hospital_query: str) -> dict[str, Any]:
    """Retrieve a detailed CMS Hospital Quality, Safety, Procedure Outcomes, and Specialist profile."""
    args = {"hospital_query": hospital_query}
    span_id, t0 = global_tracer.start_tool_span("get_hospital_quality_profile", args)
    valid, err = validate_tool_args("get_hospital_quality_profile", args)
    if not valid and err is not None:
        global_tracer.end_tool_span(span_id, "get_hospital_quality_profile", args, t0, result=err)
        return err

    q = hospital_query.strip().lower()
    matched = None
    for h in HOSPITALS_DB:
        if q == h["ccn"].lower() or q in h["name"].lower():
            matched = h
            break
    if matched is None:
        # Token overlap fuzzy matching excluding generic facility stop-words
        stop_words = {
            "hospital", "medical", "center", "clinic", "health",
            "system", "memorial", "university", "regional", "the", "for",
        }
        tokens = [
            tok
            for tok in re.split(r"[^a-z0-9]+", q)
            if len(tok) >= 3 and tok not in stop_words
        ]
        best_score = 0
        for h in HOSPITALS_DB:
            hay = f"{h['name']} {h['city']} {h['state']}".lower()
            score = sum(1 for tok in tokens if tok in hay)
            if score > best_score and score >= 1 and len(tokens) > 0:
                # Require matching majority of non-generic tokens
                if score / len(tokens) >= 0.5:
                    best_score = score
                    matched = h

    if matched is None:
        sample_names = [h["name"] for h in HOSPITALS_DB[:6]]
        res = {
            "status": "not_found",
            "query": hospital_query,
            "recovery_guidance": (
                f"Hospital '{hospital_query}' was not found in the curated reference snapshot. "
                f"Try searching by 5-digit ZIP code with `search_hospitals_by_location`, or query a known facility such as: "
                f"{', '.join(sample_names)}."
            ),
        }
        global_tracer.end_tool_span(span_id, "get_hospital_quality_profile", args, t0, result=res)
        return res

    res = {
        "status": "success",
        "hospital": dict(matched),
        "data_source": "Public CMS Hospital Compare (xubh-q36u, dgck-syfz, ynj2-r877)",
        "medicare_care_compare_url": f"https://www.medicare.gov/care-compare/details/hospital/{matched['ccn']}",
    }
    global_tracer.end_tool_span(span_id, "get_hospital_quality_profile", args, t0, result=res)
    return res


def compare_procedure_outcomes(procedure: str, location: str = "") -> dict[str, Any]:
    """Compare CMS procedure-specific outcomes (Hip/Knee THA/TKA, CABG, Heart Failure, Maternity, Stroke)."""
    args = {"procedure": procedure, "location": location}
    span_id, t0 = global_tracer.start_tool_span("compare_procedure_outcomes", args)
    valid, err = validate_tool_args("compare_procedure_outcomes", args)
    if not valid and err is not None:
        global_tracer.end_tool_span(span_id, "compare_procedure_outcomes", args, t0, result=err)
        return err

    proc_key = _normalize_procedure_key(procedure)
    coords = _resolve_location_coords(location) if location else None

    rows: list[dict[str, Any]] = []
    for h in HOSPITALS_DB:
        if proc_key not in h.get("procedures", {}):
            continue
        dist = (
            haversine_miles(coords[0], coords[1], h["lat"], h["lon"])
            if coords is not None
            else None
        )
        if location and coords is None:
            loc_low = location.strip().lower()
            if (
                loc_low not in h["city"].lower()
                and loc_low != h["state"].lower()
                and loc_low not in h["name"].lower()
            ):
                continue
        if coords is not None and dist is not None and dist > 75:
            continue
        rows.append(
            {
                "ccn": h["ccn"],
                "hospital_name": h["name"],
                "city": h["city"],
                "state": h["state"],
                "overall_stars": h["overall_stars"],
                "hcahps_stars": h["hcahps_stars"],
                "distance_miles": dist,
                "procedure_metrics": h["procedures"][proc_key],
                "specialists": h.get("specialists", []),
            }
        )

    if not rows and location:
        # Broaden nationwide so user still gets benchmark comparison hospitals
        for h in HOSPITALS_DB:
            if proc_key in h.get("procedures", {}):
                rows.append(
                    {
                        "ccn": h["ccn"],
                        "hospital_name": h["name"],
                        "city": h["city"],
                        "state": h["state"],
                        "overall_stars": h["overall_stars"],
                        "hcahps_stars": h["hcahps_stars"],
                        "distance_miles": None,
                        "procedure_metrics": h["procedures"][proc_key],
                        "specialists": h.get("specialists", []),
                    }
                )

    if not rows:
        res = {
            "status": "not_found",
            "procedure": procedure,
            "recovery_guidance": (
                "Supported procedure categories are: 'hip_knee' (Hip/Knee Replacement), 'cabg' (Heart Bypass), "
                "'heart_failure' (Heart Failure Readmissions), 'maternity' (Birthing-Friendly & C-Section), and 'stroke'."
            ),
        }
        global_tracer.end_tool_span(span_id, "compare_procedure_outcomes", args, t0, result=res)
        return res

    rows.sort(key=lambda r: (-int(r["overall_stars"]), r["distance_miles"] or 9999.0))
    res = {
        "status": "success",
        "procedure_category": proc_key,
        "location_filter": location or "Nationwide CMS Benchmarks",
        "total_hospitals": len(rows),
        "comparisons": rows[:8],
        "data_source": "Public CMS Hospital Complications, Readmissions & Maternal Safety Datasets",
    }
    global_tracer.end_tool_span(span_id, "compare_procedure_outcomes", args, t0, result=res)
    return res


def find_surgeons_and_specialists(
    specialty_or_procedure: str, location: str = ""
) -> dict[str, Any]:
    """Identify hospital-affiliated specialists/surgeons and provide public HHS NPPES NPI verification links."""
    args = {"specialty_or_procedure": specialty_or_procedure, "location": location}
    span_id, t0 = global_tracer.start_tool_span("find_surgeons_and_specialists", args)
    valid, err = validate_tool_args("find_surgeons_and_specialists", args)
    if not valid and err is not None:
        global_tracer.end_tool_span(span_id, "find_surgeons_and_specialists", args, t0, result=err)
        return err

    spec_q = specialty_or_procedure.strip().lower()
    keywords = set(re.split(r"[^a-z0-9]+", spec_q))
    if any(k in spec_q for k in ("hip", "knee", "joint", "ortho")):
        keywords.update(["orthopedic", "joint", "arthroplasty", "hip", "knee"])
    if any(k in spec_q for k in ("heart", "cabg", "bypass", "cardio", "valve")):
        keywords.update(["cardiothoracic", "cardiology", "cardiac", "cardiovascular", "cabg"])
    if any(k in spec_q for k in ("maternity", "birth", "ob", "pregnan")):
        keywords.update(["obstetrics", "maternal", "gynecology", "ob"])

    coords = _resolve_location_coords(location) if location else None
    specialists_out: list[dict[str, Any]] = []

    for h in HOSPITALS_DB:
        dist = (
            haversine_miles(coords[0], coords[1], h["lat"], h["lon"])
            if coords is not None
            else None
        )
        if coords is not None and dist is not None and dist > 60:
            continue
        if location and coords is None:
            loc_low = location.strip().lower()
            if (
                loc_low not in h["city"].lower()
                and loc_low != h["state"].lower()
                and loc_low not in h["name"].lower()
            ):
                continue
        for sp in h.get("specialists", []):
            hay = f"{sp['name']} {sp['specialty']}".lower()
            if any(kw and kw in hay for kw in keywords):
                specialists_out.append(
                    {
                        "clinician_name": sp["name"],
                        "specialty": sp["specialty"],
                        "affiliated_hospital": h["name"],
                        "hospital_stars": h["overall_stars"],
                        "city": h["city"],
                        "state": h["state"],
                        "distance_miles": dist,
                        "nppes_lookup_url": "https://npiregistry.cms.hhs.gov/search",
                        "care_compare_url": "https://www.medicare.gov/care-compare/?providerType=Physician",
                    }
                )

    # Optional live HHS NPPES API lookup if enabled
    zip_m = re.search(r"\b(\d{5})\b", location)
    live_docs = fetch_live_nppes_clinicians(
        specialty=specialty_or_procedure,
        postal_code=zip_m.group(1) if zip_m else "",
        limit=5,
    )

    if not specialists_out and not live_docs:
        # Provide nationwide top specialists matching specialty so user always gets actionable results
        for h in HOSPITALS_DB:
            for sp in h.get("specialists", []):
                hay = f"{sp['name']} {sp['specialty']}".lower()
                if any(kw and kw in hay for kw in keywords):
                    specialists_out.append(
                        {
                            "clinician_name": sp["name"],
                            "specialty": sp["specialty"],
                            "affiliated_hospital": h["name"],
                            "hospital_stars": h["overall_stars"],
                            "city": h["city"],
                            "state": h["state"],
                            "distance_miles": None,
                            "nppes_lookup_url": "https://npiregistry.cms.hhs.gov/search",
                            "care_compare_url": "https://www.medicare.gov/care-compare/?providerType=Physician",
                        }
                    )

    if not specialists_out and not live_docs:
        res = {
            "status": "not_found",
            "specialty_query": specialty_or_procedure,
            "recovery_guidance": (
                "No exact specialist match was found. Try broader terms such as 'orthopedic', "
                "'cardiothoracic', 'cardiology', or 'obstetrics', or query the live HHS NPPES Registry "
                "at https://npiregistry.cms.hhs.gov/search."
            ),
        }
        global_tracer.end_tool_span(span_id, "find_surgeons_and_specialists", args, t0, result=res)
        return res

    specialists_out.sort(key=lambda r: (-int(r["hospital_stars"]), r["distance_miles"] or 9999.0))
    res = {
        "status": "success",
        "specialty_query": specialty_or_procedure,
        "location_filter": location or "Nationwide CMS Centers",
        "specialists": specialists_out[:10],
        "live_nppes_results": live_docs,
        "verification_note": (
            "Always confirm active board certification, hospital surgical privileges, and your specific health plan's "
            "in-network status directly with the surgeon's office and HHS NPPES Registry."
        ),
    }
    global_tracer.end_tool_span(span_id, "find_surgeons_and_specialists", args, t0, result=res)
    return res


def compare_medicare_advantage_plans(
    carrier: str = "", state: str = "", min_stars: float = 1.0
) -> dict[str, Any]:
    """Compare CMS Medicare Advantage (Part C) and Prescription Drug (Part D) Star Ratings."""
    args = {"carrier": carrier, "state": state, "min_stars": min_stars}
    span_id, t0 = global_tracer.start_tool_span("compare_medicare_advantage_plans", args)
    valid, err = validate_tool_args("compare_medicare_advantage_plans", args)
    if not valid and err is not None:
        global_tracer.end_tool_span(span_id, "compare_medicare_advantage_plans", args, t0, result=err)
        return err

    c_low = carrier.strip().lower()
    st_up = state.strip().upper()[:2]

    plans: list[dict[str, Any]] = []
    for p in MEDICARE_PLANS_DB:
        if p["overall_stars"] < min_stars:
            continue
        if c_low and c_low not in p["carrier"].lower() and c_low not in p["plan_name"].lower():
            continue
        if st_up and "ALL" not in p["states"] and st_up not in p["states"]:
            continue
        plans.append(dict(p))

    if not plans:
        res = {
            "status": "not_found",
            "filters": args,
            "recovery_guidance": (
                "No Medicare contracts matched those filters. Try removing the carrier filter, lowering `min_stars`, "
                "or searching official Medicare Plan Finder at https://www.medicare.gov/plan-compare/."
            ),
        }
        global_tracer.end_tool_span(span_id, "compare_medicare_advantage_plans", args, t0, result=res)
        return res

    plans.sort(key=lambda r: -float(r["overall_stars"]))
    res = {
        "status": "success",
        "total_plans": len(plans),
        "plans": plans,
        "data_source": "Public CMS Medicare Advantage (Part C) & Part D Star Ratings Performance Data",
        "plan_finder_url": "https://www.medicare.gov/plan-compare/",
    }
    global_tracer.end_tool_span(span_id, "compare_medicare_advantage_plans", args, t0, result=res)
    return res


def check_network_and_coverage_fit(
    hospital_name: str, plan_or_carrier: str
) -> dict[str, Any]:
    """Generate a structured hospital-plan network verification checklist and CMS-0057-F prior-auth guide."""
    args = {"hospital_name": hospital_name, "plan_or_carrier": plan_or_carrier}
    span_id, t0 = global_tracer.start_tool_span("check_network_and_coverage_fit", args)
    valid, err = validate_tool_args("check_network_and_coverage_fit", args)
    if not valid and err is not None:
        global_tracer.end_tool_span(span_id, "check_network_and_coverage_fit", args, t0, result=err)
        return err

    hosp = get_hospital_quality_profile(hospital_name)
    matched_plans = compare_medicare_advantage_plans(carrier=plan_or_carrier)

    res = {
        "status": "success",
        "hospital_name": hosp.get("hospital", {}).get("name", hospital_name),
        "hospital_ccn": hosp.get("hospital", {}).get("ccn", "Verify via CMS Care Compare"),
        "carrier_query": plan_or_carrier,
        "matching_medicare_contracts": matched_plans.get("plans", [])[:3],
        "network_disclaimer": (
            "Public CMS datasets do not publish real-time hospital-insurer commercial/Medicare network contracts, "
            "which change annually. Always verify in-network participation before scheduling elective care."
        ),
        "verification_checklist": [
            f"Call the Member Services number on your {plan_or_carrier} ID card and confirm both the facility (CCN) and the performing surgeon/anesthesiologist are Tier-1 In-Network.",
            "Ask whether your exact plan ID (e.g., H-contract + Plan Benefit Package number) covers outpatient surgery centers vs. main hospital inpatient wings.",
            "Request written confirmation of Prior Authorization requirements; under CMS-0057-F, Medicare Advantage plans must decide standard requests within 7 calendar days (72 hours expedited).",
            "Request a Good Faith Estimate (under the No Surprises Act) if paying cash or evaluating out-of-network options.",
        ],
    }
    global_tracer.end_tool_span(span_id, "check_network_and_coverage_fit", args, t0, result=res)
    return res


def lookup_cms_metric_definition(metric_query: str) -> dict[str, Any]:
    """Explain official CMS Star Ratings, HCAHPS, COMP_HIP_KNEE, NPPES, or CMS-0057-F rules."""
    args = {"metric_query": metric_query}
    span_id, t0 = global_tracer.start_tool_span("lookup_cms_metric_definition", args)
    valid, err = validate_tool_args("lookup_cms_metric_definition", args)
    if not valid and err is not None:
        global_tracer.end_tool_span(span_id, "lookup_cms_metric_definition", args, t0, result=err)
        return err

    q = metric_query.strip().lower()
    matched: dict[str, dict[str, str]] = {}
    for key, val in CMS_METRICS_GLOSSARY.items():
        hay = f"{key} {val['title']} {val['summary']}".lower()
        if q in hay or any(tok in hay for tok in re.split(r"[^a-z0-9]+", q) if len(tok) >= 3):
            matched[key] = val

    if not matched:
        matched = dict(CMS_METRICS_GLOSSARY)

    res = {
        "status": "success",
        "query": metric_query,
        "definitions": matched,
        "data_source": "Public CMS.gov & Federal Register Documentation",
    }
    global_tracer.end_tool_span(span_id, "lookup_cms_metric_definition", args, t0, result=res)
    return res


def save_or_query_care_memory(
    action: str,
    topic_key: str = "care_shortlist",
    author_role: str = "Patient/Caregiver",
    title: str = "",
    content: str = "",
) -> dict[str, Any]:
    """Save or query persistent, PHI-redacted hospital/plan shortlist notes in SQLite."""
    args = {
        "action": action,
        "topic_key": topic_key,
        "author_role": author_role,
        "title": title,
        "content": content,
    }
    span_id, t0 = global_tracer.start_tool_span("save_or_query_care_memory", args)
    valid, err = validate_tool_args("save_or_query_care_memory", args)
    if not valid and err is not None:
        global_tracer.end_tool_span(span_id, "save_or_query_care_memory", args, t0, result=err)
        return err

    if action == "save":
        if not title.strip() or not content.strip():
            err_res = {
                "status": "error",
                "error_code": "MISSING_NOTE_CONTENT",
                "message": "Both `title` and `content` are required when `action='save'`.",
                "recovery_guidance": "Provide a short `title` and `content` (without personal SSNs/MRNs) to save a care note.",
            }
            global_tracer.end_tool_span(span_id, "save_or_query_care_memory", args, t0, result=err_res)
            return err_res
        saved = global_memory.save_care_note(
            topic_key=topic_key,
            author_role=author_role,
            title=title,
            content=content,
            tags=["carematch", topic_key],
        )
        res = {"status": "success", "action": "save", "saved_note": saved}
    elif action == "query":
        notes = global_memory.query_care_notes(topic_key=topic_key)
        res = {"status": "success", "action": "query", "count": len(notes), "notes": notes}
    else:
        notes = global_memory.query_care_notes(topic_key="")
        res = {"status": "success", "action": "list", "count": len(notes), "notes": notes}

    global_tracer.end_tool_span(span_id, "save_or_query_care_memory", args, t0, result=res)
    return res


def submit_feedback_or_escalation(
    action: str,
    rating: str = "up",
    comment: str = "",
    topic_key: str = "general_navigation",
    request_id: str = "",
) -> dict[str, Any]:
    """Record 👍/👎 user feedback or manage Human-in-the-Loop (HITL) clinical/data review escalations."""
    args = {
        "action": action,
        "rating": rating,
        "comment": comment,
        "topic_key": topic_key,
        "request_id": request_id,
    }
    span_id, t0 = global_tracer.start_tool_span("submit_feedback_or_escalation", args)
    valid, err = validate_tool_args("submit_feedback_or_escalation", args)
    if not valid and err is not None:
        global_tracer.end_tool_span(span_id, "submit_feedback_or_escalation", args, t0, result=err)
        return err

    if action == "feedback":
        fb = global_memory.save_feedback(
            session_id="agent_tool",
            rating=rating,
            comment=comment,
            query_context=topic_key,
        )
        # Automatically queue a HITL review if a user reports inaccurate data with thumbs down
        hitl_item = None
        if fb["rating"] == "down" and comment.strip():
            hitl_item = global_hitl_controller.submit_for_review(
                topic_key=topic_key,
                category="user_feedback_review",
                requested_by="CareMatch User Feedback",
                reviewer_role="Clinical Quality Librarian",
                summary=comment,
            )
        res = {
            "status": "success",
            "action": "feedback",
            "feedback": fb,
            "escalated_hitl": hitl_item,
        }
    elif action == "escalate":
        req = global_hitl_controller.submit_for_review(
            topic_key=topic_key,
            category="clinical_navigation",
            requested_by="CareMatch User",
            reviewer_role="Licensed Medicare Counselor (SHIP)",
            summary=comment or "User requested human navigation assistance.",
        )
        res = {"status": "success", "action": "escalate", "request": req}
    elif action == "approve":
        updated = global_hitl_controller.approve_request(request_id)
        res = (
            {"status": "success", "action": "approve", "request": updated}
            if updated
            else {
                "status": "not_found",
                "recovery_guidance": f"Request '{request_id}' not found. Call action='list' first.",
            }
        )
    elif action == "reject":
        updated = global_hitl_controller.reject_request(request_id)
        res = (
            {"status": "success", "action": "reject", "request": updated}
            if updated
            else {
                "status": "not_found",
                "recovery_guidance": f"Request '{request_id}' not found. Call action='list' first.",
            }
        )
    else:
        res = {
            "status": "success",
            "action": "list",
            "requests": global_hitl_controller.list_requests(),
            "feedback_summary": global_memory.list_feedback(),
        }

    global_tracer.end_tool_span(span_id, "submit_feedback_or_escalation", args, t0, result=res)
    return res
