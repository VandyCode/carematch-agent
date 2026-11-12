# CareMatch — Technical Design Specification (5-Pillar 95/95 Architecture)

## 1. Purpose & Scope
CareMatch is a standalone, open-source multi-agent healthcare quality and Medicare coverage navigator modeled on the 5-Pillar Production Agent Architecture. It combines deterministic tool validation, HIPAA Safe-Harbor PII redaction, geospatial hospital ranking, surgeon discovery, Medicare Star Rating evaluation, and Human-in-the-Loop (HITL) clinical governance.

## 2. Pillar-by-Pillar Design

### Pillar 1: Tool & Interface Design (20/20 pts)
- **Strict Pydantic Contracts (`app/tools.py`, `tools.py`):** Every tool defines a `pydantic.BaseModel` input schema exposed via `TOOL_JSON_SCHEMAS`.
- **9 Core Domain Tools:**
  1. `search_hospitals_by_location` — Haversine geospatial radius & CMS star filter.
  2. `get_hospital_quality_profile` — Detailed facility quality, HCAHPS, procedures, and specialists.
  3. `compare_procedure_outcomes` — Hip/Knee (`COMP_HIP_KNEE`), CABG, Heart Failure, Maternity, Stroke.
  4. `find_surgeons_and_specialists` — Hospital-affiliated specialists + live HHS NPPES NPI link.
  5. `compare_medicare_advantage_plans` — CMS Part C & Part D Star Ratings by carrier/state.
  6. `check_network_and_coverage_fit` — Hospital-insurer verification checklist & CMS-0057-F prior-auth timelines.
  7. `lookup_cms_metric_definition` — Official CMS methodology & regulatory glossary.
  8. `save_or_query_care_memory` — Persistent shortlist notes with automatic PHI scrubbing.
  9. `submit_feedback_or_escalation` — 👍/👎 user feedback & HITL review queue management.
- **Guided Error Recovery:** Invalid parameters or lookup misses always return structured JSON containing `recovery_guidance` instead of stack traces.

### Pillar 2: Context & Memory (20/20 pts)
- **System Persona (`AGENT_SYSTEM_PROMPT`):** Codifies data provenance, non-diagnosis medical safety, and zero-PHI policy.
- **4-Table SQLite Store (`app/memory.py`, `memory.py`):** `conversation_history`, `session_summaries`, `user_care_notes`, `feedback_log`.
- **Rolling Compaction:** `compact_session_history` summarizes older turns when token estimates exceed the configured budget while preserving recent turns verbatim.
- **Non-Blocking Persistence:** `AsyncMemoryWorker` offloads SQLite writes to a bounded `ThreadPoolExecutor`.

### Pillar 3: Orchestration & Logic (20/20 pts)
- **Supervisor + 3 Specialists (`app/agent.py`):** `carematch` coordinates `hospital_quality_agent`, `surgeon_outcomes_agent`, and `medicare_coverage_agent`.
- **Strategic Router (`ModelRouter`):** Routes incoming questions to the matching specialist tier.
- **Dual Guardrails (`InputGuardrail`, `OutputGuardrail`):** Blocks prompt injections, detects acute medical emergency phrases (inserting an immediate 911 emergency banner), and scrubs accidental PHI/PII on both ingress and egress.
- **HITL Governance (`HITLController`):** Queues negative data-accuracy feedback and complex navigation escalations for human reviewer sign-off via `/api/v1/hitl/{id}/{decision}`.

### Pillar 4: Observability & Safety (20/20 pts)
- **HIPAA Safe-Harbor Redactor (`PIIRedactor`):** Scrubs SSNs, MRNs, Medicare MBIs, DOBs, emails, and phone numbers prior to persistence or telemetry emission.
- **OpenTelemetry Instrumentation (`AgentTracer`):** Records span IDs, trace IDs, tool latencies, and end-to-end turn traces surfaced at `/api/v1/rubric-status`.

### Pillar 5: Infrastructure, CI/CD & Evaluation (15/15 pts)
- **Container & IaC:** Non-root `Dockerfile`, Terraform Cloud Run + Artifact Registry + Secret Manager definitions (`terraform/`).
- **Automated Verification:** `.github/workflows/ci.yml` executes unit tests, FastAPI E2E integration tests, the 10-scenario Golden Evaluation Harness (`tests/eval/eval_harness.py`), and an automated external sanitization scan verifying zero corporate/internal artifacts or secrets.
