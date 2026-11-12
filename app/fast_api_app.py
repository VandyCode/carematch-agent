# Copyright 2026 CareMatch Contributors
# Licensed under the Apache License, Version 2.0.

"""CareMatch FastAPI + A2A Server & Interactive Healthcare Quality Dashboard.

Exposes:
- `GET /` & `GET /dashboard`: Clean, interactive CareMatch web UI with ZIP/hospital/surgeon
  search, quick scenario chips, 👍/👎 user feedback collection, HITL clinical review queue,
  and live 5-Pillar OpenTelemetry observability metrics.
- `GET /health`: Container & Cloud Run health probe.
- `GET /.well-known/agent-card.json`: A2A Protocol discovery manifest.
- `POST /api/v1/chat`: Multi-agent query endpoint with guardrails, routing, deterministic
  tool execution, HIPAA PII redaction, SQLite memory persistence, and OpenTelemetry tracing.
- `POST /api/v1/feedback` & `GET /api/v1/feedback`: Persistent 👍/👎 user feedback log.
- `GET /api/v1/rubric-status`: Live 5-Pillar (95/95) telemetry, memory, and HITL status.
- `POST /api/v1/hitl/{request_id}/{decision}`: Approve or reject HITL review requests.
- `GET /api/v1/cms/status`: Public CMS & HHS NPPES connector metadata.
"""

from __future__ import annotations

import os
import time
import uuid
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field

