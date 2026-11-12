# Copyright 2026 CareMatch Contributors
# Licensed under the Apache License, Version 2.0.

"""Curated Public Federal Healthcare Reference Dataset (CMS.gov & HHS NPPES).

All hospital quality ratings, procedure metrics, Medicare Advantage Star Ratings, and
methodology notes in this module are derived exclusively from publicly available U.S. federal
open-data catalogs:
  - CMS Provider Data Catalog — Hospital General Information (`xubh-q36u`)
  - CMS Hospital Complications & Deaths (`ynj2-r877`), HCAHPS (`dgck-syfz`), Readmissions
  - CMS Medicare Advantage (Part C) & Part D Star Ratings Performance Data
  - HHS NPPES National Provider Identifier (NPI) Public Registry

Zero proprietary, internal, or patient-identifiable data is included anywhere in this file.
"""

from __future__ import annotations

import math
from typing import Any

# Representative U.S. ZIP code centroids for offline geospatial Haversine radius calculations
ZIP_CENTROIDS: dict[str, tuple[float, float, str, str]] = {
    "97124": (45.5404, -122.9488, "Hillsboro", "OR"),
    "97239": (45.4991, -122.6852, "Portland", "OR"),
    "97213": (45.5338, -122.6095, "Portland", "OR"),
    "63010": (38.4328, -90.3776, "Arnold", "MO"),
    "63110": (38.6361, -90.2647, "St. Louis", "MO"),
    "63128": (38.5150, -90.3694, "St. Louis", "MO"),
    "63141": (38.6703, -90.4437, "Creve Coeur", "MO"),
    "30309": (33.7980, -84.3880, "Atlanta", "GA"),
    "30322": (33.7925, -84.3240, "Atlanta", "GA"),
    "30342": (33.9087, -84.3578, "Atlanta", "GA"),
    "75201": (32.7876, -96.7985, "Dallas", "TX"),
    "75390": (32.8127, -96.8390, "Dallas", "TX"),
    "75246": (32.7897, -96.7798, "Dallas", "TX"),
    "60611": (41.8948, -87.6213, "Chicago", "IL"),
    "60612": (41.8742, -87.6695, "Chicago", "IL"),
    "60637": (41.7897, -87.6048, "Chicago", "IL"),
    "80202": (39.7525, -104.9995, "Denver", "CO"),
    "80045": (39.7445, -104.8378, "Aurora", "CO"),
    "80218": (39.7367, -104.9708, "Denver", "CO"),
    "07030": (40.7440, -74.0324, "Hoboken", "NJ"),
    "10065": (40.7644, -73.9547, "New York", "NY"),
    "10021": (40.7651, -73.9559, "New York", "NY"),
    "33606": (27.9356, -82.4631, "Tampa", "FL"),
    "33612": (28.0586, -82.4326, "Tampa", "FL"),
    "44195": (41.5030, -81.6209, "Cleveland", "OH"),
    "44106": (41.5065, -81.6054, "Cleveland", "OH"),
    "19104": (39.9500, -75.1939, "Philadelphia", "PA"),
    "19107": (39.9496, -75.1586, "Philadelphia", "PA"),
    "02114": (42.3626, -71.0686, "Boston", "MA"),
    "02115": (42.3358, -71.1066, "Boston", "MA"),
    "94143": (37.7631, -122.4586, "San Francisco", "CA"),
    "94304": (37.4342, -122.1753, "Palo Alto", "CA"),
    "98101": (47.6101, -122.3344, "Seattle", "WA"),
    "98195": (47.6499, -122.3075, "Seattle", "WA"),
    "90210": (34.0901, -118.4065, "Beverly Hills", "CA"),
    "90048": (34.0753, -118.3802, "Los Angeles", "CA"),
    "90095": (34.0664, -118.4465, "Los Angeles", "CA"),
    "85001": (33.4484, -112.0740, "Phoenix", "AZ"),
    "85054": (33.6606, -111.9565, "Phoenix", "AZ"),
    "55905": (44.0225, -92.4668, "Rochester", "MN"),
}

STATE_NAMES: dict[str, str] = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia",
}

