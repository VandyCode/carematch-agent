# Copyright 2026 CareMatch Contributors
# Licensed under the Apache License, Version 2.0.

"""Public Federal Healthcare Open-Data Connector (CMS.gov Provider Data + HHS NPPES NPI API).

Strictly uses publicly documented U.S. federal open-data APIs:
- CMS Provider Data Catalog (Hospital General Information `xubh-q36u`):
  https://data.cms.gov/provider-data/api/1/datastore/query/xubh-q36u/0
- HHS NPPES National Provider Identifier (NPI) Registry API v2.1:
  https://npiregistry.cms.hhs.gov/api/?version=2.1

Live HTTP queries are opt-in via `CAREMATCH_CMS_LIVE_API=true` so unit tests, CI pipelines,
and air-gapped environments run deterministically using the curated public reference snapshot
in `app/cms_data.py` with zero external flakiness.
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from typing import Any

CMS_HOSPITAL_INFO_API = (
    "https://data.cms.gov/provider-data/api/1/datastore/query/xubh-q36u/0"
)
NPPES_NPI_API = "https://npiregistry.cms.hhs.gov/api/?version=2.1"
MEDICARE_CARE_COMPARE_URL = "https://www.medicare.gov/care-compare/"
CMS_PART_CD_RATINGS_URL = (
    "https://www.cms.gov/medicare/health-drug-plans/part-c-d-performance-data"
)


def is_live_cms_enabled() -> bool:
    return os.getenv("CAREMATCH_CMS_LIVE_API", "false").lower() in ("1", "true", "yes")


def fetch_live_cms_hospitals_by_zip(
    zip_code: str, limit: int = 10, timeout_sec: float = 4.0
) -> list[dict[str, Any]]:
    """Optionally query live CMS Provider Data API (`xubh-q36u`) for a 5-digit ZIP code."""
    if not is_live_cms_enabled():
        return []

    clean_zip = "".join(ch for ch in zip_code if ch.isdigit())[:5]
    if len(clean_zip) != 5:
        return []

    payload = json.dumps(
        {
            "conditions": [
                {"property": "zip_code", "value": clean_zip, "operator": "="}
            ],
            "limit": min(max(limit, 1), 25),
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        CMS_HOSPITAL_INFO_API,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "CareMatch-OpenSource-Navigator/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        results = data.get("results", [])
        normalized: list[dict[str, Any]] = []
        for row in results:
            star_raw = row.get("hospital_overall_rating", "Not Available")
            try:
                overall_stars: float | str = int(star_raw)
            except (TypeError, ValueError):
                overall_stars = str(star_raw)
            normalized.append(
                {
                    "ccn": str(row.get("facility_id", "")),
                    "name": str(row.get("facility_name", "")).title(),
                    "city": str(row.get("citytown", row.get("city", ""))).title(),
                    "state": str(row.get("state", "")).upper(),
                    "zip": str(row.get("zip_code", clean_zip)),
                    "hospital_type": str(row.get("hospital_type", "Acute Care Hospitals")),
                    "emergency_services": str(row.get("emergency_services", "Yes")),
                    "overall_stars": overall_stars,
                    "source": "LIVE_CMS_PROVIDER_DATA_API",
                }
            )
        return normalized
    except Exception:
        return []


def fetch_live_nppes_clinicians(
    specialty: str = "",
    city: str = "",
    state: str = "",
    postal_code: str = "",
    limit: int = 5,
    timeout_sec: float = 4.0,
) -> list[dict[str, Any]]:
    """Optionally query live HHS NPPES NPI Registry API v2.1 for board-certified clinicians."""
    if not is_live_cms_enabled():
        return []

    params: dict[str, str] = {
        "version": "2.1",
        "enumeration_type": "NPI-1",
        "limit": str(min(max(limit, 1), 20)),
    }
    if specialty:
        params["taxonomy_description"] = specialty
    if city:
        params["city"] = city
    if state:
        params["state"] = state.upper()[:2]
    if postal_code:
        params["postal_code"] = "".join(ch for ch in postal_code if ch.isdigit())[:5]

    url = f"https://npiregistry.cms.hhs.gov/api/?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        url, headers={"User-Agent": "CareMatch-OpenSource-Navigator/1.0"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        out: list[dict[str, Any]] = []
        for item in data.get("results", []):
            basic = item.get("basic", {})
            taxonomies = item.get("taxonomies", [])
            addresses = item.get("addresses", [])
            primary_tax = next(
                (t for t in taxonomies if t.get("primary")),
                taxonomies[0] if taxonomies else {},
            )
            loc_addr = next(
                (a for a in addresses if a.get("address_purpose") == "LOCATION"),
                addresses[0] if addresses else {},
            )
            full_name = (
                f"Dr. {basic.get('first_name', '').title()} {basic.get('last_name', '').title()}"
            ).strip()
            cred = basic.get("credential", "MD")
            out.append(
                {
                    "npi": str(item.get("number", "")),
                    "name": f"{full_name}, {cred}" if cred else full_name,
                    "specialty": primary_tax.get("desc", specialty or "Specialist"),
                    "city": loc_addr.get("city", city).title(),
                    "state": loc_addr.get("state", state).upper(),
                    "postal_code": str(loc_addr.get("postal_code", ""))[:5],
                    "source": "LIVE_HHS_NPPES_NPI_API",
                    "verify_url": f"https://npiregistry.cms.hhs.gov/provider-view/{item.get('number', '')}",
                }
            )
        return out
    except Exception:
        return []


def get_cms_connector_status() -> dict[str, Any]:
    """Return metadata and public provenance links for CareMatch's CMS/NPPES connector."""
    return {
        "live_api_enabled": is_live_cms_enabled(),
        "mode": "LIVE_WITH_REFERENCE_FALLBACK"
        if is_live_cms_enabled()
        else "CURATED_PUBLIC_CMS_REFERENCE",
        "public_data_sources": [
            {
                "name": "CMS Provider Data Catalog — Hospital General Information (xubh-q36u)",
                "url": CMS_HOSPITAL_INFO_API,
                "portal": "https://data.cms.gov/provider-data/topics/hospitals",
            },
            {
                "name": "CMS Medicare Care Compare (HCAHPS, Complications, Mortality, Readmissions)",
                "url": MEDICARE_CARE_COMPARE_URL,
            },
            {
                "name": "HHS NPPES National Provider Identifier (NPI) Registry API v2.1",
                "url": NPPES_NPI_API,
            },
            {
                "name": "CMS Medicare Advantage (Part C) & Part D Star Ratings",
                "url": CMS_PART_CD_RATINGS_URL,
            },
        ],
    }