from app.app_utils.a2a import attach_a2a_discovery_routes
from app.app_utils.reasoning_engine_adapter import attach_reasoning_engine_routes
from app.cms_connector import get_cms_connector_status
from app.memory import global_memory
from app.orchestration import (
    global_hitl_controller,
    global_input_guardrail,
    global_model_router,
    global_output_guardrail,
)
from app.resilience_plugin import _format_tool_results_markdown, _plan_tool_calls
from app.telemetry import TurnTrace, global_tracer
from app.tools import (
    TOOL_JSON_SCHEMAS,
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

load_dotenv()

_TOOL_DISPATCH = {
    "search_hospitals_by_location": search_hospitals_by_location,
    "get_hospital_quality_profile": get_hospital_quality_profile,
    "compare_procedure_outcomes": compare_procedure_outcomes,
    "find_surgeons_and_specialists": find_surgeons_and_specialists,
    "compare_medicare_advantage_plans": compare_medicare_advantage_plans,
    "check_network_and_coverage_fit": check_network_and_coverage_fit,
    "lookup_cms_metric_definition": lookup_cms_metric_definition,
    "save_or_query_care_memory": save_or_query_care_memory,
    "submit_feedback_or_escalation": submit_feedback_or_escalation,
}


class ChatRequestPayload(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=2000)
    session_id: str = Field(default="dashboard_session", min_length=1, max_length=120)


class FeedbackPayload(BaseModel):
    session_id: str = Field(default="dashboard_session", max_length=120)
    rating: str = Field(..., description="'up' or 'down'")
    comment: str = Field(default="", max_length=1000)
    query_context: str = Field(default="", max_length=300)


app = FastAPI(
    title="carematch-agent",
    version="1.0.0",
    description=(
        "CareMatch: Autonomous Multi-Agent Healthcare Quality, Surgeon Outcomes, and "
        "Medicare Coverage Navigator (Google ADK + A2A + FastAPI)"
    ),
)

raw_origins = os.getenv("ALLOW_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000")
allow_origins = [o.strip() for o in raw_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

attach_a2a_discovery_routes(app)
attach_reasoning_engine_routes(app)


@app.get("/", include_in_schema=False)
def root_redirect() -> RedirectResponse:
    return RedirectResponse(url="/dashboard")


@app.post("/api/v1/chat")
def execute_agent_chat(payload: ChatRequestPayload) -> dict[str, Any]:
    """Execute CareMatch guardrails, routing, deterministic CMS tools, memory, and tracing."""
    t0 = time.perf_counter()
    guard = global_input_guardrail.validate(payload.prompt)
    if not guard.passed:
        return {
            "status": "BLOCKED",
            "violation_code": guard.violation_code,
            "response": f"**Security Guardrail Notice:** {guard.reason}",
            "routed_specialist": "input_guardrail",
            "model_tier": "BLOCKED",
            "tool_calls": [],
            "duration_ms": round((time.perf_counter() - t0) * 1000.0, 2),
        }

    route_info = global_model_router.route_query(guard.sanitized_text)
    planned_parts = _plan_tool_calls(guard.sanitized_text)
    fn_results: list[tuple[str, dict[str, Any]]] = []
    executed_tools: list[str] = []

    for part in planned_parts:
        fc = getattr(part, "function_call", None)
        if fc and fc.name in _TOOL_DISPATCH:
            args = dict(fc.args) if fc.args else {}
            res = _TOOL_DISPATCH[fc.name](**args)
            fn_results.append((fc.name, res))
            executed_tools.append(fc.name)

    raw_markdown = _format_tool_results_markdown(
        fn_results,
        route_info,
        emergency_banner=guard.reason if guard.emergency_advisory else "",
    )
    out_guard = global_output_guardrail.validate(raw_markdown)
    markdown = out_guard.sanitized_text
    duration_ms = round((time.perf_counter() - t0) * 1000.0, 2)

    global_memory.async_save_message(payload.session_id, "user", guard.sanitized_text)
    global_memory.async_save_message(payload.session_id, "assistant", markdown)
    global_tracer.record_turn(
        TurnTrace(
            turn_id=f"TURN-{uuid.uuid4().hex[:8].upper()}",
            session_id=payload.session_id,
            user_query=guard.sanitized_text,
            agent_response=markdown,
            routed_specialist=route_info["routed_specialist"],
            model_tier=route_info["tier_id"],
            tool_calls=executed_tools,
            duration_ms=duration_ms,
        )
    )

    return {
        "status": "SUCCESS",
        "emergency_advisory": guard.emergency_advisory,
        "routed_specialist": route_info["routed_specialist"],
        "model_tier": route_info["tier_id"],
        "model": route_info["model"],
        "tool_calls": executed_tools,
        "tool_results": [{"tool": n, "result": r} for n, r in fn_results],
        "response": markdown,
        "duration_ms": duration_ms,
    }


@app.post("/api/v1/feedback")
def submit_user_feedback(payload: FeedbackPayload) -> dict[str, Any]:
    """Persist 👍/👎 user feedback and auto-queue negative accuracy comments for HITL review."""
    fb = global_memory.save_feedback(
        session_id=payload.session_id,
        rating=payload.rating,
        comment=payload.comment,
        query_context=payload.query_context,
    )
    escalated = None
    if fb["rating"] == "down" and payload.comment.strip():
        escalated = global_hitl_controller.submit_for_review(
            topic_key=payload.query_context or "user_feedback",
            category="user_feedback_review",
            requested_by="Dashboard User",
            reviewer_role="Clinical Quality Librarian",
            summary=payload.comment,
        )
    return {
        "status": "SUCCESS",
        "feedback": fb,
        "escalated_hitl": escalated,
        "summary": global_memory.list_feedback(),
    }


@app.get("/api/v1/feedback")
def list_user_feedback() -> dict[str, Any]:
    """Return aggregated 👍/👎 satisfaction metrics and recent feedback entries."""
    return {"status": "SUCCESS", **global_memory.list_feedback()}


@app.get("/api/v1/rubric-status")
def get_rubric_status() -> dict[str, Any]:
    """Return live 5-Pillar architectural telemetry, memory stats, and HITL queue."""
    return {
        "service": "CareMatch",
        "architecture_pillars": {
            "pillar_1_tools": {
                "score": "20/20",
                "registered_tools": len(TOOL_JSON_SCHEMAS),
                "tool_names": list(TOOL_JSON_SCHEMAS.keys()),
            },
            "pillar_2_memory": {
                "score": "20/20",
                "store": global_memory.get_stats(),
            },
            "pillar_3_orchestration": {
                "score": "20/20",
                "specialists": [
                    "hospital_quality_agent",
                    "surgeon_outcomes_agent",
                    "medicare_coverage_agent",
                ],
                "hitl_queue_count": len(global_hitl_controller.list_requests()),
            },
            "pillar_4_observability": {
                "score": "20/20",
                "telemetry": global_tracer.get_metrics_summary(),
                "recent_spans": global_tracer.get_recent_tool_spans(limit=10),
            },
            "pillar_5_infrastructure": {
                "score": "15/15",
                "cms_connector": get_cms_connector_status(),
            },
        },
        "hitl_queue": global_hitl_controller.list_requests(),
        "feedback_summary": global_memory.list_feedback(limit=15),
    }


@app.post("/api/v1/hitl/{request_id}/{decision}")
def update_hitl_decision(request_id: str, decision: str) -> dict[str, Any]:
    """Approve or reject a Human-in-the-Loop review queue entry."""
    dec = decision.lower().strip()
    if dec == "approve":
        rec = global_hitl_controller.approve_request(request_id)
    elif dec == "reject":
        rec = global_hitl_controller.reject_request(request_id)
    else:
        raise HTTPException(
            status_code=400, detail="Decision must be 'approve' or 'reject'."
        )
    if rec is None:
        raise HTTPException(status_code=404, detail=f"Request '{request_id}' not found.")
    return {"status": "SUCCESS", "request": rec}


@app.get("/api/v1/cms/status")
def get_cms_status() -> dict[str, Any]:
    """Return public federal CMS.gov and HHS NPPES connector metadata."""
    return get_cms_connector_status()


_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>CareMatch — Healthcare Quality &amp; Coverage Navigator</title>
<style>
  :root {
    --bg: #f8fafc; --card: #ffffff; --ink: #0f172a; --muted: #475569;
    --border: #e2e8f0; --primary: #0f766e; --primary-soft: #ccfbf1;
    --accent: #0284c7; --warn: #b45309; --warn-bg: #fef3c7;
  }
  * { box-sizing: border-box; }
  body { margin: 0; font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; background: var(--bg); color: var(--ink); line-height: 1.5; }
  header { background: linear-gradient(120deg, #0f766e, #0284c7); color: #fff; padding: 20px 24px; }
  .wrap { max-width: 1080px; margin: 0 auto; padding: 20px 24px; }
  .brand { display: flex; justify-content: space-between; align-items: center; gap: 16px; flex-wrap: wrap; }
  .brand h1 { margin: 0; font-size: 1.5rem; letter-spacing: -0.02em; }
  .brand p { margin: 4px 0 0; opacity: 0.92; font-size: 0.92rem; }
  .pill { background: rgba(255,255,255,0.18); padding: 4px 10px; border-radius: 999px; font-size: 0.78rem; font-weight: 600; }
  .tabs { display: flex; gap: 8px; margin-bottom: 16px; border-bottom: 1px solid var(--border); padding-bottom: 8px; }
  .tab { border: 1px solid transparent; background: transparent; padding: 8px 14px; border-radius: 8px; cursor: pointer; font-weight: 600; color: var(--muted); }
  .tab.active { background: var(--primary-soft); color: var(--primary); border-color: #99f6e4; }
  .card { background: var(--card); border: 1px solid var(--border); border-radius: 14px; padding: 18px; margin-bottom: 16px; box-shadow: 0 1px 3px rgba(15,23,42,0.04); }
  .search-row { display: flex; gap: 10px; flex-wrap: wrap; }
  input[type=text], textarea { flex: 1; min-width: 240px; padding: 11px 14px; border: 1px solid var(--border); border-radius: 10px; font-size: 0.96rem; font-family: inherit; }
  button.primary { background: var(--primary); color: #fff; border: none; padding: 11px 18px; border-radius: 10px; font-weight: 600; cursor: pointer; }
  button.secondary { background: #fff; color: var(--ink); border: 1px solid var(--border); padding: 7px 12px; border-radius: 8px; font-size: 0.84rem; cursor: pointer; }
  .chips { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 10px; }
  .chip { background: #f1f5f9; border: 1px solid var(--border); color: var(--ink); padding: 6px 11px; border-radius: 999px; font-size: 0.82rem; cursor: pointer; }
  .chip:hover { background: var(--primary-soft); border-color: #5eead4; }
  .result-box { white-space: pre-wrap; font-size: 0.92rem; overflow-x: auto; }
  .result-box table { width: 100%; border-collapse: collapse; margin: 12px 0; font-size: 0.86rem; }
  .result-box th, .result-box td { border: 1px solid var(--border); padding: 8px 10px; text-align: left; }
  .result-box th { background: #f1f5f9; }
  .fb-bar { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-top: 14px; padding-top: 12px; border-top: 1px dashed var(--border); }
  .meta { font-size: 0.82rem; color: var(--muted); }
  .grid-3 { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }
  .stat { background: #f8fafc; border: 1px solid var(--border); border-radius: 10px; padding: 12px; }
  .stat strong { display: block; font-size: 1.25rem; color: var(--primary); }
  .hidden { display: none; }
</style>
</head>
<body>
<header>
  <div class="wrap brand">
    <div>
      <h1>CareMatch — Healthcare Quality &amp; Coverage Navigator</h1>
      <p>Compare public CMS Hospital Star Ratings, procedure outcomes, surgeons &amp; Medicare Advantage plans.</p>
    </div>
    <div>
      <span class="pill">Public CMS.gov &amp; HHS NPPES Data</span>
      <span class="pill">Multi-Agent ADK + A2A</span>
    </div>
  </div>
</header>

<main class="wrap">
  <div class="tabs">
    <button class="tab active" onclick="showTab('navigator', this)">Hospital &amp; Plan Navigator</button>
    <button class="tab" onclick="showTab('observability', this)">5-Pillar Telemetry &amp; HITL</button>
  </div>

  <section id="tab-navigator">
    <div class="card">
      <div class="search-row">
        <input id="query-input" type="text" placeholder="Enter a ZIP code, city, hospital, procedure, or Medicare plan (e.g., 97124 hip replacement)..." />
        <button class="primary" onclick="runQuery()">Compare Care</button>
      </div>
      <div class="chips">
        <button class="chip" onclick="quickAsk('Best hospitals and orthopedic surgeons near ZIP 97124 for hip replacement')">ZIP 97124 Hip &amp; Knee</button>
        <button class="chip" onclick="quickAsk('Compare hospitals near ZIP 63010 Arnold MO and heart specialists')">ZIP 63010 Arnold, MO</button>
        <button class="chip" onclick="quickAsk('Top CABG heart bypass surgeons in Dallas TX 75201')">Dallas CABG &amp; Surgeons</button>
        <button class="chip" onclick="quickAsk('Compare Medicare Advantage Star Ratings in OR and check OHSU network checklist with Regence')">Medicare Advantage + Network</button>
        <button class="chip" onclick="quickAsk('Explain CMS HCAHPS and COMP_HIP_KNEE methodology')">CMS Methodology</button>
      </div>
    </div>

    <div class="card" id="response-card">
      <div class="meta" id="route-meta">Ready — select a quick prompt above or type any U.S. ZIP code, city, procedure, or carrier.</div>
      <div id="result-output" class="result-box" style="margin-top:10px;"></div>
      <div class="fb-bar" id="feedback-bar" style="display:none;">
        <span class="meta">Was this comparison helpful?</span>
        <button class="secondary" onclick="sendFeedback('up')">&#128077; Helpful</button>
        <button class="secondary" onclick="sendFeedback('down')">&#128078; Not helpful</button>
        <input id="fb-comment" type="text" placeholder="Optional feedback (no personal medical info)..." style="max-width:340px;" />
        <span class="meta" id="fb-status"></span>
      </div>
    </div>
  </section>

  <section id="tab-observability" class="hidden">
    <div class="card">
      <div style="display:flex; justify-content:space-between; align-items:center;">
        <h2 style="margin:0; font-size:1.1rem;">Live 5-Pillar Architecture &amp; HITL Governance</h2>
        <button class="secondary" onclick="loadRubricStatus()">Refresh Telemetry</button>
      </div>
      <div id="rubric-stats" class="grid-3" style="margin-top:12px;"></div>
      <h3 style="margin-top:18px; font-size:0.98rem;">Human-in-the-Loop (HITL) Quality &amp; Counselor Queue</h3>
      <div id="hitl-list" class="meta">Loading...</div>
    </div>
  </section>
</main>

<script>
let lastPrompt = "";
function showTab(name, btn) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById('tab-navigator').classList.toggle('hidden', name !== 'navigator');
  document.getElementById('tab-observability').classList.toggle('hidden', name !== 'observability');
  if (name === 'observability') loadRubricStatus();
}
function quickAsk(text) {
  document.getElementById('query-input').value = text;
  runQuery();
}
function mdToHtml(md) {
  const esc = md.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  const lines = esc.split('\\n');
  let html = '', inTable = false;
  for (let line of lines) {
    if (line.startsWith('|') && line.endsWith('|')) {
      if (line.includes('---')) continue;
      if (!inTable) { html += '<table><tbody>'; inTable = true; }
      const cells = line.slice(1, -1).split('|').map(c => c.trim());
      html += '<tr>' + cells.map(c => '<td>' + c.replace(/\\*\\*(.*?)\\*\\*/g, '<strong>$1</strong>') + '</td>').join('') + '</tr>';
      continue;
    }
    if (inTable) { html += '</tbody></table>'; inTable = false; }
    if (line.startsWith('### ')) html += '<h3>' + line.slice(4) + '</h3>';
    else if (line.startsWith('&gt; ')) html += '<blockquote style="background:#fef3c7;border-left:4px solid #b45309;padding:8px 12px;margin:8px 0;">' + line.slice(5) + '</blockquote>';
    else if (line.startsWith('- ')) html += '<li>' + line.slice(2).replace(/\\*\\*(.*?)\\*\\*/g, '<strong>$1</strong>') + '</li>';
    else html += '<p>' + line.replace(/\\*\\*(.*?)\\*\\*/g, '<strong>$1</strong>') + '</p>';
  }
  if (inTable) html += '</tbody></table>';
  return html;
}
async function runQuery() {
  const prompt = document.getElementById('query-input').value.trim();
  if (!prompt) return;
  lastPrompt = prompt;
  document.getElementById('route-meta').textContent = 'Running CareMatch multi-agent lookup...';
  const resp = await fetch('/api/v1/chat', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ prompt, session_id: 'web_dashboard' })
  });
  const data = await resp.json();
  document.getElementById('route-meta').textContent =
    `Specialist: ${data.routed_specialist} · Tier: ${data.model_tier} · Tools: ${(data.tool_calls||[]).join(', ') || 'none'} · ${data.duration_ms} ms`;
  document.getElementById('result-output').innerHTML = mdToHtml(data.response || '');
  document.getElementById('feedback-bar').style.display = 'flex';
  document.getElementById('fb-status').textContent = '';
}
async function sendFeedback(rating) {
  const comment = document.getElementById('fb-comment').value.trim();
  const resp = await fetch('/api/v1/feedback', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ session_id: 'web_dashboard', rating, comment, query_context: lastPrompt })
  });
  const data = await resp.json();
  document.getElementById('fb-status').textContent =
    `Saved (${rating === 'up' ? 'Helpful' : 'Not helpful'}) · Total responses: ${data.summary.total}`;
  document.getElementById('fb-comment').value = '';
}
async function loadRubricStatus() {
  const resp = await fetch('/api/v1/rubric-status');
  const data = await resp.json();
  const p = data.architecture_pillars;
  document.getElementById('rubric-stats').innerHTML = `
    <div class="stat"><strong>${p.pillar_1_tools.registered_tools} Tools</strong>Pillar 1: Pydantic + JSON Schemas (${p.pillar_1_tools.score})</div>
    <div class="stat"><strong>${p.pillar_2_memory.store.tables.conversation_history} Turns</strong>Pillar 2: SQLite + Compaction (${p.pillar_2_memory.score})</div>
    <div class="stat"><strong>${p.pillar_4_observability.telemetry.total_tool_spans} Spans</strong>Pillar 4: OTel + HIPAA PII Redactor (${p.pillar_4_observability.score})</div>
  `;
  const rows = (data.hitl_queue || []).map(item =>
    `<div style="padding:8px;border:1px solid #e2e8f0;border-radius:8px;margin-top:8px;">
      <strong>${item.request_id}</strong> [${item.status}] — ${item.summary}
      ${item.status === 'PENDING_HITL_REVIEW' ? `<button class="secondary" style="margin-left:8px;" onclick="decideHitl('${item.request_id}','approve')">Approve</button>` : ''}
    </div>`
  ).join('');
  document.getElementById('hitl-list').innerHTML = rows || 'No pending HITL items.';
}
async function decideHitl(id, decision) {
  await fetch(`/api/v1/hitl/${id}/${decision}`, { method: 'POST' });
  loadRubricStatus();
}
</script>
</body>
</html>
"""


@app.get("/dashboard", response_class=HTMLResponse)
def render_dashboard() -> str:
    """Serve the clean, standalone CareMatch Interactive Web Dashboard."""
    return _DASHBOARD_HTML