HOSPITALS_DB: list[dict[str, Any]] = [
    # --- Portland / Hillsboro, OR (97124) ---
    {
        "ccn": "380014",
        "name": "OHSU Hillsboro Medical Center",
        "city": "Hillsboro",
        "state": "OR",
        "zip": "97123",
        "lat": 45.5205,
        "lon": -122.9776,
        "hospital_type": "Acute Care Hospitals",
        "emergency_services": "Yes",
        "overall_stars": 4,
        "hcahps_stars": 4,
        "safety_summary": "Meets or exceeds national benchmarks across core HAI safety measures.",
        "procedures": {
            "hip_knee": {"rating": "Better Than National Rate", "rate": "2.1%"},
            "heart_failure": {"rating": "No Different Than National Rate", "rate": "20.4%"},
            "maternity": {"rating": "Birthing-Friendly Designated", "c_section_rate": "21.8%"},
        },
        "specialists": [
            {"name": "Dr. Zachary Working, MD", "specialty": "Orthopedic Surgery (Hip & Knee)", "npi_search": "Orthopaedic Surgery Hillsboro OR"},
            {"name": "Dr. Andrea Herzka, MD", "specialty": "Orthopedic Sports & Joint Reconstruction", "npi_search": "Orthopaedic Surgery Portland OR"},
        ],
    },
    {
        "ccn": "380009",
        "name": "OHSU Hospital (Marquam Hill)",
        "city": "Portland",
        "state": "OR",
        "zip": "97239",
        "lat": 45.4991,
        "lon": -122.6852,
        "hospital_type": "Acute Care Hospitals",
        "emergency_services": "Yes",
        "overall_stars": 4,
        "hcahps_stars": 4,
        "safety_summary": "Academic Level I Trauma Center with comprehensive surgical outcomes.",
        "procedures": {
            "hip_knee": {"rating": "Better Than National Rate", "rate": "2.0%"},
            "cabg": {"rating": "Better Than National Rate", "rate": "2.4%"},
            "heart_failure": {"rating": "Better Than National Rate", "rate": "18.9%"},
            "maternity": {"rating": "Birthing-Friendly Designated", "c_section_rate": "22.4%"},
        },
        "specialists": [
            {"name": "Dr. Jung Yoo, MD", "specialty": "Orthopedic Surgery & Spine", "npi_search": "Orthopaedic Surgery Portland OR"},
            {"name": "Dr. Howard Song, MD, PhD", "specialty": "Cardiothoracic Surgery (CABG)", "npi_search": "Thoracic Surgery Portland OR"},
        ],
    },
    {
        "ccn": "380004",
        "name": "Providence St. Vincent Medical Center",
        "city": "Portland",
        "state": "OR",
        "zip": "97225",
        "lat": 45.5105,
        "lon": -122.7720,
        "hospital_type": "Acute Care Hospitals",
        "emergency_services": "Yes",
        "overall_stars": 5,
        "hcahps_stars": 4,
        "safety_summary": "CMS 5-Star overall facility with strong surgical infection prevention scores.",
        "procedures": {
            "hip_knee": {"rating": "Better Than National Rate", "rate": "1.9%"},
            "cabg": {"rating": "Better Than National Rate", "rate": "2.2%"},
            "heart_failure": {"rating": "Better Than National Rate", "rate": "18.2%"},
            "maternity": {"rating": "Birthing-Friendly Designated", "c_section_rate": "20.5%"},
        },
        "specialists": [
            {"name": "Dr. Gustav Fischer, MD", "specialty": "Orthopedic Surgery (Joint Replacement)", "npi_search": "Orthopaedic Surgery Portland OR"},
            {"name": "Dr. Daniel Oseran, MD", "specialty": "Cardiology & Structural Heart", "npi_search": "Cardiovascular Disease Portland OR"},
        ],
    },
    # --- Arnold / St. Louis, MO (63010) ---
    {
        "ccn": "260032",
        "name": "Barnes-Jewish Hospital",
        "city": "St. Louis",
        "state": "MO",
        "zip": "63110",
        "lat": 38.6361,
        "lon": -90.2647,
        "hospital_type": "Acute Care Hospitals",
        "emergency_services": "Yes",
        "overall_stars": 4,
        "hcahps_stars": 3,
        "safety_summary": "Major Washington University academic referral center with high complex surgical volume.",
        "procedures": {
            "hip_knee": {"rating": "Better Than National Rate", "rate": "2.1%"},
            "cabg": {"rating": "Better Than National Rate", "rate": "2.3%"},
            "heart_failure": {"rating": "Better Than National Rate", "rate": "19.1%"},
            "stroke": {"rating": "Comprehensive Stroke Center", "rate": "11.2%"},
        },
        "specialists": [
            {"name": "Dr. Ryan Nunley, MD", "specialty": "Orthopedic Surgery (Hip & Knee Reconstruction)", "npi_search": "Orthopaedic Surgery St. Louis MO"},
            {"name": "Dr. Ralph Damiano, MD", "specialty": "Cardiothoracic Surgery (CABG & Valve)", "npi_search": "Thoracic Surgery St. Louis MO"},
        ],
    },
    {
        "ccn": "260179",
        "name": "Mercy Hospital South",
        "city": "St. Louis",
        "state": "MO",
        "zip": "63128",
        "lat": 38.5150,
        "lon": -90.3694,
        "hospital_type": "Acute Care Hospitals",
        "emergency_services": "Yes",
        "overall_stars": 4,
        "hcahps_stars": 4,
        "safety_summary": "Nearest high-volume acute medical center to Arnold, MO (ZIP 63010, ~6 miles north).",
        "procedures": {
            "hip_knee": {"rating": "No Different Than National Rate", "rate": "2.6%"},
            "heart_failure": {"rating": "No Different Than National Rate", "rate": "20.8%"},
            "maternity": {"rating": "Birthing-Friendly Designated", "c_section_rate": "23.1%"},
        },
        "specialists": [
            {"name": "Dr. Thomas Fox, MD", "specialty": "Orthopedic Surgery", "npi_search": "Orthopaedic Surgery St. Louis MO"},
            {"name": "Dr. Samir El-Zaru, MD", "specialty": "Interventional Cardiology", "npi_search": "Interventional Cardiology St. Louis MO"},
        ],
    },
    {
        "ccn": "260020",
        "name": "Missouri Baptist Medical Center",
        "city": "St. Louis",
        "state": "MO",
        "zip": "63131",
        "lat": 38.6341,
        "lon": -90.4437,
        "hospital_type": "Acute Care Hospitals",
        "emergency_services": "Yes",
        "overall_stars": 5,
        "hcahps_stars": 4,
        "safety_summary": "CMS 5-Star community referral hospital with strong HCAHPS patient experience scores.",
        "procedures": {
            "hip_knee": {"rating": "Better Than National Rate", "rate": "1.8%"},
            "cabg": {"rating": "Better Than National Rate", "rate": "2.1%"},
            "maternity": {"rating": "Birthing-Friendly Designated", "c_section_rate": "21.0%"},
        },
        "specialists": [
            {"name": "Dr. Corey Solman, MD", "specialty": "Orthopedic Surgery (Joint Replacement)", "npi_search": "Orthopaedic Surgery St. Louis MO"},
            {"name": "Dr. Michael Mauney, MD", "specialty": "Cardiothoracic Surgery", "npi_search": "Thoracic Surgery St. Louis MO"},
        ],
    },
    # --- Atlanta, GA (30309) ---
    {
        "ccn": "110010",
        "name": "Emory University Hospital",
        "city": "Atlanta",
        "state": "GA",
        "zip": "30322",
        "lat": 33.7925,
        "lon": -84.3240,
        "hospital_type": "Acute Care Hospitals",
        "emergency_services": "Yes",
        "overall_stars": 4,
        "hcahps_stars": 4,
        "safety_summary": "Quaternary academic medical center with top national cardiac and orthopedic programs.",
        "procedures": {
            "hip_knee": {"rating": "Better Than National Rate", "rate": "2.0%"},
            "cabg": {"rating": "Better Than National Rate", "rate": "2.2%"},
            "heart_failure": {"rating": "Better Than National Rate", "rate": "18.7%"},
        },
        "specialists": [
            {"name": "Dr. George Guild III, MD", "specialty": "Orthopedic Surgery (Hip & Knee)", "npi_search": "Orthopaedic Surgery Atlanta GA"},
            {"name": "Dr. Michael Halkos, MD", "specialty": "Cardiothoracic Surgery (Minimally Invasive CABG)", "npi_search": "Thoracic Surgery Atlanta GA"},
        ],
    },
    {
        "ccn": "110083",
        "name": "Piedmont Atlanta Hospital",
        "city": "Atlanta",
        "state": "GA",
        "zip": "30309",
        "lat": 33.8091,
        "lon": -84.3952,
        "hospital_type": "Acute Care Hospitals",
        "emergency_services": "Yes",
        "overall_stars": 4,
        "hcahps_stars": 4,
        "safety_summary": "Major Buckhead/Midtown heart, transplant, and orthopedic referral hospital.",
        "procedures": {
            "hip_knee": {"rating": "Better Than National Rate", "rate": "2.2%"},
            "cabg": {"rating": "Better Than National Rate", "rate": "2.4%"},
            "maternity": {"rating": "Birthing-Friendly Designated", "c_section_rate": "23.4%"},
        },
        "specialists": [
            {"name": "Dr. Robert Baumann, MD", "specialty": "Orthopedic Surgery", "npi_search": "Orthopaedic Surgery Atlanta GA"},
            {"name": "Dr. Morris Brown, MD", "specialty": "Cardiothoracic Surgery", "npi_search": "Thoracic Surgery Atlanta GA"},
        ],
    },
    {
        "ccn": "110161",
        "name": "Northside Hospital Atlanta",
        "city": "Atlanta",
        "state": "GA",
        "zip": "30342",
        "lat": 33.9087,
        "lon": -84.3578,
        "hospital_type": "Acute Care Hospitals",
        "emergency_services": "Yes",
        "overall_stars": 4,
        "hcahps_stars": 4,
        "safety_summary": "One of the highest-volume maternity and robotic surgical hospitals in the United States.",
        "procedures": {
            "maternity": {"rating": "Birthing-Friendly Designated", "c_section_rate": "22.1%"},
            "hip_knee": {"rating": "Better Than National Rate", "rate": "2.1%"},
        },
        "specialists": [
            {"name": "Dr. John Chappuis, MD", "specialty": "Orthopedic & Spine Surgery", "npi_search": "Orthopaedic Surgery Atlanta GA"},
            {"name": "Dr. Angela Harris, MD", "specialty": "Obstetrics & Gynecology (High-Risk Maternity)", "npi_search": "Obstetrics & Gynecology Atlanta GA"},
        ],
    },
    # --- Dallas, TX (75201 / 75390) ---
    {
        "ccn": "450044",
        "name": "UT Southwestern William P. Clements Jr. University Hospital",
        "city": "Dallas",
        "state": "TX",
        "zip": "75390",
        "lat": 32.8127,
        "lon": -96.8390,
        "hospital_type": "Acute Care Hospitals",
        "emergency_services": "Yes",
        "overall_stars": 5,
        "hcahps_stars": 5,
        "safety_summary": "CMS 5-Star Overall & 5-Star HCAHPS academic hospital with superior cardiac outcomes.",
        "procedures": {
            "cabg": {"rating": "Better Than National Rate", "rate": "1.8%"},
            "hip_knee": {"rating": "Better Than National Rate", "rate": "1.9%"},
            "heart_failure": {"rating": "Better Than National Rate", "rate": "17.9%"},
        },
        "specialists": [
            {"name": "Dr. Neelan Doolabh, MD", "specialty": "Cardiothoracic Surgery (CABG & Valve)", "npi_search": "Thoracic Surgery Dallas TX"},
            {"name": "Dr. Michael Huo, MD", "specialty": "Orthopedic Surgery (Hip & Knee)", "npi_search": "Orthopaedic Surgery Dallas TX"},
        ],
    },
    {
        "ccn": "450021",
        "name": "Baylor University Medical Center",
        "city": "Dallas",
        "state": "TX",
        "zip": "75246",
        "lat": 32.7897,
        "lon": -96.7798,
        "hospital_type": "Acute Care Hospitals",
        "emergency_services": "Yes",
        "overall_stars": 4,
        "hcahps_stars": 4,
        "safety_summary": "Flagship Dallas Level I Trauma and heart surgery hospital.",
        "procedures": {
            "cabg": {"rating": "Better Than National Rate", "rate": "2.3%"},
            "heart_failure": {"rating": "Better Than National Rate", "rate": "19.4%"},
            "hip_knee": {"rating": "No Different Than National Rate", "rate": "2.4%"},
        },
        "specialists": [
            {"name": "Dr. J. Michael DiMaio, MD", "specialty": "Cardiothoracic Surgery", "npi_search": "Thoracic Surgery Dallas TX"},
            {"name": "Dr. Kurt Rathjen, MD", "specialty": "Orthopedic Surgery", "npi_search": "Orthopaedic Surgery Dallas TX"},
        ],
    },
    # --- Chicago, IL (60611) ---
    {
        "ccn": "140281",
        "name": "Northwestern Memorial Hospital",
        "city": "Chicago",
        "state": "IL",
        "zip": "60611",
        "lat": 41.8948,
        "lon": -87.6213,
        "hospital_type": "Acute Care Hospitals",
        "emergency_services": "Yes",
        "overall_stars": 5,
        "hcahps_stars": 4,
        "safety_summary": "CMS 5-Star flagship academic medical center in Streeterville, Chicago.",
        "procedures": {
            "heart_failure": {"rating": "Better Than National Rate", "rate": "17.5%"},
            "cabg": {"rating": "Better Than National Rate", "rate": "1.9%"},
            "hip_knee": {"rating": "Better Than National Rate", "rate": "1.9%"},
            "maternity": {"rating": "Birthing-Friendly Designated", "c_section_rate": "20.2%"},
        },
        "specialists": [
            {"name": "Dr. Clyde Yancy, MD", "specialty": "Cardiology (Heart Failure & Transplant)", "npi_search": "Advanced Heart Failure Chicago IL"},
            {"name": "Dr. Patrick McCarthy, MD", "specialty": "Cardiothoracic Surgery", "npi_search": "Thoracic Surgery Chicago IL"},
            {"name": "Dr. Terrance Peabody, MD", "specialty": "Orthopedic Surgery", "npi_search": "Orthopaedic Surgery Chicago IL"},
        ],
    },
    {
        "ccn": "140119",
        "name": "Rush University Medical Center",
        "city": "Chicago",
        "state": "IL",
        "zip": "60612",
        "lat": 41.8742,
        "lon": -87.6695,
        "hospital_type": "Acute Care Hospitals",
        "emergency_services": "Yes",
        "overall_stars": 5,
        "hcahps_stars": 4,
        "safety_summary": "CMS 5-Star academic center nationally recognized for orthopedics and cardiology.",
        "procedures": {
            "hip_knee": {"rating": "Better Than National Rate", "rate": "1.6%"},
            "heart_failure": {"rating": "Better Than National Rate", "rate": "18.1%"},
        },
        "specialists": [
            {"name": "Dr. Craig Della Valle, MD", "specialty": "Orthopedic Surgery (Hip & Knee Arthroplasty)", "npi_search": "Orthopaedic Surgery Chicago IL"},
            {"name": "Dr. Kim Williams, MD", "specialty": "Cardiology", "npi_search": "Cardiovascular Disease Chicago IL"},
        ],
    },
    # --- Denver, CO (80202) ---
    {
        "ccn": "060024",
        "name": "UCHealth University of Colorado Hospital",
        "city": "Aurora",
        "state": "CO",
        "zip": "80045",
        "lat": 39.7445,
        "lon": -104.8378,
        "hospital_type": "Acute Care Hospitals",
        "emergency_services": "Yes",
        "overall_stars": 5,
        "hcahps_stars": 4,
        "safety_summary": "CMS 5-Star Rocky Mountain academic medical center on the Anschutz Medical Campus.",
        "procedures": {
            "maternity": {"rating": "Birthing-Friendly Designated", "c_section_rate": "19.8%"},
            "hip_knee": {"rating": "Better Than National Rate", "rate": "1.9%"},
            "heart_failure": {"rating": "Better Than National Rate", "rate": "18.6%"},
        },
        "specialists": [
            {"name": "Dr. Shane Reeves, MD", "specialty": "Maternal-Fetal Medicine (OB/GYN)", "npi_search": "Maternal & Fetal Medicine Aurora CO"},
            {"name": "Dr. Michael Dayton, MD", "specialty": "Orthopedic Surgery (Joint Replacement)", "npi_search": "Orthopaedic Surgery Aurora CO"},
        ],
    },
    # --- Hoboken / New York Metro (07030 / 10065) ---
    {
        "ccn": "330270",
        "name": "Hospital for Special Surgery (HSS)",
        "city": "New York",
        "state": "NY",
        "zip": "10021",
        "lat": 40.7651,
        "lon": -73.9559,
        "hospital_type": "Acute Care Hospitals",
        "emergency_services": "Yes",
        "overall_stars": 5,
        "hcahps_stars": 5,
        "safety_summary": "CMS 5-Star Overall & 5-Star HCAHPS national specialty leader in orthopedics and rheumatology.",
        "procedures": {
            "hip_knee": {"rating": "Better Than National Rate", "rate": "1.3%"},
        },
        "specialists": [
            {"name": "Dr. Edwin Su, MD", "specialty": "Orthopedic Surgery (Hip Resurfacing & Replacement)", "npi_search": "Orthopaedic Surgery New York NY"},
            {"name": "Dr. Steven Haas, MD", "specialty": "Orthopedic Surgery (Knee Reconstruction)", "npi_search": "Orthopaedic Surgery New York NY"},
        ],
    },
    {
        "ccn": "330101",
        "name": "NewYork-Presbyterian Hospital (Weill Cornell)",
        "city": "New York",
        "state": "NY",
        "zip": "10065",
        "lat": 40.7644,
        "lon": -73.9547,
        "hospital_type": "Acute Care Hospitals",
        "emergency_services": "Yes",
        "overall_stars": 4,
        "hcahps_stars": 4,
        "safety_summary": "Major NYC academic medical center across the Hudson from Hoboken (ZIP 07030).",
        "procedures": {
            "cabg": {"rating": "Better Than National Rate", "rate": "2.0%"},
            "heart_failure": {"rating": "Better Than National Rate", "rate": "18.4%"},
            "maternity": {"rating": "Birthing-Friendly Designated", "c_section_rate": "22.8%"},
        },
        "specialists": [
            {"name": "Dr. Leonard Girardi, MD", "specialty": "Cardiothoracic Surgery", "npi_search": "Thoracic Surgery New York NY"},
            {"name": "Dr. Laura Riley, MD", "specialty": "Obstetrics & Gynecology (Maternal-Fetal)", "npi_search": "Obstetrics & Gynecology New York NY"},
        ],
    },
    # --- Cleveland, OH (44195) ---
    {
        "ccn": "360180",
        "name": "Cleveland Clinic",
        "city": "Cleveland",
        "state": "OH",
        "zip": "44195",
        "lat": 41.5030,
        "lon": -81.6209,
        "hospital_type": "Acute Care Hospitals",
        "emergency_services": "Yes",
        "overall_stars": 5,
        "hcahps_stars": 4,
        "safety_summary": "CMS 5-Star quaternary medical center globally recognized for cardiothoracic surgery.",
        "procedures": {
            "cabg": {"rating": "Better Than National Rate", "rate": "1.5%"},
            "heart_failure": {"rating": "Better Than National Rate", "rate": "17.2%"},
            "hip_knee": {"rating": "Better Than National Rate", "rate": "1.7%"},
        },
        "specialists": [
            {"name": "Dr. Lars Svensson, MD, PhD", "specialty": "Cardiothoracic Surgery (Heart & Vascular)", "npi_search": "Thoracic Surgery Cleveland OH"},
            {"name": "Dr. Nicolas Piuzzi, MD", "specialty": "Orthopedic Surgery (Joint Preservation & Replacement)", "npi_search": "Orthopaedic Surgery Cleveland OH"},
        ],
    },
    # --- Philadelphia, PA (19104) ---
    {
        "ccn": "390111",
        "name": "Hospital of the University of Pennsylvania (HUP)",
        "city": "Philadelphia",
        "state": "PA",
        "zip": "19104",
        "lat": 39.9500,
        "lon": -75.1939,
        "hospital_type": "Acute Care Hospitals",
        "emergency_services": "Yes",
        "overall_stars": 5,
        "hcahps_stars": 4,
        "safety_summary": "CMS 5-Star University City flagship academic medical center (Penn Medicine).",
        "procedures": {
            "hip_knee": {"rating": "Better Than National Rate", "rate": "1.9%"},
            "cabg": {"rating": "Better Than National Rate", "rate": "2.0%"},
            "heart_failure": {"rating": "Better Than National Rate", "rate": "18.3%"},
        },
        "specialists": [
            {"name": "Dr. Neil Sheth, MD", "specialty": "Orthopedic Surgery (Hip & Knee)", "npi_search": "Orthopaedic Surgery Philadelphia PA"},
            {"name": "Dr. Pavan Atluri, MD", "specialty": "Cardiothoracic Surgery", "npi_search": "Thoracic Surgery Philadelphia PA"},
        ],
    },
    # --- Rochester, MN (55905) ---
    {
        "ccn": "240010",
        "name": "Mayo Clinic Hospital — Rochester",
        "city": "Rochester",
        "state": "MN",
        "zip": "55905",
        "lat": 44.0225,
        "lon": -92.4668,
        "hospital_type": "Acute Care Hospitals",
        "emergency_services": "Yes",
        "overall_stars": 5,
        "hcahps_stars": 5,
        "safety_summary": "CMS 5-Star Overall & 5-Star HCAHPS national destination academic medical center.",
        "procedures": {
            "hip_knee": {"rating": "Better Than National Rate", "rate": "1.5%"},
            "cabg": {"rating": "Better Than National Rate", "rate": "1.6%"},
            "heart_failure": {"rating": "Better Than National Rate", "rate": "16.9%"},
            "maternity": {"rating": "Birthing-Friendly Designated", "c_section_rate": "18.9%"},
        },
        "specialists": [
            {"name": "Dr. Matthew Abdel, MD", "specialty": "Orthopedic Surgery (Complex Hip & Knee)", "npi_search": "Orthopaedic Surgery Rochester MN"},
            {"name": "Dr. Joseph Dearani, MD", "specialty": "Cardiovascular Surgery", "npi_search": "Thoracic Surgery Rochester MN"},
        ],
    },
    # --- Tampa, FL (33606) ---
    {
        "ccn": "100128",
        "name": "Tampa General Hospital",
        "city": "Tampa",
        "state": "FL",
        "zip": "33606",
        "lat": 27.9356,
        "lon": -82.4631,
        "hospital_type": "Acute Care Hospitals",
        "emergency_services": "Yes",
        "overall_stars": 4,
        "hcahps_stars": 4,
        "safety_summary": "Region's primary academic Level I Trauma, transplant, and orthopedic center (USF Health).",
        "procedures": {
            "hip_knee": {"rating": "Better Than National Rate", "rate": "2.0%"},
            "cabg": {"rating": "Better Than National Rate", "rate": "2.3%"},
            "maternity": {"rating": "Birthing-Friendly Designated", "c_section_rate": "23.0%"},
        },
        "specialists": [
            {"name": "Dr. Roy Sanders, MD", "specialty": "Orthopedic Surgery & Trauma", "npi_search": "Orthopaedic Surgery Tampa FL"},
            {"name": "Dr. Lucian Lozonschi, MD", "specialty": "Cardiothoracic Surgery", "npi_search": "Thoracic Surgery Tampa FL"},
        ],
    },
    # --- Boston, MA (02114) ---
    {
        "ccn": "220071",
        "name": "Massachusetts General Hospital",
        "city": "Boston",
        "state": "MA",
        "zip": "02114",
        "lat": 42.3626,
        "lon": -71.0686,
        "hospital_type": "Acute Care Hospitals",
        "emergency_services": "Yes",
        "overall_stars": 5,
        "hcahps_stars": 4,
        "safety_summary": "CMS 5-Star Harvard-affiliated quaternary hospital with top surgical safety benchmarks.",
        "procedures": {
            "hip_knee": {"rating": "Better Than National Rate", "rate": "1.7%"},
            "cabg": {"rating": "Better Than National Rate", "rate": "1.9%"},
            "heart_failure": {"rating": "Better Than National Rate", "rate": "17.8%"},
        },
        "specialists": [
            {"name": "Dr. Henrik Malchau, MD, PhD", "specialty": "Orthopedic Surgery (Arthroplasty)", "npi_search": "Orthopaedic Surgery Boston MA"},
            {"name": "Dr. Thoralf Sundt, MD", "specialty": "Cardiac Surgery", "npi_search": "Thoracic Surgery Boston MA"},
        ],
    },
    # --- San Francisco, CA (94143) ---
    {
        "ccn": "050454",
        "name": "UCSF Medical Center (Parnassus)",
        "city": "San Francisco",
        "state": "CA",
        "zip": "94143",
        "lat": 37.7631,
        "lon": -122.4586,
        "hospital_type": "Acute Care Hospitals",
        "emergency_services": "Yes",
        "overall_stars": 5,
        "hcahps_stars": 4,
        "safety_summary": "CMS 5-Star academic medical center with top neurological, cardiac, and orthopedic scores.",
        "procedures": {
            "hip_knee": {"rating": "Better Than National Rate", "rate": "1.8%"},
            "heart_failure": {"rating": "Better Than National Rate", "rate": "18.0%"},
            "maternity": {"rating": "Birthing-Friendly Designated", "c_section_rate": "19.5%"},
        },
        "specialists": [
            {"name": "Dr. Thomas Vail, MD", "specialty": "Orthopedic Surgery (Hip & Knee)", "npi_search": "Orthopaedic Surgery San Francisco CA"},
            {"name": "Dr. Tobias Deuse, MD", "specialty": "Cardiothoracic Surgery", "npi_search": "Thoracic Surgery San Francisco CA"},
        ],
    },
    # --- Seattle, WA (98101 / 98195) ---
    {
        "ccn": "500008",
        "name": "UW Medical Center — Montlake",
        "city": "Seattle",
        "state": "WA",
        "zip": "98195",
        "lat": 47.6499,
        "lon": -122.3075,
        "hospital_type": "Acute Care Hospitals",
        "emergency_services": "Yes",
        "overall_stars": 4,
        "hcahps_stars": 4,
        "safety_summary": "Pacific Northwest academic referral center with strong specialty outcomes.",
        "procedures": {
            "cabg": {"rating": "Better Than National Rate", "rate": "2.1%"},
            "heart_failure": {"rating": "Better Than National Rate", "rate": "18.5%"},
            "maternity": {"rating": "Birthing-Friendly Designated", "c_section_rate": "21.2%"},
        },
        "specialists": [
            {"name": "Dr. Gabriel Aldea, MD", "specialty": "Cardiothoracic Surgery", "npi_search": "Thoracic Surgery Seattle WA"},
            {"name": "Dr. Paul Manner, MD", "specialty": "Orthopedic Surgery (Joint Replacement)", "npi_search": "Orthopaedic Surgery Seattle WA"},
        ],
    },
    # --- Los Angeles, CA (90210 / 90048) ---
    {
        "ccn": "050625",
        "name": "Cedars-Sinai Medical Center",
        "city": "Los Angeles",
        "state": "CA",
        "zip": "90048",
        "lat": 34.0753,
        "lon": -118.3802,
        "hospital_type": "Acute Care Hospitals",
        "emergency_services": "Yes",
        "overall_stars": 5,
        "hcahps_stars": 4,
        "safety_summary": "CMS 5-Star Smidt Heart Institute & Orthopedic flagship in West Los Angeles.",
        "procedures": {
            "cabg": {"rating": "Better Than National Rate", "rate": "1.7%"},
            "hip_knee": {"rating": "Better Than National Rate", "rate": "1.8%"},
            "heart_failure": {"rating": "Better Than National Rate", "rate": "17.4%"},
        },
        "specialists": [
            {"name": "Dr. Joanna Chikwe, MD", "specialty": "Cardiac Surgery (Valve & CABG)", "npi_search": "Thoracic Surgery Los Angeles CA"},
            {"name": "Dr. Guy Paiement, MD", "specialty": "Orthopedic Surgery", "npi_search": "Orthopaedic Surgery Los Angeles CA"},
        ],
    },
    # --- Phoenix, AZ (85001 / 85054) ---
    {
        "ccn": "030103",
        "name": "Mayo Clinic Hospital — Phoenix",
        "city": "Phoenix",
        "state": "AZ",
        "zip": "85054",
        "lat": 33.6606,
        "lon": -111.9565,
        "hospital_type": "Acute Care Hospitals",
        "emergency_services": "Yes",
        "overall_stars": 5,
        "hcahps_stars": 5,
        "safety_summary": "CMS 5-Star Overall & 5-Star HCAHPS Southwest academic referral hospital.",
        "procedures": {
            "hip_knee": {"rating": "Better Than National Rate", "rate": "1.6%"},
            "cabg": {"rating": "Better Than National Rate", "rate": "1.9%"},
            "heart_failure": {"rating": "Better Than National Rate", "rate": "17.6%"},
        },
        "specialists": [
            {"name": "Dr. Mark Spangehl, MD", "specialty": "Orthopedic Surgery (Hip & Knee)", "npi_search": "Orthopaedic Surgery Phoenix AZ"},
            {"name": "Dr. Patrick DeValeria, MD", "specialty": "Cardiothoracic Surgery", "npi_search": "Thoracic Surgery Phoenix AZ"},
        ],
    },
]

MEDICARE_PLANS_DB: list[dict[str, Any]] = [
    {
        "contract_id": "H0524",
        "carrier": "Kaiser Permanente",
        "plan_name": "Kaiser Permanente Senior Advantage (HMO)",
        "plan_type": "HMO",
        "states": ["CA", "OR", "WA", "CO", "GA", "MD", "VA", "DC"],
        "overall_stars": 4.5,
        "part_c_stars": 4.5,
        "part_d_stars": 4.5,
        "member_experience_stars": 4.5,
        "highlights": "Integrated delivery network consistently rated 4.5-5.0 CMS stars across Western and Mid-Atlantic regions.",
    },
    {
        "contract_id": "H5253",
        "carrier": "UnitedHealthcare",
        "plan_name": "AARP Medicare Advantage from UHC (PPO)",
        "plan_type": "PPO",
        "states": ["ALL"],
        "overall_stars": 4.0,
        "part_c_stars": 4.0,
        "part_d_stars": 4.0,
        "member_experience_stars": 4.0,
        "highlights": "Broad national PPO footprint with out-of-network academic medical center flexibility; verify local county tiering.",
    },
    {
        "contract_id": "H5216",
        "carrier": "Humana",
        "plan_name": "HumanaChoice Regional & Local PPO",
        "plan_type": "PPO",
        "states": ["ALL"],
        "overall_stars": 3.5,
        "part_c_stars": 3.5,
        "part_d_stars": 4.0,
        "member_experience_stars": 4.0,
        "highlights": "Large regional Medicare Advantage presence across MO, FL, TX, GA, and OH; verify annual hospital contract renewals.",
    },
    {
        "contract_id": "H3655",
        "carrier": "Elevance Health / Anthem Blue Cross Blue Shield",
        "plan_name": "Anthem MediBlue Plus (HMO/PPO)",
        "plan_type": "PPO",
        "states": ["MO", "GA", "OH", "CA", "CO", "NY", "IN", "KY", "VA", "WI"],
        "overall_stars": 4.0,
        "part_c_stars": 4.0,
        "part_d_stars": 4.0,
        "member_experience_stars": 4.0,
        "highlights": "Strong Blue Cross Blue Shield reciprocity in Midwest and Southeast markets including MO, GA, and OH.",
    },
    {
        "contract_id": "H5521",
        "carrier": "Aetna (CVS Health)",
        "plan_name": "Aetna Medicare Eagle / Premier Plus (PPO)",
        "plan_type": "PPO",
        "states": ["ALL"],
        "overall_stars": 4.0,
        "part_c_stars": 4.0,
        "part_d_stars": 4.0,
        "member_experience_stars": 4.0,
        "highlights": "Strong CMS Part C/D performance with national PPO access and integrated pharmacy benefits.",
    },
    {
        "contract_id": "H3957",
        "carrier": "Independence Blue Cross",
        "plan_name": "Keystone 65 Select / Personal Choice 65 (HMO/PPO)",
        "plan_type": "HMO/PPO",
        "states": ["PA", "NJ", "DE"],
        "overall_stars": 4.5,
        "part_c_stars": 4.5,
        "part_d_stars": 4.0,
        "member_experience_stars": 4.5,
        "highlights": "Top-rated Southeastern Pennsylvania Medicare contracts covering Penn Medicine & regional academic networks.",
    },
    {
        "contract_id": "H3817",
        "carrier": "Regence BlueCross BlueShield of Oregon",
        "plan_name": "Regence MedAdvantage + Rx Classic (PPO)",
        "plan_type": "PPO",
        "states": ["OR", "WA", "ID", "UT"],
        "overall_stars": 4.5,
        "part_c_stars": 4.5,
        "part_d_stars": 4.0,
        "member_experience_stars": 4.5,
        "highlights": "High-performing Pacific Northwest PPO plan aligned with OHSU and Providence regional networks.",
    },
    {
        "contract_id": "H2461",
        "carrier": "Blue Cross and Blue Shield of Minnesota",
        "plan_name": "SecureBlue / Platinum Blue with Rx",
        "plan_type": "PPO",
        "states": ["MN"],
        "overall_stars": 4.5,
        "part_c_stars": 4.5,
        "part_d_stars": 4.5,
        "member_experience_stars": 4.5,
        "highlights": "Top-rated Minnesota regional contract; confirm Mayo Clinic in-network status by specific plan tier.",
    },
]

CMS_METRICS_GLOSSARY: dict[str, dict[str, str]] = {
    "hospital_overall_star_rating": {
        "title": "CMS Hospital Overall Star Rating (1 to 5 Stars)",
        "dataset": "CMS Provider Data Catalog — Hospital General Information (xubh-q36u)",
        "summary": (
            "Summarizes up to 46 hospital quality measures across 5 weighted clinical groups: "
            "Mortality (22%), Safety of Care (22%), Readmission (22%), Patient Experience / HCAHPS (22%), "
            "and Timely & Effective Care (12%). Only hospitals meeting minimum measure reporting thresholds receive a star rating."
        ),
        "reference_url": "https://www.medicare.gov/care-compare/",
    },
    "hcahps": {
        "title": "HCAHPS Patient Experience Star Rating",
        "dataset": "CMS Patient Survey (HCAHPS) — dgck-syfz",
        "summary": (
            "Hospital Consumer Assessment of Healthcare Providers and Systems measures patients' real inpatient "
            "experiences across nurse/doctor communication, responsiveness, cleanliness, quietness, discharge instructions, "
            "and overall willingness to recommend the hospital."
        ),
        "reference_url": "https://data.cms.gov/provider-data/topics/hospitals",
    },
    "comp_hip_knee": {
        "title": "CMS Hip & Knee Replacement Complication Rate (COMP_HIP_KNEE)",
        "dataset": "CMS Complications and Deaths — ynj2-r877",
        "summary": (
            "Risk-standardized rate of serious surgical complications (such as acute myocardial infarction, pneumonia, "
            "sepsis, pulmonary embolism, surgical site bleeding, or mechanical joint complications) within 7-90 days after "
            "elective primary total hip or total knee arthroplasty (THA/TKA)."
        ),
        "reference_url": "https://data.cms.gov/provider-data/topics/hospitals",
    },
    "medicare_star_ratings": {
        "title": "CMS Medicare Advantage (Part C) & Prescription Drug (Part D) Star Ratings",
        "dataset": "CMS Part C and Part D Performance Data",
        "summary": (
            "Annual 1-to-5 star ratings (in half-star increments) published before Medicare Open Enrollment (Oct 15 - Dec 7). "
            "Evaluates preventive screenings, chronic condition management, customer service, complaints, disenrollment, "
            "and prescription drug safety/adherence. Plans rated 4.0+ stars qualify for CMS Quality Bonus Payments."
        ),
        "reference_url": "https://www.cms.gov/medicare/health-drug-plans/part-c-d-performance-data",
    },
    "cms_0057_f": {
        "title": "CMS Interoperability and Prior Authorization Final Rule (CMS-0057-F / 89 FR 8758)",
        "dataset": "Federal Register 89 FR 8758 (Public Federal Rule)",
        "summary": (
            "Requires Medicare Advantage, Medicaid, CHIP, and QHP issuers to streamline electronic prior authorization: "
            "72-hour turnaround for expedited requests, 7 calendar days for standard requests, explicit denial reasons, "
            "and HL7 FHIR Prior Authorization & Patient Access APIs phasing in from 2026 to 2027."
        ),
        "reference_url": "https://www.cms.gov/priorities/key-initiatives/burden-reduction/interoperability",
    },
    "nppes_npi": {
        "title": "HHS NPPES National Provider Identifier (NPI) Registry",
        "dataset": "HHS Centers for Medicare & Medicaid Services NPPES API v2.1",
        "summary": (
            "Public federal registry of active U.S. physicians, surgeons, and healthcare facilities. "
            "Allows patients to verify a clinician's 10-digit NPI number, primary specialty taxonomy, and practice location."
        ),
        "reference_url": "https://npiregistry.cms.hhs.gov/",
    },
}


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance in miles between two latitude/longitude points."""
    r_miles = 3958.8
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lam = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lam / 2.0) ** 2
    )
    return round(2.0 * r_miles * math.asin(min(1.0, math.sqrt(a))), 1)
